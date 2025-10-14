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
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request
        response = self.get_response(request)
        
        # Only process authenticated users with sessions
        if hasattr(request, 'user') and request.user.is_authenticated and hasattr(request, 'session'):
            try:
                # Ensure session is saved and extended
                if request.session.session_key:
                    # Extend session if it's close to expiry (within 1 hour)
                    session_obj = Session.objects.filter(session_key=request.session.session_key).first()
                    if session_obj:
                        # Check if session expires within 1 hour
                        time_until_expiry = session_obj.expire_date - timezone.now()
                        if time_until_expiry < timedelta(hours=1):
                            # Extend session by 24 hours
                            session_obj.expire_date = timezone.now() + timedelta(hours=24)
                            session_obj.save()
                            logger.debug(f"Extended session {request.session.session_key[:8]}... for user {request.user.id}")
                
                # Force session save to ensure persistence
                request.session.save()
                
            except Exception as e:
                logger.warning(f"Session persistence middleware error: {e}")
        
        return response
