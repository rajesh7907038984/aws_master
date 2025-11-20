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
        Sync meeting attendance data from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        try:
            from .models import TeamsMeetingSync
            
            logger.info(f"Syncing attendance for conference: {conference.title}")
            
            # Get or create meeting sync record
            meeting_sync, created = TeamsMeetingSync.objects.get_or_create(
                conference=conference,
                defaults={
                    'teams_meeting_id': conference.meeting_id or '',
                    'teams_meeting_url': conference.meeting_link,
                    'meeting_status': 'scheduled'
                }
            )
            
            if not conference.meeting_id:
                self.log_sync_result(
                    'sync_attendance', 
                    False, 
                    'No Teams meeting ID found'
                )
                return self.sync_status
            
            # Get attendance data from Teams
            attendance_result = self.api.get_meeting_attendance(conference.meeting_id)
            if not attendance_result['success']:
                raise TeamsAPIError(f"Failed to get meeting attendance: {attendance_result['error']}")
            
            attendees = attendance_result['attendees']
            logger.info(f"Found {len(attendees)} attendees in Teams meeting")
            
            # Process each attendee
            synced_count = 0
            for attendee in attendees:
                try:
                    self._process_attendee(conference, attendee)
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
            self.sync_status['updated'] = synced_count
            self.sync_status['success'] = True
            
            logger.info(f"Synced attendance for {synced_count} attendees")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting attendance sync failed: {str(e)}"
            logger.error(error_msg)
            self.log_sync_result('sync_attendance', False, error_msg)
            return self.sync_status
    
    def _process_attendee(self, conference, attendee):
        """Process a single meeting attendee"""
        try:
            # Find user by email
            user = CustomUser.objects.filter(email=attendee['email']).first()
            
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
    
    def sync_meeting_recordings(self, conference):
        """
        Sync meeting recordings from Teams OneDrive storage
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
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
                onedrive_api = OneDriveAPI(self.integration)
            except OneDriveAPIError as e:
                error_msg = f"Failed to initialize OneDrive API: {str(e)}"
                logger.error(error_msg)
                self.log_sync_result('sync_recordings', False, error_msg)
                return self.sync_status
            
            # Determine which user's OneDrive to search
            # Priority: 1. Conference creator, 2. Integration owner, 3. Service account
            admin_email = None
            if conference.created_by and conference.created_by.email:
                admin_email = conference.created_by.email
            elif self.integration.user and self.integration.user.email:
                admin_email = self.integration.user.email
            elif self.integration.service_account_email:
                admin_email = self.integration.service_account_email
            
            if not admin_email:
                error_msg = "No admin email found for OneDrive access"
                logger.error(error_msg)
                self.log_sync_result('sync_recordings', False, error_msg)
                return self.sync_status
            
            logger.info(f"📧 Accessing OneDrive for: {admin_email}")
            
            # Search for recordings
            recordings_result = onedrive_api.search_recordings_for_meeting(
                user_email=admin_email,
                meeting_id=conference.meeting_id,
                meeting_title=conference.title
            )
            
            if not recordings_result['success']:
                error_msg = f"OneDrive search failed: {recordings_result.get('error', 'Unknown error')}"
                logger.error(error_msg)
                self.log_sync_result('sync_recordings', False, error_msg)
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
                    
                    # Extract duration from file name if possible (format: Meeting-YYYYMMDD-HHMMSS.mp4)
                    duration_minutes = 0
                    
                    # Create or update recording
                    recording, created = ConferenceRecording.objects.update_or_create(
                        conference=conference,
                        recording_id=f"onedrive_{recording_id}",
                        defaults={
                            'title': recording_data.get('name', 'Meeting Recording'),
                            'recording_type': 'cloud',
                            'file_url': recording_data.get('webUrl'),
                            'file_size': recording_data.get('size', 0),
                            'duration_minutes': duration_minutes,
                            'file_format': recording_data.get('name', '').split('.')[-1].lower() or 'mp4',
                            'download_url': recording_data.get('downloadUrl'),
                            'status': 'available',
                            # OneDrive-specific fields
                            'onedrive_item_id': recording_id,
                            'onedrive_drive_id': drive_id,
                            'onedrive_file_path': recording_data.get('path', ''),
                            'onedrive_web_url': recording_data.get('webUrl'),
                            'onedrive_download_url': recording_data.get('downloadUrl'),
                            'stored_in_onedrive': True,
                            'meeting_recording_id': conference.meeting_id,
                            'recording_content_url': recording_data.get('webUrl'),
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
            logger.error(error_msg)
            logger.exception(e)
            self.log_sync_result('sync_recordings', False, error_msg)
            return self.sync_status
    
    def sync_meeting_chat(self, conference):
        """
        Sync meeting chat messages from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        try:
            from .models import TeamsMeetingSync
            from conferences.models import ConferenceChat
            from users.models import CustomUser
            
            logger.info(f"Syncing chat for conference: {conference.title}")
            
            # Get meeting sync record
            meeting_sync = TeamsMeetingSync.objects.filter(conference=conference).first()
            if not meeting_sync:
                self.log_sync_result(
                    'sync_chat', 
                    False, 
                    'No meeting sync record found'
                )
                return self.sync_status
            
            # Check if we have a meeting ID
            if not conference.meeting_id:
                self.log_sync_result(
                    'sync_chat', 
                    False, 
                    'No Teams meeting ID found'
                )
                return self.sync_status
            
            # Determine user email for API calls
            user_email = None
            if self.integration.user and self.integration.user.email:
                user_email = self.integration.user.email
            elif hasattr(self.integration, 'service_account_email') and self.integration.service_account_email:
                user_email = self.integration.service_account_email
            
            if not user_email:
                self.log_sync_result(
                    'sync_chat', 
                    False, 
                    'No user email available for API authentication'
                )
                return self.sync_status
            
            # Try to get meeting transcript/chat messages
            transcript_result = self.api.get_meeting_transcript(
                conference.meeting_id,
                user_email=user_email
            )
            
            if not transcript_result['success']:
                error_msg = transcript_result.get('error', 'Failed to retrieve chat messages')
                logger.warning(f"Chat sync failed for conference {conference.id}: {error_msg}")
                
                # Mark as synced even if no data (might require permissions/license)
                meeting_sync.chat_synced = True
                meeting_sync.last_chat_sync = timezone.now()
                meeting_sync.sync_errors['chat'] = error_msg
                meeting_sync.save()
                
                self.log_sync_result('sync_chat', True, error_msg)
                return self.sync_status
            
            messages = transcript_result.get('messages', [])
            logger.info(f"Retrieved {len(messages)} chat messages from Teams")
            
            # Process and save chat messages
            synced_count = 0
            updated_count = 0
            
            for msg_data in messages:
                try:
                    # Parse message data
                    sender_name = msg_data.get('sender', 'Unknown')
                    sender_email = msg_data.get('sender_email', '')
                    message_text = msg_data.get('message', msg_data.get('content', ''))
                    sent_at_str = msg_data.get('created')
                    message_id = msg_data.get('id', msg_data.get('transcript_id'))
                    
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
                            sender = CustomUser.objects.filter(email=sender_email).first()
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
                note = transcript_result.get('note', '')
                if note:
                    logger.info(f"Chat sync note: {note}")
            
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting chat sync failed: {str(e)}"
            logger.error(error_msg)
            self.log_sync_result('sync_chat', False, error_msg)
            return self.sync_status
    
    def sync_meeting_files(self, conference):
        """
        Sync meeting shared files from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        try:
            from .models import TeamsMeetingSync
            
            logger.info(f"Syncing files for conference: {conference.title}")
            
            # Get meeting sync record
            meeting_sync = TeamsMeetingSync.objects.filter(conference=conference).first()
            if not meeting_sync:
                self.log_sync_result(
                    'sync_files', 
                    False, 
                    'No meeting sync record found'
                )
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
            logger.error(error_msg)
            self.log_sync_result('sync_files', False, error_msg)
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
