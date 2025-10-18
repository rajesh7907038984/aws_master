"""
SCORM Middleware for Enhanced Authentication

This middleware handles authentication for SCORM content that runs in iframes
and may not have proper authentication headers.
"""

import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

class SCORMAuthenticationMiddleware:
    """
    Middleware to handle SCORM authentication for iframe scenarios.
    
    This middleware ensures that SCORM content can access user sessions
    even when loaded in iframes where authentication headers might not
    be properly passed.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if this is a SCORM-related request
        if self.is_scorm_request(request):
            self.handle_scorm_authentication(request)
        
        response = self.get_response(request)
        return response
    
    def is_scorm_request(self, request):
        """Check if this is a SCORM-related request"""
        path = request.path
        return (
            path.startswith('/scorm/') or
            'scorm' in path.lower() or
            'scormcontent' in path.lower()
        )
    
    def handle_scorm_authentication(self, request):
        """Handle authentication for SCORM requests with proper security"""
        # If user is already authenticated, no need to do anything
        if request.user.is_authenticated:
            return
        
        # Try to restore user from session using proper Django authentication
        session_user_id = request.session.get('_auth_user_id')
        if session_user_id:
            try:
                User = get_user_model()
                user = User.objects.get(id=session_user_id, is_active=True)
                # Use proper Django authentication instead of manual assignment
                from django.contrib.auth import login
                login(request, user)
                logger.info("SCORM Middleware: Properly authenticated user {{user.username}} from session")
            except User.DoesNotExist:
                logger.warning("SCORM Middleware: Invalid or inactive session user ID: {{session_user_id}}")
                # Clear invalid session
                request.session.flush()
        
        # Check for referer-based authentication with proper validation
        elif request.META.get('HTTP_REFERER'):
            referer = request.META.get('HTTP_REFERER', '')
            if 'scorm/launch' in referer or 'scorm/content' in referer:
                # Try to get user from session based on referer with proper authentication
                session_user_id = request.session.get('_auth_user_id')
                if session_user_id:
                    try:
                        User = get_user_model()
                        user = User.objects.get(id=session_user_id, is_active=True)
                        from django.contrib.auth import login
                        login(request, user)
                        logger.info("SCORM Middleware: Properly authenticated user {{user.username}} from referer")
                    except User.DoesNotExist:
                        logger.warning("SCORM Middleware: Invalid user from referer: {{session_user_id}}")
                        request.session.flush()
