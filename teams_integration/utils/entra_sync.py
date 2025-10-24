"""
Entra ID Synchronization Service

This module provides services for synchronizing Entra ID groups and users
with the LMS system, following the same patterns as SharePoint integration.
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
from users.models import CustomUser
from groups.models import BranchGroup, GroupMembership

logger = logging.getLogger(__name__)
User = get_user_model()


class EntraSyncService:
    """Service for synchronizing Entra ID data with LMS"""
    
    def __init__(self, integration_config):
        """
        Initialize Entra sync service
        
        Args:
            integration_config: TeamsIntegration model instance
        """
        self.config = integration_config
        self.api = TeamsAPIClient(integration_config)
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
        logger.info(f"Entra Sync [{operation}] - {status}: {message}")
        
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
    
    def sync_entra_groups(self):
        """
        Sync Entra ID groups with LMS groups (both user groups and course groups)
        
        Returns:
            dict: Sync results
        """
        try:
            logger.info("Starting Entra ID groups synchronization...")
            
            # Get Entra ID groups
            groups_result = self.api.get_entra_groups()
            if not groups_result['success']:
                raise TeamsAPIError(f"Failed to get Entra groups: {groups_result['error']}")
            
            entra_groups = groups_result['groups']
            logger.info(f"Found {len(entra_groups)} Entra ID groups")
            
            # Process each group
            for entra_group in entra_groups:
                try:
                    self._process_entra_group(entra_group)
                    self.sync_status['processed'] += 1
                except Exception as e:
                    self.log_sync_result(
                        f"process_group_{entra_group['id']}", 
                        False, 
                        str(e)
                    )
            
            # Update sync status
            success = self.sync_status['errors'] == 0
            self.update_integration_sync_status(success)
            
            logger.info(f"Entra groups sync completed: {self.sync_status}")
            return self.sync_status
            
        except Exception as e:
            error_msg = f"Entra groups sync failed: {str(e)}"
            logger.error(error_msg)
            self.update_integration_sync_status(False, error_msg)
            return {
                'success': False,
                'error': error_msg,
                'sync_status': self.sync_status
            }
    
    def _process_entra_group(self, entra_group):
        """Process a single Entra ID group"""
        from .models import EntraGroupMapping
        
        try:
            # Check if mapping already exists
            mapping, created = EntraGroupMapping.objects.get_or_create(
                integration=self.config,
                entra_group_id=entra_group['id'],
                defaults={
                    'entra_group_name': entra_group['name'],
                    'entra_group_email': entra_group.get('email'),
                    'lms_group': self._find_or_create_lms_group(entra_group),
                    'last_sync_status': 'never'
                }
            )
            
            if not created:
                # Update existing mapping
                mapping.entra_group_name = entra_group['name']
                mapping.entra_group_email = entra_group.get('email')
                mapping.save(update_fields=['entra_group_name', 'entra_group_email'])
            
            # Sync group members if auto-sync is enabled
            if mapping.auto_sync_enabled:
                self._sync_group_members(mapping)
            
            self.log_sync_result(
                f"process_group_{entra_group['id']}", 
                True, 
                f"Processed group: {entra_group['name']}"
            )
            
        except Exception as e:
            self.log_sync_result(
                f"process_group_{entra_group['id']}", 
                False, 
                str(e)
            )
            raise
    
    def _find_or_create_lms_group(self, entra_group):
        """Find or create corresponding LMS group (user or course group)"""
        try:
            # Determine group type based on Entra ID group name/description
            group_type = self._determine_group_type(entra_group)
            
            # Try to find existing group by name
            lms_group = BranchGroup.objects.filter(
                branch=self.config.branch,
                name=entra_group['name'],
                group_type=group_type
            ).first()
            
            if not lms_group:
                # Create new group with appropriate type
                lms_group = BranchGroup.objects.create(
                    name=entra_group['name'],
                    description=f"Auto-created from Entra ID group: {entra_group['name']}",
                    branch=self.config.branch,
                    group_type=group_type,
                    is_active=True
                )
                logger.info(f"Created new LMS {group_type} group: {lms_group.name}")
                
                # If it's a course group, set up course access
                if group_type == 'course':
                    self._setup_course_group_access(lms_group, entra_group)
            else:
                logger.info(f"Found existing LMS {group_type} group: {lms_group.name}")
            
            return lms_group
            
        except Exception as e:
            logger.error(f"Error finding/creating LMS group: {str(e)}")
            raise
    
    def _determine_group_type(self, entra_group):
        """
        Determine if an Entra ID group should map to a user group or course group
        
        Args:
            entra_group: Entra ID group data
            
        Returns:
            str: 'user' or 'course'
        """
        # Check for course-related keywords in group name
        course_keywords = ['course', 'training', 'learning', 'class', 'module', 'lesson', 'education']
        group_name = entra_group.get('displayName', '').lower()
        description = entra_group.get('description', '').lower()
        
        # Check group name for course indicators
        for keyword in course_keywords:
            if keyword in group_name:
                return 'course'
        
        # Check description for course indicators
        for keyword in course_keywords:
            if keyword in description:
                return 'course'
        
        # Default to user group
        return 'user'
    
    def _setup_course_group_access(self, lms_group, entra_group):
        """
        Set up course access for a course group
        
        Args:
            lms_group: BranchGroup instance
            entra_group: Entra ID group data
        """
        from groups.models import CourseGroupAccess
        
        # Try to find a course that matches the group name or description
        course = self._find_matching_course(entra_group)
        
        if course:
            # Set up course access
            CourseGroupAccess.objects.get_or_create(
                group=lms_group,
                course=course,
                defaults={
                    'can_access': True,
                    'can_create_topics': True,
                    'can_manage_members': False
                }
            )
            
            logger.info(f"Set up course access for group {lms_group.name} to course {course.title}")
        else:
            logger.warning(f"No matching course found for Entra group: {entra_group.get('displayName', 'Unknown')}")
    
    def _find_matching_course(self, entra_group):
        """
        Find a course that matches the Entra ID group
        
        Args:
            entra_group: Entra ID group data
            
        Returns:
            Course or None
        """
        from courses.models import Course
        
        group_name = entra_group.get('displayName', '').lower()
        description = entra_group.get('description', '').lower()
        
        # Search for courses by title
        courses = Course.objects.filter(
            branch=self.config.branch,
            is_active=True
        )
        
        for course in courses:
            course_title_lower = course.title.lower()
            
            # Check if course title appears in group name or description
            if (course_title_lower in group_name or 
                course_title_lower in description or
                any(word in course_title_lower for word in group_name.split() if len(word) > 3)):
                return course
        
        return None
    
    def _sync_group_members(self, mapping):
        """Sync members of an Entra ID group"""
        try:
            # Get group members from Entra ID
            members_result = self.api.get_group_members(mapping.entra_group_id)
            if not members_result['success']:
                raise TeamsAPIError(f"Failed to get group members: {members_result['error']}")
            
            entra_members = members_result['members']
            logger.info(f"Found {len(entra_members)} members in group {mapping.entra_group_name}")
            
            # Process each member
            synced_count = 0
            for member in entra_members:
                try:
                    self._process_group_member(mapping, member)
                    synced_count += 1
                except Exception as e:
                    logger.warning(f"Failed to process member {member['email']}: {str(e)}")
            
            # Update mapping statistics
            mapping.last_sync_at = timezone.now()
            mapping.last_sync_status = 'success'
            mapping.last_sync_users_count = synced_count
            mapping.total_users_synced += synced_count
            mapping.save()
            
            logger.info(f"Synced {synced_count} members for group {mapping.entra_group_name}")
            
        except Exception as e:
            mapping.last_sync_status = 'failed'
            mapping.sync_error = str(e)
            mapping.save()
            logger.error(f"Error syncing group members: {str(e)}")
            raise
    
    def _process_group_member(self, mapping, member):
        """Process a single group member"""
        try:
            # Find or create user
            user = self._find_or_create_user(member)
            
            # Add user to LMS group
            membership, created = GroupMembership.objects.get_or_create(
                group=mapping.lms_group,
                user=user,
                defaults={
                    'is_active': True,
                    'joined_at': timezone.now()
                }
            )
            
            if created:
                logger.info(f"Added user {user.username} to group {mapping.lms_group.name}")
            else:
                logger.debug(f"User {user.username} already in group {mapping.lms_group.name}")
            
        except Exception as e:
            logger.error(f"Error processing group member {member['email']}: {str(e)}")
            raise
    
    def _find_or_create_user(self, member):
        """Find or create LMS user from Entra ID member"""
        try:
            # Try to find existing user by email
            user = CustomUser.objects.filter(email=member['email']).first()
            
            if not user:
                # Create new user
                username = member['email'].split('@')[0]
                # Ensure username is unique
                base_username = username
                counter = 1
                while CustomUser.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                user = CustomUser.objects.create(
                    username=username,
                    email=member['email'],
                    first_name=member['name'].split(' ')[0] if member['name'] else '',
                    last_name=' '.join(member['name'].split(' ')[1:]) if member['name'] and ' ' in member['name'] else '',
                    role='learner',  # Default role
                    branch=self.config.branch,
                    is_active=True
                )
                logger.info(f"Created new user: {user.username}")
            
            return user
            
        except Exception as e:
            logger.error(f"Error finding/creating user: {str(e)}")
            raise
    
    def sync_user_groups(self, user):
        """
        Sync Entra ID groups for a specific user
        
        Args:
            user: CustomUser instance
            
        Returns:
            dict: Sync results
        """
        try:
            logger.info(f"Syncing Entra groups for user: {user.username}")
            
            # Get user's Entra ID groups
            # This would require additional API calls to get user's group memberships
            # For now, we'll sync based on existing mappings
            
            from .models import EntraGroupMapping
            mappings = EntraGroupMapping.objects.filter(
                integration=self.config,
                is_active=True
            )
            
            synced_groups = []
            for mapping in mappings:
                try:
                    # Check if user should be in this group
                    if self._user_should_be_in_group(user, mapping):
                        # Add user to group if not already a member
                        membership, created = GroupMembership.objects.get_or_create(
                            group=mapping.lms_group,
                            user=user,
                            defaults={'is_active': True}
                        )
                        if created:
                            synced_groups.append(mapping.lms_group.name)
                except Exception as e:
                    logger.warning(f"Error syncing user to group {mapping.lms_group.name}: {str(e)}")
            
            logger.info(f"Synced user {user.username} to {len(synced_groups)} groups")
            return {
                'success': True,
                'synced_groups': synced_groups
            }
            
        except Exception as e:
            logger.error(f"Error syncing user groups: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _user_should_be_in_group(self, user, mapping):
        """Check if user should be in a specific group based on Entra ID membership"""
        # This is a simplified check - in a real implementation,
        # you would query Entra ID to check if the user is a member of the group
        # For now, we'll assume all users should be in all groups
        return True
