"""
Global File Upload Validation System for LMS
===========================================

This module provides centralized file validation functionality across all LMS applications.
It integrates with Django's existing Session utilities and provides consistent validation
rules for file uploads throughout the system.
"""

import os
import mimetypes
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _
# from LMS_Project.Session_utils import SessionUtils
import logging

logger = logging.getLogger(__name__)

class FileUploadValidator:
    """
    Centralized file upload validator that provides consistent validation
    rules across all LMS applications.
    """
    
    # Default file size limits (in bytes)
    DEFAULT_LIMITS = {
        'image': 10 * 1024 * 1024,      # 10MB for images
        'document': 600 * 1024 * 1024,   # 600MB for documents
        'video': 600 * 1024 * 1024,     # 600MB for videos
        'audio': 600 * 1024 * 1024,     # 600MB for audio
        'archive': 600 * 1024 * 1024,   # 600MB for archives
        'scorm': 600 * 1024 * 1024,     # 600MB for SCORM packages
        'general': 600 * 1024 * 1024    # 600MB for general files
    }
    
    # File type categories
    FILE_CATEGORIES = {
        'image': {
            'extensions': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'},
            'mime_types': {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/svg+xml'}
        },
        'document': {
            'extensions': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.csv', '.ppt', '.pptx'},
            'mime_types': {
                'application/pdf', 'application/msword', 
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'text/plain', 'application/rtf',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'text/csv',
                'application/vnd.ms-powerpoint',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            }
        },
        'video': {
            'extensions': {'.mp4', '.webm', '.ogg', '.avi', '.mov', '.wmv', '.flv', '.mkv'},
            'mime_types': {'video/mp4', 'video/webm', 'video/ogg', 'video/avi', 'video/quicktime'}
        },
        'audio': {
            'extensions': {'.mp3', '.wav', '.ogg', '.aac', '.m4a', '.wma', '.flac'},
            'mime_types': {'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/aac', 'audio/mp4'}
        },
        'archive': {
            'extensions': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'},
            'mime_types': {'application/zip', 'application/octet-stream', 'application/x-zip-compressed', 'application/x-rar-compressed', 'application/x-7z-compressed'}
        },
        'scorm': {
            'extensions': {'.zip'},
            'mime_types': {'application/zip', 'application/octet-stream', 'application/x-zip-compressed'}
        }
    }
    
    @classmethod
    def validate_file(cls, uploaded_file, allowed_categories=None, custom_max_size=None, 
                     allowed_extensions=None, required_extensions=None):
        """
        Comprehensive file validation with enhanced Session checks.
        
        Args:
            uploaded_file: The uploaded file object
            allowed_categories: List of allowed file categories (e.g., ['image', 'document'])
            custom_max_size: Custom maximum file size in bytes
            allowed_extensions: Custom list of allowed extensions (overrides categories)
            required_extensions: Specific extensions that are required (stricter than allowed)
        
        Returns:
            dict: Validation result with 'valid' boolean and 'message' string
            
        Raises:
            ValidationError: If validation fails and strict mode is enabled
        """
        
        if not uploaded_file:
            return {'valid': False, 'message': _('No file provided')}
        
        errors = []
        
        try:
            # Use existing SessionUtils for core Session validation
            # Session_errors = SessionUtils.validate_file_upload(uploaded_file)
            # if Session_errors:
            #     errors.extend(Session_errors)
            
            # Additional validation for file categories and sizes
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            file_size = uploaded_file.size
            
            # Determine allowed extensions and size limit
            if allowed_extensions:
                valid_extensions = set(ext.lower() for ext in allowed_extensions)
                max_size = custom_max_size or cls.DEFAULT_LIMITS['general']
            elif allowed_categories:
                valid_extensions = set()
                max_size = 0
                
                for category in allowed_categories:
                    if category in cls.FILE_CATEGORIES:
                        valid_extensions.update(cls.FILE_CATEGORIES[category]['extensions'])
                        category_limit = custom_max_size or cls.DEFAULT_LIMITS.get(category, cls.DEFAULT_LIMITS['general'])
                        max_size = max(max_size, category_limit)
            else:
                # Default to general validation
                valid_extensions = set()
                for category_data in cls.FILE_CATEGORIES.values():
                    valid_extensions.update(category_data['extensions'])
                max_size = custom_max_size or cls.DEFAULT_LIMITS['general']
            
            # Required extensions check (stricter)
            if required_extensions:
                required_exts = set(ext.lower() for ext in required_extensions)
                if file_extension not in required_exts:
                    errors.append(_('File must have one of these extensions: {}').format(', '.join(required_extensions)))
            elif valid_extensions and file_extension not in valid_extensions:
                errors.append(_('File extension {} is not allowed').format(file_extension))
            
            # File size validation
            if file_size > max_size:
                max_size_mb = max_size / (1024 * 1024)
                file_size_mb = file_size / (1024 * 1024)
                errors.append(_('File size ({:.2f}MB) exceeds maximum allowed size ({:.2f}MB)').format(
                    file_size_mb, max_size_mb))
            
            # Additional category-specific validation
            if allowed_categories:
                cls._validate_category_specific(uploaded_file, allowed_categories, errors)
            
            # Log validation results
            if errors:
                error_messages = [str(error) for error in errors]
                logger.warning(f"File validation failed for {uploaded_file.name}: {', '.join(error_messages)}")
            else:
                logger.info(f"File validation passed for {uploaded_file.name} ({file_size / (1024*1024):.2f}MB)")
            
            return {
                'valid': len(errors) == 0,
                'message': '; '.join(str(error) for error in errors) if errors else _('File validation passed'),
                'file_size_mb': file_size / (1024 * 1024),
                'max_size_mb': max_size / (1024 * 1024)
            }
            
        except Exception as e:
            error_msg = _('File validation error: {}').format(str(e))
            logger.error(f"File validation exception for {uploaded_file.name}: {str(e)}")
            return {'valid': False, 'message': error_msg}
    
    @classmethod
    def _validate_category_specific(cls, uploaded_file, allowed_categories, errors):
        """Perform category-specific validation checks."""
        
        # Get file extension for conditional validation
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        
        # SCORM-specific validation
        if 'scorm' in allowed_categories and file_extension == '.zip':
            try:
                import zipfile
                uploaded_file.seek(0)
                with zipfile.ZipFile(uploaded_file, 'r') as zip_file:
                    # Check for SCORM manifest
                    file_list = zip_file.namelist()
                    has_manifest = any('imsmanifest.xml' in f.lower() for f in file_list)
                    if not has_manifest:
                        errors.append(_('ZIP file does not contain a valid SCORM manifest (imsmanifest.xml)'))
            except zipfile.BadZipFile:
                errors.append(_('File is not a valid ZIP archive'))
            except Exception as e:
                logger.warning(f"SCORM validation warning: {str(e)}")
            finally:
                uploaded_file.seek(0)
        
        # Image-specific validation - only validate as image if file has image extension
        if 'image' in allowed_categories and file_extension in cls.FILE_CATEGORIES['image']['extensions']:
            try:
                from PIL import Image
                uploaded_file.seek(0)
                with Image.open(uploaded_file) as img:
                    # Check image dimensions if needed
                    if img.size[0] > 10000 or img.size[1] > 10000:
                        errors.append(_('Image dimensions too large (max 10000x10000 pixels)'))
            except Exception as e:
                errors.append(_('Invalid image file: {}').format(str(e)))
            finally:
                uploaded_file.seek(0)
    
    @classmethod
    def get_size_limit_for_categories(cls, categories):
        """Get the maximum size limit for given categories."""
        max_size = 0
        for category in categories:
            category_limit = cls.DEFAULT_LIMITS.get(category, cls.DEFAULT_LIMITS['general'])
            max_size = max(max_size, category_limit)
        return max_size
    
    @classmethod
    def get_allowed_extensions_for_categories(cls, categories):
        """Get all allowed extensions for given categories."""
        extensions = set()
        for category in categories:
            if category in cls.FILE_CATEGORIES:
                extensions.update(cls.FILE_CATEGORIES[category]['extensions'])
        return extensions
    
    @classmethod
    def format_size_limit(cls, size_bytes):
        """Format file size limit in human-readable format."""
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"
        elif size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.0f}MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f}KB"
        else:
            return f"{size_bytes}B"


