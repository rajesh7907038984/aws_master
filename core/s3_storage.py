"""
S3 Storage Configuration for LMS
Handles file storage using AWS S3
"""

import os
import logging
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


@deconstructible
class S3Storage(S3Boto3Storage):
    """
    Custom S3 storage for LMS
    """
    def __init__(self, *args, **kwargs):
        # Set default bucket name if not provided
        if 'bucket_name' not in kwargs:
            kwargs['bucket_name'] = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'lms-storage')
        
        # Set default location if not provided
        if 'location' not in kwargs:
            kwargs['location'] = getattr(settings, 'AWS_S3_LOCATION', 'media')
        
        super().__init__(*args, **kwargs)
    
    def url(self, name):
        """
        Get S3 URL for file with error handling and security validation
        """
        try:
            # Security: Validate filename to prevent path traversal
            if not name or '..' in name or name.startswith('/'):
                logger.error(f"Invalid filename for S3 URL: {name}")
                raise ValueError("Invalid filename")
            
            return super().url(name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 URL generation failed for {name}: {e}")
            # Return a fallback URL with security validation
            bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'unknown')
            region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
            # Sanitize filename for security
            safe_name = name.replace('..', '').replace('/', '_')
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{safe_name}"
        except Exception as e:
            logger.error(f"S3 URL generation error for {name}: {e}")
            # Return a fallback URL with security validation
            bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'unknown')
            region = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
            # Sanitize filename for security
            safe_name = name.replace('..', '').replace('/', '_')
            return f"https://{bucket_name}.s3.{region}.amazonaws.com/{safe_name}"
    
    def exists(self, name):
        """
        Check if file exists in S3 with error handling
        """
        try:
            return super().exists(name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                return False
            else:
                logger.error(f"S3 exists check failed for {name}: {e}")
                return False
        except Exception as e:
            logger.error(f"S3 exists check error for {name}: {e}")
            return False


class StaticS3Storage(S3Storage):
    """
    S3 storage for static files
    """
    def __init__(self, *args, **kwargs):
        kwargs['location'] = getattr(settings, 'AWS_S3_STATIC_LOCATION', 'static')
        super().__init__(*args, **kwargs)


class MediaS3Storage(S3Storage):
    """
    S3 storage for media files
    """
    def __init__(self, *args, **kwargs):
        kwargs['location'] = getattr(settings, 'AWS_S3_MEDIA_LOCATION', 'media')
        super().__init__(*args, **kwargs)


# Fallback storage classes for when S3 is not configured
class LocalStorage(Storage):
    """
    Local storage fallback (deprecated - S3 only)
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def _open(self, name, mode='rb'):
        from django.core.files.storage import default_storage
        return default_storage._open(name, mode)
    
    def _save(self, name, content):
        from django.core.files.storage import default_storage
        return default_storage._save(name, content)
    
    def delete(self, name):
        from django.core.files.storage import default_storage
        return default_storage.delete(name)
    
    def exists(self, name):
        from django.core.files.storage import default_storage
        return default_storage.exists(name)
    
    def listdir(self, path):
        from django.core.files.storage import default_storage
        return default_storage.listdir(path)
    
    def size(self, name):
        from django.core.files.storage import default_storage
        return default_storage.size(name)
    
    def url(self, name):
        from django.core.files.storage import default_storage
        return default_storage.url(name)
    
    def get_available_name(self, name, max_length=None):
        from django.core.files.storage import default_storage
        return default_storage.get_available_name(name, max_length)


# Default storage configuration
def get_default_storage():
    """
    Get the appropriate storage backend based on configuration
    """
    # Check if S3 is configured
    if (hasattr(settings, 'AWS_ACCESS_KEY_ID') and 
        hasattr(settings, 'AWS_SECRET_ACCESS_KEY') and
        hasattr(settings, 'AWS_STORAGE_BUCKET_NAME')):
        return S3Storage()
    else:
        return LocalStorage()


# S3 Path Validation Utilities
def validate_s3_path(path):
    """
    Validate S3 path for compatibility
    Returns: (is_valid: bool, error_message: str)
    """
    if not path:
        return False, "Path cannot be empty"
    
    # Check path length (S3 key limit is 1024 characters)
    if len(path) > 1024:
        return False, f"Path too long: {len(path)} characters (max 1024)"
    
    # Check for invalid characters
    invalid_chars = ['\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        if char in path:
            return False, f"Invalid character '{char}' in path"
    
    # Check for consecutive dots (not allowed in S3)
    if '..' in path:
        return False, "Consecutive dots not allowed in S3 paths"
    
    # Check for leading/trailing spaces
    if path != path.strip():
        return False, "Path cannot have leading or trailing spaces"
    
    return True, None

def sanitize_s3_path(path):
    """
    Sanitize path for S3 compatibility
    Returns: sanitized_path: str
    """
    if not path:
        return ""
    
    # Remove invalid characters
    invalid_chars = ['\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        path = path.replace(char, '_')
    
    # Replace consecutive dots
    while '..' in path:
        path = path.replace('..', '.')
    
    # Strip spaces
    path = path.strip()
    
    # Ensure path doesn't exceed length limit
    if len(path) > 1024:
        # Truncate while preserving extension
        name, ext = os.path.splitext(path)
        max_name_length = 1024 - len(ext)
        path = name[:max_name_length] + ext
    
    return path

    def save(self, name, content, max_length=None):
        """
        Save file to S3 with error handling
        """
        try:
            # Validate path before saving
            is_valid, error = validate_s3_path(name)
            if not is_valid:
                logger.warning(f"S3 path validation failed: {error}. Sanitizing path.")
                name = sanitize_s3_path(name)
            
            return super().save(name, content, max_length)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 save failed for {name}: {e}")
            raise
        except Exception as e:
            logger.error(f"S3 save error for {name}: {e}")
            raise
    
    def delete(self, name):
        """
        Delete file from S3 with error handling
        """
        try:
            return super().delete(name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f"File {name} already deleted or doesn't exist")
                return True
            else:
                logger.error(f"S3 delete failed for {name}: {e}")
                raise
        except Exception as e:
            logger.error(f"S3 delete error for {name}: {e}")
            raise

# Export the storage classes and utilities
__all__ = ['S3Storage', 'StaticS3Storage', 'MediaS3Storage', 'LocalStorage', 'get_default_storage', 'validate_s3_path', 'sanitize_s3_path']
