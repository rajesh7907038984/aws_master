"""
Custom S3 Storage Classes for LMS
Only overrides what's absolutely necessary to avoid HeadObject 403 errors
"""

from storages.backends.s3boto3 import S3Boto3Storage


class MediaS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for media files that doesn't require HeadObject permission
    Lets django-storages handle all signature generation and AWS configuration
    """
    
    @property
    def location(self):
        """
        Return location from settings - this is needed for existing files to work
        """
        from django.conf import settings
        return getattr(settings, 'AWS_MEDIA_LOCATION', 'media')
    
    def exists(self, name):
        """
        Override exists() to skip HeadObject permission check
        Always return False to skip the existence check
        This is safe because we use file_overwrite=False and unique filenames (UUIDs)
        
        Why: HeadObject requires s3:HeadObject permission which many IAM policies don't grant.
        By returning False, we skip the check and let S3 handle duplicates (won't happen with UUIDs).
        """
        return False
    
    def get_available_name(self, name, max_length=None):
        """
        Override to return the name as-is without checking existence
        Since we use UUIDs and file_overwrite=False, names are always unique
        """
        # Don't check for file_overwrite, just return the name
        # This avoids extra S3 calls
        return name

class StaticS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for static files
    """
    
    def __init__(self, *args, **kwargs):
        # Static files don't need the media prefix
        kwargs['location'] = 'static'
        super().__init__(*args, **kwargs)
