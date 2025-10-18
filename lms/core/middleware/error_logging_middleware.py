"""
Error Logging Middleware
Automatically logs errors and performance issues
"""

import time
import logging
from django.http import HttpRequest, HttpResponse
from django.conf import settings
from core.utils.error_logging import log_error, error_logger

logger = logging.getLogger(__name__)

class ErrorLoggingMiddleware:
    """Middleware to automatically log errors and performance issues"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Record start time for performance monitoring
        start_time = time.time()
        
        try:
            response = self.get_response(request)
            
            # Log performance issues with memory optimization
            duration = time.time() - start_time
            if duration > 5.0:  # Log if request takes more than 5 seconds
                # Use minimal context to prevent memory leaks
                try:
                    context = {
                        'user': request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous',
                        'ip': self._get_client_ip(request),
                    }
                    error_logger.log_performance_issue(
                        operation=f"{request.method} {request.path}",
                        duration=duration,
                        threshold=5.0,
                        context=context
                    )
                except Exception as log_error:
                    # Prevent logging errors from causing memory leaks
                    logger.error(f"Error logging performance issue: {log_error}")
                    # Clear context to free memory
                    del context
            
            return response
            
        except Exception as e:
            # Log the error with minimal context to prevent memory leaks
            try:
                log_error(
                    error=e,
                    request=request,
                    user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                    context={
                        'middleware': 'ErrorLoggingMiddleware',
                        'duration': time.time() - start_time,
                    },
                    severity='CRITICAL'  # Mark middleware errors as critical
                )
            except Exception as log_error:
                # Prevent logging errors from causing additional issues
                logger.error(f"Error logging middleware exception: {log_error}")
            
            # Re-raise the exception to let Django handle it
            # Don't mask the original exception
            raise
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
