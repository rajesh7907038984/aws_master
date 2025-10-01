"""
Core views for health checks, debugging, and navigation
"""

from django.http import JsonResponse, Http404, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
# from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
from django.views.decorators.http import require_http_methods, require_POST
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
# from django.views.decorators.csrf import csrf_failure as django_csrf_failure
from users.models import CustomUser
from core.utils.calendar_service import CalendarService
from datetime import datetime, timedelta
import json
import logging
import pytz

logger = logging.getLogger(__name__)

# COMMENTED OUT CSRF FAILURE VIEW TO FIX ERRORS
# def csrf_failure(request, reason=""):
#     """
#     Custom CSRF failure view that provides better error handling
#     """
#     logger.warning(f"CSRF failure: {reason} for {request.path}")
#     
#     # For API requests, return JSON response
#     if request.path.startswith('/api/') or request.content_type == 'application/json':
#         return JsonResponse({
#             'error': 'CSRF token missing or incorrect',
#             'detail': 'Please refresh the page and try again',
#             'reason': str(reason)
#         }, status=403)
#     
#     # For regular requests, redirect to login or show error page
#     if not request.user.is_authenticated:
#         return redirect('login')
#     
#     # For authenticated users, show a friendly error page
#     return render(request, 'core/csrf_error.html', {
#         'reason': reason,
#         'user': request.user
#     }, status=403)

# @csrf_exempt  # COMMENTED OUT TO FIX ERRORS
def ping_view(request):
    """Simple ping endpoint for health checks"""
    return JsonResponse({
        'status': 'ok',
        'message': 'LMS server is running',
        'authenticated': request.user.is_authenticated if hasattr(request, 'user') else False
    })

# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
@require_http_methods(["POST"])
def error_log(request):
    """Log client-side errors"""
    try:
        data = json.loads(request.body)
        error_message = data.get('message', '')
        error_stack = data.get('stack', '')
        error_url = data.get('url', '')
        
        logger.error(f"Client Error: {error_message} | URL: {error_url} | Stack: {error_stack}")
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error logging failed: {str(e)}")
        return JsonResponse({'error': 'Failed to log error'}, status=500)


@require_http_methods(["GET"])
def calendar_activities(request):
    """Calendar activities API endpoint"""
    try:
        # Return empty activities for now - can be expanded later
        activities = []
        return JsonResponse({
            'success': True,
            'activities': activities,
            'message': 'Calendar activities retrieved successfully'
        })
    except Exception as e:
        logger.error(f"Calendar activities error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve calendar activities'
        }, status=500)

@require_http_methods(["GET"])
# @csrf_exempt  # COMMENTED OUT TO FIX ERRORS
def health_check(request):
    """Simple health check endpoint for deployment monitoring"""
    try:
        # Basic health check - just return server status
        return JsonResponse({
            'status': 'ok',
            'message': 'LMS server is running',
            'timestamp': timezone.now().isoformat(),
            'server': 'django',
            'version': '1.0.0'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Health check failed: {str(e)}',
            'timestamp': timezone.now().isoformat()
        }, status=500)


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

# COMMENTED OUT CSRF FAILURE FUNCTION TO FIX ERRORS
# def csrf_failure(request, reason=""):
#     """CSRF failure handling"""
#     return render(request, 'core/csrf_failure.html', {
#         'reason': reason
#     }, status=403)


# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
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


@staff_member_required
def debug_media_info(request):
    """Debug media files information (admin only)"""
    try:
        import os
        from django.conf import settings
        
        media_info = {
            'MEDIA_ROOT': getattr(settings, 'MEDIA_ROOT', 'Not set'),
            'MEDIA_URL': getattr(settings, 'MEDIA_URL', 'Not set'),
            'STATICFILES_STORAGE': getattr(settings, 'STATICFILES_STORAGE', 'Not set'),
            'DEFAULT_FILE_STORAGE': getattr(settings, 'DEFAULT_FILE_STORAGE', 'Not set'),
            'media_root_exists': os.path.exists(getattr(settings, 'MEDIA_ROOT', '')) if getattr(settings, 'MEDIA_ROOT', None) else False,
        }
        
        return JsonResponse(media_info)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)




@login_required
@require_POST
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
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
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
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


# ============================================================================
# ERROR PAGE TESTING VIEWS (DEBUG MODE ONLY)
# ============================================================================

def test_404(request):
    """Test 404 error page"""
    raise Http404("Test 404 error")


