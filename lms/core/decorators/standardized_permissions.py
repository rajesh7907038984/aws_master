
# Standardized Permission Decorator
from functools import wraps
from django.http import JsonResponse
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

def require_permission(permission_func):
    """
    Standardized permission decorator for consistent error handling
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            try:
                # Check permission
                if not permission_func(request.user, *args, **kwargs):
                    logger.warning(f"Permission denied for user {request.user.id} in {view_func.__name__}")
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': 'You do not have permission to perform this action.',
                            'error_type': 'permission_denied'
                        }, status=403)
                    else:
                        messages.error(request, 'You do not have permission to perform this action.')
                        return HttpResponseRedirect('/')
                
                return view_func(request, *args, **kwargs)
                
            except Exception as e:
                logger.error(f"Permission check error in {view_func.__name__}: {e}")
                return JsonResponse({
                    'success': False,
                    'error': 'Permission check failed.'
                }, status=500)
        
        return wrapper
    return decorator
