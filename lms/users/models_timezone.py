from django.db import models
from django.conf import settings
from django.utils import timezone
import pytz

class UserTimezone(models.Model):
    """Model to store user timezone preferences"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='timezone_preference'
    )
    timezone = models.CharField(
        max_length=100,
        default='UTC',
        help_text="User's preferred timezone (e.g., 'America/New_York', 'Europe/London')"
    )
    auto_detected = models.BooleanField(
        default=False,
        help_text="Whether timezone was auto-detected from browser"
    )
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'users'
        verbose_name = 'User Timezone'
        verbose_name_plural = 'User Timezones'
    
    def __str__(self):
        return f"{self.user.username} - {self.timezone}"
    
    def get_timezone_obj(self):
        """Get pytz timezone object"""
        try:
            return pytz.timezone(self.timezone)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC
    
    def convert_to_user_timezone(self, utc_datetime):
        """Convert UTC datetime to user's timezone"""
        if not utc_datetime:
            return None
        
        if timezone.is_naive(utc_datetime):
            utc_datetime = timezone.make_aware(utc_datetime, pytz.UTC)
        
        user_tz = self.get_timezone_obj()
        return utc_datetime.astimezone(user_tz)
    
    def convert_to_utc(self, local_datetime):
        """Convert local datetime to UTC"""
            return None
        
        user_tz = self.get_timezone_obj()
        
            local_datetime = user_tz.localize(local_datetime)
        
        return local_datetime.astimezone(pytz.UTC)
    
    @classmethod
    def get_user_timezone(cls, user):
        """Get user's timezone, create default if doesn't exist"""
        try:
            return cls.objects.get(user=user)
        except cls.DoesNotExist:
            return cls.objects.create(
                user=user,
                timezone='UTC',
                auto_detected=False
            )
    
    @classmethod
    def detect_timezone_from_offset(cls, offset_minutes):
        """Detect timezone from UTC offset in minutes"""
        # Common timezone mappings based on UTC offset
        offset_mapping = {
            -720: 'Pacific/Midway',      # UTC-12
            -660: 'Pacific/Honolulu',    # UTC-11
            -600: 'Pacific/Marquesas',   # UTC-10
            -540: 'America/Anchorage',   # UTC-9
            -480: 'America/Los_Angeles', # UTC-8
            -420: 'America/Denver',      # UTC-7
            -360: 'America/Chicago',     # UTC-6
            -300: 'America/New_York',    # UTC-5
            -240: 'America/Caracas',     # UTC-4
            -180: 'America/Argentina/Buenos_Aires', # UTC-3
            -120: 'Atlantic/South_Georgia', # UTC-2
            -60: 'Atlantic/Azores',      # UTC-1
            0: 'UTC',                    # UTC+0
            60: 'Europe/London',         # UTC+1
            120: 'Europe/Paris',         # UTC+2
            180: 'Europe/Moscow',        # UTC+3
            240: 'Asia/Dubai',           # UTC+4
            300: 'Asia/Karachi',         # UTC+5
            360: 'Asia/Dhaka',           # UTC+6
            420: 'Asia/Bangkok',         # UTC+7
            480: 'Asia/Shanghai',        # UTC+8
            540: 'Asia/Tokyo',           # UTC+9
            600: 'Australia/Sydney',     # UTC+10
            660: 'Pacific/Noumea',       # UTC+11
            720: 'Pacific/Auckland',     # UTC+12
        }
        
        return offset_mapping.get(offset_minutes, 'UTC')
