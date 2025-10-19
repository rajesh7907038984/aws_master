"""
Custom storage for SCORM packages - uses S3 storage for SCORM packages
while maintaining compatibility with existing SCORM extraction logic
"""
import os
from django.core.files.storage import Storage
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class SCORMS3Storage(S3Boto3Storage):
    """
    Custom S3 storage class for SCORM packages
    This allows SCORM packages to be stored in S3 while maintaining
    compatibility with the existing SCORM extraction logic
    """
    
    def __init__(self, location=None, base_url=None, **kwargs):
        # Use a dedicated S3 path for SCORM packages
        if location is None:
            location = 'elearning'
        
        if base_url is None:
            # Use SCORM-specific media URL if available, otherwise construct it
            base_url = getattr(settings, 'SCORM_MEDIA_URL', None)
            if not base_url:
                base_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/elearning/"
        
        # Set S3-specific options
        kwargs.update({
            'bucket_name': settings.AWS_STORAGE_BUCKET_NAME,
            'region_name': settings.AWS_S3_REGION_NAME,
            'access_key': settings.AWS_ACCESS_KEY_ID,
            'secret_key': settings.AWS_SECRET_ACCESS_KEY,
            'default_acl': 'private',
            'file_overwrite': False,
            'querystring_auth': True,  # Enable signed URLs for security
            'querystring_expire': 7200,  # 2 hours expiration for signed URLs (increased for SCORM content)
            'custom_domain': getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None),
        })
        
        super().__init__(**kwargs)
        
        # Set the location after initialization
        if location:
            self.location = location
    
    def get_available_name(self, name, max_length=None):
        """Get an available name for the file"""
        return super().get_available_name(name, max_length)
    
    def path(self, name):
        """Return the S3 key path (not a local path)"""
        # Avoid double prefixing if name already includes the location
        if name.startswith(f"{self.location}/"):
            return name
        return f"{self.location}/{name}"
    
    def exists(self, name):
        """Check if the file exists in S3"""
        try:
            return super().exists(name)
        except Exception:
            # If we can't check existence, assume it doesn't exist
            return False
    
    def listdir(self, path):
        """List directory contents in S3"""
        try:
            return super().listdir(path)
        except Exception:
            return [], []
    
    def delete(self, name):
        """Delete the file from S3"""
        try:
            return super().delete(name)
        except Exception:
            # Log error but don't raise exception
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to delete S3 file: {name}")
            return False
    
    def size(self, name):
        """Get file size from S3"""
        try:
            return super().size(name)
        except Exception:
            return 0
    
    def url(self, name):
        """Get the URL for the file (signed URL for private files)"""
        try:
            # The parent class S3Boto3Storage will handle the location prefix
            # We should NOT add it manually here to avoid double prefixing
            # Just pass the name as-is to the parent class
            signed_url = super().url(name)
            return signed_url
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Error generating S3 URL for {}: {}".format(name, e))
            
            # Fallback to direct S3 URL with proper path construction
            if not name.startswith(f"{self.location}/"):
                full_path = f"{self.location}/{name}"
            else:
                full_path = name
            
            fallback_url = "https://{}.s3.{}.amazonaws.com/{}".format(
                settings.AWS_STORAGE_BUCKET_NAME, 
                settings.AWS_S3_REGION_NAME, 
                full_path
            )
            logger.warning("Using fallback URL: {}".format(fallback_url))
            return fallback_url
    
    def get_accessed_time(self, name):
        """Get file access time from S3"""
        try:
            return super().get_accessed_time(name)
        except Exception:
            return None
    
    def get_created_time(self, name):
        """Get file creation time from S3"""
        try:
            return super().get_created_time(name)
        except Exception:
            return None
    
    def get_modified_time(self, name):
        """Get file modification time from S3"""
        try:
            return super().get_modified_time(name)
        except Exception:
            return None
