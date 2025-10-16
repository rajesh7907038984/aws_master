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
        Uses HeadObject for accurate existence checking
        """
        try:
            # Use HeadObject for accurate file existence checking
            self.bucket.meta.client.head_object(
                Bucket=self.bucket.name,
                Key=name
            )
            return True
        except Exception as e:
            # If HeadObject fails, try ListObjectsV2 as fallback
            try:
                response = self.bucket.meta.client.list_objects_v2(
                    Bucket=self.bucket.name,
                    Prefix=name,
                    MaxKeys=1
                )
                return 'Contents' in response and len(response['Contents']) > 0
            except Exception:
                # If both methods fail, assume file doesn't exist
                return False
    
    def get_available_name(self, name, max_length=None):
        """
        Override to return the name as-is without checking existence
        Since we use UUIDs and file_overwrite=False, names are always unique
        """
        # Don't check for file_overwrite, just return the name
        # This avoids extra S3 calls
        return name
    
    def save(self, name, content, max_length=None):
        """
        Save file to S3 and return the full path including location prefix
        """
        # Call parent save method
        saved_name = super().save(name, content, max_length)
        # Return the full path including location prefix
        return saved_name
    
    def _normalize_name(self, name):
        """
        Normalize the name to include the location prefix
        """
        # If the name doesn't start with the location, add it
        if not name.startswith(self.location):
            return f"{self.location}/{name}"
        return name

class StaticS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for static files
    """
    
    def __init__(self, *args, **kwargs):
        # Static files don't need the media prefix
        kwargs['location'] = 'static'
        super().__init__(*args, **kwargs)
