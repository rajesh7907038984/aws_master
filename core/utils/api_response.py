"""
Standardized API Response Utilities
Provides consistent API response formats across all endpoints
"""

from django.http import JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError
import logging
import traceback
import json
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

class APIResponse:
    """
    Standardized API response handler
    """
    
    @staticmethod
    def success(data: Any = None, message: str = "Success", status_code: int = 200) -> JsonResponse:
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
            "success": True,
            "message": message,
            "data": data,
            "error": None,
            "error_type": None
        }
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def error(
        message: str = "An error occurred", 
        error_type: str = "generic_error",
        data: Any = None,
        status_code: int = 400,
        details: Optional[str] = None
    ) -> JsonResponse:
        """
        Create a standardized error response
        
        Args:
            message: Error message
            error_type: Type of error
            data: Additional data
            status_code: HTTP status code
            details: Additional error details
            
        Returns:
            JsonResponse: Standardized error response
        """
        response_data = {
            "success": False,
            "message": message,
            "data": data,
            "error": message,
            "error_type": error_type,
            "details": details
        }
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def validation_error(
        errors: Union[Dict, str], 
        message: str = "Validation failed"
    ) -> JsonResponse:
        """
        Create a standardized validation error response
        
        Args:
            errors: Validation errors
            message: Error message
            
        Returns:
            JsonResponse: Standardized validation error response
        """
        return APIResponse.error(
            message=message,
            error_type="validation_error",
            data=errors,
            status_code=400,
            details="Please check your input and try again"
        )
    
    @staticmethod
    def permission_denied(
        message: str = "Permission denied",
        details: str = "You don't have permission to perform this action"
    ) -> JsonResponse:
        """
        Create a standardized permission denied response
        
        Args:
            message: Error message
            details: Additional details
            
        Returns:
            JsonResponse: Standardized permission denied response
        """
        return APIResponse.error(
            message=message,
            error_type="permission_denied",
            status_code=403,
            details=details
        )
    
    @staticmethod
    def not_found(
        message: str = "Resource not found",
        details: str = "The requested resource does not exist"
    ) -> JsonResponse:
        """
        Create a standardized not found response
        
        Args:
            message: Error message
            details: Additional details
            
        Returns:
            JsonResponse: Standardized not found response
        """
        return APIResponse.error(
            message=message,
            error_type="not_found",
            status_code=404,
            details=details
        )
    
    @staticmethod
    def server_error(
        message: str = "Internal server error",
        details: str = "Server error occurred - Our team has been notified. Please try again in a few minutes"
    ) -> JsonResponse:
        """
        Create a standardized server error response
        
        Args:
            message: Error message
            details: Additional details
            
        Returns:
            JsonResponse: Standardized server error response
        """
        return APIResponse.error(
            message=message,
            error_type="server_error",
            status_code=500,
            details=details
        )
    
    # COMMENTED OUT CSRF ERROR METHOD TO FIX ERRORS
    # @staticmethod
    # def csrf_error(
    #     message: str = "Session token expired. Please refresh the page and try again.",
    #     details: str = "Your Session session has expired. The page will automatically refresh to restore access."
    # ) -> JsonResponse:
    #     """
    #     Create a standardized CSRF error response
    #     
    #     Args:
    #         message: Error message
    #         details: Additional details
    #         
    #     Returns:
    #         JsonResponse: Standardized CSRF error response
    #     """
    #     response = APIResponse.error(
    #         message=message,
    #         error_type="csrf_error",
    #         status_code=403,
    #         details=details
    #     )
    #     
    #     # Add automatic refresh instruction for frontend
    #     response_data = json.loads(response.content)
    #     response_data['action_required'] = 'refresh'
    #     response_data['auto_refresh_seconds'] = 5
    #     
    #     return JsonResponse(response_data, status=403)


def handle_api_exception(exception: Exception, request=None) -> JsonResponse:
    """
    Handle exceptions and return standardized API responses
    
    Args:
        exception: The exception that occurred
        request: The request object (optional)
        
    Returns:
        JsonResponse: Standardized error response
    """
    # Log the exception
    logger.error(f"API Exception: {str(exception)}", exc_info=True)
    
    # Handle specific exception types
    if isinstance(exception, ValidationError):
        return APIResponse.validation_error(
            errors=str(exception),
            message="Validation failed"
        )
    
    elif isinstance(exception, PermissionDenied):
        return APIResponse.permission_denied(
            message="Permission denied",
            details="You don't have permission to perform this action"
        )
    
    elif isinstance(exception, DatabaseError):
        return APIResponse.server_error(
            message="Database error",
            details="A database error occurred. Please try again later"
        )
    
    elif hasattr(exception, 'status_code'):
        # Handle HTTP exceptions
        if exception.status_code == 404:
            return APIResponse.not_found()
        elif exception.status_code == 403:
            return APIResponse.permission_denied()
        else:
            return APIResponse.error(
                message=str(exception),
                error_type="http_error",
                status_code=exception.status_code
            )
    
    else:
        # Generic server error
        return APIResponse.server_error(
            message="An unexpected error occurred",
            details="Please try again later or contact support if the problem persists"
        )


def api_view_wrapper(view_func):
    """
    Decorator to wrap API views with standardized error handling
    
    Args:
        view_func: The view function to wrap
        
    Returns:
        Wrapped view function
    """
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception as e:
            return handle_api_exception(e, request)
    
    return wrapper


# Convenience functions for common responses
def success_response(data=None, message="Success", status_code=200):
    """Convenience function for success responses"""
    return APIResponse.success(data, message, status_code)

def error_response(message="An error occurred", error_type="generic_error", status_code=400):
    """Convenience function for error responses"""
    return APIResponse.error(message, error_type, status_code=status_code)

def validation_response(errors, message="Validation failed"):
    """Convenience function for validation error responses"""
    return APIResponse.validation_error(errors, message)
