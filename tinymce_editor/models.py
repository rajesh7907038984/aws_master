from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import datetime, timedelta
import calendar

User = get_user_model()

class BranchAITokenLimit(models.Model):
    """Model to store AI token limits for each branch"""
    branch = models.OneToOneField(
        'branches.Branch',
        on_delete=models.CASCADE,
        related_name='ai_token_limits',
        help_text="The branch these AI token limits apply to"
    )
    monthly_token_limit = models.PositiveIntegerField(
        default=10000,
        validators=[MinValueValidator(0)],
        help_text="Maximum number of AI tokens allowed per month for this branch"
    )
    is_unlimited = models.BooleanField(
        default=False,
        help_text="If enabled, this branch has unlimited AI token usage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_ai_token_limits',
        help_text="Global admin who last updated these limits"
    )

    class Meta:
        verbose_name = 'Branch AI Token Limit'
        verbose_name_plural = 'Branch AI Token Limits'
        ordering = ['branch__name']

    def __str__(self):
        if self.is_unlimited:
            return f"AI Token limits for {self.branch.name}: Unlimited"
        return f"AI Token limits for {self.branch.name}: {self.monthly_token_limit:,}/month"

    def clean(self):
        """Validate that limits are reasonable"""
        if not self.is_unlimited and self.monthly_token_limit == 0:
            raise ValidationError("Monthly token limit must be greater than 0 if not unlimited")

    def get_current_month_usage(self):
        """Get current month's token usage for this branch"""
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        usage = AITokenUsage.objects.filter(
            user__branch=self.branch,
            created_at__gte=start_of_month
        ).aggregate(
            total_tokens=models.Sum('tokens_used')
        )['total_tokens'] or 0
        
        return usage

    def get_remaining_tokens(self):
        """Get remaining tokens for current month"""
        if self.is_unlimited:
            return float('inf')
        
        current_usage = self.get_current_month_usage()
        remaining = self.monthly_token_limit - current_usage
        return max(0, remaining)

    def is_limit_exceeded(self):
        """Check if current month's limit is exceeded"""
        if self.is_unlimited:
            return False
        
        return self.get_current_month_usage() >= self.monthly_token_limit

    def get_usage_percentage(self):
        """Get current usage as percentage of limit"""
        if self.is_unlimited:
            return 0
        
        if self.monthly_token_limit == 0:
            return 100
        
        current_usage = self.get_current_month_usage()
        return min(100, (current_usage / self.monthly_token_limit) * 100)


class AITokenUsage(models.Model):
    """Model to track AI token usage by users"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ai_token_usage',
        help_text="User who generated AI content"
    )
    tokens_used = models.PositiveIntegerField(
        help_text="Number of tokens consumed in this request"
    )
    prompt_text = models.TextField(
        help_text="The prompt used for AI generation (truncated for privacy)"
    )
    response_length = models.PositiveIntegerField(
        default=0,
        help_text="Length of generated response in characters"
    )
    model_used = models.CharField(
        max_length=100,
        default='claude-3-opus-20240229',
        help_text="AI model used for generation"
    )
    success = models.BooleanField(
        default=True,
        help_text="Whether the AI generation was successful"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error message if generation failed"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'AI Token Usage'
        verbose_name_plural = 'AI Token Usage Records'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.tokens_used} tokens on {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        # Truncate prompt for privacy and storage efficiency
        if self.prompt_text and len(self.prompt_text) > 500:
            self.prompt_text = self.prompt_text[:500] + "..."
        super().save(*args, **kwargs)

    @staticmethod
    def estimate_tokens_from_text(text):
        """Estimate token count from text (rough approximation: 1 token ≈ 4 characters)"""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def get_branch_usage_stats(cls, branch, start_date=None, end_date=None):
        """Get usage statistics for a branch within date range"""
        queryset = cls.objects.filter(user__branch=branch)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        stats = queryset.aggregate(
            total_requests=models.Count('id'),
            total_tokens=models.Sum('tokens_used'),
            successful_requests=models.Count('id', filter=models.Q(success=True)),
            failed_requests=models.Count('id', filter=models.Q(success=False))
        )
        
        return {
            'total_requests': stats['total_requests'] or 0,
            'total_tokens': stats['total_tokens'] or 0,
            'successful_requests': stats['successful_requests'] or 0,
            'failed_requests': stats['failed_requests'] or 0,
            'success_rate': (stats['successful_requests'] / max(1, stats['total_requests'])) * 100
        }

    @classmethod
    def get_user_monthly_usage(cls, user, year=None, month=None):
        """Get user's token usage for a specific month"""
        now = timezone.now()
        if not year:
            year = now.year
        if not month:
            month = now.month
        
        start_date = datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
        end_date = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59, tzinfo=timezone.get_current_timezone())
        
        usage = cls.objects.filter(
            user=user,
            created_at__range=[start_date, end_date]
        ).aggregate(
            total_tokens=models.Sum('tokens_used')
        )['total_tokens'] or 0
        
        return usage
