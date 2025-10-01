from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db.models import Sum
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class BranchStorageLimit(models.Model):
    """Model to store file storage limits for each branch"""
    branch = models.OneToOneField(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='storage_limits',
        help_text="The branch these storage limits apply to"
    )
    storage_limit_bytes = models.BigIntegerField(
        default=1073741824,  # 1GB default
        validators=[MinValueValidator(0)],
        help_text="Maximum storage allowed in bytes for this branch"
    )
    is_unlimited = models.BooleanField(
        default=False,
        help_text="If enabled, this branch has unlimited storage"
    )
    warning_threshold_percent = models.PositiveIntegerField(
        default=80,
        validators=[MinValueValidator(1)],
        help_text="Warning threshold as percentage of limit (e.g., 80 for 80%)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_storage_limits',
        help_text="Global admin who last updated these limits"
    )

    class Meta:
        verbose_name = 'Branch Storage Limit'
        verbose_name_plural = 'Branch Storage Limits'
        ordering = ['branch__name']

    def __str__(self):
        if self.is_unlimited:
            return f"Storage limits for {self.branch.name}: Unlimited"
        return f"Storage limits for {self.branch.name}: {self.get_limit_display()}"

    def clean(self):
        """Validate that limits are reasonable"""
        if not self.is_unlimited and self.storage_limit_bytes == 0:
            raise ValidationError("Storage limit must be greater than 0 bytes if not unlimited")
        
        if self.warning_threshold_percent > 100:
            raise ValidationError("Warning threshold cannot exceed 100%")

    def get_limit_display(self):
        """Get human-readable storage limit"""
        if self.is_unlimited:
            return "Unlimited"
        
        bytes_val = self.storage_limit_bytes
        if bytes_val >= 1073741824:  # GB
            return f"{bytes_val / 1073741824:.1f}GB"
        elif bytes_val >= 1048576:  # MB
            return f"{bytes_val / 1048576:.1f}MB"
        elif bytes_val >= 1024:  # KB
            return f"{bytes_val / 1024:.1f}KB"
        else:
            return f"{bytes_val} bytes"

    def get_current_usage(self):
        """Get current storage usage for this branch in bytes"""
        usage = FileStorageUsage.objects.filter(
            user__branch=self.branch,
            is_deleted=False
        ).aggregate(
            total_bytes=Sum('file_size_bytes')
        )['total_bytes'] or 0
        
        return usage

    def get_remaining_storage(self):
        """Get remaining storage in bytes"""
        if self.is_unlimited:
            return float('inf')
        
        current_usage = self.get_current_usage()
        remaining = self.storage_limit_bytes - current_usage
        return max(0, remaining)

    def is_limit_exceeded(self):
        """Check if storage limit is exceeded"""
        if self.is_unlimited:
            return False
        
        return self.get_current_usage() >= self.storage_limit_bytes

    def is_warning_threshold_exceeded(self):
        """Check if warning threshold is exceeded"""
        if self.is_unlimited:
            return False
        
        current_usage = self.get_current_usage()
        warning_threshold_bytes = self.storage_limit_bytes * (self.warning_threshold_percent / 100)
        return current_usage >= warning_threshold_bytes

    def get_usage_percentage(self):
        """Get current usage as percentage of limit"""
        if self.is_unlimited:
            return 0
        
        if self.storage_limit_bytes == 0:
            return 100
        
        current_usage = self.get_current_usage()
        return min(100, (current_usage / self.storage_limit_bytes) * 100)

    def can_upload_file(self, file_size_bytes):
        """Check if a file of given size can be uploaded"""
        if self.is_unlimited:
            return True, ""
        
        current_usage = self.get_current_usage()
        after_upload = current_usage + file_size_bytes
        
        if after_upload > self.storage_limit_bytes:
            limit_display = self.get_limit_display()
            current_display = self.get_usage_display(current_usage)
            file_display = self.get_usage_display(file_size_bytes)
            
            return False, (
                f"Storage limit exceeded! "
                f"Your branch limit: {limit_display}, "
                f"Current usage: {current_display}, "
                f"File size: {file_display}. "
                f"Please contact your administrator to increase your storage limit."
            )
        
        return True, ""

    def get_usage_display(self, bytes_val):
        """Get human-readable usage display"""
        if bytes_val >= 1073741824:  # GB
            return f"{bytes_val / 1073741824:.1f}GB"
        elif bytes_val >= 1048576:  # MB
            return f"{bytes_val / 1048576:.1f}MB"
        elif bytes_val >= 1024:  # KB
            return f"{bytes_val / 1024:.1f}KB"
        else:
            return f"{bytes_val} bytes"

    @classmethod
    def get_or_create_for_branch(cls, branch):
        """Get or create storage limits for a branch"""
        limit, created = cls.objects.get_or_create(
            branch=branch,
            defaults={
                'storage_limit_bytes': 1073741824,  # 1GB default
                'is_unlimited': False,
                'warning_threshold_percent': 80,
            }
        )
        return limit


