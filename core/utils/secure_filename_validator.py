"""
Comprehensive Secure Filename Validator for LMS
===============================================

This module provides a centralized, user-friendly filename validation system 
that balances Session with usability across the entire LMS platform.

Features:
- Session-focused validation to prevent attacks
- User-friendly error messages with clear guidance
- Support for international characters
- Consistent validation rules across all apps
- Clear instructions for users
"""

import os
import re
import unicodedata
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SecureFilenameValidator:
    """
    Comprehensive filename validator that provides Session while being user-friendly.
    """
    
    # Session patterns
    DANGEROUS_PATTERNS = [
        r'\.\.+',              # Path traversal attempts
        r'^\.+',               # Hidden files (starting with dots)
        r'[<>:"|?*]',         # Windows reserved characters
        r'[\x00-\x1f\x7f]',   # Control characters
        r'[\\/]',             # Path separators
    ]
    
    # Dangerous file extensions (executable files, scripts, etc.)
    DANGEROUS_EXTENSIONS = {
        '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.vbe',
        '.js', '.jse', '.wsf', '.wsh', '.msc', '.jar', '.php', '.asp', 
        '.aspx', '.jsp', '.py', '.rb', '.pl', '.sh', '.ps1', '.psm1'
    }
    
    # Allowed file extensions by category
    ALLOWED_EXTENSIONS = {
        'image': {'.jpg', '.jpeg', '.png'},
        'document': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.csv', '.ppt', '.pptx'},
        'video': {'.mp4', '.webm'},
        'audio': {'.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'},
        'archive': {'.zip', '.rar', '.7z', '.tar', '.gz'},
        'general': None  # No restrictions for general uploads
    }
    
    # Maximum filename lengths
    MAX_FILENAME_LENGTH = 200  # Conservative limit for cross-platform compatibility
    MAX_EXTENSION_LENGTH = 10
    
    # User-friendly validation messages
    VALIDATION_MESSAGES = {
        'too_long': _('Filename is too long. Please use a filename shorter than {max_length} characters.'),
        'empty': _('Filename cannot be empty.'),
        'dangerous_extension': _('File type "{ext}" is not allowed for Session reasons. Please use a different file format.'),
        'extension_not_allowed': _('File type "{ext}" is not allowed. Allowed formats: {allowed_formats}'),
        'dangerous_characters': _('Filename contains invalid characters. Please use only letters, numbers, spaces, hyphens (-), underscores (_), and dots (.).'),
        'hidden_file': _('Hidden files (starting with dots) are not allowed.'),
        'path_traversal': _('Filename contains path traversal patterns which are not allowed for Session reasons.'),
        'control_characters': _('Filename contains invalid control characters. Please use a simpler filename.'),
        'double_extension': _('Files with double extensions are not allowed for Session reasons.'),
        'reserved_name': _('This filename is reserved by the system. Please choose a different name.'),
    }
    
    # System reserved filenames (Windows/Unix)
    RESERVED_NAMES = {
        'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5', 
        'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 'lpt3', 'lpt4', 
        'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
    }
    
    def __init__(self, allowed_categories=None, max_size_mb=None, custom_extensions=None):
        """
        Initialize the validator with specific rules.
        
        Args:
            allowed_categories: List of allowed file categories (e.g., ['image', 'document'])
            max_size_mb: Maximum file size in MB
            custom_extensions: Custom set of allowed extensions (overrides categories)
        """
        self.allowed_categories = allowed_categories or ['general']
        self.max_size_mb = max_size_mb
        self.custom_extensions = custom_extensions
        
    def validate_filename(self, filename):
        """
        Validate a filename for Session and compliance.
        
        Args:
            filename: The filename to validate
            
        Returns:
            dict: Validation result with 'valid' boolean and 'errors' list
        """
        if not filename:
            return {
                'valid': False,
                'errors': [str(self.VALIDATION_MESSAGES['empty'])]
            }
        
        errors = []
        
        # Normalize filename to handle Unicode issues
        try:
            normalized_filename = unicodedata.normalize('NFKC', filename)
        except Exception:
            normalized_filename = filename
        
        # Extract base filename and extension
        base_name, extension = os.path.splitext(normalized_filename)
        extension = extension.lower()
        
        # Check filename length
        if len(normalized_filename) > self.MAX_FILENAME_LENGTH:
            errors.append(str(self.VALIDATION_MESSAGES['too_long']).format(
                max_length=self.MAX_FILENAME_LENGTH
            ))
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, normalized_filename):
                if pattern == r'\.\.+':
                    errors.append(str(self.VALIDATION_MESSAGES['path_traversal']))
                elif pattern == r'^\.+':
                    errors.append(str(self.VALIDATION_MESSAGES['hidden_file']))
                elif pattern == r'[\x00-\x1f\x7f]':
                    errors.append(str(self.VALIDATION_MESSAGES['control_characters']))
                else:
                    errors.append(str(self.VALIDATION_MESSAGES['dangerous_characters']))
                break
        
        # Check for dangerous extensions
        if extension in self.DANGEROUS_EXTENSIONS:
            errors.append(str(self.VALIDATION_MESSAGES['dangerous_extension']).format(ext=extension))
        
        # Check for double extensions (Session risk)
        parts = base_name.split('.')
        if len(parts) > 1:
            for part in parts[:-1]:  # Don't check the last part (it's the actual base name)
                if f'.{part.lower()}' in self.DANGEROUS_EXTENSIONS:
                    errors.append(str(self.VALIDATION_MESSAGES['double_extension']))
                    break
        
        # Check reserved names
        if base_name.lower() in self.RESERVED_NAMES:
            errors.append(str(self.VALIDATION_MESSAGES['reserved_name']))
        
        # Check allowed extensions
        if self.custom_extensions:
            allowed_exts = set(ext.lower() for ext in self.custom_extensions)
        else:
            allowed_exts = set()
            for category in self.allowed_categories:
                if category in self.ALLOWED_EXTENSIONS and self.ALLOWED_EXTENSIONS[category]:
                    allowed_exts.update(self.ALLOWED_EXTENSIONS[category])
        
        if allowed_exts and extension not in allowed_exts:
            formatted_exts = ', '.join(sorted(allowed_exts))
            errors.append(str(self.VALIDATION_MESSAGES['extension_not_allowed']).format(
                ext=extension, allowed_formats=formatted_exts
            ))
        
        # Check base filename characters (more permissive than before)
        # Allow: letters, numbers, spaces, hyphens, underscores, and some punctuation
        if not re.match(r'^[a-zA-Z0-9\s._\-()[\]{}]+$', base_name):
            errors.append(str(self.VALIDATION_MESSAGES['dangerous_characters']))
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'normalized_filename': normalized_filename
        }
    
    def validate_uploaded_file(self, uploaded_file):
        """
        Validate an uploaded Django file object.
        
        Args:
            uploaded_file: Django UploadedFile object
            
        Returns:
            dict: Validation result
        """
        filename_result = self.validate_filename(uploaded_file.name)
        
        # Add file size validation if specified
        if self.max_size_mb and hasattr(uploaded_file, 'size'):
            max_size_bytes = self.max_size_mb * 1024 * 1024
            if uploaded_file.size > max_size_bytes:
                filename_result['errors'].append(
                    f'File size ({uploaded_file.size / (1024*1024):.1f}MB) exceeds the maximum allowed size of {self.max_size_mb}MB.'
                )
                filename_result['valid'] = False
        
        return filename_result
    
    def get_help_text(self, categories=None):
        """
        Generate user-friendly help text for file uploads.
        
        Args:
            categories: List of file categories to show help for
            
        Returns:
            str: Help text for users
        """
        categories = categories or self.allowed_categories
        
        # Get allowed extensions
        allowed_exts = set()
        for category in categories:
            if category in self.ALLOWED_EXTENSIONS and self.ALLOWED_EXTENSIONS[category]:
                allowed_exts.update(self.ALLOWED_EXTENSIONS[category])
        
        if allowed_exts:
            ext_text = ', '.join(sorted(allowed_exts)).upper()
            help_parts = [f'Allowed formats: {ext_text}']
        else:
            help_parts = ['All file types allowed']
        
        if self.max_size_mb:
            help_parts.append(f'Maximum size: {self.max_size_mb}MB')
        
        help_parts.append('Use simple filenames with letters, numbers, spaces, hyphens, and underscores')
        
        return ' • '.join(help_parts)
    
    @classmethod
    def get_category_validator(cls, category, max_size_mb=None):
        """
        Get a pre-configured validator for a specific category.
        
        Args:
            category: File category ('image', 'document', 'video', etc.)
            max_size_mb: Maximum file size in MB
            
        Returns:
            SecureFilenameValidator: Configured validator instance
        """
        return cls(allowed_categories=[category], max_size_mb=max_size_mb)


