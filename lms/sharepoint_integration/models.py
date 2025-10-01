from django.db import models
from django.conf import settings
from django.utils import timezone


class SharePointSyncLog(models.Model):
    """Comprehensive logging for SharePoint sync operations"""
    
    OPERATION_CHOICES = [
        ('sync_to_sharepoint', 'Sync to SharePoint'),
        ('sync_from_sharepoint', 'Sync from SharePoint'),
        ('bidirectional_sync', 'Bidirectional Sync'),
        ('conflict_resolution', 'Conflict Resolution'),
        ('monitoring', 'Change Monitoring'),
        ('health_check', 'Health Check'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    integration = models.ForeignKey(
        'account_settings.SharePointIntegration',
        on_delete=models.CASCADE,
        related_name='sync_logs'
    )
    operation_type = models.CharField(max_length=50, choices=OPERATION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    model_type = models.CharField(max_length=50, null=True, blank=True)
    record_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    
    result_summary = models.JSONField(default=dict)
    error_details = models.JSONField(default=list)
    
    task_id = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        verbose_name = 'SharePoint Sync Log'
        verbose_name_plural = 'SharePoint Sync Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.operation_type} - {self.integration.name} ({self.status})"
    
    def mark_completed(self, success_count=None, error_count=None, result_summary=None):
        """Mark the sync operation as completed"""
        self.completed_at = timezone.now()
        self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
        
        if success_count is not None:
            self.success_count = success_count
        if error_count is not None:
            self.error_count = error_count
        if result_summary is not None:
            self.result_summary = result_summary
        
        self.status = 'completed' if self.error_count == 0 else 'partial'
        self.save()


class SharePointConflict(models.Model):
    """Track sync conflicts that require resolution"""
    
    CONFLICT_TYPES = [
        ('field_mismatch', 'Field Value Mismatch'),
        ('timestamp_conflict', 'Timestamp Conflict'),
        ('missing_record', 'Missing Record'),
        ('duplicate_record', 'Duplicate Record'),
    ]
    
    RESOLUTION_STATUS = [
        ('detected', 'Detected'),
        ('pending_review', 'Pending Manual Review'),
        ('auto_resolved', 'Auto Resolved'),
        ('manually_resolved', 'Manually Resolved'),
        ('ignored', 'Ignored'),
    ]
    
    integration = models.ForeignKey(
        'account_settings.SharePointIntegration',
        on_delete=models.CASCADE,
        related_name='conflicts'
    )
    
    conflict_type = models.CharField(max_length=30, choices=CONFLICT_TYPES)
    model_type = models.CharField(max_length=50)
    record_id = models.CharField(max_length=100)
    sharepoint_id = models.CharField(max_length=100, null=True, blank=True)
    
    field_name = models.CharField(max_length=100, null=True, blank=True)
    lms_value = models.JSONField(null=True, blank=True)
    sharepoint_value = models.JSONField(null=True, blank=True)
    
    resolution_status = models.CharField(max_length=30, choices=RESOLUTION_STATUS, default='detected')
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'SharePoint Conflict'
        verbose_name_plural = 'SharePoint Conflicts'
        ordering = ['-detected_at']
    
    def __str__(self):
        return f"{self.conflict_type} - {self.model_type} {self.record_id}"