class FileStorageUsage(models.Model):
    """Model to track file storage usage by users"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='file_storage_usage',
        help_text="User who uploaded the file"
    )
    file_path = models.TextField(
        help_text="Path to the uploaded file"
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original name of the uploaded file"
    )
    file_size_bytes = models.BigIntegerField(
        help_text="Size of the file in bytes"
    )
    content_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="MIME type of the file"
    )
    source_app = models.CharField(
        max_length=50,
        help_text="App that handled the upload (e.g., 'tinymce_editor', 'assignments')"
    )
    source_model = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Model that the file is associated with"
    )
    source_object_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="ID of the object the file is associated with"
    )
    upload_session_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Session identifier for batch uploads"
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="Whether the file has been deleted (for cleanup tracking)"
    )
    deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the file was marked as deleted"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'File Storage Usage'
        verbose_name_plural = 'File Storage Usage Records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['user', 'is_deleted']),
            models.Index(fields=['source_app', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.original_filename} ({self.get_file_size_display()}) - {self.source_app}"

    def get_file_size_display(self):
        """Get human-readable file size"""
        bytes_val = self.file_size_bytes
        if bytes_val >= 1073741824:  # GB
            return f"{bytes_val / 1073741824:.1f}GB"
        elif bytes_val >= 1048576:  # MB
            return f"{bytes_val / 1048576:.1f}MB"
        elif bytes_val >= 1024:  # KB
            return f"{bytes_val / 1024:.1f}KB"
        else:
            return f"{bytes_val} bytes"

    def mark_as_deleted(self):
        """Mark the file as deleted"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    @classmethod
    def register_upload(cls, user, file_path, original_filename, file_size_bytes, 
                       content_type=None, source_app=None, source_model=None, 
                       source_object_id=None, upload_session_id=None):
        """Register a new file upload"""
        
        # Check if file already registered (prevent duplicates)
        existing = cls.objects.filter(
            user=user,
            file_path=file_path,
            is_deleted=False
        ).first()
        
        if existing:
            logger.warning(f"File already registered: {file_path}")
            return existing
        
        # Create new usage record
        usage = cls.objects.create(
            user=user,
            file_path=file_path,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            content_type=content_type,
            source_app=source_app,
            source_model=source_model,
            source_object_id=source_object_id,
            upload_session_id=upload_session_id,
        )
        
        logger.info(f"Registered file upload: {original_filename} ({file_size_bytes} bytes) by {user.username}")
        return usage

    @classmethod
    def get_branch_usage_stats(cls, branch, start_date=None, end_date=None):
        """Get usage statistics for a branch within date range"""
        queryset = cls.objects.filter(user__branch=branch, is_deleted=False)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_files=models.Count('id'),
            total_bytes=models.Sum('file_size_bytes'),
        )
        
        return {
            'total_files': stats['total_files'] or 0,
            'total_bytes': stats['total_bytes'] or 0,
            'total_size_display': cls._get_size_display(stats['total_bytes'] or 0)
        }

    @staticmethod
    def _get_size_display(bytes_val):
        """Static method to get size display"""
        if bytes_val >= 1073741824:  # GB
            return f"{bytes_val / 1073741824:.1f}GB"
        elif bytes_val >= 1048576:  # MB
            return f"{bytes_val / 1048576:.1f}MB"
        elif bytes_val >= 1024:  # KB
            return f"{bytes_val / 1024:.1f}KB"
        else:
            return f"{bytes_val} bytes"


class StorageQuotaWarning(models.Model):
    """Model to track storage quota warnings sent to users/admins"""
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='storage_warnings',
        help_text="Branch that the warning is for"
    )
    warning_type = models.CharField(
        max_length=20,
        choices=[
            ('threshold', 'Warning Threshold Exceeded'),
            ('limit', 'Storage Limit Exceeded'),
            ('admin_notification', 'Admin Notification'),
        ],
        help_text="Type of warning issued"
    )
    usage_percentage = models.FloatField(
        help_text="Storage usage percentage when warning was issued"
    )
    usage_bytes = models.BigIntegerField(
        help_text="Storage usage in bytes when warning was issued"
    )
    limit_bytes = models.BigIntegerField(
        help_text="Storage limit in bytes at time of warning"
    )
    triggered_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_storage_warnings',
        help_text="User whose upload triggered this warning"
    )
    email_sent = models.BooleanField(
        default=False,
        help_text="Whether email notification was sent"
    )
    acknowledged = models.BooleanField(
        default=False,
        help_text="Whether the warning has been acknowledged"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Storage Quota Warning'
        verbose_name_plural = 'Storage Quota Warnings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'created_at']),
            models.Index(fields=['warning_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.branch.name} - {self.get_warning_type_display()} - {self.usage_percentage:.1f}%"

    @classmethod
    def create_warning(cls, branch, warning_type, usage_percentage, usage_bytes, 
                      limit_bytes, triggered_by_user=None):
        """Create a new storage warning"""
        
        # Check if similar warning was created recently (within last hour)
        recent_warning = cls.objects.filter(
            branch=branch,
            warning_type=warning_type,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        
        if recent_warning:
            logger.debug(f"Skipping duplicate warning for {branch.name}")
            return None
        
        warning = cls.objects.create(
            branch=branch,
            warning_type=warning_type,
            usage_percentage=usage_percentage,
            usage_bytes=usage_bytes,
            limit_bytes=limit_bytes,
            triggered_by_user=triggered_by_user,
        )
        
        logger.info(f"Created storage warning for {branch.name}: {warning_type} - {usage_percentage:.1f}%")
        return warning