# Convenience functions for common use cases
def validate_image_filename(filename, max_size_mb=10):
    """Validate image filenames."""
    validator = SecureFilenameValidator.get_category_validator('image', max_size_mb)
    return validator.validate_filename(filename)

def validate_document_filename(filename, max_size_mb=50):
    """Validate document filenames."""
    validator = SecureFilenameValidator.get_category_validator('document', max_size_mb)
    return validator.validate_filename(filename)

def validate_video_filename(filename, max_size_mb=500):
    """Validate video filenames."""
    validator = SecureFilenameValidator.get_category_validator('video', max_size_mb)
    return validator.validate_filename(filename)


def validate_general_filename(filename, max_size_mb=100):
    """Validate general file uploads."""
    validator = SecureFilenameValidator.get_category_validator('general', max_size_mb)
    return validator.validate_filename(filename)


# Django validator functions
def django_filename_validator(uploaded_file, categories=None, max_size_mb=None):
    """
    Django-compatible validator function for file uploads.
    
    Usage in forms:
        file_field = forms.FileField(validators=[
            lambda f: django_filename_validator(f, categories=['image'], max_size_mb=10)
        ])
    """
    validator = SecureFilenameValidator(allowed_categories=categories, max_size_mb=max_size_mb)
    result = validator.validate_uploaded_file(uploaded_file)
    
    if not result['valid']:
        # Join errors into a single message to prevent Django from duplicating them
        error_message = '. '.join(result['errors'])
        raise ValidationError(error_message)
    
    return True
