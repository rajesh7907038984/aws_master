"""
Core views for health checks, debugging, and navigation
"""

from django.http import JsonResponse, Http404, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_failure as django_csrf_failure
from users.models import CustomUser
from core.utils.calendar_service import CalendarService
from datetime import datetime, timedelta
import json
import logging
import pytz

logger = logging.getLogger(__name__)

def api_version(request):
    """API endpoint to return system version information"""
    return JsonResponse({
        'version': '1.0.0',
        'build': '2025-10-17',
        'environment': getattr(settings, 'DJANGO_ENV', 'production'),
        'timestamp': timezone.now().isoformat()
    })

def security_txt(request):
    """Security.txt endpoint for responsible disclosure"""
    from django.http import HttpResponse
    from django.conf import settings
    
    # Get security contact from environment variable
    security_contact = getattr(settings, 'SECURITY_CONTACT_EMAIL', 'security@example.com')
    base_url = getattr(settings, 'BASE_URL', 'https://example.com')
    
    security_content = f"""Contact: {security_contact}
Expires: 2026-12-31T23:59:59.000Z
Encryption: {base_url}/pgp-key.txt
Acknowledgments: {base_url}/security-acknowledgments
Preferred-Languages: en
Canonical: {base_url}/.well-known/security.txt
"""
    return HttpResponse(security_content, content_type='text/plain')

@csrf_protect
@require_POST
def log_error(request):
    """Endpoint for JavaScript error logging with CSRF protection"""
    try:
        import json
        data = json.loads(request.body.decode('utf-8'))
        
        # Log the error with appropriate level
        error_message = data.get('message', 'Unknown JavaScript error')
        error_details = data.get('error', {})
        url = data.get('url', request.path)
        user_agent = data.get('userAgent', request.META.get('HTTP_USER_AGENT', ''))
        
        logger.error(f"JavaScript Error: {error_message}")
        logger.error(f"URL: {url}")
        logger.error(f"User Agent: {user_agent}")
        logger.error(f"Error Details: {error_details}")
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error in log_error endpoint: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to log error'}, status=500)


@csrf_protect
def ping_view(request):
    """Simple ping endpoint for health checks"""
    return JsonResponse({
        'status': 'ok',
        'message': 'LMS server is running',
        'authenticated': request.user.is_authenticated if hasattr(request, 'user') else False
    })

@csrf_protect
@require_http_methods(["POST"])
def error_log(request):
    """Log client-side errors with enhanced error handling"""
    try:
        # Validate request body
        if not request.body:
            return JsonResponse({'error': 'Empty request body'}, status=400)
        
        # Parse JSON with enhanced error handling
        try:
            data = json.loads(request.body)
            # Validate required structure
            if not isinstance(data, dict):
                raise ValueError("Request body must be a JSON object")
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in error log request: {}".format(str(e)))
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except ValueError as e:
            logger.error("Invalid data structure in error log request: {}".format(str(e)))
            return JsonResponse({'error': 'Invalid data structure'}, status=400)
        
        # Extract and validate error data
        error_message = data.get('message', '')
        error_stack = data.get('stack', '')
        error_url = data.get('url', '')
        error_timestamp = data.get('timestamp', '')
        
        # Validate required fields
        if not error_message:
            return JsonResponse({'error': 'Error message is required'}, status=400)
        
        # Sanitize error data to prevent log injection
        error_message = error_message[:500]  # Limit length
        error_stack = error_stack[:1000]    # Limit stack trace length
        error_url = error_url[:200]         # Limit URL length
        
        # Log with structured data
        logger.error(f"Client Error: {error_message} | URL: {error_url} | Stack: {error_stack} | Timestamp: {error_timestamp}")
        
        return JsonResponse({'success': True, 'logged': True})
        
    except Exception as e:
        logger.error(f"Error logging failed: {str(e)}")
        return JsonResponse({'error': 'Failed to log error'}, status=500)


