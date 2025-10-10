"""
Core Views Package
Contains session management and other core view modules
"""

# Import session management views
from .session_management import (
    session_heartbeat,
    session_warning,
    session_extend,
    session_status
)

# Import main views from the parent views.py file
# Note: We avoid circular imports by importing directly from the parent module
# when needed, rather than importing everything at module level

# Define functions to avoid circular imports
def health_check(request):
    """Health check endpoint - will be overridden by parent views.py"""
    from django.http import JsonResponse
    return JsonResponse({'status': 'error', 'message': 'Health check not available'})

def custom_404_view(request, exception=None):
    """Custom 404 view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('404 - Page not found', status=404)

def custom_500_view(request, exception=None):
    """Custom 500 view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('500 - Server error', status=500)

def custom_403_view(request, exception=None):
    """Custom 403 view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('403 - Permission denied', status=403)

def terms_of_service(request):
    """Terms of service view - renders the terms template"""
    from django.shortcuts import render
    return render(request, 'core/terms_of_service.html')

def privacy_policy(request):
    """Privacy policy view - renders the privacy template"""
    from django.shortcuts import render
    return render(request, 'core/privacy_policy.html')

def error_log(request):
    """Error log view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('Error Log', status=200)

def calendar_activities(request):
    """Calendar activities view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('Calendar Activities', status=200)

# Calendar API functions - actual implementation
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@login_required
def api_calendar_activities(request):
    """Get activities for calendar view"""
    try:
        from core.utils.calendar_service import CalendarService
        
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        calendar_service = CalendarService(request.user)
        
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                activities = calendar_service.get_user_calendar_data(start_date, end_date)
            except ValueError:
                activities = calendar_service.get_user_calendar_data()
        else:
            activities = calendar_service.get_user_calendar_data()
        
        # Convert activities to JSON-serializable format
        serialized_activities = []
        for activity in activities:
            serialized_activity = {
                'title': activity['title'],
                'date': activity['date'].strftime('%Y-%m-%d'),
                'type': activity['type'],
                'priority': activity.get('priority', 'medium'),
                'status': activity.get('status', 'pending'),
                'url': activity.get('url', '#'),
                'description': activity.get('description', ''),
                'course': activity.get('course', ''),
                'icon': activity.get('icon', 'default')
            }
            if 'time' in activity and activity['time']:
                serialized_activity['time'] = activity['time'].strftime('%H:%M')
            serialized_activities.append(serialized_activity)
        
        return JsonResponse({
            'success': True,
            'activities': serialized_activities
        })
    except Exception as e:
        logger.error(f"Error in api_calendar_activities: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def api_daily_activities(request, date_str):
    """Get activities for specific date"""
    try:
        from core.utils.calendar_service import CalendarService
        
        # Parse the date string
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=400)
        
        calendar_service = CalendarService(request.user)
        activities = calendar_service.get_daily_activities(date)
        
        # Convert activities to JSON-serializable format
        serialized_activities = []
        for activity in activities:
            serialized_activity = {
                'title': activity['title'],
                'date': activity['date'].strftime('%Y-%m-%d'),
                'type': activity['type'],
                'priority': activity.get('priority', 'medium'),
                'status': activity.get('status', 'pending'),
                'url': activity.get('url', '#'),
                'description': activity.get('description', ''),
                'course': activity.get('course', ''),
                'icon': activity.get('icon', 'default')
            }
            if 'time' in activity and activity['time']:
                serialized_activity['time'] = activity['time'].strftime('%H:%M')
            serialized_activities.append(serialized_activity)
        
        return JsonResponse({
            'success': True,
            'date': date_str,
            'activities': serialized_activities
        })
    except Exception as e:
        logger.error(f"Error in api_daily_activities: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def api_calendar_summary(request):
    """Get calendar summary data"""
    try:
        from core.utils.calendar_service import CalendarService
        
        calendar_service = CalendarService(request.user)
        
        # Get activities for the next 30 days
        today = timezone.now().date()
        activities = calendar_service.get_user_calendar_data(today, today + timedelta(days=30))
        
        # Calculate summary statistics
        total_events = len(activities)
        upcoming_events = len([a for a in activities if a['date'] >= today])
        overdue_tasks = len([a for a in activities if a['date'] < today and a.get('status') != 'completed'])
        
        return JsonResponse({
            'success': True,
            'summary': {
                'total_events': total_events,
                'upcoming_events': upcoming_events,
                'overdue_tasks': overdue_tasks
            }
        })
    except Exception as e:
        logger.error(f"Error in api_calendar_summary: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def log_client_error(request):
    """Log client error view - actual implementation"""
    from django.http import JsonResponse
    import json
    from django.views.decorators.csrf import csrf_exempt
    from django.views.decorators.http import require_http_methods
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        data = json.loads(request.body) if request.body else {}
        error_message = data.get('message', 'No message')
        error_url = data.get('url', 'Unknown URL')
        error_line = data.get('line', 'Unknown line')
        
        logger.error(f"Client Error: {error_message} at {error_url}:{error_line}")
        
        return JsonResponse({'status': 'success', 'message': 'Error logged'})
    except Exception as e:
        logger.error(f"Error logging client error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': 'Failed to log error'}, status=500)

def csrf_failure(request, reason=""):
    """CSRF failure view - will be overridden by parent views.py"""
    from django.http import HttpResponse
    return HttpResponse('CSRF Failure', status=403)

def test_sidebar(request):
    """Test view for sidebar expand button functionality"""
    from django.shortcuts import render
    return render(request, 'test_sidebar_expand.html')

def ping_view(request):
    """Simple ping endpoint for health checks"""
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    
    return JsonResponse({
        'status': 'ok',
        'message': 'LMS server is running',
        'authenticated': request.user.is_authenticated if hasattr(request, 'user') else False
    })

# API functions for device time sync and remote login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.utils import timezone
from django.shortcuts import redirect
import json
import logging
import pytz
from datetime import datetime
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

logger = logging.getLogger(__name__)

@csrf_protect
@require_http_methods(["POST"])
def sync_device_time(request):
    """
    API endpoint to sync device time with server
    Handles timezone synchronization for better user experience
    """
    try:
        data = json.loads(request.body)
        client_time = data.get('client_time')
        timezone_name = data.get('timezone')
        
        if not client_time:
            return JsonResponse({
                'error': 'Client time is required'
            }, status=400)
        
        # Parse client time
        try:
            client_datetime = datetime.fromisoformat(client_time.replace('Z', '+00:00'))
        except ValueError:
            return JsonResponse({
                'error': 'Invalid time format'
            }, status=400)
        
        # Get server time
        server_time = timezone.now()
        
        # Calculate time difference
        time_diff = (client_datetime - server_time).total_seconds()
        
        # Store timezone if provided and user is authenticated
        if request.user.is_authenticated and timezone_name:
            try:
                # Validate timezone
                pytz.timezone(timezone_name)
                # Store user timezone preference
                request.user.timezone = timezone_name
                request.user.save(update_fields=['timezone'])
            except pytz.exceptions.UnknownTimeZoneError:
                return JsonResponse({
                    'error': 'Invalid timezone'
                }, status=400)
        
        return JsonResponse({
            'success': True,
            'server_time': server_time.isoformat(),
            'client_time': client_time,
            'time_difference': time_diff,
            'timezone_synced': bool(timezone_name and request.user.is_authenticated)
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Device time sync error: {e}")
        return JsonResponse({
            'error': 'Internal server error'
        }, status=500)

@csrf_protect
@require_http_methods(["GET", "POST"])
def remote_login(request):
    """
    Remote login endpoint for external authentication
    Provides a simple login interface for remote access
    """
    if request.method == 'GET':
        # Return login form or redirect to main login
        return redirect('login')
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                return JsonResponse({
                    'error': 'Username and password are required'
                }, status=400)
            
            # Authenticate user
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                if user.is_active:
                    # Log the user in
                    login(request, user)
                    
                    return JsonResponse({
                        'success': True,
                        'user_id': user.id,
                        'username': user.username,
                        'redirect_url': '/dashboard/'
                    })
                else:
                    return JsonResponse({
                        'error': 'Account is disabled'
                    }, status=403)
            else:
                return JsonResponse({
                    'error': 'Invalid credentials'
                }, status=401)
                
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            logger.error(f"Remote login error: {e}")
            return JsonResponse({
                'error': 'Internal server error'
            }, status=500)
