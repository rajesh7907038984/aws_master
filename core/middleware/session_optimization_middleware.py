"""
Session Optimization Middleware
Ensures sessions are only saved when data actually changes
"""

import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class SessionOptimizationMiddleware(MiddlewareMixin):
    """
    Middleware to optimize session saving by only saving when data changes
    """
    
    def process_request(self, request):
        """Store original session data at request start"""
        if hasattr(request, 'session'):
            try:
                # Store a copy of the session data at the start of the request
                # Only access session if it's properly initialized
                request._original_session_data = dict(request.session)
            except (AttributeError, KeyError) as e:
                # Session not yet initialized or database not available
                logger.debug("Session not accessible in process_request: {}".format(e))
                request._original_session_data = {}
    
    def process_response(self, request, response):
        """Only save session if data has actually changed"""
        if hasattr(request, 'session') and hasattr(request, '_original_session_data'):
            # Compare current session data with original
            current_data = dict(request.session)
            original_data = request._original_session_data
            
            # Only save if data has changed
            if current_data != original_data:
                try:
                    request.session.save()
                    logger.debug("Session saved - data changed")
                except Exception as e:
                    logger.error("Error saving session: {}".format(e))
            else:
                logger.debug("Session not saved - no changes detected")
        
        return response
