"""
Auto-timezone detection for new users on first login
"""
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.conf import settings
import json
import pytz
from .models import UserTimezone

logger = logging.getLogger(__name__)

@csrf_protect
@require_http_methods(["POST"])
@login_required
def set_user_timezone_auto(request):
    """
    Automatically set user timezone on first login based on device detection
    """
    try:
        data = json.loads(request.body)
        user_timezone = data.get('timezone')
        offset_minutes = data.get('offset', 0)
        auto_detected = data.get('auto_detected', True)
        
        if not user_timezone:
            return JsonResponse({
                'success': False,
                'error': 'Timezone is required'
            }, status=400)
        
        # Check if this is first login (no timezone set yet)
        timezone_obj, created = UserTimezone.objects.get_or_create(
            user=request.user,
            defaults={
                'timezone': user_timezone,
                'auto_detected': auto_detected
            }
        )
        
        # If timezone already exists but was auto-detected, update it
        if not created and timezone_obj.auto_detected:
            timezone_obj.timezone = user_timezone
            timezone_obj.auto_detected = auto_detected
            timezone_obj.save()
            logger.info(f"Updated auto-detected timezone for user {request.user.username} to {user_timezone}")
        elif not created:
            # User has manually set timezone, don't override
            logger.info(f"User {request.user.username} has manually set timezone {timezone_obj.timezone}, not overriding")
            return JsonResponse({
                'success': True,
                'message': 'User has manually set timezone, not overriding',
                'timezone': timezone_obj.timezone
            })
        else:
            logger.info(f"Set initial timezone for user {request.user.username} to {user_timezone}")
        
        # Mark user as having timezone detected for first time
        if not hasattr(request.user, 'timezone_detected_at') or not request.user.timezone_detected_at:
            request.user.timezone_detected_at = timezone.now()
            request.user.save(update_fields=['timezone_detected_at'])
        
        return JsonResponse({
            'success': True,
            'message': 'Timezone set successfully',
            'timezone': user_timezone,
            'auto_detected': auto_detected,
            'first_time': created
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error setting auto timezone for user {request.user.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to set timezone'
        }, status=500)

@login_required
def get_user_timezone_status(request):
    """
    Get user's current timezone status and whether it needs to be set
    """
    try:
        # Check if user has timezone set
        try:
            user_timezone = UserTimezone.objects.get(user=request.user)
            has_timezone = True
            timezone_name = user_timezone.timezone
            auto_detected = user_timezone.auto_detected
        except UserTimezone.DoesNotExist:
            has_timezone = False
            timezone_name = 'UTC'
            auto_detected = False
        
        # Check if this is first login (no timezone_detected_at timestamp)
        is_first_login = not hasattr(request.user, 'timezone_detected_at') or not request.user.timezone_detected_at
        
        return JsonResponse({
            'success': True,
            'has_timezone': has_timezone,
            'timezone': timezone_name,
            'auto_detected': auto_detected,
            'is_first_login': is_first_login,
            'needs_detection': not has_timezone or is_first_login
        })
        
    except Exception as e:
        logger.error(f"Error getting timezone status for user {request.user.username}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get timezone status'
        }, status=500)

def validate_timezone(timezone_name):
    """
    Validate if timezone name is valid
    """
    try:
        pytz.timezone(timezone_name)
        return True
    except pytz.UnknownTimeZoneError:
        return False

def get_timezone_from_offset(offset_minutes):
    """
    Get timezone name from UTC offset in minutes
    """
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
