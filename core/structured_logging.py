"""
Structured logging utilities for better debugging and monitoring
"""

import logging
import json
import traceback
from typing import Dict, Any, Optional
from django.http import HttpRequest
from django.contrib.auth.models import User

class StructuredLogger:
    """Enhanced logger with structured output"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _create_context(self, 
                       user: Optional[User] = None,
                       request: Optional[HttpRequest] = None,
                       extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create structured context for logging"""
        context = {}
        
        if user:
            context.update({
                'user_id': user.id,
                'username': user.username,
                'user_email': user.email
            })
        
        if request:
            context.update({
                'request_method': request.method,
                'request_path': request.path,
                'request_ip': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'session_id': request.session.session_key
            })
        
        if extra_data:
            context.update(extra_data)
        
        return context
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def info(self, message: str, 
             user: Optional[User] = None,
             request: Optional[HttpRequest] = None,
             extra_data: Optional[Dict[str, Any]] = None):
        """Log info message with context"""
        context = self._create_context(user, request, extra_data)
        self.logger.info(f"{message} | Context: {json.dumps(context)}")
    
    def error(self, message: str,
              exception: Optional[Exception] = None,
              user: Optional[User] = None,
              request: Optional[HttpRequest] = None,
              extra_data: Optional[Dict[str, Any]] = None):
        """Log error message with context and exception details"""
        context = self._create_context(user, request, extra_data)
        
        if exception:
            context.update({
                'exception_type': type(exception).__name__,
                'exception_message': str(exception),
                'traceback': traceback.format_exc()
            })
        
        self.logger.error(f"{message} | Context: {json.dumps(context)}")
    
    def warning(self, message: str,
                user: Optional[User] = None,
                request: Optional[HttpRequest] = None,
                extra_data: Optional[Dict[str, Any]] = None):
        """Log warning message with context"""
        context = self._create_context(user, request, extra_data)
        self.logger.warning(f"{message} | Context: {json.dumps(context)}")
    
    def debug(self, message: str,
              user: Optional[User] = None,
              request: Optional[HttpRequest] = None,
              extra_data: Optional[Dict[str, Any]] = None):
        """Log debug message with context"""
        context = self._create_context(user, request, extra_data)
        self.logger.debug(f"{message} | Context: {json.dumps(context)}")

auth_logger = StructuredLogger('auth')
api_logger = StructuredLogger('api')
security_logger = StructuredLogger('security')
