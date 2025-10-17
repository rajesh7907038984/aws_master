"""
Enhanced Error Handler for LMS
=============================

This module provides comprehensive error handling, user feedback,
and error recovery mechanisms for the LMS system.
"""

import logging
import traceback
from typing import Dict, Any, Optional
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.template.loader import render_to_string
from django.template import RequestContext
import json

logger = logging.getLogger(__name__)

class EnhancedErrorHandler:
    """Enhanced error handling with user feedback and recovery"""
    
    def __init__(self):
        self.error_types = {
            'validation': ValidationError,
            'permission': PermissionDenied,
            'database': DatabaseError,
            'integrity': IntegrityError,
        }
    
    def handle_error(self, request, error: Exception, context: Dict[str, Any] = None) -> HttpResponse:
        """Handle errors with appropriate user feedback"""
        error_type = self._classify_error(error)
        error_id = self._generate_error_id()
        
        # Log the error
        self._log_error(error, error_id, context)
        
        # Handle different error types
        if error_type == 'validation':
            return self._handle_validation_error(request, error, error_id)
        elif error_type == 'permission':
            return self._handle_permission_error(request, error, error_id)
        elif error_type == 'database':
            return self._handle_database_error(request, error, error_id)
        else:
            return self._handle_generic_error(request, error, error_id)
    
    def _classify_error(self, error: Exception) -> str:
        """Classify error type"""
        for error_type, error_class in self.error_types.items():
            if isinstance(error, error_class):
                return error_type
        return 'generic'
    
    def _generate_error_id(self) -> str:
        """Generate unique error ID for tracking"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _log_error(self, error: Exception, error_id: str, context: Dict[str, Any] = None):
        """Log error with context"""
        error_info = {
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': timezone.now().isoformat(),
            'context': context or {},
            'traceback': traceback.format_exc()
        }
        
        logger.error(f"Error {error_id}: {error_info}")
        
        # Cache functionality removed - error information no longer cached
    
    def _handle_validation_error(self, request, error: ValidationError, error_id: str) -> HttpResponse:
        """Handle validation errors with user-friendly messages"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Validation Error',
                'message': 'Please check your input and try again.',
                'details': error.message if hasattr(error, 'message') else str(error),
                'error_id': error_id
            }, status=400)
        
        # For HTML requests, show validation error page
        return self._render_error_page(request, {
            'error_type': 'Validation Error',
            'error_message': 'Please check your input and try again.',
            'error_details': error.message if hasattr(error, 'message') else str(error),
            'error_id': error_id,
            'suggestions': [
                'Check that all required fields are filled',
                'Verify that email addresses are valid',
                'Ensure passwords meet requirements'
            ]
        })
    
    def _handle_permission_error(self, request, error: PermissionDenied, error_id: str) -> HttpResponse:
        """Handle permission errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Access Denied',
                'message': 'You do not have permission to perform this action.',
                'error_id': error_id
            }, status=403)
        
        return self._render_error_page(request, {
            'error_type': 'Access Denied',
            'error_message': 'You do not have permission to perform this action.',
            'error_id': error_id,
            'suggestions': [
                'Contact your administrator for access',
                'Check if you are logged in with the correct account',
                'Verify your role has the necessary permissions'
            ]
        })
    
    def _handle_database_error(self, request, error: DatabaseError, error_id: str) -> HttpResponse:
        """Handle database errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Database Error',
                'message': 'A database error occurred. Please try again.',
                'error_id': error_id
            }, status=500)
        
        return self._render_error_page(request, {
            'error_type': 'Database Error',
            'error_message': 'A database error occurred. Please try again.',
            'error_id': error_id,
            'suggestions': [
                'Try refreshing the page',
                'Check your internet connection',
                'Contact support if the problem persists'
            ]
        })
    
    def _handle_generic_error(self, request, error: Exception, error_id: str) -> HttpResponse:
        """Handle generic errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred.',
                'error_id': error_id
            }, status=500)
        
        return self._render_error_page(request, {
            'error_type': 'Internal Server Error',
            'error_message': 'An unexpected error occurred.',
            'error_id': error_id,
            'suggestions': [
                'Try refreshing the page',
                'Clear your browser cache',
                'Contact support if the problem persists'
            ]
        })
    
    def _render_error_page(self, request, error_data: Dict[str, Any]) -> HttpResponse:
        """Render error page with user-friendly information"""
        try:
            # Try to render custom error page
            return render_to_string('core/error_page.html', {
                'error_data': error_data,
                'user': request.user if hasattr(request, 'user') else None
            })
        except:
            # Fallback to simple error response
            return HttpResponse(f"""
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>{error_data['error_type']}</h1>
                <p>{error_data['error_message']}</p>
                <p>Error ID: {error_data['error_id']}</p>
                <ul>
                    {''.join(f'<li>{suggestion}</li>' for suggestion in error_data.get('suggestions', []))}
                </ul>
            </body>
            </html>
            """, status=500)

# Global error handler instance
error_handler = EnhancedErrorHandler()

def handle_view_error(view_func):
    """Decorator to handle errors in views"""
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return error_handler.handle_error(request, e, {
                'view': view_func.__name__,
                'path': request.path,
                'method': request.method
            })
    return wrapper

def safe_api_call(func, *args, **kwargs):
    """Safely call API functions with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }
