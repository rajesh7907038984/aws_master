"""
Unified Error Handling System
Provides consistent error handling across the entire LMS application
"""

import logging
import traceback
from typing import Any, Dict, Optional, Union
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

class UnifiedErrorHandler:
    """Centralized error handling for the LMS application"""
    
    ERROR_TYPES = {
        'VALIDATION': 'validation_error',
        'AUTHENTICATION': 'auth_error', 
        'AUTHORIZATION': 'permission_error',
        'NOT_FOUND': 'not_found_error',
        'SERVER': 'server_error',
        'NETWORK': 'network_error',
        'BUSINESS_LOGIC': 'business_logic_error'
    }
    
    USER_FRIENDLY_MESSAGES = {
        'VALIDATION': 'Please check your input and try again',
        'AUTHENTICATION': 'Please log in to continue',
        'AUTHORIZATION': 'You do not have permission to perform this action',
        'NOT_FOUND': 'The requested resource was not found',
        'SERVER': 'Something went wrong. Please try again later',
        'NETWORK': 'Network error. Please check your connection',
        'BUSINESS_LOGIC': 'This action cannot be completed at this time'
    }
    
    @classmethod
    def handle_error(cls, error: Exception, request: Optional[HttpRequest] = None, 
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle errors with consistent formatting and logging
        
        Args:
            error: The exception that occurred
            request: The HTTP request (optional)
            context: Additional context information (optional)
            
        Returns:
            Dict containing error information
        """
        error_type = cls._classify_error(error)
        error_id = cls._generate_error_id()
        
        # Prepare error context
        error_context = {
            'error_id': error_id,
            'error_type': error_type,
            'error_class': error.__class__.__name__,
            'error_message': str(error),
            'user_friendly_message': cls.USER_FRIENDLY_MESSAGES.get(error_type, 'An error occurred'),
            'timestamp': cls._get_timestamp(),
            'context': context or {}
        }
        
        # Add request information if available
        if request:
            error_context.update({
                'user': cls._get_user_info(request),
                'path': request.path,
                'method': request.method,
                'ip': cls._get_client_ip(request)
            })
        
        # Log the error
        cls._log_error(error, error_context)
        
        return error_context
    
    @classmethod
    def create_error_response(cls, error: Exception, request: Optional[HttpRequest] = None,
                            context: Optional[Dict[str, Any]] = None) -> Union[JsonResponse, HttpResponse]:
        """
        Create a standardized error response
        
        Args:
            error: The exception that occurred
            request: The HTTP request (optional)
            context: Additional context information (optional)
            
        Returns:
            HTTP response with error information
        """
        error_info = cls.handle_error(error, request, context)
        
        # Determine if this is an AJAX request
        is_ajax = request and request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': error_info['user_friendly_message'],
                'error_type': error_info['error_type'],
                'error_id': error_info['error_id']
            }, status=cls._get_http_status_code(error_info['error_type']))
        else:
            # For non-AJAX requests, return a simple error page
            from django.shortcuts import render
            return render(request, 'core/error.html', {
                'error_message': error_info['user_friendly_message'],
                'error_id': error_info['error_id']
            })
    
    @classmethod
    def _classify_error(cls, error: Exception) -> str:
        """Classify the type of error"""
        if isinstance(error, ValidationError):
            return 'VALIDATION'
        elif isinstance(error, PermissionDenied):
            return 'AUTHORIZATION'
        elif 'authentication' in str(error).lower() or 'login' in str(error).lower():
            return 'AUTHENTICATION'
        elif 'not found' in str(error).lower() or 'does not exist' in str(error).lower():
            return 'NOT_FOUND'
        elif 'network' in str(error).lower() or 'connection' in str(error).lower():
            return 'NETWORK'
        else:
            return 'SERVER'
    
    @classmethod
    def _generate_error_id(cls) -> str:
        """Generate a unique error ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    @classmethod
    def _get_timestamp(cls) -> str:
        """Get current timestamp"""
        from django.utils import timezone
        return timezone.now().isoformat()
    
    @classmethod
    def _get_user_info(cls, request: HttpRequest) -> Dict[str, Any]:
        """Get user information from request"""
        if hasattr(request, 'user') and request.user.is_authenticated:
            return {
                'id': request.user.id,
                'username': request.user.username,
                'role': getattr(request.user, 'role', 'unknown')
            }
        return {'id': None, 'username': 'Anonymous', 'role': 'anonymous'}
    
    @classmethod
    def _get_client_ip(cls, request: HttpRequest) -> str:
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
    
    @classmethod
    def _get_http_status_code(cls, error_type: str) -> int:
        """Get appropriate HTTP status code for error type"""
        status_codes = {
            'VALIDATION': 400,
            'AUTHENTICATION': 401,
            'AUTHORIZATION': 403,
            'NOT_FOUND': 404,
            'SERVER': 500,
            'NETWORK': 503,
            'BUSINESS_LOGIC': 422
        }
        return status_codes.get(error_type, 500)
    
    @classmethod
    def _log_error(cls, error: Exception, error_context: Dict[str, Any]) -> None:
        """Log error with appropriate level"""
        log_message = f"Error {error_context['error_id']}: {error_context['error_message']}"
        
        if error_context['error_type'] in ['VALIDATION', 'AUTHENTICATION', 'AUTHORIZATION']:
            logger.warning(log_message, extra=error_context)
        else:
            logger.error(log_message, extra=error_context, exc_info=True)

# Convenience functions for easy use
def handle_error(error: Exception, request: Optional[HttpRequest] = None, 
                context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Handle an error and return error information"""
    return UnifiedErrorHandler.handle_error(error, request, context)

def create_error_response(error: Exception, request: Optional[HttpRequest] = None,
                        context: Optional[Dict[str, Any]] = None) -> Union[JsonResponse, HttpResponse]:
    """Create a standardized error response"""
    return UnifiedErrorHandler.create_error_response(error, request, context)
