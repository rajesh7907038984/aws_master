from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class CalendarEvent(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_all_day = models.BooleanField(default=False)
    color = models.CharField(max_length=20, default='#3498db')  # Default blue color
    is_recurring = models.BooleanField(default=False)
    notification = models.CharField(
        max_length=10,
        choices=[
            ("none", "None"),
            ("15min", "15 minutes before"),
            ("30min", "30 minutes before"),
            ("1hour", "1 hour before"),
            ("2hours", "2 hours before"),
            ("1day", "1 day before"),
        ],
        default="none"
    )
    tags = models.CharField(max_length=200, blank=True, help_text="Comma-separated tags")
    category = models.ForeignKey('EventCategory', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        app_label = 'calendar_app'
        ordering = ['start_date']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Ensure datetimes are timezone-aware
        if timezone.is_naive(self.start_date):
            self.start_date = timezone.make_aware(self.start_date)
        if timezone.is_naive(self.end_date):
            self.end_date = timezone.make_aware(self.end_date)
        super().save(*args, **kwargs)

class EventCategory(models.Model):
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default='#3498db')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name_plural = "Event Categories"
    
    def __str__(self):
        return self.name 