"""
SharePoint Sync Conflict Resolver

This module handles conflicts that arise when the same data is modified
in both LMS and SharePoint simultaneously.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.cache import cache

from .sharepoint_api import SharePointAPI, SharePointAPIError
from account_settings.models import SharePointIntegration

logger = logging.getLogger(__name__)
User = get_user_model()


class ConflictResolutionStrategy:
    """Base class for conflict resolution strategies"""
    
    LMS_WINS = "lms_wins"
    SHAREPOINT_WINS = "sharepoint_wins"
    LATEST_WINS = "latest_wins"
    MANUAL_REVIEW = "manual_review"
    MERGE_FIELDS = "merge_fields"


class SharePointConflictResolver:
    """
    Service for resolving synchronization conflicts between LMS and SharePoint
    """
    
    def __init__(self, integration_config: SharePointIntegration):
        """
        Initialize the conflict resolver
        
        Args:
            integration_config: SharePointIntegration model instance
        """
        self.config = integration_config
        self.api = SharePointAPI(integration_config)
        self.cache_prefix = f"sp_conflicts_{integration_config.id}"
        
        # Default conflict resolution strategies
        self.default_strategies = {
            'user': ConflictResolutionStrategy.LATEST_WINS,
            'enrollment': ConflictResolutionStrategy.LMS_WINS,
            'progress': ConflictResolutionStrategy.LATEST_WINS,
            'grade': ConflictResolutionStrategy.LMS_WINS,
            'course': ConflictResolutionStrategy.LMS_WINS
        }
    
    def resolve_all_conflicts(self) -> Dict[str, Any]:
        """
        Resolve all detected conflicts between LMS and SharePoint
        
        Returns:
            Dictionary with resolution results
        """
        results = {
            'total_conflicts': 0,
            'resolved': 0,
            'failed': 0,
            'manual_review_required': 0,
            'details': [],
            'errors': []
        }
        
        try:
            # Detect and resolve user conflicts
            user_conflicts = self._detect_user_conflicts()
            for conflict in user_conflicts:
                result = self._resolve_user_conflict(conflict)
                self._update_results(results, result)
            
            # Detect and resolve enrollment conflicts
            enrollment_conflicts = self._detect_enrollment_conflicts()
            for conflict in enrollment_conflicts:
                result = self._resolve_enrollment_conflict(conflict)
                self._update_results(results, result)
            
            # Detect and resolve progress conflicts
            progress_conflicts = self._detect_progress_conflicts()
            for conflict in progress_conflicts:
                result = self._resolve_progress_conflict(conflict)
                self._update_results(results, result)
            
            logger.info(f"Conflict resolution completed for {self.config.name}: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in conflict resolution: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def _detect_user_conflicts(self) -> List[Dict]:
        """
        Detect conflicts in user data between LMS and SharePoint
        
        Returns:
            List of conflict dictionaries
        """
        conflicts = []
        
        try:
            # Get users from SharePoint
            sharepoint_users = self.api.get_list_items(self.config.user_list_name)
            
            # Compare with LMS users
            for sp_user in sharepoint_users:
                try:
                    fields = sp_user.get('fields', {})
                    email = fields.get('Email', '')
                    
                    if not email:
                        continue
                    
                    # Find corresponding LMS user
                    try:
                        lms_user = User.objects.get(email=email)
                        
                        # Check for conflicts
                        conflict_fields = self._compare_user_data(lms_user, fields)
                        
                        if conflict_fields:
                            conflicts.append({
                                'type': 'user',
                                'lms_user_id': lms_user.id,
                                'sharepoint_item_id': sp_user.get('id'),
                                'email': email,
                                'conflict_fields': conflict_fields,
                                'lms_data': self._extract_user_data(lms_user),
                                'sharepoint_data': fields,
                                'lms_updated': lms_user.date_joined,  # Use available timestamp
                                'sharepoint_updated': fields.get('UpdatedDate')
                            })
                            
                    except User.DoesNotExist:
                        # User exists in SharePoint but not in LMS
                        conflicts.append({
                            'type': 'user_missing_lms',
                            'email': email,
                            'sharepoint_item_id': sp_user.get('id'),
                            'sharepoint_data': fields
                        })
                        
                except Exception as e:
                    logger.error(f"Error detecting user conflict: {str(e)}")
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Error detecting user conflicts: {str(e)}")
            return []
    
    def _detect_enrollment_conflicts(self) -> List[Dict]:
        """Detect enrollment conflicts"""
        conflicts = []
        
        try:
            sharepoint_enrollments = self.api.get_list_items(self.config.enrollment_list_name)
            
            for sp_enrollment in sharepoint_enrollments:
                try:
                    fields = sp_enrollment.get('fields', {})
                    lms_enrollment_id = fields.get('LMSEnrollmentID', '')
                    user_email = fields.get('UserEmail', '')
                    
                    if not lms_enrollment_id or not user_email:
                        continue
                    
                    # Find corresponding LMS enrollment
                    try:
                        from courses.models import CourseEnrollment
                        lms_enrollment = CourseEnrollment.objects.get(id=lms_enrollment_id)
                        
                        # Check for status conflicts
                        lms_status = getattr(lms_enrollment, 'status', 'enrolled')
                        sp_status = fields.get('Status', 'enrolled')
                        
                        if lms_status != sp_status:
                            conflicts.append({
                                'type': 'enrollment',
                                'lms_enrollment_id': lms_enrollment_id,
                                'sharepoint_item_id': sp_enrollment.get('id'),
                                'user_email': user_email,
                                'conflict_fields': ['status'],
                                'lms_status': lms_status,
                                'sharepoint_status': sp_status
                            })
                            
                    except CourseEnrollment.DoesNotExist:
                        # Enrollment exists in SharePoint but not in LMS
                        conflicts.append({
                            'type': 'enrollment_missing_lms',
                            'lms_enrollment_id': lms_enrollment_id,
                            'sharepoint_item_id': sp_enrollment.get('id'),
                            'sharepoint_data': fields
                        })
                        
                except Exception as e:
                    logger.error(f"Error detecting enrollment conflict: {str(e)}")
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Error detecting enrollment conflicts: {str(e)}")
            return []
    
    def _detect_progress_conflicts(self) -> List[Dict]:
        """Detect progress conflicts"""
        conflicts = []
        
        try:
            sharepoint_progress = self.api.get_list_items(self.config.progress_list_name)
            
            for sp_progress in sharepoint_progress:
                try:
                    fields = sp_progress.get('fields', {})
                    lms_progress_id = fields.get('LMSProgressID', '')
                    user_email = fields.get('UserEmail', '')
                    
                    if not lms_progress_id or not user_email:
                        continue
                    
                    # Find corresponding LMS progress
                    try:
                        from courses.models import TopicProgress
                        lms_progress = TopicProgress.objects.get(id=lms_progress_id)
                        
                        # Check for progress conflicts
                        lms_percentage = getattr(lms_progress, 'progress_percentage', 0)
                        sp_percentage = fields.get('ProgressPercent', 0)
                        
                        if abs(lms_percentage - sp_percentage) > 5:  # Allow 5% difference
                            conflicts.append({
                                'type': 'progress',
                                'lms_progress_id': lms_progress_id,
                                'sharepoint_item_id': sp_progress.get('id'),
                                'user_email': user_email,
                                'conflict_fields': ['progress_percentage'],
                                'lms_percentage': lms_percentage,
                                'sharepoint_percentage': sp_percentage
                            })
                            
                    except TopicProgress.DoesNotExist:
                        # Progress exists in SharePoint but not in LMS
                        conflicts.append({
                            'type': 'progress_missing_lms',
                            'lms_progress_id': lms_progress_id,
                            'sharepoint_item_id': sp_progress.get('id'),
                            'sharepoint_data': fields
                        })
                        
                except Exception as e:
                    logger.error(f"Error detecting progress conflict: {str(e)}")
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Error detecting progress conflicts: {str(e)}")
            return []
    
    def _resolve_user_conflict(self, conflict: Dict) -> Dict:
        """
        Resolve a user data conflict
        
        Args:
            conflict: Conflict dictionary
            
        Returns:
            Resolution result
        """
        try:
            strategy = self.default_strategies.get('user', ConflictResolutionStrategy.LATEST_WINS)
            
            if strategy == ConflictResolutionStrategy.LATEST_WINS:
                return self._resolve_user_conflict_latest_wins(conflict)
            elif strategy == ConflictResolutionStrategy.LMS_WINS:
                return self._resolve_user_conflict_lms_wins(conflict)
            elif strategy == ConflictResolutionStrategy.SHAREPOINT_WINS:
                return self._resolve_user_conflict_sharepoint_wins(conflict)
            elif strategy == ConflictResolutionStrategy.MERGE_FIELDS:
                return self._resolve_user_conflict_merge_fields(conflict)
            else:
                return {
                    'success': False,
                    'action': 'manual_review_required',
                    'conflict': conflict
                }
                
        except Exception as e:
            logger.error(f"Error resolving user conflict: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'conflict': conflict
            }
    
    def _resolve_enrollment_conflict(self, conflict: Dict) -> Dict:
        """Resolve enrollment conflict"""
        try:
            # For enrollments, LMS typically wins
            if conflict['type'] == 'enrollment':
                return self._resolve_enrollment_lms_wins(conflict)
            else:
                return {
                    'success': False,
                    'action': 'manual_review_required',
                    'conflict': conflict
                }
                
        except Exception as e:
            logger.error(f"Error resolving enrollment conflict: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'conflict': conflict
            }
    
    def _resolve_progress_conflict(self, conflict: Dict) -> Dict:
        """Resolve progress conflict"""
        try:
            # For progress, use latest wins strategy
            return self._resolve_progress_latest_wins(conflict)
                
        except Exception as e:
            logger.error(f"Error resolving progress conflict: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'conflict': conflict
            }
    
    def _resolve_user_conflict_latest_wins(self, conflict: Dict) -> Dict:
        """Resolve user conflict using latest timestamp wins"""
        try:
            lms_updated = conflict.get('lms_updated')
            sp_updated_str = conflict.get('sharepoint_updated')
            
            # Parse SharePoint timestamp
            sp_updated = None
            if sp_updated_str:
                try:
                    from dateutil import parser
                    sp_updated = parser.parse(sp_updated_str)
                except:
                    pass
            
            # Default to LMS if we can't compare timestamps
            if not sp_updated or not lms_updated:
                return self._resolve_user_conflict_lms_wins(conflict)
            
            # Compare timestamps
            if sp_updated > lms_updated:
                return self._resolve_user_conflict_sharepoint_wins(conflict)
            else:
                return self._resolve_user_conflict_lms_wins(conflict)
                
        except Exception as e:
            logger.error(f"Error in latest wins resolution: {str(e)}")
            return self._resolve_user_conflict_lms_wins(conflict)
    
    def _resolve_user_conflict_lms_wins(self, conflict: Dict) -> Dict:
        """Resolve user conflict by updating SharePoint with LMS data"""
        try:
            lms_user_id = conflict.get('lms_user_id')
            sharepoint_item_id = conflict.get('sharepoint_item_id')
            
            if not lms_user_id or not sharepoint_item_id:
                return {'success': False, 'error': 'Missing required IDs'}
            
            # Get LMS user
            lms_user = User.objects.get(id=lms_user_id)
            
            # Update SharePoint with LMS data
            from .sync_services import SharePointBidirectionalSync
            sync_service = SharePointBidirectionalSync(self.config)
            
            success = sync_service.sync_lms_user_to_sharepoint(lms_user)
            
            return {
                'success': success,
                'action': 'lms_wins',
                'updated': 'sharepoint',
                'conflict': conflict
            }
            
        except Exception as e:
            logger.error(f"Error in LMS wins resolution: {str(e)}")
            return {'success': False, 'error': str(e), 'conflict': conflict}
    
    def _resolve_user_conflict_sharepoint_wins(self, conflict: Dict) -> Dict:
        """Resolve user conflict by updating LMS with SharePoint data"""
        try:
            # This would require implementing SharePoint to LMS sync for users
            # For now, just log and mark as manual review
            logger.info(f"SharePoint wins resolution needed for user conflict: {conflict['email']}")
            
            return {
                'success': False,
                'action': 'manual_review_required',
                'reason': 'SharePoint to LMS user sync not implemented',
                'conflict': conflict
            }
            
        except Exception as e:
            logger.error(f"Error in SharePoint wins resolution: {str(e)}")
            return {'success': False, 'error': str(e), 'conflict': conflict}
    
    def _resolve_user_conflict_merge_fields(self, conflict: Dict) -> Dict:
        """Resolve user conflict by merging non-conflicting fields"""
        try:
            # Advanced field merging logic would go here
            # For now, fall back to latest wins
            return self._resolve_user_conflict_latest_wins(conflict)
            
        except Exception as e:
            logger.error(f"Error in merge fields resolution: {str(e)}")
            return {'success': False, 'error': str(e), 'conflict': conflict}
    
    def _resolve_enrollment_lms_wins(self, conflict: Dict) -> Dict:
        """Resolve enrollment conflict with LMS data"""
        try:
            # Update SharePoint enrollment with LMS status
            lms_enrollment_id = conflict.get('lms_enrollment_id')
            sharepoint_item_id = conflict.get('sharepoint_item_id')
            
            # Get LMS enrollment
            from courses.models import CourseEnrollment
            lms_enrollment = CourseEnrollment.objects.get(id=lms_enrollment_id)
            
            # Update SharePoint
            enrollment_data = {
                'Status': getattr(lms_enrollment, 'status', 'enrolled'),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.update_list_item(
                self.config.enrollment_list_name,
                sharepoint_item_id,
                enrollment_data
            )
            
            return {
                'success': result is not None,
                'action': 'lms_wins',
                'updated': 'sharepoint',
                'conflict': conflict
            }
            
        except Exception as e:
            logger.error(f"Error resolving enrollment conflict: {str(e)}")
            return {'success': False, 'error': str(e), 'conflict': conflict}
    
    def _resolve_progress_latest_wins(self, conflict: Dict) -> Dict:
        """Resolve progress conflict using latest timestamp"""
        try:
            # For progress, assume LMS is more recent and update SharePoint
            lms_progress_id = conflict.get('lms_progress_id')
            sharepoint_item_id = conflict.get('sharepoint_item_id')
            
            # Get LMS progress
            from courses.models import TopicProgress
            lms_progress = TopicProgress.objects.get(id=lms_progress_id)
            
            # Update SharePoint
            progress_data = {
                'ProgressPercent': getattr(lms_progress, 'progress_percentage', 0),
                'IsCompleted': getattr(lms_progress, 'is_completed', False),
                'UpdatedDate': timezone.now().isoformat()
            }
            
            result = self.api.update_list_item(
                self.config.progress_list_name,
                sharepoint_item_id,
                progress_data
            )
            
            return {
                'success': result is not None,
                'action': 'lms_wins',
                'updated': 'sharepoint',
                'conflict': conflict
            }
            
        except Exception as e:
            logger.error(f"Error resolving progress conflict: {str(e)}")
            return {'success': False, 'error': str(e), 'conflict': conflict}
    
    def _compare_user_data(self, lms_user, sharepoint_data: Dict) -> List[str]:
        """
        Compare LMS user data with SharePoint data to find conflicts
        
        Returns:
            List of field names that have conflicts
        """
        conflicts = []
        
        # Compare basic fields
        field_mappings = {
            'FirstName': 'first_name',
            'LastName': 'last_name',
            'Role': 'role',
            'IsActive': 'is_active',
            'Phone': 'phone_number'
        }
        
        for sp_field, lms_field in field_mappings.items():
            sp_value = sharepoint_data.get(sp_field)
            lms_value = getattr(lms_user, lms_field, None)
            
            # Handle type conversions
            if sp_field == 'IsActive':
                lms_value = bool(lms_value)
            elif sp_field == 'Phone':
                lms_value = lms_value or ''
                sp_value = sp_value or ''
            
            if sp_value is not None and str(sp_value) != str(lms_value):
                conflicts.append(sp_field)
        
        return conflicts
    
    def _extract_user_data(self, user) -> Dict:
        """Extract user data for comparison"""
        return {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role,
            'is_active': user.is_active,
            'phone_number': getattr(user, 'phone_number', ''),
            'date_joined': user.date_joined.isoformat()
        }
    
    def _update_results(self, results: Dict, resolution_result: Dict):
        """Update main results with resolution result"""
        results['total_conflicts'] += 1
        
        if resolution_result.get('success'):
            results['resolved'] += 1
        elif resolution_result.get('action') == 'manual_review_required':
            results['manual_review_required'] += 1
        else:
            results['failed'] += 1
        
        results['details'].append(resolution_result)
        
        if resolution_result.get('error'):
            results['errors'].append(resolution_result['error'])


def create_conflict_report(integration_id: int) -> Dict[str, Any]:
    """
    Create a detailed conflict report for an integration
    
    Args:
        integration_id: SharePoint integration ID
        
    Returns:
        Detailed conflict report
    """
    try:
        integration = SharePointIntegration.objects.get(id=integration_id)
        resolver = SharePointConflictResolver(integration)
        
        # Detect all conflicts without resolving them
        user_conflicts = resolver._detect_user_conflicts()
        enrollment_conflicts = resolver._detect_enrollment_conflicts()
        progress_conflicts = resolver._detect_progress_conflicts()
        
        all_conflicts = user_conflicts + enrollment_conflicts + progress_conflicts
        
        report = {
            'integration_id': integration_id,
            'integration_name': integration.name,
            'generated_at': timezone.now().isoformat(),
            'total_conflicts': len(all_conflicts),
            'user_conflicts': len(user_conflicts),
            'enrollment_conflicts': len(enrollment_conflicts),
            'progress_conflicts': len(progress_conflicts),
            'conflicts': all_conflicts
        }
        
        logger.info(f"Generated conflict report for {integration.name}: {report['total_conflicts']} conflicts found")
        return report
        
    except Exception as e:
        logger.error(f"Error creating conflict report: {str(e)}")
        return {'error': str(e)}