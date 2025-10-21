"""
Comprehensive Error Handling Middleware
Prevents 500 errors and provides better error handling
"""

import logging
import traceback
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError, OperationalError
from django.shortcuts import render
from core.utils.error_monitoring import monitor_error
from core.utils.enhanced_error_handler import EnhancedErrorHandler

logger = logging.getLogger(__name__)

class ComprehensiveErrorMiddleware:
    """Middleware to handle all types of errors comprehensively"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            return self.handle_exception(request, e)
    
    def handle_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle all exceptions with comprehensive error handling"""
        
        # Log the error with monitoring
        monitor_error(
            error_type=type(exception).__name__,
            error_message=str(exception),
            context={
                'path': request.path,
                'method': request.method,
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown'),
                'user_id': getattr(request.user, 'id', None) if hasattr(request, 'user') else None,
                'traceback': traceback.format_exc()
            },
            severity='error',
            user_id=getattr(request.user, 'id', None) if hasattr(request, 'user') else None
        )
        
        # Handle specific error types
        if isinstance(exception, DatabaseError):
            return self._handle_database_error(request, exception)
        elif isinstance(exception, ValidationError):
            return self._handle_validation_error(request, exception)
        elif isinstance(exception, PermissionDenied):
            return self._handle_permission_error(request, exception)
        elif isinstance(exception, FileNotFoundError):
            return self._handle_file_error(request, exception)
        else:
            return self._handle_generic_error(request, exception)
    
    def _handle_database_error(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle database errors"""
        if isinstance(exception, OperationalError) and 'connection' in str(exception).lower():
            return self._create_error_response(
                request, 
                'Database connection failed',
                'The database is temporarily unavailable. Please try again in a few moments.',
                503,
                'DATABASE_CONNECTION_ERROR'
            )
        elif isinstance(exception, IntegrityError):
            return self._create_error_response(
                request,
                'Data integrity violation',
                'The operation would violate data constraints. Please check your input.',
                400,
                'DATABASE_INTEGRITY_ERROR'
            )
        else:
            return self._create_error_response(
                request,
                'Database operation failed',
                'A database error occurred. Please try again.',
                500,
                'DATABASE_ERROR'
            )
    
    def _handle_validation_error(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle validation errors"""
        return self._create_error_response(
            request,
            'Validation failed',
            'Please check your input and try again.',
            400,
            'VALIDATION_ERROR'
        )
    
    def _handle_permission_error(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle permission errors"""
        return self._create_error_response(
            request,
            'Permission denied',
            'You do not have permission to perform this action.',
            403,
            'PERMISSION_ERROR'
        )
    
    def _handle_file_error(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle file-related errors"""
        return self._create_error_response(
            request,
            'File not found',
            'The requested file could not be found.',
            404,
            'FILE_ERROR'
        )
    
    def _handle_generic_error(self, request: HttpRequest, exception: Exception) -> HttpResponse:
        """Handle generic errors"""
        return self._create_error_response(
            request,
            'Internal server error',
            'An unexpected error occurred. Our team has been notified.',
            500,
            'GENERIC_ERROR'
        )
    
    def _create_error_response(self, request: HttpRequest, error_title: str, 
                              error_message: str, status_code: int, error_type: str) -> HttpResponse:
        """Create standardized error response"""
        
        # Check if it's an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': error_title,
                'message': error_message,
                'error_type': error_type,
                'status_code': status_code
            }, status=status_code)
        else:
            # For non-AJAX requests, return appropriate error page
            if status_code == 404:
                return render(request, '404.html', {
                    'error_title': error_title,
                    'error_message': error_message
                }, status=404)
            elif status_code == 403:
                return render(request, '403.html', {
                    'error_title': error_title,
                    'error_message': error_message
                }, status=403)
            else:
                return render(request, '500.html', {
                    'error_title': error_title,
                    'error_message': error_message,
                    'error_type': error_type
                }, status=status_code)
