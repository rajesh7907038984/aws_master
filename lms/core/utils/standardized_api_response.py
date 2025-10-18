"""
Standardized API Response Utility
Provides consistent API response formatting across the LMS
"""

from django.http import JsonResponse
from typing import Any, Dict, Optional, Union
import logging

logger = logging.getLogger(__name__)

class StandardizedAPIResponse:
    """
    Standardized API response class for consistent error handling
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
            JsonResponse with standardized format
        """
        response_data = {
            'success': True,
            'message': message,
            'data': data,
            'timestamp': None  # Will be set by middleware
        }
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def error(message: str, error_code: str = None, status_code: int = 400, 
              data: Any = None, details: Dict[str, Any] = None) -> JsonResponse:
        """
        Create a standardized error response
        
        Args:
            message: Error message
            error_code: Specific error code for client handling
            status_code: HTTP status code
            data: Additional error data
            details: Detailed error information
            
        Returns:
            JsonResponse with standardized error format
        """
        response_data = {
            'success': False,
            'message': message,
            'error_code': error_code,
            'data': data,
            'details': details,
            'timestamp': None  # Will be set by middleware
        }
        
        # Log error for debugging
        logger.error(f"API Error: {message} (Code: {error_code}, Status: {status_code})")
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def validation_error(errors: Dict[str, Any], message: str = "Validation failed", 
                        status_code: int = 400) -> JsonResponse:
        """
        Create a standardized validation error response
        
        Args:
            errors: Validation errors dictionary
            message: Error message
            status_code: HTTP status code
            
        Returns:
            JsonResponse with validation error format
        """
        response_data = {
            'success': False,
            'message': message,
            'error_code': 'VALIDATION_ERROR',
            'errors': errors,
            'timestamp': None
        }
        
        logger.warning(f"Validation Error: {message} - {errors}")
        
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def not_found(message: str = "Resource not found", status_code: int = 404) -> JsonResponse:
        """
        Create a standardized not found response
        
        Args:
            message: Error message
            status_code: HTTP status code
            
        Returns:
            JsonResponse with not found format
        """
        return StandardizedAPIResponse.error(
            message=message,
            error_code='NOT_FOUND',
            status_code=status_code
        )
    
    @staticmethod
    def unauthorized(message: str = "Authentication required", status_code: int = 401) -> JsonResponse:
        """
        Create a standardized unauthorized response
        
        Args:
            message: Error message
            status_code: HTTP status code
            
        Returns:
            JsonResponse with unauthorized format
        """
        return StandardizedAPIResponse.error(
            message=message,
            error_code='UNAUTHORIZED',
            status_code=status_code
        )
    
    @staticmethod
    def forbidden(message: str = "Permission denied", status_code: int = 403) -> JsonResponse:
        """
        Create a standardized forbidden response
        
        Args:
            message: Error message
            status_code: HTTP status code
            
        Returns:
            JsonResponse with forbidden format
        """
        return StandardizedAPIResponse.error(
            message=message,
            error_code='FORBIDDEN',
            status_code=status_code
        )
    
    @staticmethod
    def server_error(message: str = "Internal server error", status_code: int = 500) -> JsonResponse:
        """
        Create a standardized server error response
        
        Args:
            message: Error message
            status_code: HTTP status code
            
        Returns:
            JsonResponse with server error format
        """
        return StandardizedAPIResponse.error(
            message=message,
            error_code='SERVER_ERROR',
            status_code=status_code
        )

# Convenience functions for backward compatibility
def api_success(data: Any = None, message: str = "Success", status_code: int = 200) -> JsonResponse:
    """Convenience function for success responses"""
    return StandardizedAPIResponse.success(data, message, status_code)

def api_error(message: str, error_code: str = None, status_code: int = 400, 
              data: Any = None, details: Dict[str, Any] = None) -> JsonResponse:
    """Convenience function for error responses"""
    return StandardizedAPIResponse.error(message, error_code, status_code, data, details)

def api_validation_error(errors: Dict[str, Any], message: str = "Validation failed", 
                         status_code: int = 400) -> JsonResponse:
    """Convenience function for validation error responses"""
    return StandardizedAPIResponse.validation_error(errors, message, status_code)