@require_http_methods(["GET"])
def calendar_activities(request):
    """Calendar activities API endpoint with enhanced error handling"""
    try:
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)
        
        # Return empty activities for now - can be expanded later
        activities = []
        
        # Log successful request
        logger.info("Calendar activities requested by user: {}".format(request.user.id))
        
        return JsonResponse({
            'success': True,
            'activities': activities,
            'message': 'Calendar activities retrieved successfully',
            'count': len(activities)
        })
        
    except Exception as e:
        logger.error("Calendar activities error: {}".format(str(e)))
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve calendar activities',
            'details': 'Internal server error'
        }, status=500)

@require_http_methods(["GET"])
@csrf_protect
def health_check(request):
    """Comprehensive health check endpoint for deployment monitoring"""
    from core.utils.standardized_api_response import StandardizedAPIResponse
    
    try:
        # Test database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        
        return StandardizedAPIResponse.success(
            data={
                'status': 'healthy',
                'server': 'django',
                'database': 'connected',
                'version': '1.0.0'
            },
            message='All systems operational'
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return StandardizedAPIResponse.server_error(
            message=f"Health check failed: {str(e)}",
            error_code='HEALTH_CHECK_FAILED'
        )


@require_http_methods(["GET"])
def simple_test(request):
    """Simple test endpoint to verify deployment"""
    from django.utils import timezone
    return JsonResponse({
        'status': 'deployment_test',
        'message': 'New code deployed successfully!',
        'timestamp': str(timezone.now()),
        'deployment_version': '2025-08-18-06:45'
    })

# in production environments


# ============================================================================
# NAVIGATION VIEWS - Redirect to appropriate app URLs
# ============================================================================

@login_required
def discussions(request):
    """Redirect to discussions app"""
    return redirect('discussions:discussion_list')


@login_required
def reports(request):
    """Redirect to reports app"""
    return redirect('reports:reports')


@login_required
def outcomes(request):
    """Redirect to outcomes app"""
    return redirect('lms_outcomes:outcomes_index')


@login_required
def rubrics(request):
    """Redirect to rubrics app"""
    return redirect('lms_rubrics:rubric_list')


@login_required
def branches(request):
    """Redirect to branches app"""
    return redirect('branches:branch_list')


@login_required
def quizzes(request):
    """Redirect to quiz app"""
    return redirect('quiz:quiz_list')


@login_required
def assignments(request):
    """Redirect to assignments app"""
    return redirect('assignments:assignment_list')


@login_required
def account(request):
    """Redirect to account settings"""
    return redirect('account_settings:account_settings')


# ============================================================================
# ============================================================================

@login_required
def css_test(request):
    """CSS framework testing page"""
    return render(request, 'core/css_test.html', {
        'title': 'CSS Framework Test'
    })




@login_required
def enhanced_table_demo(request):
    """Enhanced table component demo"""
    return render(request, 'core/table_demo.html', {
        'title': 'Enhanced Table Demo'
    })


@login_required
def ai_content_demo(request):
    """AI content generation demo"""
    return render(request, 'core/ai_demo.html', {
        'title': 'AI Content Demo'
    })


# ============================================================================
# ERROR HANDLING VIEWS
# ============================================================================

def csrf_failure(request, reason=""):
    """CSRF failure handling"""
    try:
        return render(request, 'core/csrf_failure.html', {
            'reason': reason
        }, status=403)
    except Exception as e:
        logger.error(f"CSRF failure template error: {e}")
        from django.http import HttpResponse
        return HttpResponse("CSRF verification failed. Please try again.", status=403)


@csrf_protect
@require_http_methods(["POST"])
def log_client_error(request):
    """Log JavaScript errors from client side"""
    try:
        data = json.loads(request.body) if request.body else {}
        error_message = data.get('message', 'No message')
        error_url = data.get('url', 'Unknown URL')
        error_line = data.get('line', 'Unknown line')
        
        logger.error(f"Client error: {error_message} at {error_url}:{error_line}")
        
        return JsonResponse({'status': 'logged'})
    except Exception as e:
        logger.error(f"Error logging client error: {str(e)}")
        return JsonResponse({'status': 'error'}, status=500)


# Debug function removed for production security




@login_required
@require_POST
@ensure_csrf_cookie
def editor_image_upload(request):
    """TinyMCE image upload handler"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        # This is a simplified implementation
        # Real implementation would handle file uploads for TinyMCE
        return JsonResponse({
            'location': '/static/img/placeholder.png'  # Placeholder image
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
@ensure_csrf_cookie
def editor_video_upload(request):
    """TinyMCE video upload handler"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        # This is a simplified implementation
        # Real implementation would handle video uploads for TinyMCE
        return JsonResponse({
            'location': '/static/video/placeholder.mp4'  # Placeholder video
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# CALENDAR API VIEWS - Full implementations using CalendarService
# ============================================================================

@login_required
def api_calendar_activities(request):
    """Get activities for calendar view"""
    try:
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


# Debug testing views removed for production security


# ============================================================================
# CUSTOM ERROR HANDLERS FOR PRODUCTION
# ============================================================================

def custom_404_view(request, exception=None):
    """Custom 404 error handler with proper error handling"""
    try:
        logger.warning(
            f"404 Error - Page not found: {request.path}",
            extra={
                'path': request.path,
                'method': request.method,
                'user_id': getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
                'referer': request.META.get('HTTP_REFERER', 'Direct'),
                'query_params': dict(request.GET),
            }
        )
        
        context = {
            'error_code': 404,
            'error_title': 'Page Not Found',
            'error_message': 'The page you are looking for could not be found.',
            'request_path': request.path,
        }
        
        return render(request, '404.html', context, status=404)
    except Exception as e:
        logger.error(f"Error in custom_404_view: {e}")
        # Fallback to simple 404 response
        from django.http import HttpResponse
        return HttpResponse("Page not found", status=404)


def custom_500_view(request, exception=None):
    """Custom 500 error handler with proper error handling"""
    try:
        logger.error(
            f"500 Error - Internal server error on {request.path}",
            extra={
                'path': request.path,
                'method': request.method,
                'user_id': getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
                'referer': request.META.get('HTTP_REFERER', 'Direct'),
                'exception': str(exception) if exception else 'Unknown error',
            },
            exc_info=True
        )
        
        context = {
            'error_code': 500,
            'error_title': 'Server Error',
            'error_message': 'We encountered an unexpected error. Our team has been notified and is working to fix it.',
            'request_path': request.path,
        }
        
        return render(request, '500.html', context, status=500)
    except Exception as e:
        logger.error(f"Error in custom_500_view: {e}")
        # Fallback to simple 500 response
        from django.http import HttpResponse
        return HttpResponse("Internal server error", status=500)


def custom_403_view(request, exception=None):
    """Custom 403 error handler with proper error handling"""
    try:
        logger.warning(
            f"403 Error - Permission denied: {request.path}",
            extra={
                'path': request.path,
                'method': request.method,
                'user_id': getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous',
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
                'referer': request.META.get('HTTP_REFERER', 'Direct'),
            }
        )
        
        context = {
            'error_code': 403,
            'error_title': 'Permission Denied',
            'error_message': 'You do not have permission to access this resource.',
            'request_path': request.path,
        }
        
        return render(request, '403.html', context, status=403)
    except Exception as e:
        logger.error(f"Error in custom_403_view: {e}")
        # Fallback to simple 403 response
        from django.http import HttpResponse
        return HttpResponse("Permission denied", status=403)


# Debug error testing views removed for production security


def terms_of_service(request):
    """Terms of Service page"""
    return render(request, 'core/terms_of_service.html')


def privacy_policy(request):
    """Privacy Policy page"""
    return render(request, 'core/privacy_policy.html')


# Debug chart and testing views removed for production security






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
                    from django.contrib.auth import login
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

