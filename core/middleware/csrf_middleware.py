"""
Enhanced CSRF Middleware
Handles CSRF token issues and provides better error handling
"""

import logging
from django.middleware.csrf import CsrfViewMiddleware
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger(__name__)


class EnhancedCsrfMiddleware(CsrfViewMiddleware):
    """
    Enhanced CSRF middleware with better error handling and AJAX support
    """
    
    def process_view(self, request, callback, callback_args, callback_kwargs):
        """Process view with enhanced CSRF handling"""
        try:
            # Skip CSRF for certain paths
            if self._should_skip_csrf(request):
                return None
            
            # Handle AJAX requests specially
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return self._handle_ajax_csrf(request, callback, callback_args, callback_kwargs)
            
            # Standard CSRF processing
            return super().process_view(request, callback, callback_args, callback_kwargs)
            
        except Exception as e:
            logger.error(f"CSRF middleware error: {e}")
            return None
    
    def _should_skip_csrf(self, request):
        """Determine if CSRF should be skipped for this request"""
        skip_paths = [
            '/scorm/api/',  # SCORM API endpoints
            '/api/',        # API endpoints
            '/admin/',      # Admin interface
        ]
        
        for path in skip_paths:
            if request.path.startswith(path):
                return True
        
        return False
    
    def _handle_ajax_csrf(self, request, callback, callback_args, callback_kwargs):
        """Handle CSRF for AJAX requests with better error messages"""
        try:
            # Check if CSRF token is present
            csrf_token = request.META.get('HTTP_X_CSRFTOKEN') or request.POST.get('csrfmiddlewaretoken')
            
            if not csrf_token:
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'error': 'CSRF token missing',
                        'message': 'Please refresh the page and try again',
                        'csrf_required': True
                    }, status=403)
                else:
                    return super().process_view(request, callback, callback_args, callback_kwargs)
            
            # Validate CSRF token
            if not self._csrf_token_valid(request, csrf_token):
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'error': 'Invalid CSRF token',
                        'message': 'Your session may have expired. Please refresh the page and try again',
                        'csrf_required': True
                    }, status=403)
                else:
                    return super().process_view(request, callback, callback_args, callback_kwargs)
            
            return None  # CSRF check passed
            
        except Exception as e:
            logger.error(f"AJAX CSRF handling error: {e}")
            return super().process_view(request, callback, callback_args, callback_kwargs)
    
    def _csrf_token_valid(self, request, token):
        """Validate CSRF token"""
        try:
            # Get the session CSRF token
            session_token = request.session.get('csrf_token')
            if not session_token:
                return False
            
            # Compare tokens
            return token == session_token
            
        except Exception as e:
            logger.error(f"CSRF token validation error: {e}")
            return False


class CsrfTokenMiddleware(MiddlewareMixin):
    """
    Middleware to ensure CSRF tokens are available in templates
    """
    
    def process_response(self, request, response):
        """Add CSRF token to response headers for AJAX requests"""
        try:
            # Add CSRF token to response headers for AJAX
            if hasattr(request, 'csrf_token'):
                response['X-CSRFToken'] = str(request.csrf_token)
            
            # Add session info for debugging
            if hasattr(request, 'session') and request.user.is_authenticated:
                response['X-Session-Key'] = request.session.session_key[:8] + '...' if request.session.session_key else 'None'
            
        except Exception as e:
            logger.error(f"CSRF token middleware error: {e}")
        
        return response
