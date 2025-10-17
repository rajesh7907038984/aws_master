"""
Unified Error Handling System for 100% Frontend-Backend Alignment
This module provides consistent error handling across the entire LMS
"""

from typing import Any, Dict, List, Optional, Union
from django.http import JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.translation import gettext as _
from django.contrib.auth.models import AnonymousUser
import logging
import traceback
from .standardized_api_response import StandardizedAPIResponse

logger = logging.getLogger(__name__)

class UnifiedErrorHandler:
    """
    Unified error handling system for consistent frontend-backend alignment
    """
    
    # Error categories for consistent handling
    ERROR_CATEGORIES = {
        'VALIDATION': 'validation_error',
        'AUTHENTICATION': 'auth_error', 
        'AUTHORIZATION': 'permission_error',
        'NOT_FOUND': 'not_found_error',
        'SERVER': 'server_error',
        'NETWORK': 'network_error',
        'BUSINESS_LOGIC': 'business_logic_error'
    }
    
    # User-friendly error messages
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
    def handle_validation_error(cls, error: ValidationError, context: str = 'Validation') -> JsonResponse:
        """
        Handle Django validation errors with standardized format
        """
        errors = {}
        
        if hasattr(error, 'message_dict'):
            # Form validation errors
            for field, messages in error.message_dict.items():
                errors[field] = list(messages) if isinstance(messages, list) else [str(messages)]
        elif hasattr(error, 'messages'):
            # Single field validation errors
            errors['non_field_errors'] = list(error.messages)
        else:
            # Generic validation error
            errors['non_field_errors'] = [str(error)]
        
        logger.warning(f"{context} validation error: {errors}")
        
        return StandardizedAPIResponse.validation_error(
            errors=errors,
            message=cls.USER_FRIENDLY_MESSAGES['VALIDATION']
        )
    
    @classmethod
    def handle_permission_error(cls, error: PermissionDenied, context: str = 'Permission') -> JsonResponse:
        """
        Handle permission denied errors
        """
        logger.warning(f"{context} permission denied: {str(error)}")
        
        return StandardizedAPIResponse.forbidden(
            message=cls.USER_FRIENDLY_MESSAGES['AUTHORIZATION']
        )
    
    @classmethod
    def handle_not_found_error(cls, error: Exception, resource: str = 'Resource', context: str = 'Not Found') -> JsonResponse:
        """
        Handle not found errors
        """
        logger.warning(f"{context} not found: {str(error)}")
        
        return StandardizedAPIResponse.not_found(
            message=f"{resource} not found",
            resource=resource
        )
    
    @classmethod
    def handle_authentication_error(cls, error: Exception, context: str = 'Authentication') -> JsonResponse:
        """
        Handle authentication errors
        """
        logger.warning(f"{context} authentication error: {str(error)}")
        
        return StandardizedAPIResponse.unauthorized(
            message=cls.USER_FRIENDLY_MESSAGES['AUTHENTICATION']
        )
    
    @classmethod
    def handle_server_error(cls, error: Exception, context: str = 'Server Error') -> JsonResponse:
        """
        Handle server errors with proper logging
        """
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'traceback': traceback.format_exc()
        }
        
        logger.error(f"{context} server error: {error_details}")
        
        return StandardizedAPIResponse.server_error(
            message=cls.USER_FRIENDLY_MESSAGES['SERVER'],
            details={'error_id': f"ERR_{hash(str(error)) % 10000:04d}"}
        )
    
    @classmethod
    def handle_generic_error(cls, error: Exception, context: str = 'Generic Error') -> JsonResponse:
        """
        Handle generic errors with categorization
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Categorize error based on type and message
        if isinstance(error, ValidationError):
            return cls.handle_validation_error(error, context)
        elif isinstance(error, PermissionDenied):
            return cls.handle_permission_error(error, context)
        elif 'not found' in error_message.lower() or 'does not exist' in error_message.lower():
            return cls.handle_not_found_error(error, context=context)
        elif 'authentication' in error_message.lower() or 'login' in error_message.lower():
            return cls.handle_authentication_error(error, context)
        else:
            return cls.handle_server_error(error, context)
    
    @classmethod
    def get_error_category(cls, error: Exception) -> str:
        """
        Determine error category for consistent handling
        """
        if isinstance(error, ValidationError):
            return cls.ERROR_CATEGORIES['VALIDATION']
        elif isinstance(error, PermissionDenied):
            return cls.ERROR_CATEGORIES['AUTHORIZATION']
        elif 'not found' in str(error).lower():
            return cls.ERROR_CATEGORIES['NOT_FOUND']
        elif 'authentication' in str(error).lower():
            return cls.ERROR_CATEGORIES['AUTHENTICATION']
        else:
            return cls.ERROR_CATEGORIES['SERVER']
    
    @classmethod
    def get_user_friendly_message(cls, error: Exception) -> str:
        """
        Get user-friendly error message
        """
        category = cls.get_error_category(error)
        return cls.USER_FRIENDLY_MESSAGES.get(category.split('_')[0], cls.USER_FRIENDLY_MESSAGES['SERVER'])

def unified_error_handler(view_func):
    """
    Decorator for unified error handling in views
    """
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValidationError as e:
            return UnifiedErrorHandler.handle_validation_error(e, f"View: {view_func.__name__}")
        except PermissionDenied as e:
            return UnifiedErrorHandler.handle_permission_error(e, f"View: {view_func.__name__}")
        except Exception as e:
            return UnifiedErrorHandler.handle_generic_error(e, f"View: {view_func.__name__}")
    
    return wrapper

def api_error_handler(view_func):
    """
    Decorator specifically for API views with enhanced error handling
    """
    def wrapper(request, *args, **kwargs):
        try:
            # Check authentication for API endpoints
            if not request.user.is_authenticated and not isinstance(request.user, AnonymousUser):
                return UnifiedErrorHandler.handle_authentication_error(
                    Exception("Authentication required"), 
                    f"API: {view_func.__name__}"
                )
            
            return view_func(request, *args, **kwargs)
        except ValidationError as e:
            return UnifiedErrorHandler.handle_validation_error(e, f"API: {view_func.__name__}")
        except PermissionDenied as e:
            return UnifiedErrorHandler.handle_permission_error(e, f"API: {view_func.__name__}")
        except Exception as e:
            return UnifiedErrorHandler.handle_generic_error(e, f"API: {view_func.__name__}")
    
    return wrapper
