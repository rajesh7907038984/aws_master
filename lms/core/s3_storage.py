"""
Custom S3 Storage Classes for LMS
Handles proper media location prefixing for S3 storage
"""

from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class MediaS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for media files that properly handles AWS_MEDIA_LOCATION
    and fixes absolute path issues for SCORM uploads
    """
    
    def __init__(self, *args, **kwargs):
        # Set the location to include the media prefix
        kwargs['location'] = getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
        super().__init__(*args, **kwargs)
    
    @property
    def base_url(self):
        """Return the base URL for this storage"""
        return getattr(settings, 'MEDIA_URL', '')
    
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
