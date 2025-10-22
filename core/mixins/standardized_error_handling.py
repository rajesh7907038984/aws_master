"""
Standardized Error Handling Mixin for Django Views
Provides consistent error handling across all LMS views
"""

import logging
from django.http import JsonResponse, HttpResponseServerError
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.contrib.auth.decorators import login_required
from functools import wraps
import traceback

logger = logging.getLogger(__name__)


class StandardizedErrorHandlingMixin:
    """
    Mixin that provides standardized error handling for all views
    """
    
    def handle_error(self, request, error, context=None):
        """
        Standardized error handling method
        """
        error_context = context or {}
        error_context.update({
            'user': getattr(request, 'user', None),
            'path': getattr(request, 'path', 'unknown'),
            'method': getattr(request, 'method', 'unknown'),
        })
        
        # Log the error with context
        logger.error(f"Error in {self.__class__.__name__}: {str(error)}", 
                    extra=error_context, exc_info=True)
        
        # Determine error type and response
        if isinstance(error, ValidationError):
            return self.handle_validation_error(request, error)
        elif isinstance(error, PermissionDenied):
            return self.handle_permission_error(request, error)
        elif isinstance(error, (DatabaseError, IntegrityError)):
            return self.handle_database_error(request, error)
        else:
            return self.handle_generic_error(request, error)
    
    def handle_validation_error(self, request, error):
        """Handle validation errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Validation failed',
                'details': error.message if hasattr(error, 'message') else str(error),
                'type': 'validation_error'
            }, status=400)
        else:
            return HttpResponseServerError("Validation error occurred. Please check your input.")
    
    def handle_permission_error(self, request, error):
        """Handle permission denied errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Permission denied',
                'details': 'You do not have permission to perform this action.',
                'type': 'permission_error'
            }, status=403)
        else:
            return HttpResponseServerError("Permission denied.")
    
    def handle_database_error(self, request, error):
        """Handle database errors"""
        logger.error(f"Database error: {str(error)}", exc_info=True)
        
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Database error',
                'details': 'A database error occurred. Please try again later.',
                'type': 'database_error'
            }, status=500)
        else:
            return HttpResponseServerError("Database error occurred. Please try again later.")
    
    def handle_generic_error(self, request, error):
        """Handle generic errors"""
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'error': 'Internal server error',
                'details': 'An unexpected error occurred. Please try again later.',
                'type': 'server_error'
            }, status=500)
        else:
            return HttpResponseServerError("An unexpected error occurred. Please try again later.")


def standardized_error_handler(view_func):
    """
    Decorator for standardized error handling on view functions
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as error:
            # Create a temporary mixin instance for error handling
            mixin = StandardizedErrorHandlingMixin()
            return mixin.handle_error(request, error)
    
    return wrapper


def api_error_handler(view_func):
    """
    Decorator specifically for API views that always return JSON
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValidationError as error:
            return JsonResponse({
                'error': 'Validation failed',
                'details': error.message if hasattr(error, 'message') else str(error),
                'type': 'validation_error'
            }, status=400)
        except PermissionDenied as error:
            return JsonResponse({
                'error': 'Permission denied',
                'details': 'You do not have permission to perform this action.',
                'type': 'permission_error'
            }, status=403)
        except (DatabaseError, IntegrityError) as error:
            logger.error(f"Database error in API view: {str(error)}", exc_info=True)
            return JsonResponse({
                'error': 'Database error',
                'details': 'A database error occurred. Please try again later.',
                'type': 'database_error'
            }, status=500)
        except Exception as error:
            logger.error(f"Unexpected error in API view: {str(error)}", exc_info=True)
            return JsonResponse({
                'error': 'Internal server error',
                'details': 'An unexpected error occurred. Please try again later.',
                'type': 'server_error'
            }, status=500)
    
    return wrapper


class ErrorResponse:
    """
    Standardized error response class
    """
    
    @staticmethod
    def validation_error(message, details=None):
        return {
            'error': 'Validation failed',
            'message': message,
            'details': details,
            'type': 'validation_error'
        }
    
    @staticmethod
    def permission_error(message="Permission denied"):
        return {
            'error': 'Permission denied',
            'message': message,
            'type': 'permission_error'
        }
    
    @staticmethod
    def database_error(message="Database error occurred"):
        return {
            'error': 'Database error',
            'message': message,
            'type': 'database_error'
        }
    
    @staticmethod
    def server_error(message="Internal server error"):
        return {
            'error': 'Internal server error',
            'message': message,
            'type': 'server_error'
        }