def test_500(request):
    """Test 500 error page"""
    raise Exception("Test 500 error")


def test_403(request):
    """Test 403 error page"""
    from django.core.exceptions import PermissionDenied
    raise PermissionDenied("Test 403 error")


def test_custom_404(request):
    """Preview custom 404 page"""
    return render(request, '404.html', status=404)


def test_custom_500(request):
    """Preview custom 500 page"""
    return render(request, '500.html', status=500)


def test_custom_403(request):
    """Preview custom 403 page"""
    return render(request, '403.html', status=403)


# ============================================================================
# CUSTOM ERROR HANDLERS FOR PRODUCTION
# ============================================================================

def custom_404_view(request, exception=None):
    """Custom 404 error handler"""
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


def custom_500_view(request, exception=None):
    """Custom 500 error handler"""
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


def custom_403_view(request, exception=None):
    """Custom 403 error handler"""
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


# ============================================================================
# ERROR HANDLING TEST VIEWS (DEBUG MODE ONLY)
# ============================================================================

def test_error_handling(request):
    """Test all error handling mechanisms"""
    error_type = request.GET.get('type', '500')
    
    if error_type == '404':
        raise Http404("Test 404 error")
    elif error_type == '403':
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Test 403 error")
    elif error_type == 'database':
        # Simulate database error
        raise Exception("Database connection failed")
    elif error_type == 'scorm':
        # Simulate SCORM error  
        raise Exception("SCORM content could not be loaded")
    elif error_type == 'file':
        # Simulate file error
        raise Exception("File upload failed")
    else:
        # Default 500 error
        raise Exception("Test server error")


def terms_of_service(request):
    """Terms of Service page"""
    return render(request, 'core/terms_of_service.html')


def privacy_policy(request):
    """Privacy Policy page"""
    return render(request, 'core/privacy_policy.html')


def chart_debug(request):
    """Chart debugging page for production issue diagnosis"""
    return render(request, 'core/chart_debug_simple.html')

def test_learner_data(request):
    """Test learner dashboard data and chart rendering"""
    # Simulate learner dashboard data
    from users.views import learner_dashboard
    
    # Get the context from learner_dashboard
    if request.user.is_authenticated and request.user.role == 'learner':
        # Call the actual learner_dashboard view to get the data
        from django.http import HttpResponse
        response = learner_dashboard(request)
        if hasattr(response, 'context_data'):
            context = response.context_data
        else:
            # Fallback data
            context = {
                'total_courses': 0,
                'completed_courses': 0,
                'courses_in_progress': 0,
                'courses_not_started': 0,
                'courses_not_passed': 0,
            }
    else:
        # Test data for non-learner users
        context = {
            'total_courses': 5,
            'completed_courses': 2,
            'courses_in_progress': 2,
            'courses_not_started': 1,
            'courses_not_passed': 0,
        }
    
    return render(request, 'core/test_learner_data.html', context)

def minimal_chart_test(request):
    """Minimal chart test to verify Chart.js is working"""
    return render(request, 'core/minimal_chart_test.html')


# COMMENTED OUT CSRF VALIDATION FUNCTION TO FIX ERRORS
# def validate_csrf_token(request):
#     """API endpoint to validate CSRF token for debugging"""
#     if request.method == 'POST':
#         if token and CSRFProtection.validate_csrf_token(request, token):
#             return JsonResponse({
#                 'valid': True,
#                 'message': 'CSRF token is valid'
#             })
#         return JsonResponse({
#             'valid': False,
#             'message': 'CSRF token is invalid or missing'
#         }, status=403)
#     return JsonResponse({
#         'error': 'Method not allowed',
#         'message': 'Only POST requests are allowed'
#     }, status=405)


# COMMENTED OUT CSRF FAILURE FUNCTION TO FIX ERRORS
# def csrf_failure(request, reason=""):
#     """Custom CSRF failure view that provides a more helpful response"""
#     logger.warning(f"CSRF failure for {request.path}: {reason}")
#     
#     # For API requests, return JSON error
#     if request.path.startswith('/api/') or request.headers.get('Accept', '').startswith('application/json'):
#         return JsonResponse({
#             'error': 'CSRF validation failed',
#             'reason': reason,
#             'message': 'Please refresh the page and try again'
#         }, status=403)
#     
#     # For regular requests, render an error page or redirect
#     context = {
#         'reason': reason,
#         'request_path': request.path
#     }
#     return render(request, 'core/csrf_failure.html', context, status=403)


# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
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


# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
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

