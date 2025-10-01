"""
Standardized API Response System for LMS
Provides consistent API response formats across all endpoints
"""

from django.http import JsonResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)

class StandardizedResponse:
    """
    Standardized response system for consistent API responses
    """
    
    @staticmethod
    def success(data=None, message="Operation completed successfully", status_code=200):
        """
        Create a standardized success response
        
        Args:
            data: Response data
            message: Success message
            status_code: HTTP status code
            
        Returns:
            JsonResponse: Standardized success response
        """
        response_data = {
            'success': True,
            'message': message,
            'data': data
        }
        
        # Remove None values
        response_data = {k: v for k, v in response_data.items() if v is not None}
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def error(message="An error occurred", error_code=None, details=None, status_code=400):
        """
        Create a standardized error response
        
        Args:
            message: Error message
            error_code: Specific error code
            details: Additional error details
            status_code: HTTP status code
            
        Returns:
            JsonResponse: Standardized error response
        """
        response_data = {
            'success': False,
            'error': message,
            'error_code': error_code,
            'details': details
        }
        
        # Remove None values
        response_data = {k: v for k, v in response_data.items() if v is not None}
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def permission_denied(message="You do not have permission to perform this action"):
        """
        Create a standardized permission denied response
        
        Args:
            message: Permission denied message
            
        Returns:
            JsonResponse: Permission denied response
        """
        return StandardizedResponse.error(
            message=message,
            error_code="PERMISSION_DENIED",
            status_code=403
        )
    
    @staticmethod
    def not_found(message="The requested resource was not found"):
        """
        Create a standardized not found response
        
        Args:
            message: Not found message
            
        Returns:
            JsonResponse: Not found response
        """
        return StandardizedResponse.error(
            message=message,
            error_code="NOT_FOUND",
            status_code=404
        )
    
    @staticmethod
    def validation_error(message="Validation failed", details=None):
        """
        Create a standardized validation error response
        
        Args:
            message: Validation error message
            details: Validation error details
            
        Returns:
            JsonResponse: Validation error response
        """
        return StandardizedResponse.error(
            message=message,
            error_code="VALIDATION_ERROR",
            details=details,
            status_code=400
        )
    
    @staticmethod
    def server_error(message="An internal server error occurred"):
        """
        Create a standardized server error response
        
        Args:
            message: Server error message
            
        Returns:
            JsonResponse: Server error response
        """
        return StandardizedResponse.error(
            message=message,
            error_code="SERVER_ERROR",
            status_code=500
        )
    
    @staticmethod
    def handle_exception(exception, operation="operation"):
        """
        Handle exceptions and return standardized responses
        
        Args:
            exception: Exception object
            operation: Description of the operation that failed
            
        Returns:
            JsonResponse: Standardized error response
        """
        logger.error(f"Exception in {operation}: {str(exception)}", exc_info=True)
        
        if isinstance(exception, PermissionDenied):
            return StandardizedResponse.permission_denied()
        
        elif isinstance(exception, ValidationError):
            return StandardizedResponse.validation_error(
                message="Validation failed",
                details=exception.message_dict if hasattr(exception, 'message_dict') else str(exception)
            )
        
        elif isinstance(exception, IntegrityError):
            return StandardizedResponse.error(
                message="Database integrity error. The operation conflicts with existing data.",
                error_code="INTEGRITY_ERROR",
                status_code=409
            )
        
        else:
            return StandardizedResponse.server_error(
                message=f"An unexpected error occurred during {operation}. Please try again."
            )


def standardized_api_view(view_func):
    """
    Decorator to standardize API view responses
    
    Args:
        view_func: View function to decorate
        
    Returns:
        Decorated view function
    """
    def wrapper(request, *args, **kwargs):
        try:
            response = view_func(request, *args, **kwargs)
            
            # If response is already a JsonResponse, return it
            if isinstance(response, JsonResponse):
                return response
            
            # If response is a dict, wrap it in success response
            if isinstance(response, dict):
                return StandardizedResponse.success(data=response)
            
            # For other responses, return as-is
            return response
            
        except Exception as e:
            return StandardizedResponse.handle_exception(e, view_func.__name__)
    
    return wrapper


def require_permissions(permission_check_func):
    """
    Decorator to require specific permissions for API views
    
    Args:
        permission_check_func: Function to check permissions
        
    Returns:
        Decorated view function
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            try:
                # Check permissions
                if not permission_check_func(request, *args, **kwargs):
                    return StandardizedResponse.permission_denied()
                
                # Call the original view
                return view_func(request, *args, **kwargs)
                
            except Exception as e:
                return StandardizedResponse.handle_exception(e, view_func.__name__)
        
        return wrapper
    return decorator


def validate_required_fields(required_fields):
    """
    Decorator to validate required fields in request data
    
    Args:
        required_fields: List of required field names
        
    Returns:
        Decorated view function
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            try:
                # Get request data
                if request.method == 'GET':
                    data = request.GET
                else:
                    try:
                        import json
                        data = json.loads(request.body) if request.body else {}
                    except json.JSONDecodeError:
                        data = request.POST
                
                # Check required fields
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    return StandardizedResponse.validation_error(
                        message=f"Missing required fields: {', '.join(missing_fields)}",
                        details={"missing_fields": missing_fields}
                    )
                
                # Call the original view
                return view_func(request, *args, **kwargs)
                
            except Exception as e:
                return StandardizedResponse.handle_exception(e, view_func.__name__)
        
        return wrapper
    return decorator
