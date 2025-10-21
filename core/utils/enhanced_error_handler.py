"""
Enhanced Error Handler for LMS
Comprehensive error handling to prevent 500 errors and provide better user experience
"""

import logging
import traceback
from typing import Any, Dict, Optional, Union, Callable
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.core.exceptions import ValidationError, PermissionDenied, ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError, OperationalError
from django.contrib.auth.models import AnonymousUser
from django.shortcuts import render
from functools import wraps
import json

logger = logging.getLogger(__name__)

class EnhancedErrorHandler:
    """Enhanced error handling with specific fixes for common 500 errors"""
    
    ERROR_TYPES = {
        'DATABASE_CONNECTION': 'database_connection_error',
        'DATABASE_OPERATION': 'database_operation_error', 
        'FILE_PROCESSING': 'file_processing_error',
        'PERMISSION_DENIED': 'permission_error',
        'VALIDATION_ERROR': 'validation_error',
        'EXTERNAL_SERVICE': 'external_service_error',
        'MEMORY_ERROR': 'memory_error',
        'TIMEOUT_ERROR': 'timeout_error',
        'GENERIC_ERROR': 'generic_error'
    }
    
    @classmethod
    def handle_database_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle database-related errors with specific fixes"""
        error_type = cls._classify_database_error(error)
        
        logger.error(f"Database error in {context}: {str(error)}", exc_info=True)
        
        # Check if it's a connection error
        if isinstance(error, OperationalError) and 'connection' in str(error).lower():
            return cls._handle_connection_error(error, context, request)
        
        # Check if it's an integrity error
        if isinstance(error, IntegrityError):
            return cls._handle_integrity_error(error, context, request)
        
        # Generic database error
        return cls._create_error_response(
            error_type='DATABASE_OPERATION',
            message='Database operation failed. Please try again.',
            details='A database error occurred while processing your request.',
            status_code=500,
            request=request
        )
    
    @classmethod
    def handle_file_processing_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle file processing errors with specific fixes"""
        logger.error(f"File processing error in {context}: {str(error)}", exc_info=True)
        
        # Check for specific file processing errors
        if 'excel' in str(error).lower() or 'xlsx' in str(error).lower():
            return cls._handle_excel_processing_error(error, context, request)
        
        if 'pdf' in str(error).lower():
            return cls._handle_pdf_processing_error(error, context, request)
        
        if 'image' in str(error).lower() or 'photo' in str(error).lower():
            return cls._handle_image_processing_error(error, context, request)
        
        return cls._create_error_response(
            error_type='FILE_PROCESSING',
            message='File processing failed. Please check your file and try again.',
            details='There was an error processing your file.',
            status_code=500,
            request=request
        )
    
    @classmethod
    def handle_permission_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle permission-related errors"""
        logger.warning(f"Permission error in {context}: {str(error)}")
        
        return cls._create_error_response(
            error_type='PERMISSION_DENIED',
            message='You do not have permission to perform this action.',
            details='Please contact your administrator if you believe this is an error.',
            status_code=403,
            request=request
        )
    
    @classmethod
    def handle_validation_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle validation errors"""
        logger.warning(f"Validation error in {context}: {str(error)}")
        
        return cls._create_error_response(
            error_type='VALIDATION_ERROR',
            message='Please check your input and try again.',
            details=str(error),
            status_code=400,
            request=request
        )
    
    @classmethod
    def handle_external_service_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle external service errors"""
        logger.error(f"External service error in {context}: {str(error)}", exc_info=True)
        
        return cls._create_error_response(
            error_type='EXTERNAL_SERVICE',
            message='External service temporarily unavailable. Please try again later.',
            details='A required external service is currently unavailable.',
            status_code=503,
            request=request
        )
    
    @classmethod
    def handle_generic_error(cls, error: Exception, context: str = "", request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Handle generic errors with proper logging"""
        logger.error(f"Unexpected error in {context}: {str(error)}", exc_info=True)
        
        return cls._create_error_response(
            error_type='GENERIC_ERROR',
            message='An unexpected error occurred. Please try again.',
            details='Our team has been notified and is working to fix this issue.',
            status_code=500,
            request=request
        )
    
    @classmethod
    def _classify_database_error(cls, error: Exception) -> str:
        """Classify database error type"""
        error_str = str(error).lower()
        
        if 'connection' in error_str or 'connect' in error_str:
            return 'DATABASE_CONNECTION'
        elif 'integrity' in error_str or 'constraint' in error_str:
            return 'DATABASE_INTEGRITY'
        elif 'timeout' in error_str:
            return 'DATABASE_TIMEOUT'
        else:
            return 'DATABASE_OPERATION'
    
    @classmethod
    def _handle_connection_error(cls, error: Exception, context: str, request: Optional[HttpRequest]) -> Union[JsonResponse, HttpResponse]:
        """Handle database connection errors"""
        return cls._create_error_response(
            error_type='DATABASE_CONNECTION',
            message='Database connection failed. Please try again in a few moments.',
            details='The database is temporarily unavailable.',
            status_code=503,
            request=request
        )
    
    @classmethod
    def _handle_integrity_error(cls, error: Exception, context: str, request: Optional[HttpRequest]) -> Union[JsonResponse, HttpResponse]:
        """Handle database integrity errors"""
        return cls._create_error_response(
            error_type='DATABASE_INTEGRITY',
            message='Data integrity violation. Please check your input.',
            details='The operation would violate data constraints.',
            status_code=400,
            request=request
        )
    
    @classmethod
    def _handle_excel_processing_error(cls, error: Exception, context: str, request: Optional[HttpRequest]) -> Union[JsonResponse, HttpResponse]:
        """Handle Excel processing errors"""
        # Check if it's a library availability issue
        if 'openpyxl' in str(error) or 'xlrd' in str(error):
            return cls._create_error_response(
                error_type='FILE_PROCESSING',
                message='Excel processing library not available. Please contact support.',
                details='Required Excel processing library is not installed.',
                status_code=500,
                request=request
            )
        
        return cls._create_error_response(
            error_type='FILE_PROCESSING',
            message='Excel file processing failed. Please check your file format.',
            details='The Excel file could not be processed.',
            status_code=400,
            request=request
        )
    
    @classmethod
    def _handle_pdf_processing_error(cls, error: Exception, context: str, request: Optional[HttpRequest]) -> Union[JsonResponse, HttpResponse]:
        """Handle PDF processing errors"""
        if 'pdfplumber' in str(error) or 'PyPDF2' in str(error):
            return cls._create_error_response(
                error_type='FILE_PROCESSING',
                message='PDF processing library not available. Please contact support.',
                details='Required PDF processing library is not installed.',
                status_code=500,
                request=request
            )
        
        return cls._create_error_response(
            error_type='FILE_PROCESSING',
            message='PDF file processing failed. Please check your file.',
            details='The PDF file could not be processed.',
            status_code=400,
            request=request
        )
    
    @classmethod
    def _handle_image_processing_error(cls, error: Exception, context: str, request: Optional[HttpRequest]) -> Union[JsonResponse, HttpResponse]:
        """Handle image processing errors"""
        return cls._create_error_response(
            error_type='FILE_PROCESSING',
            message='Image processing failed. Please check your image file.',
            details='The image file could not be processed.',
            status_code=400,
            request=request
        )
    
    @classmethod
    def _create_error_response(cls, error_type: str, message: str, details: str, 
                              status_code: int, request: Optional[HttpRequest] = None) -> Union[JsonResponse, HttpResponse]:
        """Create standardized error response"""
        is_ajax = request and request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': message,
                'error_type': error_type,
                'details': details,
                'status_code': status_code
            }, status=status_code)
        else:
            # For non-AJAX requests, return error page
            context = {
                'error_message': message,
                'error_details': details,
                'error_type': error_type,
                'status_code': status_code
            }
            return render(request, 'core/error.html', context, status=status_code)

