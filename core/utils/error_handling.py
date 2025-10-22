"""
Standardized Error Handling Utilities
Provides consistent error handling across the LMS platform
"""

import logging
import traceback
from typing import Dict, Any, Optional, Union
from django.http import JsonResponse, HttpResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Centralized error handling for the LMS platform"""
    
    # Error type mappings
    ERROR_TYPES = {
        'validation': 'VALIDATION_ERROR',
        'permission': 'PERMISSION_DENIED',
        'database': 'DATABASE_ERROR',
        'integrity': 'INTEGRITY_ERROR',
        'authentication': 'AUTHENTICATION_ERROR',
        'not_found': 'NOT_FOUND',
        'server': 'SERVER_ERROR',
        'client': 'CLIENT_ERROR',
    }
    
    @classmethod
    def handle_exception(cls, exception: Exception, request=None, context: Dict[str, Any] = None) -> JsonResponse:
        """
        Handle exceptions with standardized error responses
        
        Args:
            exception: The exception to handle
            request: Django request object (optional)
            context: Additional context for error handling
            
        Returns:
            JsonResponse with standardized error format
        """
        context = context or {}
        
        # Log the error with context
        cls._log_error(exception, request, context)
        
        # Determine error type and response
        if isinstance(exception, ValidationError):
            return cls._handle_validation_error(exception, request)
        elif isinstance(exception, PermissionDenied):
            return cls._handle_permission_error(exception, request)
        elif isinstance(exception, (DatabaseError, IntegrityError)):
            return cls._handle_database_error(exception, request)
        elif isinstance(exception, ValueError):
            return cls._handle_client_error(exception, request)
        else:
            return cls._handle_server_error(exception, request)
    
    @classmethod
    def _log_error(cls, exception: Exception, request=None, context: Dict[str, Any] = None):
        """Log error with detailed context"""
        error_context = {
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'traceback': traceback.format_exc(),
        }
        
        if request:
            error_context.update({
                'path': request.path,
                'method': request.method,
                'user': getattr(request, 'user', None),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'remote_addr': request.META.get('REMOTE_ADDR', ''),
            })
        
        if context:
            error_context.update(context)
        
        # Log based on error severity
        if isinstance(exception, (DatabaseError, IntegrityError)):
            logger.error(f"Database error: {error_context}")
        elif isinstance(exception, ValidationError):
            logger.warning(f"Validation error: {error_context}")
        elif isinstance(exception, PermissionDenied):
            logger.warning(f"Permission denied: {error_context}")
        else:
            logger.error(f"Unexpected error: {error_context}")
    
    @classmethod
    def _handle_validation_error(cls, exception: ValidationError, request=None) -> JsonResponse:
        """Handle validation errors"""
        error_data = {
            'error': cls.ERROR_TYPES['validation'],
            'message': 'Validation failed',
            'details': str(exception),
            'status_code': 400,
        }
        
        # Add field-specific errors if available
        if hasattr(exception, 'error_dict'):
            error_data['field_errors'] = exception.error_dict
        
        return JsonResponse(error_data, status=400)
    
    @classmethod
    def _handle_permission_error(cls, exception: PermissionDenied, request=None) -> JsonResponse:
        """Handle permission denied errors"""
        return JsonResponse({
            'error': cls.ERROR_TYPES['permission'],
            'message': 'Permission denied',
            'details': str(exception),
            'status_code': 403,
        }, status=403)
    
    @classmethod
    def _handle_database_error(cls, exception: Union[DatabaseError, IntegrityError], request=None) -> JsonResponse:
        """Handle database errors"""
        error_type = cls.ERROR_TYPES['integrity'] if isinstance(exception, IntegrityError) else cls.ERROR_TYPES['database']
        
        return JsonResponse({
            'error': error_type,
            'message': 'Database operation failed',
            'details': 'A database error occurred. Please try again.',
            'status_code': 500,
        }, status=500)
    
    @classmethod
    def _handle_client_error(cls, exception: ValueError, request=None) -> JsonResponse:
        """Handle client errors (bad requests)"""
        return JsonResponse({
            'error': cls.ERROR_TYPES['client'],
            'message': 'Invalid request',
            'details': str(exception),
            'status_code': 400,
        }, status=400)
    
    @classmethod
    def _handle_server_error(cls, exception: Exception, request=None) -> JsonResponse:
        """Handle server errors"""
        return JsonResponse({
            'error': cls.ERROR_TYPES['server'],
            'message': 'Internal server error',
            'details': 'Server error occurred - Our team has been automatically notified. Please try again in a few minutes.',
            'status_code': 500,
        }, status=500)
    
    @classmethod
    def create_success_response(cls, data: Any = None, message: str = "Success", status_code: int = 200) -> JsonResponse:
        """Create standardized success response"""
        response_data = {
            'success': True,
            'message': message,
            'status_code': status_code,
        }
        
        if data is not None:
            response_data['data'] = data
        
        return JsonResponse(response_data, status=status_code)
    
    @classmethod
    def create_error_response(cls, error_type: str, message: str, details: str = None, 
                           status_code: int = 400, field_errors: Dict = None) -> JsonResponse:
        """Create standardized error response"""
        response_data = {
            'error': error_type,
            'message': message,
            'status_code': status_code,
        }
        
        if details:
            response_data['details'] = details
        
        if field_errors:
            response_data['field_errors'] = field_errors
        
        return JsonResponse(response_data, status=status_code)


def handle_api_exception(exception: Exception, request=None) -> JsonResponse:
    """Convenience function for API error handling"""
    return ErrorHandler.handle_exception(exception, request)


def safe_view_execution(view_func):
    """
    Decorator for safe view execution with standardized error handling
    """
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return ErrorHandler.handle_exception(e, request)
    return wrapper


def safe_model_operation(operation_func):
    """
    Decorator for safe model operations with error handling
    """
    def wrapper(*args, **kwargs):
        try:
            return operation_func(*args, **kwargs)
        except (ValidationError, IntegrityError) as e:
            logger.error(f"Model operation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in model operation: {str(e)}")
            raise
    return wrapper
