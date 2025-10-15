"""
Comprehensive Error Logging Utilities
Provides enhanced error logging and monitoring for the LMS
"""

import logging
import traceback
import sys
from typing import Any, Dict, Optional, List
from django.conf import settings
from django.http import HttpRequest
from django.contrib.auth import get_user_model
import json
from datetime import datetime

User = get_user_model()

class ErrorLogger:
    """Enhanced error logging with context and monitoring"""
    
    def __init__(self, logger_name: str = 'lms_error'):
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.ERROR)
    
    def log_error(self, 
                  error: Exception, 
                  request: Optional[HttpRequest] = None,
                  user: Optional[User] = None,
                  context: Optional[Dict[str, Any]] = None,
                  severity: str = 'ERROR') -> None:
        """
        Log error with comprehensive context
        
        Args:
            error: The exception that occurred
            request: HTTP request object (if available)
            user: User object (if available)
            context: Additional context dictionary
            severity: Error severity level
        """
        try:
            # Build error context
            error_context = self._build_error_context(error, request, user, context)
            
            # Log with appropriate level
            if severity == 'CRITICAL':
                self.logger.critical(self._format_error_message(error, error_context))
            elif severity == 'WARNING':
                self.logger.warning(self._format_error_message(error, error_context))
            else:
                self.logger.error(self._format_error_message(error, error_context))
                
        except Exception as log_error:
            # Fallback to basic logging if enhanced logging fails
            self.logger.error(f"Error logging failed: {log_error}")
            self.logger.error(f"Original error: {error}")
    
    def _build_error_context(self, 
                           error: Exception, 
                           request: Optional[HttpRequest],
                           user: Optional[User],
                           context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build comprehensive error context"""
        error_context = {
            'timestamp': datetime.now().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
        }
        
        # Add request context
        if request:
            error_context.update({
                'request_method': request.method,
                'request_path': request.path,
                'request_headers': dict(request.headers),
                'request_user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'request_ip': self._get_client_ip(request),
                'request_user': request.user.username if request.user.is_authenticated else 'Anonymous',
            })
        
        # Add user context
        if user:
            error_context.update({
                'user_id': user.id,
                'user_username': user.username,
                'user_email': user.email,
                'user_role': getattr(user, 'role', 'unknown'),
                'user_branch': getattr(user, 'branch', None),
            })
        
        # Add additional context
        if context:
            error_context.update(context)
        
        return error_context
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _format_error_message(self, error: Exception, context: Dict[str, Any]) -> str:
        """Format error message with context"""
        return f"""
ERROR: {type(error).__name__}: {str(error)}
CONTEXT: {json.dumps(context, indent=2, default=str)}
TRACEBACK:
{traceback.format_exc()}
"""
    
    def log_performance_issue(self, 
                             operation: str, 
                             duration: float, 
                             threshold: float = 5.0,
                             context: Optional[Dict[str, Any]] = None) -> None:
        """Log performance issues"""
        if duration > threshold:
            self.logger.warning(f"""
PERFORMANCE ISSUE: {operation} took {duration:.2f}s (threshold: {threshold}s)
CONTEXT: {json.dumps(context or {}, indent=2, default=str)}
""")
    
    def log_security_event(self, 
                          event_type: str, 
                          description: str,
                          request: Optional[HttpRequest] = None,
                          user: Optional[User] = None) -> None:
        """Log security-related events"""
        context = {
            'event_type': event_type,
            'description': description,
            'timestamp': datetime.now().isoformat(),
        }
        
        if request:
            context.update({
                'request_path': request.path,
                'request_ip': self._get_client_ip(request),
                'request_user_agent': request.META.get('HTTP_USER_AGENT', ''),
            })
        
        if user:
            context.update({
                'user_id': user.id,
                'user_username': user.username,
            })
        
        self.logger.warning(f"SECURITY EVENT: {json.dumps(context, indent=2)}")


class DatabaseErrorLogger:
    """Specialized logger for database-related errors"""
    
    def __init__(self):
        self.logger = logging.getLogger('lms_database_error')
        self.logger.setLevel(logging.ERROR)
    
    def log_database_error(self, 
                          error: Exception, 
                          query: Optional[str] = None,
                          operation: Optional[str] = None,
                          context: Optional[Dict[str, Any]] = None) -> None:
        """Log database-specific errors"""
        error_context = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'query': query,
            'operation': operation,
            'timestamp': datetime.now().isoformat(),
        }
        
        if context:
            error_context.update(context)
        
        self.logger.error(f"""
DATABASE ERROR: {type(error).__name__}: {str(error)}
QUERY: {query}
OPERATION: {operation}
CONTEXT: {json.dumps(error_context, indent=2, default=str)}
TRACEBACK:
{traceback.format_exc()}
""")


class SCORMErrorLogger:
    """Specialized logger for SCORM-related errors"""
    
    def __init__(self):
        self.logger = logging.getLogger('lms_scorm_error')
        self.logger.setLevel(logging.ERROR)
    
    def log_scorm_error(self, 
                       error: Exception, 
                       topic_id: Optional[int] = None,
                       scorm_package_id: Optional[int] = None,
                       user_id: Optional[int] = None,
                       context: Optional[Dict[str, Any]] = None) -> None:
        """Log SCORM-specific errors"""
        error_context = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'topic_id': topic_id,
            'scorm_package_id': scorm_package_id,
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
        }
        
        if context:
            error_context.update(context)
        
        self.logger.error(f"""
SCORM ERROR: {type(error).__name__}: {str(error)}
TOPIC ID: {topic_id}
SCORM PACKAGE ID: {scorm_package_id}
USER ID: {user_id}
CONTEXT: {json.dumps(error_context, indent=2, default=str)}
TRACEBACK:
{traceback.format_exc()}
""")


# Global error logger instances
error_logger = ErrorLogger()
database_error_logger = DatabaseErrorLogger()
scorm_error_logger = SCORMErrorLogger()


def log_error(error: Exception, 
              request: Optional[HttpRequest] = None,
              user: Optional[User] = None,
              context: Optional[Dict[str, Any]] = None,
              severity: str = 'ERROR') -> None:
    """Convenience function for logging errors"""
    error_logger.log_error(error, request, user, context, severity)


def log_database_error(error: Exception, 
                      query: Optional[str] = None,
                      operation: Optional[str] = None,
                      context: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function for logging database errors"""
    database_error_logger.log_database_error(error, query, operation, context)


def log_scorm_error(error: Exception, 
                   topic_id: Optional[int] = None,
                   scorm_package_id: Optional[int] = None,
                   user_id: Optional[int] = None,
                   context: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function for logging SCORM errors"""
    scorm_error_logger.log_scorm_error(error, topic_id, scorm_package_id, user_id, context)
