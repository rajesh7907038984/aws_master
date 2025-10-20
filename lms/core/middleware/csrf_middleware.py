"""
Enhanced CSRF Middleware
Provides comprehensive CSRF protection with proper error handling
"""

import logging
from django.middleware.csrf import CsrfViewMiddleware
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

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
            
        return super().process_view(request, callback, callback_args, callback_kwargs)
    
    def process_response(self, request, response):
        # Add CSRF token to response headers for AJAX requests
        if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response['X-CSRFToken'] = request.META.get('CSRF_COOKIE', '')
        
        return response


class CsrfErrorMiddleware(MiddlewareMixin):
    """
    Middleware to handle CSRF errors gracefully
    """
    
    def process_exception(self, request, exception):
        if isinstance(exception, Exception) and 'CSRF' in str(exception):
            logger.warning(f"CSRF error for {request.path}: {exception}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': 'CSRF token missing or incorrect',
                    'detail': 'Please refresh the page and try again'
                }, status=403)
            else:
                # Redirect to login page for non-AJAX requests
                from django.shortcuts import redirect
                return redirect('login')
        
        return None