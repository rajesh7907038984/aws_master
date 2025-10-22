"""
Simplified Error Handling System
Provides clean, simple error handling for database operations
"""

import logging
from typing import Dict, Any
from django.http import JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError, IntegrityError, OperationalError

logger = logging.getLogger(__name__)

class SimpleErrorHandler:
    """Simple, effective error handling system"""
    
    @staticmethod
    def handle_database_error(error: Exception) -> JsonResponse:
        """Handle database-related errors"""
        if isinstance(error, IntegrityError):
            return JsonResponse({
                'error': 'Data conflict',
                'message': 'The operation conflicts with existing data'
            }, status=409)
        elif isinstance(error, OperationalError):
            return JsonResponse({
                'error': 'Database connection error',
                'message': 'Database connection failed'
            }, status=503)
        else:
            return JsonResponse({
                'error': 'Database error', 
                'message': 'A database error occurred'
            }, status=500)
    
    @staticmethod
    def handle_permission_error(error: PermissionDenied) -> JsonResponse:
        """Handle permission errors"""
        return JsonResponse({
            'error': 'Permission denied',
            'message': 'You do not have permission to perform this action'
        }, status=403)
    
    @staticmethod
    def handle_validation_error(error: ValidationError) -> JsonResponse:
        """Handle validation errors"""
        return JsonResponse({
            'error': 'Validation error',
            'message': str(error)
        }, status=400)