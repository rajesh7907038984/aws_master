"""
Score History and Audit Trail System
Tracks all changes to scores and grades for audit purposes
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal
import json


class ScoreHistory(models.Model):
    """
    Model to track all score changes for audit trail purposes
    """
    CHANGE_TYPES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
        ('overridden', 'Overridden'),
        ('recalculated', 'Recalculated'),
        ('imported', 'Imported'),
        ('exported', 'Exported'),
    ]
    
    # Generic foreign key to link to any score-related model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # User who made the change
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='score_changes'
    )
    
    # Change details
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPES)
    old_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Previous score value"
    )
    new_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="New score value"
    )
    
    # Additional metadata
    reason = models.TextField(
        blank=True,
        help_text="Reason for the change"
    )
    change_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata about the change"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'score_history'
        verbose_name = 'Score History'
        verbose_name_plural = 'Score Histories'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['changed_by', '-created_at']),
            models.Index(fields=['change_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_change_type_display()} - {self.content_object} - {self.created_at}"
    
    @classmethod
    def log_score_change(cls, obj, old_score, new_score, changed_by, change_type, reason='', metadata=None):
        """
        Log a score change
        
        Args:
            obj: The object whose score changed
            old_score: Previous score value
            new_score: New score value
            changed_by: User who made the change
            change_type: Type of change
            reason: Reason for the change
            metadata: Additional metadata
        """
        try:
            # Convert scores to Decimal for consistency
            old_decimal = Decimal(str(old_score)) if old_score is not None else None
            new_decimal = Decimal(str(new_score)) if new_score is not None else None
            
            # Only log if there's actually a change
            if old_decimal != new_decimal:
                cls.objects.create(
                    content_object=obj,
                    changed_by=changed_by,
                    change_type=change_type,
                    old_score=old_decimal,
                    new_score=new_decimal,
                    reason=reason,
                    change_metadata=metadata or {}
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log score change: {str(e)}", exc_info=True)
    
    @classmethod
    def get_score_history(cls, obj):
        """
        Get score history for a specific object
        
        Args:
            obj: The object to get history for
            
        Returns:
            QuerySet of ScoreHistory objects
        """
        content_type = ContentType.objects.get_for_model(obj)
        return cls.objects.filter(
            content_type=content_type,
            object_id=obj.id
        ).select_related('changed_by')
    
    @classmethod
    def get_user_score_changes(cls, user, days=30):
        """
        Get all score changes made by a specific user
        
        Args:
            user: User to get changes for
            days: Number of days to look back
            
        Returns:
            QuerySet of ScoreHistory objects
        """
        since = timezone.now() - timezone.timedelta(days=days)
        return cls.objects.filter(
            changed_by=user,
            created_at__gte=since
        ).select_related('content_type')
    
    @classmethod
    def get_recent_changes(cls, hours=24):
        """
        Get recent score changes
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            QuerySet of ScoreHistory objects
        """
        since = timezone.now() - timezone.timedelta(hours=hours)
        return cls.objects.filter(
            created_at__gte=since
        ).select_related('changed_by', 'content_type')
    
    @property
    def score_difference(self):
        """Calculate the difference between old and new scores"""
        if self.old_score is not None and self.new_score is not None:
            return self.new_score - self.old_score
        return None
    
    @property
    def is_improvement(self):
        """Check if the change was an improvement"""
        diff = self.score_difference
        return diff is not None and diff > 0
    
    @property
    def is_decline(self):
        """Check if the change was a decline"""
        diff = self.score_difference
        return diff is not None and diff < 0


class ScoreAuditLog(models.Model):
    """
    Detailed audit log for score-related operations
    """
    SEVERITY_LEVELS = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]
    
    # Related score history entry
    score_history = models.ForeignKey(
        ScoreHistory,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True
    )
    
    # Operation details
    operation = models.CharField(max_length=100, help_text="Operation performed")
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='info')
    message = models.TextField(help_text="Detailed message")
    
    # Context information
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    
    # Additional data
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'score_audit_log'
        verbose_name = 'Score Audit Log'
        verbose_name_plural = 'Score Audit Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['operation', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.get_severity_display()} - {self.operation} - {self.created_at}"
    
    @classmethod
    def log_operation(cls, operation, message, severity='info', score_history=None, 
                     user_agent='', ip_address=None, request_id='', extra_data=None):
        """
        Log a score-related operation
        
        Args:
            operation: Operation performed
            message: Detailed message
            severity: Severity level
            score_history: Related score history entry
            user_agent: User agent string
            ip_address: IP address
            request_id: Request ID for tracking
            extra_data: Additional data
        """
        try:
            cls.objects.create(
                score_history=score_history,
                operation=operation,
                severity=severity,
                message=message,
                user_agent=user_agent,
                ip_address=ip_address,
                request_id=request_id,
                extra_data=extra_data or {}
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log audit operation: {str(e)}", exc_info=True)
