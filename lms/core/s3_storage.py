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
        Check if file exists in S3 storage
        Uses ListObjectsV2 to avoid HeadObject permission issues
        """
        try:
            # Use ListObjectsV2 instead of HeadObject to avoid permission issues
            response = self.bucket.meta.client.list_objects_v2(
                Bucket=self.bucket.name,
                Prefix=name,
                MaxKeys=1
            )
            return 'Contents' in response and len(response['Contents']) > 0
        except Exception:
            # If we can't check, assume it exists to avoid breaking existing functionality
            return True
    
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
