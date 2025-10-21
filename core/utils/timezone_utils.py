"""
Timezone utilities for LMS
Handles timezone conversions and time formatting
"""
import logging
from typing import Optional, Union
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_datetime
import pytz

logger = logging.getLogger(__name__)

class TimezoneUtils:
    """Utility class for timezone operations"""
    
    @staticmethod
    def get_user_timezone(user) -> str:
        """Get user's timezone preference"""
        if hasattr(user, 'timezone') and user.timezone:
            return user.timezone
        return 'UTC'
    
    @staticmethod
    def convert_to_user_timezone(utc_datetime, user) -> str:
        """Convert UTC datetime to user's timezone"""
        try:
            user_tz = TimezoneUtils.get_user_timezone(user)
            
            # Ensure datetime is timezone aware
            if django_timezone.is_naive(utc_datetime):
                utc_datetime = django_timezone.make_aware(utc_datetime)
            
            # Convert to user timezone
            user_timezone = pytz.timezone(user_tz)
            local_datetime = utc_datetime.astimezone(user_timezone)
            
            return local_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')
        except Exception as e:
            logger.error(f"Error converting timezone: {e}")
            return utc_datetime.strftime('%Y-%m-%d %H:%M:%S UTC')
    
    @staticmethod
    def format_time_spent(seconds: Union[int, float], user_timezone: Optional[str] = None) -> str:
        """Format time spent in seconds to human readable format"""
        if not isinstance(seconds, (int, float)) or seconds < 0:
            return "0s"
        
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {remaining_seconds}s"
        elif minutes > 0:
            return f"{minutes}m {remaining_seconds}s"
        else:
            return f"{remaining_seconds}s"
    
    @staticmethod
    def validate_time_spent(time_spent: Union[int, float]) -> bool:
        """Validate time spent value"""
        if not isinstance(time_spent, (int, float)):
            return False
        
        # Allow 0 to 1 hour (3600 seconds) per update to prevent abuse
        return 0 <= time_spent <= 3600
    
    @staticmethod
    def get_server_time() -> str:
        """Get current server time in ISO format"""
        return django_timezone.now().isoformat()
    
    @staticmethod
    def get_timezone_offset(user_timezone: str) -> int:
        """Get timezone offset in minutes"""
        try:
            tz = pytz.timezone(user_timezone)
            now = django_timezone.now()
            local_time = tz.localize(now.replace(tzinfo=None))
            return int(local_time.utcoffset().total_seconds() / 60)
        except Exception as e:
            logger.error(f"Error getting timezone offset: {e}")
            return 0
