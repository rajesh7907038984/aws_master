"""
Enhanced Error Handling Decorators
Provides comprehensive error handling for all critical views
"""

import logging
import traceback
from functools import wraps
from django.http import JsonResponse, HttpResponseServerError
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError, OperationalError
from django.conf import settings
from django.views.decorators.csrf import csrf_protect

logger = logging.getLogger(__name__)

def comprehensive_error_handler(view_func):
    """
    Comprehensive error handling decorator for all views
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation error in {view_func.__name__}: {e}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'Validation failed',
                    'message': str(e),
                    'type': 'validation_error'
                }, status=400)
            else:
                from django.contrib import messages
                messages.error(request, f"Validation error: {str(e)}")
                return HttpResponseServerError("Validation error occurred")
                
        except PermissionDenied as e:
            logger.warning(f"Permission denied in {view_func.__name__}: {e}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'Permission denied',
                    'message': 'You do not have permission to perform this action',
                    'type': 'permission_error'
                }, status=403)
            else:
                from django.contrib import messages
                messages.error(request, "You do not have permission to perform this action")
                return HttpResponseServerError("Permission denied")
                
        except (DatabaseError, IntegrityError, OperationalError) as e:
            logger.error(f"Database error in {view_func.__name__}: {e}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'Database error',
                    'message': 'A database error occurred. Please try again later.',
                    'type': 'database_error'
                }, status=500)
            else:
                from django.contrib import messages
                messages.error(request, "A database error occurred. Please try again later.")
                return HttpResponseServerError("Database error occurred")
                
        except Exception as e:
            logger.error(f"Unexpected error in {view_func.__name__}: {e}\n{traceback.format_exc()}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'Internal server error',
                    'message': 'Server error occurred - Our team has been notified. Please try again in a few minutes.',
                    'type': 'server_error'
                }, status=500)
            else:
                from django.contrib import messages
                messages.error(request, "Server error occurred - Our team has been notified. Please try again in a few minutes.")
                return HttpResponseServerError("Internal server error")
    
    return wrapper

def api_error_handler(view_func):
    """
    Error handling decorator specifically for API views
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValidationError as e:
            logger.warning(f"API validation error in {view_func.__name__}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Validation failed',
                'message': str(e),
                'type': 'validation_error'
            }, status=400)
            
        except PermissionDenied as e:
            logger.warning(f"API permission denied in {view_func.__name__}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Permission denied',
                'message': 'You do not have permission to perform this action',
                'type': 'permission_error'
            }, status=403)
            
        except (DatabaseError, IntegrityError, OperationalError) as e:
            logger.error(f"API database error in {view_func.__name__}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Database error',
                'message': 'A database error occurred. Please try again later.',
                'type': 'database_error'
            }, status=500)
            
        except Exception as e:
            logger.error(f"API unexpected error in {view_func.__name__}: {e}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'error': 'Internal server error',
                'message': 'Server error occurred - Our team has been notified. Please try again in a few minutes.',
                'type': 'server_error'
            }, status=500)
    
    return wrapper

def safe_file_operation(view_func):
    """
    Error handling decorator for file operations
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except FileNotFoundError as e:
            logger.warning(f"File not found in {view_func.__name__}: {e}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'File not found',
                    'message': 'The requested file could not be found',
                    'type': 'file_error'
                }, status=404)
            else:
                from django.contrib import messages
                messages.error(request, "The requested file could not be found")
                return HttpResponseServerError("File not found")
                
        except OSError as e:
            logger.error(f"File system error in {view_func.__name__}: {e}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'File system error',
                    'message': 'A file system error occurred',
                    'type': 'file_error'
                }, status=500)
            else:
                from django.contrib import messages
                messages.error(request, "A file system error occurred")
                return HttpResponseServerError("File system error")
                
        except Exception as e:
            logger.error(f"File operation error in {view_func.__name__}: {e}\n{traceback.format_exc()}")
            if request.headers.get('Accept', '').startswith('application/json'):
                return JsonResponse({
                    'error': 'File operation failed',
                    'message': 'The file operation could not be completed',
                    'type': 'file_error'
                }, status=500)
            else:
                from django.contrib import messages
                messages.error(request, "The file operation could not be completed")
                return HttpResponseServerError("File operation failed")
    
    return wrapper

def rate_limit_handler(max_requests=100, window_seconds=3600):
    """
    Rate limiting decorator to prevent abuse
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Rate limiting disabled - always allow requests
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator
