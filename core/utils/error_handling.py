"""
Standardized Error Handling Utilities
Provides consistent error handling patterns across the application
"""

import logging
from typing import Any, Dict, Optional, Union
from django.http import JsonResponse, HttpRequest
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Standardized error handling for the LMS application"""
    
    @staticmethod
    def handle_database_error(error: DatabaseError, context: str = "") -> JsonResponse:
        """Handle database-related errors"""
        logger.error(f"Database error in {context}: {str(error)}")
        return JsonResponse({
            'success': False,
            'error': 'Database operation failed',
            'message': 'Please try again later'
        }, status=500)
    
    @staticmethod
    def handle_validation_error(error: ValidationError, context: str = "") -> JsonResponse:
        """Handle validation errors"""
        logger.warning(f"Validation error in {context}: {str(error)}")
        return JsonResponse({
            'success': False,
            'error': 'Validation failed',
            'message': str(error),
            'errors': error.message_dict if hasattr(error, 'message_dict') else [str(error)]
        }, status=400)
    
    @staticmethod
    def handle_permission_error(error: PermissionDenied, context: str = "") -> JsonResponse:
        """Handle permission-related errors"""
        logger.warning(f"Permission denied in {context}: {str(error)}")
        return JsonResponse({
            'success': False,
            'error': 'Permission denied',
            'message': 'You do not have permission to perform this action'
        }, status=403)
    
    @staticmethod
    def handle_integrity_error(error: IntegrityError, context: str = "") -> JsonResponse:
        """Handle database integrity errors"""
        logger.error(f"Integrity error in {context}: {str(error)}")
        return JsonResponse({
            'success': False,
            'error': 'Data integrity violation',
            'message': 'The operation would violate data constraints'
        }, status=400)
    
    @staticmethod
    def handle_generic_error(error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> JsonResponse:
        """Handle generic exceptions with proper logging"""
        # Log the full error for debugging
        logger.error(f"Unexpected error in {context}: {str(error)}", exc_info=True)
        
        # Determine if this is an AJAX request
        is_ajax = request and request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': 'An unexpected error occurred',
                'message': 'Please try again later'
            }, status=500)
        else:
            # For non-AJAX requests, we might want to redirect or show a different response
            return JsonResponse({
                'success': False,
                'error': 'An unexpected error occurred',
                'message': 'Please try again later'
            }, status=500)
    
    @staticmethod
    def handle_api_exception(error: Exception, request: HttpRequest, context: str = "") -> Union[JsonResponse, Response]:
        """Main error handler that routes to specific handlers"""
        if isinstance(error, ValidationError):
            return ErrorHandler.handle_validation_error(error, context)
        elif isinstance(error, PermissionDenied):
            return ErrorHandler.handle_permission_error(error, context)
        elif isinstance(error, IntegrityError):
            return ErrorHandler.handle_integrity_error(error, context)
        elif isinstance(error, DatabaseError):
            return ErrorHandler.handle_database_error(error, context)
        else:
            return ErrorHandler.handle_generic_error(error, context, request)


def safe_execute(func, *args, context: str = "", request: Optional[HttpRequest] = None, **kwargs):
    """
    Safely execute a function with standardized error handling
    
    Args:
        func: Function to execute
        *args: Arguments for the function
        context: Context description for logging
        request: HTTP request object
        **kwargs: Keyword arguments for the function
    
    Returns:
        Tuple of (success: bool, result: Any, error_response: Optional[JsonResponse])
    """
    try:
        result = func(*args, **kwargs)
        return True, result, None
    except Exception as e:
        error_response = ErrorHandler.handle_api_exception(e, request, context)
        return False, None, error_response


def validate_required_fields(data: Dict[str, Any], required_fields: list) -> Optional[JsonResponse]:
    """
    Validate that required fields are present in data
    
    Args:
        data: Dictionary to validate
        required_fields: List of required field names
    
    Returns:
        JsonResponse with error if validation fails, None if successful
    """
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        return JsonResponse({
            'success': False,
            'error': 'Missing required fields',
            'message': f'The following fields are required: {", ".join(missing_fields)}',
            'missing_fields': missing_fields
        }, status=400)
    
    return None


def validate_user_permissions(user, required_permissions: list) -> Optional[JsonResponse]:
    """
    Validate user has required permissions
    
    Args:
        user: User object to validate
        required_permissions: List of required permissions
    
    Returns:
        JsonResponse with error if validation fails, None if successful
    """
    if isinstance(user, AnonymousUser):
        return JsonResponse({
            'success': False,
            'error': 'Authentication required',
            'message': 'You must be logged in to perform this action'
        }, status=401)
    
    # Check if user has required role
    if 'role' in required_permissions and user.role not in required_permissions['role']:
        return JsonResponse({
            'success': False,
            'error': 'Insufficient permissions',
            'message': f'This action requires one of the following roles: {", ".join(required_permissions["role"])}'
        }, status=403)
    
    return None
