"""
Custom storage backends for the LMS project
"""

import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class CustomFileStorage(FileSystemStorage):
    """
    Custom file storage that creates directories as needed
    """
    
    def _save(self, name, content):
        # Ensure the directory exists
        full_path = self.path(name)
        directory = os.path.dirname(full_path)
        
        if not os.path.exists(directory):
            os.makedirs(directory, 0o755)
        
        return super()._save(name, content)


class MediaFileStorage(CustomFileStorage):
    """
    Storage for media files (user uploads)
    """
    
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.MEDIA_ROOT
        kwargs['base_url'] = settings.MEDIA_URL
        super().__init__(*args, **kwargs)


class StaticFileStorage(CustomFileStorage):
    """
    Storage for static files
    """
    
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.STATIC_ROOT
        kwargs['base_url'] = settings.STATIC_URL
        super().__init__(*args, **kwargs)