"""
Custom S3 Storage Classes for LMS
Only overrides what's absolutely necessary to avoid HeadObject 403 errors
"""

from storages.backends.s3boto3 import S3Boto3Storage


class MediaS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for media files that doesn't require HeadObject permission
    Enhanced for video streaming with proper URL generation
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
    
    def url(self, name):
        """
        Enhanced URL generation for video streaming
        Ensures proper URL format for video files
        """
        try:
            # Get the base URL from parent class
            url = super().url(name)
            
            # For video files, ensure proper URL format
            if name and any(name.lower().endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.avi', '.mov', '.m4v']):
                # Ensure HTTPS for video streaming
                if url.startswith('http://'):
                    url = url.replace('http://', 'https://', 1)
                
                # DON'T add response-content-type parameter as it:
                # 1. Conflicts with presigned URLs
                # 2. Forces incorrect content type for non-MP4 videos
                # 3. The browser determines the type from the <source type="..."> attribute
            
            return url
            
        except Exception as e:
            # Log the error but don't raise it to avoid breaking the application
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error generating URL for {name}: {str(e)}")
            
            # Return a fallback URL
            from django.conf import settings
            bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '')
            region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
            location = self.location
            
            if bucket_name:
                return f"https://{bucket_name}.s3.{region}.amazonaws.com/{location}/{name}"
            else:
                raise e

class StaticS3Storage(S3Boto3Storage):
    """
    Custom S3 storage for static files
    """
    
    def __init__(self, *args, **kwargs):
        # Static files don't need the media prefix
        kwargs['location'] = 'static'
        super().__init__(*args, **kwargs)
