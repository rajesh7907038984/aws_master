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
            base_url = f'https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/elearning/'
        
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
            return super().url(name)
        except Exception:
            # Fallback to direct S3 URL
            return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{self.location}/{name}"
    
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
