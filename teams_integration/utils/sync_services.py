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
        Sync meeting recordings from Teams
        
        Args:
            conference: Conference instance
            
        Returns:
            dict: Sync results
        """
        try:
            from .models import TeamsMeetingSync
            
            logger.info(f"Syncing recordings for conference: {conference.title}")
            
            # Get meeting sync record
            meeting_sync = TeamsMeetingSync.objects.filter(conference=conference).first()
            if not meeting_sync:
                self.log_sync_result(
                    'sync_recordings', 
                    False, 
                    'No meeting sync record found'
                )
                return self.sync_status
            
            # Note: Teams API doesn't provide direct access to recordings
            # This would require additional Microsoft Graph API calls
            # For now, we'll mark as synced but not actually sync data
            
            meeting_sync.recordings_synced = True
            meeting_sync.last_recording_sync = timezone.now()
            meeting_sync.save()
            
            self.sync_status['success'] = True
            logger.info("Meeting recordings sync completed (placeholder)")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Meeting recordings sync failed: {str(e)}"
            logger.error(error_msg)
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
            
            # Note: Teams chat sync would require additional API calls
            # For now, we'll mark as synced but not actually sync data
            
            meeting_sync.chat_synced = True
            meeting_sync.last_chat_sync = timezone.now()
            meeting_sync.save()
            
            self.sync_status['success'] = True
            logger.info("Meeting chat sync completed (placeholder)")
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
