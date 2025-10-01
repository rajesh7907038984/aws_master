"""
API endpoints for timezone management
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
import json
import logging

from .timezone_utils import TimezoneManager

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["POST"])
def set_user_timezone(request):
    """Set user's timezone preference"""
    try:
        data = json.loads(request.body)
        timezone_name = data.get('timezone')
        offset = data.get('offset')
        auto_detected = data.get('auto_detected', True)
        
        if not timezone_name:
            return JsonResponse({
                'success': False,
                'error': 'Timezone is required'
            }, status=400)
        
        # Set user timezone
        success = TimezoneManager.set_user_timezone(
            request.user, 
            timezone_name, 
            auto_detected
        )
        
        if success:
            # Get timezone info
            tz_info = TimezoneManager.get_timezone_info(request.user)
            
            return JsonResponse({
                'success': True,
                'timezone': timezone_name,
                'timezone_info': tz_info,
                'message': 'Timezone updated successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid timezone or failed to save'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error setting timezone: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def get_user_timezone(request):
    """Get user's current timezone information"""
    try:
        tz_info = TimezoneManager.get_timezone_info(request.user)
        
        return JsonResponse({
            'success': True,
            'timezone_info': tz_info
        })
        
    except Exception as e:
        logger.error(f"Error getting timezone info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get timezone information'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def convert_time(request):
    """Convert time between UTC and user timezone"""
    try:
        data = json.loads(request.body)
        utc_time = data.get('utc_time')
        to_user_tz = data.get('to_user_tz', True)
        
        if not utc_time:
            return JsonResponse({
                'success': False,
                'error': 'UTC time is required'
            }, status=400)
        
        if to_user_tz:
            # Convert UTC to user timezone
            from django.utils.dateparse import parse_datetime
            from django.utils import timezone as django_timezone
            
            utc_dt = parse_datetime(utc_time)
            if not utc_dt:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid datetime format'
                }, status=400)
            
            # Make timezone aware if needed
            if django_timezone.is_naive(utc_dt):
                utc_dt = django_timezone.make_aware(utc_dt)
            
            user_dt = TimezoneManager.convert_to_user_timezone(utc_dt, request.user)
            
            return JsonResponse({
                'success': True,
                'original_time': utc_time,
                'converted_time': user_dt.isoformat(),
                'formatted_time': TimezoneManager.format_datetime_for_user(utc_dt, request.user)
            })
        else:
            # Convert user timezone to UTC
            from django.utils.dateparse import parse_datetime
            user_dt = parse_datetime(utc_time)
            if not user_dt:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid datetime format'
                }, status=400)
            
            utc_dt = TimezoneManager.convert_to_utc(user_dt, request.user)
            
            return JsonResponse({
                'success': True,
                'original_time': utc_time,
                'converted_time': utc_dt.isoformat(),
                'formatted_time': utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error converting time: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to convert time'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def get_timezone_list(request):
    """Get list of available timezones"""
    try:
        import pytz
        
        # Get common timezones
        common_timezones = [
            'UTC',
            'America/New_York',
            'America/Chicago',
            'America/Denver',
            'America/Los_Angeles',
            'Europe/London',
            'Europe/Paris',
            'Europe/Berlin',
            'Asia/Tokyo',
            'Asia/Shanghai',
            'Asia/Kolkata',
            'Australia/Sydney',
        ]
        
        timezone_list = []
        for tz_name in common_timezones:
            try:
                tz = pytz.timezone(tz_name)
                now = tz.localize(pytz.datetime.datetime.now())
                offset = now.utcoffset().total_seconds() / 3600
                
                timezone_list.append({
                    'name': tz_name,
                    'display_name': tz_name.replace('_', ' '),
                    'offset': offset,
                    'offset_str': f"UTC{'+' if offset >= 0 else ''}{offset:.1f}"
                })
            except:
                continue
        
        return JsonResponse({
            'success': True,
            'timezones': timezone_list
        })
        
    except Exception as e:
        logger.error(f"Error getting timezone list: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get timezone list'
        }, status=500)