def enhanced_error_handler(view_func):
    """Decorator for enhanced error handling"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except DatabaseError as e:
            return EnhancedErrorHandler.handle_database_error(e, f"{view_func.__name__}", request)
        except ValidationError as e:
            return EnhancedErrorHandler.handle_validation_error(e, f"{view_func.__name__}", request)
        except PermissionDenied as e:
            return EnhancedErrorHandler.handle_permission_error(e, f"{view_func.__name__}", request)
        except FileNotFoundError as e:
            return EnhancedErrorHandler.handle_file_processing_error(e, f"{view_func.__name__}", request)
        except Exception as e:
            return EnhancedErrorHandler.handle_generic_error(e, f"{view_func.__name__}", request)
    return wrapper

def safe_database_operation(operation_func: Callable, context: str = "", request: Optional[HttpRequest] = None):
    """Safely execute database operations with error handling"""
    try:
        return operation_func()
    except DatabaseError as e:
        return EnhancedErrorHandler.handle_database_error(e, context, request)
    except Exception as e:
        return EnhancedErrorHandler.handle_generic_error(e, context, request)

def safe_file_operation(operation_func: Callable, context: str = "", request: Optional[HttpRequest] = None):
    """Safely execute file operations with error handling"""
    try:
        return operation_func()
    except (FileNotFoundError, IOError, OSError) as e:
        return EnhancedErrorHandler.handle_file_processing_error(e, context, request)
    except Exception as e:
        return EnhancedErrorHandler.handle_generic_error(e, context, request)
