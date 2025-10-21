"""
Session Persistence Middleware
Ensures user sessions are maintained across deployments and server restarts
"""

import logging
from django.contrib.sessions.models import Session
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class SessionPersistenceMiddleware:
    """
    Middleware to ensure session persistence across deployments
    Prevents auto-logout issues after updates and page reloads
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip session persistence for logout requests
        if request.path == '/logout/' and request.method == 'POST':
            return self.get_response(request)
        
        # Save the authenticated state before processing
        was_authenticated = hasattr(request, 'user') and request.user.is_authenticated
        
        # Process request
        response = self.get_response(request)
        
        # Only process authenticated users with sessions
        if was_authenticated and hasattr(request, 'session'):
            try:
                # Create session key if it doesn't exist
                if not request.session.session_key:
                    request.session.create()
                    logger.info("Created new session for user {{request.user.id}}")
                
                session_key = request.session.session_key
                if session_key:
                    # Extend session if it's close to expiry (within 2 hours)
                    session_obj = Session.objects.filter(session_key=session_key).first()
                    if session_obj:
                        # Check if session expires within 2 hours
                        time_until_expiry = session_obj.expire_date - timezone.now()
                        if time_until_expiry < timedelta(hours=2):
                            # Extend session by 24 hours
                            session_obj.expire_date = timezone.now() + timedelta(hours=24)
                            session_obj.save(update_fields=['expire_date'])
                            logger.debug("Extended session {{session_key[:8]}}... for user {{request.user.id}}")
                    
                    # Mark session as modified to ensure it's saved
                    request.session.modified = True
                    
                    # Set session cookie to ensure it persists
                    if hasattr(response, 'set_cookie'):
                        from django.conf import settings
                        response.set_cookie(
                            settings.SESSION_COOKIE_NAME,
                            session_key,
                            max_age=settings.SESSION_COOKIE_AGE,
                            expires=None,
                            domain=settings.SESSION_COOKIE_DOMAIN,
                            path=settings.SESSION_COOKIE_PATH,
                            secure=settings.SESSION_COOKIE_SECURE,
                            httponly=settings.SESSION_COOKIE_HTTPONLY,
                            samesite=settings.SESSION_COOKIE_SAMESITE,
                        )
                
            except Exception as e:
                logger.error("Session persistence middleware error: {{e}}", exc_info=True)
        
        return response
