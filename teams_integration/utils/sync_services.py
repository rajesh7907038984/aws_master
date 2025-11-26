"""
Teams Synchronization Services

This module provides services for synchronizing different types of data
between the LMS and Microsoft Teams/Entra ID platforms.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.files.base import ContentFile
from django.db import models

from .teams_api import TeamsAPIClient, TeamsAPIError
from .entra_sync import EntraSyncService
from users.models import CustomUser
from conferences.models import Conference, ConferenceAttendance, ConferenceRecording, ConferenceChat, ConferenceFile

logger = logging.getLogger(__name__)
User = get_user_model()


class TeamsSyncService:
    """Base synchronization service for Teams integration"""
    
    def __init__(self, integration_config):
        """
        Initialize sync service
        
        Args:
            integration_config: TeamsIntegration model instance
        """
        self.config = integration_config
        self.api = TeamsAPIClient(integration_config)
        self.entra_sync = EntraSyncService(integration_config)
        self.sync_status = {
            'success': False,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
    
    def log_sync_result(self, operation: str, success: bool, message: str = ""):
        """Log synchronization result"""
        status = "SUCCESS" if success else "ERROR"
        logger.info(f"Teams Sync [{operation}] - {status}: {message}")
        
        if not success:
            self.sync_status['errors'] += 1
            self.sync_status['error_messages'].append(f"{operation}: {message}")
    
    def update_integration_sync_status(self, success: bool, error_message: str = None):
        """Update integration sync status"""
        try:
            self.config.last_sync_datetime = timezone.now()
            self.config.last_sync_status = 'success' if success else 'failed'
            if error_message:
                self.config.sync_error_message = error_message
            self.config.save(update_fields=[
                'last_sync_datetime', 
                'last_sync_status', 
                'sync_error_message'
            ])
        except Exception as e:
            logger.error(f"Error updating integration sync status: {str(e)}")


class MeetingSyncService(TeamsSyncService):
    """Service for synchronizing Teams meeting data"""
    
    def sync_meeting_attendance(self, conference):
        """
        Sync meeting attendance data from Teams WITH DURATION
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        # Reset sync status for this operation
        self.sync_status = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        try:
            from teams_integration.models import TeamsMeetingSync
            
            logger.info(f"👥 Syncing attendance WITH DURATION for conference: {conference.title}")
            
            # Get or create meeting sync record
            meeting_sync, created = TeamsMeetingSync.objects.get_or_create(
                conference=conference,
                defaults={
                    'teams_meeting_id': conference.meeting_id or '',
                    'teams_meeting_url': conference.meeting_link,
                    'meeting_status': 'scheduled'
                }
            )
            
            # 🐛 FIX: Check if online_meeting_id is in correct format (thread ID)
            # If it's a GUID (calendar event ID), try to get the thread ID
            if conference.online_meeting_id and '@thread.v2' not in conference.online_meeting_id:
                logger.warning(f"online_meeting_id appears to be calendar event ID (GUID), not thread ID")
                logger.info(f"Current ID: {conference.online_meeting_id}")
                
                # Try to extract thread ID from meeting link
                if conference.meeting_link:
                    logger.info("Attempting to extract thread ID from meeting link...")
                    thread_id = self.api.get_online_meeting_id_from_join_url(conference.meeting_link)
                    
                    if thread_id and '@thread.v2' in thread_id:
                        logger.info(f"✓ Extracted thread ID from meeting link: {thread_id}")
                        conference.online_meeting_id = thread_id
                        conference.save(update_fields=['online_meeting_id'])
                        logger.info(f"✓ Updated conference with correct thread ID")
                    else:
                        logger.warning(f"Could not extract valid thread ID from meeting link")
            
            # Check if we have online_meeting_id (required for attendance reports)
            if not conference.online_meeting_id:
                logger.warning(f"No online_meeting_id for conference {conference.id}")
                
                # Try to extract from meeting link first
                if conference.meeting_link:
                    logger.info("Attempting to extract thread ID from meeting link...")
                    thread_id = self.api.get_online_meeting_id_from_join_url(conference.meeting_link)
                    
                    if thread_id:
                        conference.online_meeting_id = thread_id
                        conference.save(update_fields=['online_meeting_id'])
                        logger.info(f"✓ Extracted and saved thread ID: {thread_id}")
                    else:
                        # Fallback: Try to get it from the calendar event if we have meeting_id
                        if conference.meeting_id:
                            logger.info("Attempting to fetch online_meeting_id from calendar event...")
                            
                            user_email = None
                            if conference.created_by and conference.created_by.email:
                                user_email = conference.created_by.email
                            elif self.config.user and self.config.user.email:
                                user_email = self.config.user.email
                            
                            if user_email:
                                try:
                                    endpoint = f'/users/{user_email}/events/{conference.meeting_id}'
                                    event_data = self.api._make_request('GET', endpoint)
                                    
                                    if event_data.get('onlineMeeting'):
                                        online_meeting_id = event_data['onlineMeeting'].get('id')
                                        if online_meeting_id:
                                            conference.online_meeting_id = online_meeting_id
                                            conference.save(update_fields=['online_meeting_id'])
                                            logger.info(f"✓ Retrieved and saved online_meeting_id: {online_meeting_id}")
                                except Exception as e:
                                    logger.warning(f"Could not fetch online_meeting_id: {str(e)}")
                        else:
                            logger.info("No meeting_id available, skipping attendance sync")
                            return self.sync_status
            
            if not conference.online_meeting_id:
                logger.info("Could not obtain online_meeting_id, skipping attendance sync")
                return self.sync_status
            
            # Determine user email - prioritize integration's user email or service account email
            # This is the admin email configured in account settings
            user_email = None
            # First priority: Use integration's user email (admin account from settings)
            if self.config.user and self.config.user.email:
                user_email = self.config.user.email
            # Second priority: Use service account email if configured
            elif hasattr(self.config, 'service_account_email') and self.config.service_account_email:
                user_email = self.config.service_account_email
            # Fallback: Use conference creator's email (less reliable)
            elif conference.created_by and conference.created_by.email:
                user_email = conference.created_by.email
                logger.warning(f"Using conference creator email as fallback: {user_email}. Consider configuring integration user email in account settings.")
            
            # ✅ FIX: Use the NEW attendance report API with duration
            logger.info(f"Fetching attendance report from Teams API...")
            attendance_result = self.api.get_meeting_attendance_report(
                conference.online_meeting_id, 
                user_email=user_email
            )
            
            if not attendance_result['success']:
                error_msg = attendance_result.get('error', 'Unknown error')
                logger.warning(f"Attendance report sync failed: {error_msg}")
                
                # Check if it's a permission error
                if 'permission' in error_msg.lower():
                    self.sync_status['error'] = f"Missing API permission: {attendance_result.get('permission_required', 'OnlineMeetingArtifact.Read.All')}"
                    return self.sync_status
                
                # 🆕 FALLBACK: Try Call Records API for instant meetings
                logger.info("⚠️ OnlineMeetings API failed. Attempting Call Records API fallback...")
                try:
                    attendees = self._get_attendance_from_call_records(conference)
                    if attendees:
                        logger.info(f"✅ Call Records API fallback succeeded: {len(attendees)} attendees found")
                        attendance_result = {
                            'success': True,
                            'attendees': attendees,
                            'note': 'Retrieved from Call Records API (instant meeting)'
                        }
                    else:
                        logger.warning("Call Records API fallback found no attendance data")
                        self.sync_status['error'] = error_msg
                        return self.sync_status
                except Exception as e:
                    logger.error(f"Call Records API fallback failed: {str(e)}")
                    self.sync_status['error'] = f"{error_msg}. Fallback also failed: {str(e)}"
                    return self.sync_status
            
            attendees = attendance_result.get('attendees', [])
            note = attendance_result.get('note', '')
            
            logger.info(f"📊 Found {len(attendees)} attendees with duration data")
            if note:
                logger.info(f"📝 Teams API Note: {note}")
            
            # Log each attendee email for debugging
            if len(attendees) > 0:
                logger.info("📋 Attendees from Teams API:")
                for idx, att in enumerate(attendees, 1):
                    logger.info(f"   {idx}. {att.get('name', 'Unknown')} - {att.get('email', 'NO EMAIL')} - {att.get('duration_minutes', 0)} min")
            else:
                # If no attendees but API returned success, log the reason
                if 'No attendance report available' in note:
                    logger.info("⚠️ Teams attendance report not yet generated. Reports are created after meeting ends.")
                else:
                    logger.info("⚠️ Teams API returned empty attendees list. Meeting may not have occurred yet or report not available.")
            
            # Process each attendee WITH DURATION
            synced_count = 0
            created_count = 0
            updated_count = 0
            
            for attendee in attendees:
                try:
                    was_created = self._process_attendee_with_duration(conference, attendee)
                    if was_created:
                        created_count += 1
                    else:
                        updated_count += 1
                    synced_count += 1
                except Exception as e:
                    self.log_sync_result(
                        f"process_attendee_{attendee.get('email', 'unknown')}", 
                        False, 
                        str(e)
                    )
            
            # Update meeting sync record
            meeting_sync.attendance_synced = True
            meeting_sync.last_attendance_sync = timezone.now()
            meeting_sync.total_participants = len(attendees)
            meeting_sync.save()
            
            self.sync_status['processed'] = len(attendees)
            self.sync_status['created'] = created_count
            self.sync_status['updated'] = updated_count
            self.sync_status['success'] = True
            
            # Include note from Teams API if no attendees were found
            if len(attendees) == 0 and note:
                self.sync_status['note'] = note
            
            logger.info(f"✓ Attendance sync completed: {created_count} created, {updated_count} updated (all with duration)")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting attendance sync failed: {str(e)}"
            logger.warning(error_msg)
            self.sync_status['error'] = error_msg
            # Log error but don't fail the entire sync
            self.log_sync_result('sync_attendance', True, f"Skipped: {str(e)}")
            return self.sync_status
    
    def _process_attendee(self, conference, attendee):
        """Process a single meeting attendee (LEGACY - no duration)"""
        try:
            # Find user by email
            # Use case-insensitive email matching
            user = CustomUser.objects.filter(email__iexact=attendee['email']).first()
            
            if not user:
                logger.warning(f"User not found for email: {attendee['email']}")
                return
            
            # Create or update attendance record
            attendance, created = ConferenceAttendance.objects.get_or_create(
                conference=conference,
                user=user,
                defaults={
                    'participant_id': attendee.get('email'),
                    'attendance_status': 'present',
                    'join_time': timezone.now()
                }
            )
            
            if not created:
                # Update existing attendance
                attendance.attendance_status = 'present'
                attendance.join_time = timezone.now()
                attendance.save()
            
            self.log_sync_result(
                f"process_attendee_{attendee['email']}", 
                True, 
                f"Processed attendee: {attendee['name']}"
            )
            
        except Exception as e:
            logger.error(f"Error processing attendee {attendee.get('email', 'unknown')}: {str(e)}")
            raise
    
    def _process_attendee_with_duration(self, conference, attendee):
        """
        Process a single meeting attendee WITH DURATION
        
        Args:
            conference: Conference instance
            attendee: Attendee data from attendance report (includes duration)
            
        Returns:
            bool: True if created, False if updated
        """
        try:
            # Find user by email
            email = attendee.get('email', '').strip()
            attendee_name = attendee.get('name', 'Unknown')
            
            if not email:
                logger.warning(f"⚠️ Attendee has no email: {attendee_name}")
                logger.warning(f"   Attendee data: {attendee}")
                return False
            
            logger.info(f"🔍 Looking for user with email: {email}")
            
            # Use case-insensitive email matching (Teams emails may have different casing)
            user = CustomUser.objects.filter(email__iexact=email).first()
            
            if not user:
                logger.warning(f"⚠️ User not found for email: {email} (case-insensitive search)")
                # Try exact match as fallback (in case email field has unique constraint)
                user = CustomUser.objects.filter(email=email).first()
                if not user:
                    logger.warning(f"❌ User not found for email: {email} (exact match also failed)")
                    logger.warning(f"   Attendee name: {attendee_name}")
                    logger.warning(f"   This attendee will be skipped. Check if user exists with this email in LMS.")
                    return False
            
            logger.info(f"✅ Found user: {user.username} ({user.email}) for attendee {attendee_name} ({email})")
            
            # Extract attendance data with duration
            join_time = attendee.get('join_time')
            leave_time = attendee.get('leave_time')
            duration_minutes = attendee.get('duration_minutes', 0)
            
            # Determine attendance status based on duration
            attendance_status = 'present'
            if duration_minutes < 5:  # Less than 5 minutes
                attendance_status = 'absent'
            elif join_time and conference.start_time:
                # Check if joined late (more than 15 minutes after scheduled start)
                from dateutil import parser as date_parser
                
                # Ensure we have datetime objects
                if isinstance(conference.date, str):
                    conf_date = date_parser.parse(conference.date).date()
                else:
                    conf_date = conference.date
                
                if isinstance(conference.start_time, str):
                    conf_start = date_parser.parse(conference.start_time).time()
                else:
                    conf_start = conference.start_time
                
                conference_start = timezone.datetime.combine(conf_date, conf_start)
                if hasattr(conference_start, 'replace'):
                    conference_start = conference_start.replace(tzinfo=timezone.get_current_timezone())
                
                # Make sure join_time is timezone-aware
                if join_time and not timezone.is_aware(join_time):
                    join_time = timezone.make_aware(join_time)
                
                if join_time > conference_start + timezone.timedelta(minutes=15):
                    attendance_status = 'late'
            
            # Create or update attendance record WITH DURATION
            attendance, created = ConferenceAttendance.objects.get_or_create(
                conference=conference,
                user=user,
                defaults={
                    'participant_id': email,
                    'join_time': join_time,
                    'leave_time': leave_time,
                    'duration_minutes': duration_minutes,
                    'attendance_status': attendance_status,
                    'device_info': {
                        'teams_attendance_report': True,
                        'role': attendee.get('role', 'Attendee'),
                        'total_attendance_seconds': attendee.get('total_attendance_seconds', 0),
                        'sync_timestamp': timezone.now().isoformat()
                    }
                }
            )
            
            if not created:
                # Update existing attendance with latest data
                # Keep the maximum duration if multiple sync attempts
                if join_time:
                    attendance.join_time = join_time
                if leave_time:
                    attendance.leave_time = leave_time
                attendance.duration_minutes = max(duration_minutes, attendance.duration_minutes or 0)
                attendance.attendance_status = attendance_status
                
                # Merge device info
                if not attendance.device_info:
                    attendance.device_info = {}
                attendance.device_info.update({
                    'teams_attendance_report': True,
                    'role': attendee.get('role', 'Attendee'),
                    'total_attendance_seconds': attendee.get('total_attendance_seconds', 0),
                    'last_sync_timestamp': timezone.now().isoformat()
                })
                
                attendance.save()
            
            action = "Created" if created else "Updated"
            logger.info(
                f"  {action} attendance: {attendee.get('name')} ({email}) - "
                f"Duration: {duration_minutes}min, Status: {attendance_status}"
            )
            
            self.log_sync_result(
                f"process_attendee_{email}", 
                True, 
                f"{action} attendee with duration: {attendee.get('name')} - {duration_minutes}min"
            )
            
            return created
            
        except Exception as e:
            logger.error(f"Error processing attendee {attendee.get('email', 'unknown')}: {str(e)}")
            raise
    
    def _get_attendance_from_call_records(self, conference):
        """
        Fallback method to get attendance from Call Records API
        Used when onlineMeetings API is not available (instant meetings)
        
        Args:
            conference: Conference instance
            
        Returns:
            list: Attendees with duration data in same format as onlineMeetings API
        """
        from dateutil import parser as date_parser
        
        logger.info("📞 Fetching attendance from Call Records API...")
        
        try:
            # Get conference date/time for filtering
            if isinstance(conference.date, str):
                conf_date = date_parser.parse(conference.date).date()
            else:
                conf_date = conference.date
            
            target_date_str = conf_date.strftime('%Y-%m-%d')
            
            # Get all call records
            endpoint = '/communications/callRecords'
            all_records = self.api._make_request('GET', endpoint)
            records = all_records.get('value', [])
            
            logger.info(f"Found {len(records)} call records, filtering for {target_date_str}...")
            
            # Filter records from conference date
            matching_calls = []
            for record in records:
                start_str = record.get('startDateTime', '')
                if target_date_str in start_str:
                    matching_calls.append(record)
            
            logger.info(f"Found {len(matching_calls)} calls on {target_date_str}")
            
            if not matching_calls:
                logger.warning(f"No calls found on {target_date_str}")
                return []
            
            # Aggregate attendance from all calls on this date
            participant_data = {}
            
            for call_record in matching_calls:
                call_id = call_record.get('id')
                
                try:
                    # Get sessions for this call
                    sessions_endpoint = f'/communications/callRecords/{call_id}/sessions'
                    sessions_data = self.api._make_request('GET', sessions_endpoint)
                    sessions = sessions_data.get('value', [])
                    
                    for session in sessions:
                        # Extract participant identity
                        caller = session.get('caller', {})
                        identity = caller.get('associatedIdentity', {})
                        
                        if not identity or not identity.get('displayName'):
                            # Fallback to identity.user
                            caller_identity = caller.get('identity', {})
                            user_info = caller_identity.get('user', {})
                            identity = user_info
                        
                        email = identity.get('userPrincipalName', '')
                        display_name = identity.get('displayName', '')
                        
                        if not email or not display_name:
                            continue
                        
                        # Get session times
                        sess_start_str = session.get('startDateTime')
                        sess_end_str = session.get('endDateTime')
                        
                        if not sess_start_str or not sess_end_str:
                            continue
                        
                        sess_start = date_parser.parse(sess_start_str)
                        sess_end = date_parser.parse(sess_end_str)
                        duration_seconds = (sess_end - sess_start).total_seconds()
                        duration_minutes = duration_seconds / 60
                        
                        # Aggregate by email
                        if email not in participant_data:
                            participant_data[email] = {
                                'email': email,
                                'name': display_name,
                                'join_time': sess_start,
                                'leave_time': sess_end,
                                'duration': duration_seconds,
                                'duration_minutes': duration_minutes,
                                'total_attendance_seconds': duration_seconds,
                                'attendance_intervals': []
                            }
                        else:
                            # Update earliest join and latest leave
                            if sess_start < participant_data[email]['join_time']:
                                participant_data[email]['join_time'] = sess_start
                            if sess_end > participant_data[email]['leave_time']:
                                participant_data[email]['leave_time'] = sess_end
                            
                            # Add duration
                            participant_data[email]['duration'] += duration_seconds
                            participant_data[email]['duration_minutes'] += duration_minutes
                            participant_data[email]['total_attendance_seconds'] += duration_seconds
                        
                        # Add interval
                        participant_data[email]['attendance_intervals'].append({
                            'joinDateTime': sess_start_str,
                            'leaveDateTime': sess_end_str
                        })
                
                except Exception as e:
                    logger.warning(f"Error processing call {call_id}: {str(e)}")
                    continue
            
            # Convert to list format expected by sync code
            attendees = list(participant_data.values())
            
            logger.info(f"📊 Extracted {len(attendees)} unique participants from Call Records:")
            for att in attendees:
                logger.info(f"   - {att['name']} ({att['email']}): {att['duration_minutes']:.2f} min")
            
            return attendees
            
        except Exception as e:
            logger.error(f"Error in Call Records fallback: {str(e)}")
            raise
    
    def sync_meeting_recordings(self, conference):
        """
        Sync meeting recordings from Teams OneDrive storage
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        # Reset sync status for this operation
        self.sync_status = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        try:
            from conferences.models import ConferenceRecording
            from teams_integration.models import TeamsMeetingSync
            from teams_integration.utils.onedrive_api import OneDriveAPI, OneDriveAPIError
            
            logger.info(f"🎥 Syncing recordings for conference: {conference.title}")
            
            # Get meeting sync record
            meeting_sync = TeamsMeetingSync.objects.filter(conference=conference).first()
            if not meeting_sync:
                logger.warning("No meeting sync record found, creating one")
                meeting_sync = TeamsMeetingSync.objects.create(
                    conference=conference,
                    teams_meeting_id=conference.meeting_id or '',
                    teams_meeting_url=conference.meeting_link
                )
            
            # Get OneDrive API client
            try:
                onedrive_api = OneDriveAPI(self.config)
            except OneDriveAPIError as e:
                error_msg = f"Failed to initialize OneDrive API: {str(e)}"
                logger.warning(error_msg)
                # Return success with 0 items - OneDrive may not be configured
                return self.sync_status
            
            # Determine which user's OneDrive to search
            # Priority: 1. Integration owner (branch admin), 2. Service account, 3. Conference creator
            admin_email = None
            if self.config.user and self.config.user.email:
                admin_email = self.config.user.email
            elif self.config.service_account_email:
                admin_email = self.config.service_account_email
            elif conference.created_by and conference.created_by.email:
                admin_email = conference.created_by.email
            
            if not admin_email:
                error_msg = "No admin email found for OneDrive access. Cannot sync recordings without admin email."
                logger.warning(error_msg)
                self.sync_status['error'] = error_msg
                self.sync_status['success'] = False
                return self.sync_status
            
            logger.info(f"📧 Accessing OneDrive for: {admin_email}")
            
            # Search for recordings (with date/time filtering)
            recordings_result = onedrive_api.search_recordings_for_meeting(
                user_email=admin_email,
                meeting_id=conference.meeting_id,
                meeting_title=conference.title,
                meeting_date=conference.date,
                meeting_start_time=conference.start_time
            )
            
            if not recordings_result['success']:
                error_msg = f"OneDrive search failed: {recordings_result.get('error', 'Unknown error')}"
                logger.warning(error_msg)
                self.sync_status['error'] = error_msg
                self.sync_status['success'] = False
                # Still mark as attempted
                meeting_sync.recordings_synced = True
                meeting_sync.last_recording_sync = timezone.now()
                if not hasattr(meeting_sync, 'sync_errors') or meeting_sync.sync_errors is None:
                    meeting_sync.sync_errors = {}
                meeting_sync.sync_errors['recordings'] = error_msg
                meeting_sync.save()
                return self.sync_status
            
            recordings = recordings_result.get('recordings', [])
            drive_id = recordings_result.get('drive_id')
            
            logger.info(f"📹 Found {len(recordings)} recordings in OneDrive")
            
            # Process each recording
            synced_count = 0
            created_count = 0
            updated_count = 0
            
            for recording_data in recordings:
                try:
                    recording_id = recording_data.get('id')
                    
                    # ✅ FIX: Get actual video duration from OneDrive metadata
                    duration_minutes = 0
                    
                    # Try to get duration from video metadata
                    if drive_id and recording_id:
                        try:
                            logger.info(f"Fetching video duration for recording: {recording_data.get('name')}")
                            
                            # Get detailed file metadata including video properties
                            item_endpoint = f'/drives/{drive_id}/items/{recording_id}'
                            params = {
                                '$select': 'id,name,size,video,createdDateTime,lastModifiedDateTime'
                            }
                            
                            try:
                                item_details = onedrive_api.api._make_request('GET', item_endpoint, params=params)
                                
                                # Extract video duration from metadata
                                video_metadata = item_details.get('video', {})
                                duration_ms = video_metadata.get('duration', 0)
                                
                                if duration_ms:
                                    duration_minutes = duration_ms // 60000  # Convert milliseconds to minutes
                                    logger.info(f"  ✓ Video duration: {duration_minutes} minutes (from metadata)")
                                else:
                                    logger.info("  ⚠ No video duration in metadata")
                                    
                            except Exception as e:
                                logger.warning(f"Could not get video metadata: {str(e)}")
                        
                        except Exception as e:
                            logger.warning(f"Error fetching video duration: {str(e)}")
                    
                    # Fallback: Try to estimate from file size (very rough estimate)
                    # Typical bitrate for Teams recordings: 1-2 Mbps
                    if duration_minutes == 0 and recording_data.get('size', 0) > 0:
                        file_size_mb = recording_data.get('size', 0) / (1024 * 1024)
                        estimated_bitrate_mbps = 1.5  # Conservative estimate
                        estimated_minutes = int((file_size_mb * 8) / (estimated_bitrate_mbps * 60))
                        if estimated_minutes > 0:
                            duration_minutes = estimated_minutes
                            logger.info(f"  ℹ Estimated duration from file size: {duration_minutes} minutes")
                    
                    # ✅ FIX: Truncate long values to fit database constraints
                    recording_name = recording_data.get('name', 'Meeting Recording')
                    web_url = recording_data.get('webUrl', '')
                    download_url = recording_data.get('downloadUrl', '')
                    file_path = recording_data.get('path', '')
                    
                    # Truncate title to 255 chars (max_length for title field)
                    title = recording_name[:255] if len(recording_name) > 255 else recording_name
                    
                    # Truncate URLs to 500 chars (max_length for URL fields)
                    file_url = web_url[:500] if len(web_url) > 500 else web_url
                    download_url_truncated = download_url[:500] if len(download_url) > 500 else download_url
                    onedrive_web_url = web_url[:500] if len(web_url) > 500 else web_url
                    onedrive_download_url = download_url[:500] if len(download_url) > 500 else download_url
                    onedrive_file_path = file_path[:500] if len(file_path) > 500 else file_path
                    recording_content_url = web_url[:500] if len(web_url) > 500 else web_url
                    
                    # Create or update recording WITH DURATION
                    recording, created = ConferenceRecording.objects.update_or_create(
                        conference=conference,
                        recording_id=f"onedrive_{recording_id}",
                        defaults={
                            'title': title,
                            'recording_type': 'cloud',
                            'file_url': file_url,
                            'file_size': recording_data.get('size', 0),
                            'duration_minutes': duration_minutes,  # ✅ NOW HAS ACTUAL DURATION
                            'file_format': recording_name.split('.')[-1].lower() if '.' in recording_name else 'mp4',
                            'download_url': download_url_truncated,
                            'status': 'available',
                            # OneDrive-specific fields
                            'onedrive_item_id': recording_id,
                            'onedrive_drive_id': drive_id,
                            'onedrive_file_path': onedrive_file_path,
                            'onedrive_web_url': onedrive_web_url,
                            'onedrive_download_url': onedrive_download_url,
                            'stored_in_onedrive': True,
                            'meeting_recording_id': conference.meeting_id,
                            'recording_content_url': recording_content_url,
                        }
                    )
                    
                    if created:
                        created_count += 1
                        logger.info(f"✓ Created new recording: {recording.title}")
                    else:
                        updated_count += 1
                        logger.info(f"↻ Updated recording: {recording.title}")
                    
                    synced_count += 1
                    
                except Exception as e:
                    logger.error(f"✗ Error processing recording {recording_data.get('name')}: {str(e)}")
                    continue
            
            # Update meeting sync record
            meeting_sync.recordings_synced = True
            meeting_sync.last_recording_sync = timezone.now()
            meeting_sync.save()
            
            # Update conference sync status
            if synced_count > 0:
                conference.data_sync_status = 'completed'
                conference.last_sync_at = timezone.now()
                conference.save(update_fields=['data_sync_status', 'last_sync_at'])
            
            self.sync_status['success'] = True
            self.sync_status['processed'] = synced_count
            self.sync_status['created'] = created_count
            self.sync_status['updated'] = updated_count
            
            logger.info(f"✓ Recording sync completed: {created_count} created, {updated_count} updated")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting recordings sync failed: {str(e)}"
            logger.warning(error_msg)
            logger.exception(e)
            # Log error but don't fail the entire sync
            self.log_sync_result('sync_recordings', True, f"Skipped: {str(e)}")
            return self.sync_status
    
    def sync_meeting_chat(self, conference):
        """
        Sync meeting chat messages from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        # Reset sync status for this operation
        self.sync_status = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        try:
            from teams_integration.models import TeamsMeetingSync
            from conferences.models import ConferenceChat
            from users.models import CustomUser
            
            logger.info(f"Syncing chat for conference: {conference.title}")
            
            # Ensure a meeting sync record exists (align behavior with attendance/recordings)
            meeting_sync, _ = TeamsMeetingSync.objects.get_or_create(
                conference=conference,
                defaults={
                    'teams_meeting_id': conference.meeting_id or '',
                    'teams_meeting_url': conference.meeting_link,
                    'meeting_status': 'scheduled'
                }
            )
            
            # Determine user email for API calls
            # Priority: 1. Integration user (branch admin - meeting organizer), 2. Service account, 3. Conference creator
            candidate_emails = []
            if self.config.user and self.config.user.email:
                candidate_emails.append(self.config.user.email)
            if hasattr(self.config, 'service_account_email') and self.config.service_account_email and self.config.service_account_email not in candidate_emails:
                candidate_emails.append(self.config.service_account_email)
            if conference.created_by and conference.created_by.email and conference.created_by.email not in candidate_emails:
                candidate_emails.append(conference.created_by.email)
            
            user_email = candidate_emails[0] if candidate_emails else None
            if user_email:
                logger.info(f"Using email for API: {user_email}")
            
            if not user_email:
                logger.info("No user email available for API authentication for chat sync, skipping")
                return self.sync_status
            
            # Get the online meeting ID (required for chat/transcript access)
            online_meeting_id = conference.online_meeting_id
            
            # If we don't have online_meeting_id but have meeting_id (calendar event ID),
            # try to fetch the online meeting details to get the online_meeting_id
            if not online_meeting_id and conference.meeting_id:
                logger.info(f"No online_meeting_id found, attempting to fetch from calendar event {conference.meeting_id}")
                # Try all candidate emails in case the creator is not the actual organizer
                for candidate in candidate_emails:
                    try:
                        endpoint = f'/users/{candidate}/calendar/events/{conference.meeting_id}'
                        event_data = self.api._make_request('GET', endpoint)
                        
                        if event_data.get('onlineMeeting'):
                            online_meeting_data = event_data['onlineMeeting']
                            # Try to get thread ID from chatInfo first (most reliable)
                            chat_info = online_meeting_data.get('chatInfo', {})
                            thread_id = chat_info.get('threadId')
                            
                            if thread_id:
                                online_meeting_id = thread_id
                                conference.online_meeting_id = online_meeting_id
                                conference.save(update_fields=['online_meeting_id'])
                                user_email = candidate
                                logger.info(f"✓ Retrieved thread ID from chatInfo via {candidate}: {online_meeting_id}")
                                break
                            # Fallback to online meeting ID
                            elif online_meeting_data.get('id'):
                                online_meeting_id = online_meeting_data.get('id')
                                # Only use if it's different from meeting_id (GUID)
                                if online_meeting_id != conference.meeting_id:
                                    conference.online_meeting_id = online_meeting_id
                                    conference.save(update_fields=['online_meeting_id'])
                                    user_email = candidate
                                    logger.info(f"✓ Retrieved online meeting ID via {candidate}: {online_meeting_id}")
                                break
                        else:
                            logger.warning(f"Calendar event {conference.meeting_id} (queried as {candidate}) has no online meeting associated")
                    except Exception as e:
                        logger.warning(f"Failed to fetch online meeting ID from calendar event as {candidate}: {str(e)}")
            
            # ✅ NEW: If online_meeting_id is still a GUID (same as meeting_id), try to query online meetings API
            if online_meeting_id == conference.meeting_id or (online_meeting_id and '@thread.v2' not in str(online_meeting_id)):
                logger.info(f"online_meeting_id appears to be a GUID, trying to find actual thread ID via online meetings API")
                for candidate in candidate_emails:
                    try:
                        # Query online meetings by subject/title
                        # Teams meetings often have the subject in the online meeting
                        filter_query = f"subject eq '{conference.title}'"
                        endpoint = f'/users/{candidate}/onlineMeetings?$filter={filter_query}&$orderby=startDateTime desc&$top=10'
                        meetings_response = self.api._make_request('GET', endpoint)
                        meetings = meetings_response.get('value', [])
                        
                        # Try to match by date/time or use most recent
                        from django.utils import timezone
                        from dateutil import parser as date_parser
                        
                        for meeting in meetings:
                            try:
                                meeting_start = meeting.get('startDateTime')
                                if meeting_start:
                                    meeting_dt = date_parser.parse(meeting_start)
                                    conf_datetime = timezone.datetime.combine(conference.date, conference.start_time)
                                    if not timezone.is_aware(conf_datetime):
                                        conf_datetime = timezone.make_aware(conf_datetime)
                                    
                                    # Check if meeting times match (within 1 hour)
                                    time_diff = abs((meeting_dt - conf_datetime).total_seconds())
                                    if time_diff < 3600:  # 1 hour
                                        chat_info = meeting.get('chatInfo', {})
                                        thread_id = chat_info.get('threadId')
                                        if thread_id:
                                            online_meeting_id = thread_id
                                            conference.online_meeting_id = online_meeting_id
                                            conference.save(update_fields=['online_meeting_id'])
                                            user_email = candidate
                                            logger.info(f"✓ Found matching online meeting and extracted thread ID: {online_meeting_id}")
                                            break
                            except Exception as e:
                                logger.debug(f"Error matching meeting: {str(e)}")
                                continue
                        
                        if online_meeting_id and '@thread.v2' in str(online_meeting_id):
                            break
                            
                    except Exception as e:
                        logger.warning(f"Failed to query online meetings API as {candidate}: {str(e)}")
            
            # ✅ NEW: If online_meeting_id is still a GUID, try to find chat thread by querying user's chats
            if online_meeting_id == conference.meeting_id or (online_meeting_id and '@thread.v2' not in str(online_meeting_id)):
                logger.info(f"online_meeting_id is still a GUID, trying to find chat thread by querying chats")
                for candidate in candidate_emails:
                    try:
                        # Query user's chats and find one matching the meeting title/date
                        chats_endpoint = f'/users/{candidate}/chats'
                        params = {
                            '$top': 50,
                            '$orderby': 'lastMessagePreview/createdDateTime desc'
                        }
                        chats_response = self.api._make_request('GET', chats_endpoint, params=params)
                        chats = chats_response.get('value', [])
                        
                        logger.info(f"Found {len(chats)} chats for {candidate}")
                        
                        # Try to match chat by topic (meeting title + date)
                        from django.utils import timezone
                        from dateutil import parser as date_parser
                        
                        meeting_date_str = conference.date.strftime('%Y-%m-%d')
                        meeting_time_str = conference.start_time.strftime('%H:%M')
                        search_patterns = [
                            conference.title.lower(),
                            f"{conference.title} - {meeting_date_str}".lower(),
                            f"{conference.title} - {meeting_date_str} {meeting_time_str}".lower(),
                        ]
                        
                        for chat in chats:
                            topic = chat.get('topic', '').lower()
                            if any(pattern in topic for pattern in search_patterns):
                                thread_id = chat.get('id')
                                if thread_id and '@thread.v2' in thread_id:
                                    online_meeting_id = thread_id
                                    conference.online_meeting_id = online_meeting_id
                                    conference.save(update_fields=['online_meeting_id'])
                                    user_email = candidate
                                    logger.info(f"✓ Found matching chat thread: {online_meeting_id}")
                                    break
                        
                        if online_meeting_id and '@thread.v2' in str(online_meeting_id):
                            break
                            
                    except Exception as e:
                        logger.warning(f"Failed to query chats API as {candidate}: {str(e)}")
            
            # Fallback: try to derive online_meeting_id from the Teams join URL if still missing
            if not online_meeting_id and conference.meeting_link:
                try:
                    derived_id = self.api.get_online_meeting_id_from_join_url(conference.meeting_link)
                    if derived_id:
                        online_meeting_id = derived_id
                        conference.online_meeting_id = online_meeting_id
                        conference.save(update_fields=['online_meeting_id'])
                        logger.info(f"✓ Derived and saved online_meeting_id from join URL: {online_meeting_id}")
                except Exception as e:
                    logger.warning(f"Failed to derive online meeting ID from join URL: {str(e)}")
            
            # ✅ FIX: If online_meeting_id is still a GUID, try to use it to query the online meeting API to get thread ID
            if online_meeting_id and '@thread.v2' not in str(online_meeting_id):
                logger.info(f"online_meeting_id is GUID format, trying to get thread ID from online meeting API")
                for candidate in candidate_emails:
                    try:
                        # Try to get online meeting details using the GUID
                        meeting_endpoint = f'/users/{candidate}/onlineMeetings/{online_meeting_id}'
                        meeting_details = self.api._make_request('GET', meeting_endpoint)
                        
                        chat_info = meeting_details.get('chatInfo', {})
                        thread_id = chat_info.get('threadId')
                        
                        if thread_id:
                            online_meeting_id = thread_id
                            conference.online_meeting_id = online_meeting_id
                            conference.save(update_fields=['online_meeting_id'])
                            user_email = candidate
                            logger.info(f"✓ Got thread ID from online meeting API: {online_meeting_id}")
                            break
                    except Exception as e:
                        logger.debug(f"Could not get online meeting details for GUID {online_meeting_id} as {candidate}: {str(e)}")
                        continue
            
            # Check if we have an online meeting ID
            if not online_meeting_id:
                error_msg = "No Teams online meeting ID found. Cannot sync chat without online meeting ID."
                logger.warning(f"Chat sync skipped for conference {conference.id}: {error_msg}")
                self.sync_status['error'] = error_msg
                self.sync_status['success'] = False
                # Still mark as attempted
                meeting_sync.chat_synced = True
                meeting_sync.last_chat_sync = timezone.now()
                if not hasattr(meeting_sync, 'sync_errors') or meeting_sync.sync_errors is None:
                    meeting_sync.sync_errors = {}
                meeting_sync.sync_errors['chat'] = error_msg
                meeting_sync.save()
                return self.sync_status
            
            logger.info(f"Fetching chat messages for online meeting: {online_meeting_id}")
            
            # ✅ FIX: Use the NEW chat messages API (more reliable than transcripts)
            # Try the improved chat messages API first
            chat_result = self.api.get_meeting_chat_messages(
                online_meeting_id,
                user_email=user_email,
                meeting_id=conference.meeting_id
            )
            
            # Fallback to transcript API if chat API fails
            # Note: Transcripts may contain chat-like data if transcription was enabled
            if not chat_result['success']:
                logger.info("Chat API failed, trying transcript API as fallback...")
                logger.info("Note: Transcripts require Teams Premium and transcription enabled")
                transcript_result = self.api.get_meeting_transcript(
                    online_meeting_id,
                    user_email=user_email
                )
                
                # If transcript succeeds, convert transcript format to chat format
                if transcript_result.get('success') and transcript_result.get('messages'):
                    logger.info(f"Found {len(transcript_result.get('messages', []))} transcript entries")
                    # Convert transcript messages to chat format
                    chat_messages = []
                    for transcript_msg in transcript_result.get('messages', []):
                        # Extract chat data from transcript if available
                        content = transcript_msg.get('content', '')
                        if content:
                            # Parse VTT format or extract chat-like data
                            # For now, add as a note that transcripts are available
                            chat_messages.append({
                                'id': transcript_msg.get('transcript_id'),
                                'created': transcript_msg.get('created'),
                                'sender': 'Meeting Transcript',
                                'sender_email': '',
                                'message': f"[Transcript available - requires parsing]",
                                'message_type': 'system',
                                'note': 'Transcript data available but requires VTT parsing'
                            })
                    
                    if chat_messages:
                        chat_result = {
                            'success': True,
                            'messages': chat_messages,
                            'total_messages': len(chat_messages),
                            'note': 'Chat data from transcripts (requires Teams Premium and transcription)'
                        }
                    else:
                        chat_result = transcript_result
                else:
                    chat_result = transcript_result
            
            if not chat_result['success']:
                error_msg = chat_result.get('error', 'Failed to retrieve chat messages')
                error_code = chat_result.get('error_code', 'UNKNOWN')
                note = chat_result.get('note', '')
                
                logger.warning(f"Chat sync failed for conference {conference.id}: {error_msg}")
                
                # Check if it's a protected API issue (check multiple indicators)
                is_protected_api = False
                if error_code == 'PROTECTED_API_REQUIRED':
                    is_protected_api = True
                elif 'protected api' in error_msg.lower() or 'restricted api' in error_msg.lower():
                    is_protected_api = True
                    error_code = 'PROTECTED_API_REQUIRED'
                    if not note:
                        note = 'Meeting chats require Protected API approval even with delegated permissions. Request access at: https://aka.ms/pa-request'
                
                if is_protected_api:
                    self.sync_status['success'] = False  # Mark as failed for Protected API
                    self.sync_status['error'] = f"Protected API Access Required: {error_msg}"
                    self.sync_status['error_code'] = error_code
                    self.sync_status['note'] = note
                    self.sync_status['errors'] += 1
                    self.sync_status['error_messages'].append(f"Chat sync requires Protected API approval: {note}")
                    logger.info(f"Chat sync requires Protected API approval. See: {note}")
                elif 'permission' in error_msg.lower() or 'forbidden' in error_msg.lower():
                    self.sync_status['success'] = False
                    self.sync_status['error'] = f"Missing API permission: {chat_result.get('permission_required', 'Chat.Read.All')}"
                    self.sync_status['errors'] += 1
                    self.sync_status['error_messages'].append(self.sync_status['error'])
                else:
                    self.sync_status['success'] = False
                    self.sync_status['error'] = error_msg
                    self.sync_status['errors'] += 1
                    self.sync_status['error_messages'].append(error_msg)
                
                # Mark as synced even if no data (might require permissions/license)
                meeting_sync.chat_synced = True
                meeting_sync.last_chat_sync = timezone.now()
                if not hasattr(meeting_sync, 'sync_errors') or meeting_sync.sync_errors is None:
                    meeting_sync.sync_errors = {}
                meeting_sync.sync_errors['chat'] = error_msg
                if note:
                    meeting_sync.sync_errors['chat_note'] = note
                if is_protected_api:
                    meeting_sync.sync_errors['chat_protected_api'] = True
                meeting_sync.save()
                
                self.log_sync_result('sync_chat', False if is_protected_api else True, error_msg)
                return self.sync_status
            
            messages = chat_result.get('messages', [])
            logger.info(f"Retrieved {len(messages)} chat messages from Teams")
            
            # Process and save chat messages
            synced_count = 0
            updated_count = 0
            
            for msg_data in messages:
                try:
                    # Parse message data
                    sender_name = msg_data.get('sender', '')
                    sender_email = msg_data.get('sender_email', '')
                    message_text = msg_data.get('message', msg_data.get('content', ''))
                    sent_at_str = msg_data.get('created')
                    message_id = msg_data.get('id', msg_data.get('transcript_id'))
                    
                    # Use "User name needed" instead of empty string when sender name is missing
                    if not sender_name:
                        sender_name = 'User name needed'
                    
                    # ✅ FIX: Ensure message text is plain text (HTML should already be stripped by API)
                    # But double-check and strip HTML if present
                    if message_text and ('<' in message_text and '>' in message_text):
                        try:
                            import re
                            import html as html_module
                            # Unescape HTML entities and strip tags
                            message_text = html_module.unescape(message_text)
                            message_text = re.sub(r'<[^>]+>', '', message_text)
                            message_text = re.sub(r'\s+', ' ', message_text).strip()
                        except Exception:
                            pass  # Keep original if stripping fails
                    
                    # Skip empty messages
                    if not message_text or not message_text.strip():
                        continue
                    
                    # Parse timestamp
                    if sent_at_str:
                        from dateutil import parser as date_parser
                        sent_at = date_parser.parse(sent_at_str)
                    else:
                        sent_at = timezone.now()
                    
                    # Try to find the user by email
                    sender = None
                    if sender_email:
                        try:
                            # Use case-insensitive email matching
                            sender = CustomUser.objects.filter(email__iexact=sender_email).first()
                        except Exception:
                            pass
                    
                    # Check if message already exists
                    existing_message = None
                    if message_id:
                        existing_message = ConferenceChat.objects.filter(
                            conference=conference,
                            platform_message_id=message_id
                        ).first()
                    
                    if existing_message:
                        # Update existing message
                        existing_message.message_text = message_text
                        existing_message.sender_name = sender_name
                        if sender:
                            existing_message.sender = sender
                        existing_message.sent_at = sent_at
                        existing_message.metadata = msg_data
                        existing_message.save()
                        updated_count += 1
                    else:
                        # Create new message
                        ConferenceChat.objects.create(
                            conference=conference,
                            sender=sender,
                            sender_name=sender_name,
                            message_text=message_text,
                            message_type='text',
                            sent_at=sent_at,
                            platform_message_id=message_id or '',
                            metadata=msg_data
                        )
                        synced_count += 1
                    
                except Exception as msg_error:
                    logger.error(f"Error processing chat message: {str(msg_error)}")
                    continue
            
            # Update meeting sync record
            meeting_sync.chat_synced = True
            meeting_sync.last_chat_sync = timezone.now()
            meeting_sync.save()
            
            # Update sync status
            self.sync_status['success'] = True
            self.sync_status['processed'] += len(messages)
            self.sync_status['created'] += synced_count
            self.sync_status['updated'] += updated_count
            
            logger.info(
                f"Chat sync completed for conference {conference.id}: "
                f"{synced_count} created, {updated_count} updated"
            )
            
            # Add note if no messages were retrieved
            if len(messages) == 0:
                note = chat_result.get('note', '')
                if note:
                    logger.info(f"Chat sync note: {note}")
            
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting chat sync failed: {str(e)}"
            logger.warning(error_msg)
            # Log error but don't fail the entire sync
            self.log_sync_result('sync_chat', True, f"Skipped: {str(e)}")
            return self.sync_status
    
    def sync_meeting_files(self, conference):
        """
        Sync meeting shared files from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        # Reset sync status for this operation
        self.sync_status = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        try:
            from teams_integration.models import TeamsMeetingSync
            
            logger.info(f"Syncing files for conference: {conference.title}")
            
            # Get meeting sync record
            meeting_sync = TeamsMeetingSync.objects.filter(conference=conference).first()
            if not meeting_sync:
                logger.info("No meeting sync record found for file sync, skipping")
                return self.sync_status
            
            # Note: Teams file sync would require additional API calls
            # For now, we'll mark as synced but not actually sync data
            
            meeting_sync.files_synced = True
            meeting_sync.last_file_sync = timezone.now()
            meeting_sync.save()
            
            self.sync_status['success'] = True
            logger.info("Meeting files sync completed (placeholder)")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting files sync failed: {str(e)}"
            logger.warning(error_msg)
            # Log error but don't fail the entire sync
            self.log_sync_result('sync_files', True, f"Skipped: {str(e)}")
            return self.sync_status


class UserSyncService(TeamsSyncService):
    """Service for synchronizing user data with Teams"""
    
    def sync_users_to_teams(self):
        """
        Sync LMS users to Teams/Entra ID
        
        Returns:
            dict: Sync results
        """
        try:
            logger.info("Starting user sync to Teams...")
            
            # Get active users from the branch
            users = CustomUser.objects.filter(
                branch=self.config.branch,
                is_active=True
            )
            
            synced_count = 0
            for user in users:
                try:
                    self._sync_user_to_teams(user)
                    synced_count += 1
                except Exception as e:
                    self.log_sync_result(
                        f"sync_user_{user.username}", 
                        False, 
                        str(e)
                    )
            
            self.sync_status['processed'] = users.count()
            self.sync_status['updated'] = synced_count
            self.sync_status['success'] = True
            
            logger.info(f"Synced {synced_count} users to Teams")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"User sync to Teams failed: {str(e)}"
            logger.error(error_msg)
            self.log_sync_result('sync_users_to_teams', False, error_msg)
            return self.sync_status
    
    def _sync_user_to_teams(self, user):
        """Sync a single user to Teams"""
        try:
            # This would involve creating or updating the user in Entra ID
            # For now, we'll just log the operation
            
            logger.info(f"Syncing user to Teams: {user.username}")
            
            # In a real implementation, you would:
            # 1. Check if user exists in Entra ID
            # 2. Create or update user in Entra ID
            # 3. Assign user to appropriate groups
            
            self.log_sync_result(
                f"sync_user_{user.username}", 
                True, 
                f"Synced user: {user.username}"
            )
            
        except Exception as e:
            logger.error(f"Error syncing user {user.username}: {str(e)}")
            raise
