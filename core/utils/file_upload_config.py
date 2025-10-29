"""
System-wide File Upload Configuration for LMS
===========================================

This module provides centralized configuration for file uploads across
all LMS applications. It defines Session policies, size limits, and
validation rules in one place.
"""

from django.conf import settings

class FileUploadConfig:
    """
    Centralized configuration for file uploads across the LMS system.
    """
    
    # Default size limits (in MB)
    DEFAULT_LIMITS = {
        'image': 10,
        'video': 600, 
        'document': 600,
        'audio': 600,
        'archive': 600,
        'general': 600
    }
    
    # Application-specific overrides
    APP_SPECIFIC_LIMITS = {
        'courses': {
            'image': 10,
            'video': 500
        },
        'assignments': {
            'document': 100,
            'image': 25,
            'video': 200
        },
        'conferences': {
            'document': 50,
            'image': 10,
            'video': 100
        },
        'users': {
            'image': 5  # Profile pictures
        }
    }
    
    # Session settings
    Session_CONFIG = {
        'enable_mime_type_validation': True,
        'enable_file_signature_validation': True,
        'quarantine_suspicious_files': True,
        'log_upload_attempts': True,
        'max_filename_length': 200,
        'allow_unicode_filenames': True,
        'normalize_unicode': True
    }
    
    # User experience settings
    UX_CONFIG = {
        'show_detailed_errors': True,
        'show_help_text': True,
        'show_file_examples': True,
        'enable_drag_drop': True,
        'show_progress_bar': True,
        'auto_resize_images': False,  # Could be enabled for optimization
        'generate_thumbnails': True
    }
    
    @classmethod
    def get_size_limit(cls, category, app_name=None):
        """
        Get the size limit for a specific category and app.
        
        Args:
            category: File category ('image', 'video', etc.)
            app_name: Django app name ('courses', 'assignments', etc.)
            
        Returns:
            int: Size limit in MB
        """
        if app_name and app_name in cls.APP_SPECIFIC_LIMITS:
            app_limits = cls.APP_SPECIFIC_LIMITS[app_name]
            if category in app_limits:
                return app_limits[category]
        
        return cls.DEFAULT_LIMITS.get(category, cls.DEFAULT_LIMITS['general'])
    
    @classmethod
    def get_validator_config(cls, category, app_name=None):
        """
        Get complete validator configuration for a category and app.
        
        Returns:
            dict: Configuration dictionary for SecureFilenameValidator
        """
        return {
            'allowed_categories': [category],
            'max_size_mb': cls.get_size_limit(category, app_name),
            'Session_config': cls.Session_CONFIG,
            'ux_config': cls.UX_CONFIG
        }
    
    @classmethod
    def get_help_text_config(cls, category):
        """
        Get configuration for help text display.
        
        Returns:
            dict: Help text configuration
        """
        return {
            'category': category,
            'show_examples': cls.UX_CONFIG['show_file_examples'],
            'show_help_text': cls.UX_CONFIG['show_help_text']
        }


# Django settings integration
def get_file_upload_setting(key, default=None):
    """
    Get file upload setting from Django settings with fallback.
    """
    return getattr(settings, f'FILE_UPLOAD_{key.upper()}', default)


# Common validator instances for different use cases
class CommonValidators:
    """
    Pre-configured validator instances for common use cases.
    """
    
    @staticmethod
    def get_course_image_validator():
        """Validator for course images."""
        from .secure_filename_validator import SecureFilenameValidator
        config = FileUploadConfig.get_validator_config('image', 'courses')
        return SecureFilenameValidator(**config)
    
    @staticmethod  
    def get_course_video_validator():
        """Validator for course videos."""
        from .secure_filename_validator import SecureFilenameValidator
        config = FileUploadConfig.get_validator_config('video', 'courses')
        return SecureFilenameValidator(**config)
    
    @staticmethod
    def get_assignment_validator():
        """Validator for assignment submissions."""
        from .secure_filename_validator import SecureFilenameValidator
        config = FileUploadConfig.get_validator_config('document', 'assignments')
        return SecureFilenameValidator(**config)
    
    @staticmethod
    def get_profile_image_validator():
        """Validator for user profile images."""
        from .secure_filename_validator import SecureFilenameValidator
        config = FileUploadConfig.get_validator_config('image', 'users')
        return SecureFilenameValidator(**config)
    
