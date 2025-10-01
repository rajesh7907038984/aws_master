"""
SharePoint to LMS Monitoring Service

This module provides real-time monitoring of SharePoint changes and syncs them back to LMS.
It uses periodic polling and webhook-style monitoring to detect changes in SharePoint lists.
"""

import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from django.contrib.auth import get_user_model

from .sharepoint_api import SharePointAPI, SharePointAPIError
from account_settings.models import SharePointIntegration

logger = logging.getLogger(__name__)
User = get_user_model()


class SharePointChangeMonitor:
    """
    Service for monitoring SharePoint changes and syncing them to LMS
    """
    
    def __init__(self, integration_config: SharePointIntegration):
        """
        Initialize the change monitor
        
        Args:
            integration_config: SharePointIntegration model instance
        """
        self.config = integration_config
        self.api = SharePointAPI(integration_config)
        self.cache_prefix = f"sp_monitor_{integration_config.id}"
        
    def start_monitoring(self) -> Dict[str, Any]:
        """
        Start monitoring SharePoint for changes
        
        Returns:
            Dictionary with monitoring status and results
        """
        results = {
            'users_synced': 0,
            'enrollments_synced': 0,
            'progress_synced': 0,
            'errors': [],
            'last_check': timezone.now().isoformat()
        }
        
        try:
            # Monitor different types of data
            if self.config.enable_user_sync:
                user_results = self.monitor_user_changes()
                results['users_synced'] = user_results.get('synced', 0)
                if user_results.get('errors'):
                    results['errors'].extend(user_results['errors'])
            
            if self.config.enable_enrollment_sync:
                enrollment_results = self.monitor_enrollment_changes()
                results['enrollments_synced'] = enrollment_results.get('synced', 0)
                if enrollment_results.get('errors'):
                    results['errors'].extend(enrollment_results['errors'])
            
            if self.config.enable_progress_sync:
                progress_results = self.monitor_progress_changes()
                results['progress_synced'] = progress_results.get('synced', 0)
                if progress_results.get('errors'):
                    results['errors'].extend(progress_results['errors'])
            
            # Update last monitoring time
            self.config.last_sync_datetime = timezone.now()
            self.config.save(update_fields=['last_sync_datetime'])
            
            logger.info(f"SharePoint monitoring completed for {self.config.name}")
            return results
            
        except Exception as e:
            logger.error(f"Error in SharePoint monitoring: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def monitor_user_changes(self) -> Dict[str, Any]:
        """Monitor changes in SharePoint user list"""
        results = {'synced': 0, 'errors': []}
        
        try:
            # Get users from SharePoint
            sharepoint_users = self.api.get_list_items(self.config.user_list_name)
            
            # Get cached version to compare
            cache_key = f"{self.cache_prefix}_users_hash"
            current_hash = self._calculate_list_hash(sharepoint_users)
            cached_hash = cache.get(cache_key)
            
            if cached_hash != current_hash:
                logger.info(f"Detected changes in SharePoint users for {self.config.name}")
                
                # Process each user
                for sp_user in sharepoint_users:
                    try:
                        if self._sync_sharepoint_user_to_lms(sp_user):
                            results['synced'] += 1
                    except Exception as e:
                        error_msg = f"Error syncing user {sp_user.get('fields', {}).get('Email', 'unknown')}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
                
                # Update cache
                cache.set(cache_key, current_hash, 300)  # Cache for 5 minutes
            
            return results
            
        except Exception as e:
            logger.error(f"Error monitoring user changes: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def monitor_enrollment_changes(self) -> Dict[str, Any]:
        """Monitor changes in SharePoint enrollment list"""
        results = {'synced': 0, 'errors': []}
        
        try:
            # Get enrollments from SharePoint
            sharepoint_enrollments = self.api.get_list_items(self.config.enrollment_list_name)
            
            # Get cached version to compare
            cache_key = f"{self.cache_prefix}_enrollments_hash"
            current_hash = self._calculate_list_hash(sharepoint_enrollments)
            cached_hash = cache.get(cache_key)
            
            if cached_hash != current_hash:
                logger.info(f"Detected changes in SharePoint enrollments for {self.config.name}")
                
                # Process each enrollment
                for sp_enrollment in sharepoint_enrollments:
                    try:
                        if self._sync_sharepoint_enrollment_to_lms(sp_enrollment):
                            results['synced'] += 1
                    except Exception as e:
                        error_msg = f"Error syncing enrollment {sp_enrollment.get('fields', {}).get('LMSEnrollmentID', 'unknown')}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
                
                # Update cache
                cache.set(cache_key, current_hash, 300)
            
            return results
            
        except Exception as e:
            logger.error(f"Error monitoring enrollment changes: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def monitor_progress_changes(self) -> Dict[str, Any]:
        """Monitor changes in SharePoint progress list"""
        results = {'synced': 0, 'errors': []}
        
        try:
            # Get progress from SharePoint
            sharepoint_progress = self.api.get_list_items(self.config.progress_list_name)
            
            # Get cached version to compare
            cache_key = f"{self.cache_prefix}_progress_hash"
            current_hash = self._calculate_list_hash(sharepoint_progress)
            cached_hash = cache.get(cache_key)
            
            if cached_hash != current_hash:
                logger.info(f"Detected changes in SharePoint progress for {self.config.name}")
                
                # Process each progress entry
                for sp_progress in sharepoint_progress:
                    try:
                        if self._sync_sharepoint_progress_to_lms(sp_progress):
                            results['synced'] += 1
                    except Exception as e:
                        error_msg = f"Error syncing progress {sp_progress.get('fields', {}).get('LMSProgressID', 'unknown')}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
                
                # Update cache
                cache.set(cache_key, current_hash, 300)
            
            return results
            
        except Exception as e:
            logger.error(f"Error monitoring progress changes: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def _calculate_list_hash(self, items: List[Dict]) -> str:
        """Calculate hash of a list of items for change detection"""
        try:
            # Sort items by ID to ensure consistent hashing
            sorted_items = sorted(items, key=lambda x: x.get('id', ''))
            content = json.dumps(sorted_items, sort_keys=True, default=str)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception:
            return str(timezone.now().timestamp())
    
    def _sync_sharepoint_user_to_lms(self, sharepoint_user: Dict) -> bool:
        """
        Sync a SharePoint user to LMS
        
        Args:
            sharepoint_user: SharePoint user data
            
        Returns:
            Boolean indicating success
        """
        try:
            fields = sharepoint_user.get('fields', {})
            email = fields.get('Email', '')
            
            if not email:
                logger.warning("SharePoint user has no email, skipping")
                return False
            
            # Try to find existing user
            try:
                user = User.objects.get(email=email)
                updated = False
                
                # Update user fields if they've changed
                if fields.get('FirstName') and user.first_name != fields.get('FirstName'):
                    user.first_name = fields.get('FirstName')
                    updated = True
                
                if fields.get('LastName') and user.last_name != fields.get('LastName'):
                    user.last_name = fields.get('LastName')
                    updated = True
                
                if fields.get('Role') and user.role != fields.get('Role'):
                    user.role = fields.get('Role')
                    updated = True
                
                if fields.get('IsActive') is not None and user.is_active != fields.get('IsActive'):
                    user.is_active = fields.get('IsActive')
                    updated = True
                
                # Update other fields as needed
                if fields.get('Phone') and hasattr(user, 'phone_number'):
                    if user.phone_number != fields.get('Phone'):
                        user.phone_number = fields.get('Phone')
                        updated = True
                
                if updated:
                    user.save()
                    logger.info(f"Updated user {email} from SharePoint")
                
                return True
                
            except User.DoesNotExist:
                # Create new user if it doesn't exist
                if self._should_create_user_from_sharepoint(fields):
                    return self._create_user_from_sharepoint(fields)
                else:
                    logger.info(f"User {email} not found in LMS and auto-creation disabled")
                    return False
            
        except Exception as e:
            logger.error(f"Error syncing SharePoint user to LMS: {str(e)}")
            return False
    
    def _sync_sharepoint_enrollment_to_lms(self, sharepoint_enrollment: Dict) -> bool:
        """Sync SharePoint enrollment to LMS"""
        try:
            fields = sharepoint_enrollment.get('fields', {})
            user_email = fields.get('UserEmail', '')
            course_id = fields.get('CourseID', '')
            
            if not user_email or not course_id:
                return False
            
            # Find user and course
            try:
                user = User.objects.get(email=user_email)
                
                # Import here to avoid circular imports
                from courses.models import Course, CourseEnrollment
                
                try:
                    course = Course.objects.get(id=course_id)
                    
                    # Check if enrollment exists
                    enrollment, created = CourseEnrollment.objects.get_or_create(
                        user=user,
                        course=course,
                        defaults={
                            'enrollment_date': timezone.now().date(),
                            'status': fields.get('Status', 'enrolled')
                        }
                    )
                    
                    if not created:
                        # Update existing enrollment
                        updated = False
                        if fields.get('Status') and enrollment.status != fields.get('Status'):
                            enrollment.status = fields.get('Status')
                            updated = True
                        
                        if updated:
                            enrollment.save()
                    
                    return True
                    
                except Course.DoesNotExist:
                    logger.warning(f"Course {course_id} not found for enrollment sync")
                    return False
                    
            except User.DoesNotExist:
                logger.warning(f"User {user_email} not found for enrollment sync")
                return False
            
        except Exception as e:
            logger.error(f"Error syncing SharePoint enrollment to LMS: {str(e)}")
            return False
    
    def _sync_sharepoint_progress_to_lms(self, sharepoint_progress: Dict) -> bool:
        """Sync SharePoint progress to LMS"""
        try:
            fields = sharepoint_progress.get('fields', {})
            user_email = fields.get('UserEmail', '')
            topic_id = fields.get('TopicID', '')
            
            if not user_email or not topic_id:
                return False
            
            try:
                user = User.objects.get(email=user_email)
                
                # Import here to avoid circular imports
                from courses.models import Topic, TopicProgress
                
                try:
                    topic = Topic.objects.get(id=topic_id)
                    
                    # Update or create progress
                    progress, created = TopicProgress.objects.get_or_create(
                        user=user,
                        topic=topic,
                        defaults={
                            'progress_percentage': fields.get('ProgressPercent', 0),
                            'is_completed': fields.get('IsCompleted', False),
                            'time_spent': fields.get('TimeSpent', 0)
                        }
                    )
                    
                    if not created:
                        # Update existing progress
                        updated = False
                        
                        if fields.get('ProgressPercent') is not None:
                            new_progress = float(fields.get('ProgressPercent', 0))
                            if progress.progress_percentage != new_progress:
                                progress.progress_percentage = new_progress
                                updated = True
                        
                        if fields.get('IsCompleted') is not None:
                            new_completed = fields.get('IsCompleted')
                            if progress.is_completed != new_completed:
                                progress.is_completed = new_completed
                                updated = True
                        
                        if updated:
                            progress.save()
                    
                    return True
                    
                except Topic.DoesNotExist:
                    logger.warning(f"Topic {topic_id} not found for progress sync")
                    return False
                    
            except User.DoesNotExist:
                logger.warning(f"User {user_email} not found for progress sync")
                return False
            
        except Exception as e:
            logger.error(f"Error syncing SharePoint progress to LMS: {str(e)}")
            return False
    
    def _should_create_user_from_sharepoint(self, user_fields: Dict) -> bool:
        """Determine if a user should be auto-created from SharePoint data"""
        # Check if auto-creation is enabled (this could be a setting)
        # For now, return False to prevent automatic user creation
        return False
    
    def _create_user_from_sharepoint(self, user_fields: Dict) -> bool:
        """Create a new user from SharePoint data"""
        try:
            from branches.models import Branch
            
            # Get branch
            branch = None
            if user_fields.get('Branch'):
                try:
                    branch = Branch.objects.get(name=user_fields.get('Branch'))
                except Branch.DoesNotExist:
                    logger.warning(f"Branch {user_fields.get('Branch')} not found")
            
            # Create user
            user = User.objects.create_user(
                username=user_fields.get('Username', user_fields.get('Email', '').split('@')[0]),
                email=user_fields.get('Email'),
                first_name=user_fields.get('FirstName', ''),
                last_name=user_fields.get('LastName', ''),
                role=user_fields.get('Role', 'learner'),
                branch=branch,
                is_active=user_fields.get('IsActive', True)
            )
            
            # Set additional fields
            if user_fields.get('Phone') and hasattr(user, 'phone_number'):
                user.phone_number = user_fields.get('Phone')
            
            if user_fields.get('DateOfBirth') and hasattr(user, 'date_of_birth'):
                try:
                    from dateutil import parser
                    user.date_of_birth = parser.parse(user_fields.get('DateOfBirth')).date()
                except:
                    pass
            
            user.save()
            logger.info(f"Created new user {user.email} from SharePoint")
            return True
            
        except Exception as e:
            logger.error(f"Error creating user from SharePoint: {str(e)}")
            return False


class SharePointWebhookHandler:
    """
    Handler for SharePoint webhook notifications
    This would be used if SharePoint webhooks are configured
    """
    
    def __init__(self, integration_config: SharePointIntegration):
        self.config = integration_config
        
    def handle_webhook(self, webhook_data: Dict) -> Dict[str, Any]:
        """
        Handle incoming webhook from SharePoint
        
        Args:
            webhook_data: Webhook payload from SharePoint
            
        Returns:
            Processing results
        """
        try:
            # Extract change information from webhook
            resource = webhook_data.get('resource', '')
            change_type = webhook_data.get('changeType', '')
            
            # Process the change based on type
            if 'users' in resource.lower():
                return self._handle_user_webhook(webhook_data)
            elif 'enrollment' in resource.lower():
                return self._handle_enrollment_webhook(webhook_data)
            elif 'progress' in resource.lower():
                return self._handle_progress_webhook(webhook_data)
            else:
                logger.info(f"Unhandled webhook resource: {resource}")
                return {'processed': False, 'reason': 'Unhandled resource type'}
            
        except Exception as e:
            logger.error(f"Error handling SharePoint webhook: {str(e)}")
            return {'processed': False, 'error': str(e)}
    
    def _handle_user_webhook(self, webhook_data: Dict) -> Dict[str, Any]:
        """Handle user-related webhook"""
        # Trigger immediate user sync
        monitor = SharePointChangeMonitor(self.config)
        return monitor.monitor_user_changes()
    
    def _handle_enrollment_webhook(self, webhook_data: Dict) -> Dict[str, Any]:
        """Handle enrollment-related webhook"""
        # Trigger immediate enrollment sync
        monitor = SharePointChangeMonitor(self.config)
        return monitor.monitor_enrollment_changes()
    
    def _handle_progress_webhook(self, webhook_data: Dict) -> Dict[str, Any]:
        """Handle progress-related webhook"""
        # Trigger immediate progress sync
        monitor = SharePointChangeMonitor(self.config)
        return monitor.monitor_progress_changes()


def start_sharepoint_monitoring():
    """
    Start monitoring all active SharePoint integrations
    This function can be called by Celery tasks or management commands
    """
    try:
        active_integrations = SharePointIntegration.objects.filter(is_active=True)
        
        results = {
            'total_integrations': active_integrations.count(),
            'successful_monitors': 0,
            'failed_monitors': 0,
            'total_synced': 0,
            'errors': []
        }
        
        for integration in active_integrations:
            try:
                monitor = SharePointChangeMonitor(integration)
                monitor_results = monitor.start_monitoring()
                
                results['successful_monitors'] += 1
                results['total_synced'] += (
                    monitor_results.get('users_synced', 0) +
                    monitor_results.get('enrollments_synced', 0) +
                    monitor_results.get('progress_synced', 0)
                )
                
                if monitor_results.get('errors'):
                    results['errors'].extend(monitor_results['errors'])
                    
            except Exception as e:
                results['failed_monitors'] += 1
                error_msg = f"Failed to monitor {integration.name}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        logger.info(f"SharePoint monitoring completed: {results['successful_monitors']} successful, {results['failed_monitors']} failed")
        return results
        
    except Exception as e:
        logger.error(f"Error in SharePoint monitoring startup: {str(e)}")
        return {'error': str(e)}