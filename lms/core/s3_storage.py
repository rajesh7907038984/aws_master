"""
S3 Storage Configuration for LMS
Handles file storage using AWS S3 with fallback to local storage
"""

import os
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from storages.backends.s3boto3 import S3Boto3Storage


@deconstructible
class S3Storage(S3Boto3Storage):
    """
    Custom S3 storage with fallback to local storage
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
        Override url method to handle missing files gracefully
        """
        try:
            return super().url(name)
        except Exception:
            # Fallback to local storage URL if S3 fails
            if hasattr(settings, 'MEDIA_URL'):
                return f"{settings.MEDIA_URL}{name}"
            return f"/media/{name}"
    
    def exists(self, name):
        """
        Check if file exists with fallback
        """
        try:
            return super().exists(name)
        except Exception:
            # Fallback to local file system check
            local_path = os.path.join(settings.MEDIA_ROOT, name)
            return os.path.exists(local_path)


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
    Local storage fallback
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


# Export the storage classes
__all__ = ['S3Storage', 'StaticS3Storage', 'MediaS3Storage', 'LocalStorage', 'get_default_storage']
