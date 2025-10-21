"""
Enhanced CSRF Middleware
Provides comprehensive CSRF protection with proper error handling
"""

import logging
from django.middleware.csrf import CsrfViewMiddleware
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class EnhancedCsrfMiddleware(CsrfViewMiddleware):
    """
    Enhanced CSRF middleware with better error handling and logging
    """
    
    def process_view(self, request, callback, callback_args, callback_kwargs):
        # Skip CSRF for certain views that don't need it
        if hasattr(callback, 'csrf_exempt'):
            return None
            
        # Skip CSRF for API endpoints that use token authentication
        if request.path.startswith('/api/') and request.META.get('HTTP_AUTHORIZATION'):
            return None
            
        # Skip CSRF for health check endpoints
        if request.path in ['/health/', '/status/']:
            return None
            
        # Skip CSRF for static files
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return None
            
        return super().process_view(request, callback, callback_args, callback_kwargs)
    
    def process_response(self, request, response):
        # Add CSRF token to response headers for AJAX requests
        if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            csrf_token = getattr(request, 'csrf_token', None)
            if csrf_token:
                response['X-CSRFToken'] = str(csrf_token)
        
        return response


class CsrfErrorMiddleware(MiddlewareMixin):
    """
    Middleware to handle CSRF errors gracefully
    """
    
    def process_exception(self, request, exception):
        if isinstance(exception, Exception) and 'CSRF' in str(exception):
            logger.warning(f"CSRF error for {request.path}: {exception}")
            
            # Check if this is an AJAX/API request
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                request.content_type == 'application/json' or
                'application/json' in request.headers.get('Accept', '') or
                request.path.startswith('/api/')
            )
            
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'error': 'Session expired. Please refresh the page and try again.',
                    'error_type': 'csrf_error',
                    'action_required': 'refresh',
                    'csrf_token_required': True
                }, status=403)
            else:
                # Use the configured CSRF failure view
                from core.views.csrf_failure import csrf_failure
                return csrf_failure(request, str(exception))
        
        return None