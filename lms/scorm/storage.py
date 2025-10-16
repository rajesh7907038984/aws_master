"""
Custom storage for SCORM packages - uses local storage for extraction
while keeping S3 for other media files
"""
import os
from django.core.files.storage import FileSystemStorage
from django.conf import settings


class SCORMLocalStorage(FileSystemStorage):
    """
    Custom storage class for SCORM packages that uses local storage
    This allows SCORM packages to be extracted locally while other
    media files continue to use S3 storage
    """
    
    def __init__(self, location=None, base_url=None, **kwargs):
        # Use a dedicated local directory for SCORM packages
        if location is None:
            location = '/home/ec2-user/lms/local_media/elearning'
        
        if base_url is None:
            base_url = '/media/elearning/'
        
        super().__init__(location=location, base_url=base_url, **kwargs)
    
    def get_available_name(self, name, max_length=None):
        """Get an available name for the file"""
        return super().get_available_name(name, max_length)
    
    def path(self, name):
        """Return the full path to the file"""
        return super().path(name)
    
    def exists(self, name):
        """Check if the file exists"""
        return super().exists(name)
    
    def listdir(self, path):
        """List directory contents"""
        return super().listdir(path)
    
    def delete(self, name):
        """Delete the file"""
        return super().delete(name)
    
    def size(self, name):
        """Get file size"""
        return super().size(name)
    
    def url(self, name):
        """Get the URL for the file"""
        return super().url(name)
    
    def get_accessed_time(self, name):
        """Get file access time"""
        return super().get_accessed_time(name)
    
    def get_created_time(self, name):
        """Get file creation time"""
        return super().get_created_time(name)
    
    def get_modified_time(self, name):
        """Get file modification time"""
        return super().get_modified_time(name)
