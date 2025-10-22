"""
Timezone utility functions for the LMS application.
Handles automatic timezone detection and conversion across all modules.
"""
import pytz
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class TimezoneManager:
    """Centralized timezone management for the application"""
    
    @staticmethod
    def detect_timezone_from_offset(offset_minutes):
        """
        Detect timezone from UTC offset in minutes.
        Returns the most common timezone for that offset.
        """
        # Comprehensive timezone mappings based on UTC offset
        offset_mapping = {
            # UTC-12 to UTC-11
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
    
    @staticmethod
    def get_user_timezone(user):
        """Get user's timezone, return UTC if not set"""
        try:
            if hasattr(user, 'timezone_preference') and user.timezone_preference:
                return user.timezone_preference.timezone
        except Exception:
            # If there's any error accessing timezone_preference, fall back to UTC
            pass
        return 'UTC'
    
    @staticmethod
    def set_user_timezone(user, timezone_name, auto_detected=True):
        """Set user's timezone preference"""
        try:
            # Validate timezone
            pytz.timezone(timezone_name)
            
            # Get or create timezone preference
            from users.models import UserTimezone
            timezone_pref, created = UserTimezone.objects.get_or_create(
                user=user,
                defaults={
                    'timezone': timezone_name,
                    'auto_detected': auto_detected
                }
            )
            
            if not created:
                timezone_pref.timezone = timezone_name
                timezone_pref.auto_detected = auto_detected
                timezone_pref.save()
            
            logger.info(f"Set timezone for user {user.username}: {timezone_name}")
            return True
            
        except pytz.UnknownTimeZoneError:
            logger.error(f"Invalid timezone: {timezone_name}")
            return False
        except Exception as e:
            logger.error(f"Error setting timezone for user {user.username}: {str(e)}")
            return False
    
    @staticmethod
    def convert_to_user_timezone(utc_datetime, user):
        """Convert UTC datetime to user's timezone"""
        if not utc_datetime:
            return None
        
        try:
            # Ensure datetime is timezone-aware
            if timezone.is_naive(utc_datetime):
                utc_datetime = timezone.make_aware(utc_datetime, pytz.UTC)
            
            # Get user's timezone
            user_tz_name = TimezoneManager.get_user_timezone(user)
            user_tz = pytz.timezone(user_tz_name)
            
            # Convert to user's timezone
            return utc_datetime.astimezone(user_tz)
            
        except Exception as e:
            logger.error(f"Error converting to user timezone: {str(e)}")
            return utc_datetime
    
    @staticmethod
    def convert_to_utc(local_datetime, user):
        """Convert local datetime to UTC"""
        if not local_datetime:
            return None
        
        try:
            # Get user's timezone
            user_tz_name = TimezoneManager.get_user_timezone(user)
            user_tz = pytz.timezone(user_tz_name)
            
            # Ensure datetime is timezone-aware
            if local_datetime.tzinfo is None:
                local_datetime = user_tz.localize(local_datetime)
            
            # Convert to UTC
            return local_datetime.astimezone(pytz.UTC)
            
        except Exception as e:
            logger.error(f"Error converting to UTC: {str(e)}")
            return local_datetime
    
    @staticmethod
    def format_datetime_for_user(dt, user, format_string=None):
        """Format datetime for user's timezone and locale"""
        if not dt:
            return ""
        
        try:
            # Convert to user's timezone
            user_dt = TimezoneManager.convert_to_user_timezone(dt, user)
            
            if format_string:
                return user_dt.strftime(format_string)
            else:
                # Default format
                return user_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                
        except Exception as e:
            logger.error(f"Error formatting datetime: {str(e)}")
            return str(dt)
    
    @staticmethod
    def get_timezone_info(user):
        """Get comprehensive timezone information for user"""
        user_tz_name = TimezoneManager.get_user_timezone(user)
        
        try:
            user_tz = pytz.timezone(user_tz_name)
            now_utc = timezone.now()
            now_user = now_utc.astimezone(user_tz)
            
            return {
                'timezone': user_tz_name,
                'offset_minutes': now_user.utcoffset().total_seconds() / 60,
                'offset_hours': now_user.utcoffset().total_seconds() / 3600,
                'current_time': now_user,
                'is_dst': now_user.dst() != timezone.timedelta(0),
                'timezone_name': now_user.tzname(),
            }
        except Exception as e:
            logger.error(f"Error getting timezone info: {str(e)}")
            return {
                'timezone': 'UTC',
                'offset_minutes': 0,
                'offset_hours': 0,
                'current_time': timezone.now(),
                'is_dst': False,
                'timezone_name': 'UTC',
            }


def get_user_timezone(user):
    """Convenience function to get user timezone"""
    return TimezoneManager.get_user_timezone(user)


def convert_to_user_timezone(utc_datetime, user):
    """Convenience function to convert UTC to user timezone"""
    return TimezoneManager.convert_to_user_timezone(utc_datetime, user)


def convert_to_utc(local_datetime, user):
    """Convenience function to convert local time to UTC"""
    return TimezoneManager.convert_to_utc(local_datetime, user)


def format_datetime_for_user(dt, user, format_string=None):
    """Convenience function to format datetime for user"""
    return TimezoneManager.format_datetime_for_user(dt, user, format_string)