def validate_file_upload(uploaded_file, allowed_categories=None, custom_max_size=None):
    """
    Convenience function for file validation that can be used as a Django validator.
    
    Usage in models:
        file = models.FileField(validators=[
            lambda f: validate_file_upload(f, allowed_categories=['image', 'document'])
        ])
    """
    result = FileUploadValidator.validate_file(
        uploaded_file, 
        allowed_categories=allowed_categories, 
        custom_max_size=custom_max_size
    )
    
    if not result['valid']:
        raise ValidationError(str(result['message']))
    
    return True


# Common validator functions for different file types
def validate_image_upload(uploaded_file):
    """Validate image file uploads."""
    return validate_file_upload(uploaded_file, allowed_categories=['image'])

def validate_document_upload(uploaded_file):
    """Validate document file uploads."""
    return validate_file_upload(uploaded_file, allowed_categories=['document'])

def validate_media_upload(uploaded_file):
    """Validate media (video/audio) file uploads."""
    return validate_file_upload(uploaded_file, allowed_categories=['video', 'audio'])

def validate_scorm_upload(uploaded_file):
    """Validate SCORM package uploads."""
    return validate_file_upload(uploaded_file, allowed_categories=['scorm'])

def validate_general_upload(uploaded_file):
    """Validate general file uploads with all allowed types."""
    return validate_file_upload(uploaded_file, allowed_categories=['image', 'document', 'video', 'audio', 'archive', 'scorm'])
