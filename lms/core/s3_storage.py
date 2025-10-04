"""
Custom S3 Storage Classes for LMS
Handles proper media location prefixing for S3 storage
"""

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.client import Config
import boto3


class MediaS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for media files that properly handles AWS_MEDIA_LOCATION
    and fixes absolute path issues for SCORM uploads
    """
    
    # Force configuration for all S3 operations
    def __init__(self, *args, **kwargs):
        # django-storages reads configuration from Django settings, not from kwargs
        # We only set the location here
        super().__init__(*args, **kwargs)
    
    @property
    def location(self):
        """Override location to use media prefix"""
        return getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
    
    def _get_connection(self):
        """Override connection method to ensure proper configuration"""
        if not hasattr(self, '_connection') or self._connection is None:
            self._connection = boto3.client(
                's3',
                aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
                region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
            )
        return self._connection
    
    @property
    def base_url(self):
        """Return the base URL for this storage"""
        return getattr(settings, 'MEDIA_URL', '')
    
    def exists(self, name):
        """
        Override exists() to skip HeadObject check for SCORM content
        Always return False to avoid 403 Forbidden errors on HeadObject
        This is safe because we use unique filenames (UUIDs)
        """
        # Skip existence check for SCORM content to avoid HeadObject 403 errors
        if name and ('scorm_content/' in name or 'topics/' in name):
            return False
        # For other files, use the parent's exists method
        try:
            return super().exists(name)
        except Exception:
            # If HeadObject fails, assume file doesn't exist
            return False
    
    def save(self, name, content, max_length=None):
        """
        Override save method to handle absolute paths from SCORM uploads
        """
        # Convert absolute paths to relative paths
        if name and name.startswith('/'):
            name = name.lstrip('/')
        return super().save(name, content, max_length)
    
    def url(self, name):
        """
        Override url method to ensure proper URL generation
        """
        # Handle absolute paths that might come from legacy code
        if name and name.startswith('/'):
            name = name.lstrip('/')
        url = super().url(name)
        return url

    def path(self, name):
        """
        Override path method to handle S3 storage that doesn't support absolute paths
        """
        # S3 storage doesn't support absolute paths, raise NotImplementedError
        raise NotImplementedError("This backend doesn't support absolute paths.")

    def rsplit(self, sep, maxsplit=-1):
        """
        Split string from the right at the specified separator
        This method is added for compatibility with legacy code
        """
        if hasattr(self, 'name') and self.name:
            return self.name.rsplit(sep, maxsplit)
        return ''.rsplit(sep, maxsplit)

class StaticS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for static files
    """
    
    def __init__(self, *args, **kwargs):
        # Static files don't need the media prefix
        kwargs['location'] = 'static'
        super().__init__(*args, **kwargs)
