"""
SharePoint Sync Configuration Manager

This module provides advanced configuration options for field-level control
and sync rules for SharePoint integration.
"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from django.db import models
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class SyncConfiguration:
    """Configuration for SharePoint sync operations"""
    
    def __init__(self, integration_config):
        self.integration = integration_config
        self.cache_key = f"sync_config_{integration_config.id}"
        
    def get_field_mapping(self, model_type: str) -> Dict[str, str]:
        """
        Get field mapping configuration for a model type
        
        Args:
            model_type: Type of model ('user', 'course', 'enrollment', etc.)
            
        Returns:
            Dictionary mapping LMS fields to SharePoint fields
        """
        mappings = {
            'user': {
                'id': 'LMSUserID',
                'username': 'Username',
                'email': 'Email',
                'first_name': 'FirstName',
                'last_name': 'LastName',
                'role': 'Role',
                'branch__name': 'Branch',
                'date_of_birth': 'DateOfBirth',
                'sex': 'Gender',
                'phone_number': 'Phone',
                'study_area': 'StudyArea',
                'job_role': 'JobRole',
                'industry': 'Industry',
                'last_login': 'LastLogin',
                'is_active': 'IsActive',
                'date_joined': 'CreatedDate'
            },
            'course': {
                'id': 'LMSCourseID',
                'title': 'CourseTitle',
                'description': 'CourseDescription',
                'branch__name': 'Branch',
                'language': 'Language',
                'status': 'Status',
                'is_visible': 'IsVisible',
                'created_at': 'CreatedDate'
            },
            'enrollment': {
                'id': 'LMSEnrollmentID',
                'user__email': 'UserEmail',
                'user__id': 'UserID',
                'course__id': 'CourseID',
                'course__title': 'CourseTitle',
                'course__branch__name': 'CourseBranch',
                'enrollment_date': 'EnrollmentDate',
                'status': 'Status',
                'progress_percentage': 'ProgressPercentage'
            },
            'progress': {
                'id': 'LMSProgressID',
                'user__email': 'UserEmail',
                'user__id': 'UserID',
                'topic__course__id': 'CourseID',
                'topic__id': 'TopicID',
                'topic__title': 'TopicName',
                'progress_percentage': 'ProgressPercent',
                'completed_at': 'CompletionDate',
                'time_spent': 'TimeSpent',
                'score': 'Score',
                'is_completed': 'IsCompleted'
            },
            'grade': {
                'id': 'LMSAssessmentID',
                'student__email': 'UserEmail',
                'student__id': 'UserID',
                'assignment__course__id': 'CourseID',
                'assignment__id': 'AssignmentID',
                'assignment__title': 'AssignmentTitle',
                'score': 'Score',
                'grade': 'Grade',
                'feedback': 'Feedback',
                'updated_at': 'GradedDate'
            },
            'certificate': {
                'id': 'LMSCertificateID',
                'user__get_full_name': 'StudentName',
                'user__email': 'StudentEmail',
                'user__id': 'StudentID',
                'course__id': 'CourseID',
                'course__title': 'CourseName',
                'user__branch__name': 'Branch',
                'certificate_number': 'CertificateNumber',
                'issued_at': 'IssueDate',
                'status': 'Status'
            }
        }
        
        return mappings.get(model_type, {})
    
    def get_sync_rules(self, model_type: str) -> Dict[str, Any]:
        """
        Get sync rules for a model type
        
        Args:
            model_type: Type of model
            
        Returns:
            Dictionary containing sync rules
        """
        rules = {
            'user': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': False,  # Mark inactive instead
                'required_fields': ['email', 'first_name', 'last_name'],
                'excluded_fields': ['password', 'last_login'],
                'conflict_resolution': 'latest_wins',
                'batch_size': 50,
                'sync_frequency': 'immediate',
                'validation_rules': {
                    'email': {'required': True, 'format': 'email'},
                    'role': {'required': True, 'choices': ['globaladmin', 'superadmin', 'admin', 'instructor', 'learner']}
                }
            },
            'course': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': False,
                'required_fields': ['title', 'branch'],
                'excluded_fields': ['password_protected'],
                'conflict_resolution': 'lms_wins',
                'batch_size': 25,
                'sync_frequency': 'immediate'
            },
            'enrollment': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': True,
                'required_fields': ['user', 'course'],
                'conflict_resolution': 'lms_wins',
                'batch_size': 100,
                'sync_frequency': 'immediate'
            },
            'progress': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': False,
                'required_fields': ['user', 'topic'],
                'conflict_resolution': 'latest_wins',
                'batch_size': 200,
                'sync_frequency': 'batched',  # Batch progress updates
                'batch_interval': 300  # 5 minutes
            },
            'grade': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': False,
                'required_fields': ['student', 'assignment', 'score'],
                'conflict_resolution': 'lms_wins',
                'batch_size': 100,
                'sync_frequency': 'immediate'
            },
            'certificate': {
                'sync_on_create': True,
                'sync_on_update': True,
                'sync_on_delete': False,
                'required_fields': ['user', 'course'],
                'conflict_resolution': 'lms_wins',
                'batch_size': 25,
                'sync_frequency': 'immediate',
                'upload_files': True
            }
        }
        
        return rules.get(model_type, {})
    
    def should_sync_field(self, model_type: str, field_name: str) -> bool:
        """
        Check if a specific field should be synced
        
        Args:
            model_type: Type of model
            field_name: Name of the field
            
        Returns:
            Boolean indicating if field should be synced
        """
        rules = self.get_sync_rules(model_type)
        excluded_fields = rules.get('excluded_fields', [])
        
        return field_name not in excluded_fields
    
    def should_sync_operation(self, model_type: str, operation: str) -> bool:
        """
        Check if a specific operation should trigger sync
        
        Args:
            model_type: Type of model
            operation: Type of operation ('create', 'update', 'delete')
            
        Returns:
            Boolean indicating if operation should trigger sync
        """
        rules = self.get_sync_rules(model_type)
        return rules.get(f'sync_on_{operation}', False)
    
    def get_batch_size(self, model_type: str) -> int:
        """Get batch size for model type"""
        rules = self.get_sync_rules(model_type)
        return rules.get('batch_size', 50)
    
    def get_conflict_resolution_strategy(self, model_type: str) -> str:
        """Get conflict resolution strategy for model type"""
        rules = self.get_sync_rules(model_type)
        return rules.get('conflict_resolution', 'latest_wins')
    
    def validate_data(self, model_type: str, data: Dict) -> tuple[bool, List[str]]:
        """
        Validate data before sync
        
        Args:
            model_type: Type of model
            data: Data to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        rules = self.get_sync_rules(model_type)
        validation_rules = rules.get('validation_rules', {})
        required_fields = rules.get('required_fields', [])
        errors = []
        
        # Check required fields
        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"Required field '{field}' is missing or empty")
        
        # Check validation rules
        for field, field_rules in validation_rules.items():
            if field in data:
                value = data[field]
                
                if field_rules.get('required') and not value:
                    errors.append(f"Field '{field}' is required")
                
                if field_rules.get('format') == 'email' and value:
                    import re
                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                    if not re.match(email_pattern, value):
                        errors.append(f"Field '{field}' must be a valid email address")
                
                choices = field_rules.get('choices')
                if choices and value not in choices:
                    errors.append(f"Field '{field}' must be one of: {', '.join(choices)}")
        
        return len(errors) == 0, errors
    
    def get_sharepoint_list_name(self, model_type: str) -> str:
        """Get SharePoint list name for model type"""
        list_names = {
            'user': self.integration.user_list_name,
            'course': 'LMS Course Groups',
            'enrollment': self.integration.enrollment_list_name,
            'progress': self.integration.progress_list_name,
            'grade': 'LMS Assessment Results',
            'certificate': 'LMS Certificate Registry',
            'group': 'LMS User Groups'
        }
        
        return list_names.get(model_type, f'LMS {model_type.title()} Data')
    
    def transform_data_for_sharepoint(self, model_type: str, instance, data: Dict = None) -> Dict:
        """
        Transform LMS model instance data for SharePoint
        
        Args:
            model_type: Type of model
            instance: Model instance
            data: Optional pre-processed data
            
        Returns:
            Transformed data dictionary for SharePoint
        """
        if data is None:
            data = self._extract_model_data(instance)
        
        field_mapping = self.get_field_mapping(model_type)
        transformed_data = {}
        
        for lms_field, sharepoint_field in field_mapping.items():
            if self.should_sync_field(model_type, lms_field):
                value = self._get_field_value(instance, lms_field)
                if value is not None:
                    transformed_data[sharepoint_field] = self._format_value_for_sharepoint(value)
        
        # Add update timestamp
        transformed_data['UpdatedDate'] = timezone.now().isoformat()
        
        return transformed_data
    
    def _extract_model_data(self, instance) -> Dict:
        """Extract data from model instance"""
        data = {}
        
        # Get all field values
        for field in instance._meta.fields:
            try:
                value = getattr(instance, field.name)
                data[field.name] = value
            except:
                pass
        
        return data
    
    def _get_field_value(self, instance, field_path: str):
        """Get field value using dot notation (e.g., 'user__email')"""
        try:
            value = instance
            for field_name in field_path.split('__'):
                if hasattr(value, field_name):
                    value = getattr(value, field_name)
                    if callable(value):
                        value = value()
                else:
                    return None
            return value
        except:
            return None
    
    def _format_value_for_sharepoint(self, value):
        """Format value for SharePoint compatibility"""
        if value is None:
            return ''
        elif isinstance(value, bool):
            return value
        elif hasattr(value, 'isoformat'):  # datetime objects
            return value.isoformat()
        elif hasattr(value, '__str__'):
            return str(value)
        else:
            return value


