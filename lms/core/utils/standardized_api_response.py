"""
Standardized API Response Utility for 100% Frontend-Backend Alignment
This module provides consistent API response formatting across the entire LMS
"""

from typing import Any, Dict, List, Optional, Union
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
import logging

logger = logging.getLogger(__name__)

class StandardizedAPIResponse:
    """
    Standardized API response format for 100% frontend-backend alignment
    """
    
    # Standard HTTP status codes
    SUCCESS = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503
    
    # Standard response structure
    @staticmethod
    def success(
        data: Any = None,
        message: str = "Operation completed successfully",
        status_code: int = SUCCESS,
        meta: Optional[Dict] = None
    ) -> JsonResponse:
        """
        Standard success response format
        """
        response_data = {
            "success": True,
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": None,  # Will be set by middleware
            "version": "1.0.0"
        }
        
        if meta:
            response_data["meta"] = meta
            
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def error(
        message: str = "An error occurred",
        errors: Optional[Dict] = None,
        status_code: int = BAD_REQUEST,
        error_code: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> JsonResponse:
        """
        Standard error response format
        """
        response_data = {
            "success": False,
            "status": "error",
            "message": message,
            "errors": errors or {},
            "timestamp": None,  # Will be set by middleware
            "version": "1.0.0"
        }
        
        if error_code:
            response_data["error_code"] = error_code
            
        if details:
            response_data["details"] = details
            
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def validation_error(
        errors: Dict,
        message: str = "Validation failed",
        status_code: int = UNPROCESSABLE_ENTITY
    ) -> JsonResponse:
        """
        Standard validation error response
        """
        return StandardizedAPIResponse.error(
            message=message,
            errors=errors,
            status_code=status_code,
            error_code="VALIDATION_ERROR"
        )
    
    @staticmethod
    def not_found(
        message: str = "Resource not found",
        resource: str = "Resource"
    ) -> JsonResponse:
        """
        Standard not found response
        """
        return StandardizedAPIResponse.error(
            message=f"{resource} not found",
            status_code=StandardizedAPIResponse.NOT_FOUND,
            error_code="NOT_FOUND"
        )
    
    @staticmethod
    def unauthorized(
        message: str = "Authentication required"
    ) -> JsonResponse:
        """
        Standard unauthorized response
        """
        return StandardizedAPIResponse.error(
            message=message,
            status_code=StandardizedAPIResponse.UNAUTHORIZED,
            error_code="UNAUTHORIZED"
        )
    
    @staticmethod
    def forbidden(
        message: str = "Access denied"
    ) -> JsonResponse:
        """
        Standard forbidden response
        """
        return StandardizedAPIResponse.error(
            message=message,
            status_code=StandardizedAPIResponse.FORBIDDEN,
            error_code="FORBIDDEN"
        )
    
    @staticmethod
    def server_error(
        message: str = "Internal server error",
        details: Optional[Dict] = None
    ) -> JsonResponse:
        """
        Standard server error response
        """
        return StandardizedAPIResponse.error(
            message=message,
            status_code=StandardizedAPIResponse.INTERNAL_SERVER_ERROR,
            error_code="SERVER_ERROR",
            details=details
        )

class APIResponseMiddleware:
    """
    Middleware to add timestamp and standardize all API responses
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Only process JSON responses
        if (hasattr(response, 'content_type') and 
            'application/json' in response.content_type and
            hasattr(response, 'content')):
            
            try:
                import json
                from django.utils import timezone
                
                # Parse existing response
                data = json.loads(response.content.decode('utf-8'))
                
                # Add timestamp if not present
                if 'timestamp' not in data:
                    data['timestamp'] = timezone.now().isoformat()
                
                # Ensure version is present
                if 'version' not in data:
                    data['version'] = '1.0.0'
                
                # Update response
                response.content = json.dumps(data, ensure_ascii=False)
                
            except (json.JSONDecodeError, UnicodeDecodeError):
                # If response is not JSON, leave it as is
                pass
        
        return response

# Convenience functions for common responses
def api_success(data=None, message="Success", status_code=200, meta=None):
    """Convenience function for success responses"""
    return StandardizedAPIResponse.success(data, message, status_code, meta)

def api_error(message="Error", errors=None, status_code=400, error_code=None, details=None):
    """Convenience function for error responses"""
    return StandardizedAPIResponse.error(message, errors, status_code, error_code, details)

def api_validation_error(errors, message="Validation failed"):
    """Convenience function for validation errors"""
    return StandardizedAPIResponse.validation_error(errors, message)

def api_not_found(message="Resource not found", resource="Resource"):
    """Convenience function for not found responses"""
    return StandardizedAPIResponse.not_found(message, resource)

def api_unauthorized(message="Authentication required"):
    """Convenience function for unauthorized responses"""
    return StandardizedAPIResponse.unauthorized(message)

def api_forbidden(message="Access denied"):
    """Convenience function for forbidden responses"""
    return StandardizedAPIResponse.forbidden(message)

def api_server_error(message="Internal server error", details=None):
    """Convenience function for server error responses"""
    return StandardizedAPIResponse.server_error(message, details)
