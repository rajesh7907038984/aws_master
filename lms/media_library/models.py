from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import os

User = get_user_model()


class MediaFile(models.Model):
    """Model to track all media files in the system"""
    
    STORAGE_TYPES = [
        ('s3', 'S3 Storage'),
        ('local', 'Local Storage'),
    ]
    
    FILE_TYPES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('archive', 'Archive'),
        ('other', 'Other'),
    ]
    
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_url = models.URLField(max_length=1000, blank=True, null=True)
    file_size = models.BigIntegerField(default=0)
    file_type = models.CharField(max_length=20, choices=FILE_TYPES)
    mime_type = models.CharField(max_length=100, blank=True)
    storage_type = models.CharField(max_length=10, choices=STORAGE_TYPES)
    
    # Metadata
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    uploaded_at = models.DateTimeField(default=timezone.now)
    last_accessed = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)
    
    # Source tracking
    source_app = models.CharField(max_length=50, blank=True)  # e.g., 'conferences', 'reports', 'tinymce'
    source_model = models.CharField(max_length=50, blank=True)  # e.g., 'ConferenceFile', 'ReportAttachment'
    source_id = models.PositiveIntegerField(null=True, blank=True)
    
    # File status
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=False)
    
    # Additional metadata
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True)  # Comma-separated tags
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['storage_type']),
            models.Index(fields=['file_type']),
            models.Index(fields=['uploaded_by']),
            models.Index(fields=['uploaded_at']),
        ]
    
    def __str__(self):
        return "{{self.filename}} ({{self.storage_type}})"
    
    @property
    def file_size_mb(self):
        """Return file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)
    
    @property
    def file_extension(self):
        """Get file extension"""
        return os.path.splitext(self.filename)[1].lower()
    
    def get_absolute_url(self):
        """Get the URL to access this file"""
        if self.storage_type == 's3' and self.file_url:
            return self.file_url
        elif self.storage_type == 'local':
            # S3 storage only - no local file serving
            return None
        return None


class StorageStatistics(models.Model):
    """Model to store storage statistics"""
    
    storage_type = models.CharField(max_length=10, choices=MediaFile.STORAGE_TYPES)
    total_files = models.PositiveIntegerField(default=0)
    total_size_bytes = models.BigIntegerField(default=0)
    last_updated = models.DateTimeField(default=timezone.now)
    
    # Breakdown by file type
    image_count = models.PositiveIntegerField(default=0)
    video_count = models.PositiveIntegerField(default=0)
    audio_count = models.PositiveIntegerField(default=0)
    document_count = models.PositiveIntegerField(default=0)
    archive_count = models.PositiveIntegerField(default=0)
    other_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['storage_type']
    
    def __str__(self):
        return "{{self.storage_type}} Storage Statistics"
    
    @property
    def total_size_mb(self):
        """Return total size in MB"""
        return round(self.total_size_bytes / (1024 * 1024), 2)
    
    @property
    def total_size_gb(self):
        """Return total size in GB"""
        return round(self.total_size_bytes / (1024 * 1024 * 1024), 2)