class SyncConfigurationManager:
    """Manager for sync configurations"""
    
    @staticmethod
    def get_configuration(integration_id: int) -> SyncConfiguration:
        """Get sync configuration for an integration"""
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        return SyncConfiguration(integration)
    
    @staticmethod
    def validate_sync_request(integration_id: int, model_type: str, operation: str, data: Dict = None) -> tuple[bool, List[str]]:
        """
        Validate a sync request
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            config = SyncConfigurationManager.get_configuration(integration_id)
            
            errors = []
            
            # Check if operation should be synced
            if not config.should_sync_operation(model_type, operation):
                errors.append(f"Sync not enabled for {operation} operations on {model_type}")
            
            # Validate data if provided
            if data:
                is_valid, data_errors = config.validate_data(model_type, data)
                if not is_valid:
                    errors.extend(data_errors)
            
            return len(errors) == 0, errors
            
        except Exception as e:
            logger.error(f"Error validating sync request: {str(e)}")
            return False, [str(e)]
    
    @staticmethod
    def get_sync_schedule() -> Dict[str, Any]:
        """
        Get the recommended sync schedule based on configurations
        
        Returns:
            Dictionary with sync schedule recommendations
        """
        return {
            'immediate_sync': ['user', 'enrollment', 'grade', 'certificate'],
            'batched_sync': ['progress'],
            'batch_intervals': {
                'progress': 300,  # 5 minutes
                'reports': 3600,  # 1 hour
                'analytics': 86400  # 24 hours
            },
            'monitoring_interval': 900,  # 15 minutes
            'health_check_interval': 21600,  # 6 hours
            'conflict_resolution_interval': 86400  # 24 hours
        }


# Configuration presets for different use cases
SYNC_PRESETS = {
    'real_time': {
        'description': 'Real-time sync for all operations',
        'settings': {
            'sync_frequency': 'immediate',
            'batch_size': 1,
            'monitoring_interval': 60,
            'conflict_resolution': 'latest_wins'
        }
    },
    'performance_optimized': {
        'description': 'Optimized for performance with batching',
        'settings': {
            'sync_frequency': 'batched',
            'batch_size': 100,
            'monitoring_interval': 900,
            'conflict_resolution': 'lms_wins'
        }
    },
    'minimal_sync': {
        'description': 'Minimal sync for basic operations only',
        'settings': {
            'sync_on_create': True,
            'sync_on_update': False,
            'sync_on_delete': False,
            'sync_frequency': 'scheduled',
            'batch_size': 200
        }
    },
    'comprehensive': {
        'description': 'Full bidirectional sync with conflict resolution',
        'settings': {
            'sync_frequency': 'immediate',
            'batch_size': 50,
            'monitoring_interval': 300,
            'conflict_resolution': 'latest_wins',
            'enable_bidirectional': True
        }
    }
}