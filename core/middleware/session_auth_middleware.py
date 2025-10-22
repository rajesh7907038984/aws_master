"""
Session Authentication Middleware
Handles session recovery and authentication state management
"""

import logging
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)
User = get_user_model()


class SessionAuthMiddleware:
    """
    Middleware to handle session authentication issues and recovery
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request before view
        self.process_request(request)
        
        response = self.get_response(request)
        
        # Process response after view
        self.process_response(request, response)
        
        return response

    def process_request(self, request):
        """Process request to ensure proper authentication state"""
        try:
            # Skip if already authenticated
            if request.user.is_authenticated:
                return
            
            # Try to recover session if user_id exists in session
            user_id = request.session.get('_auth_user_id')
            if user_id:
                try:
                    user = User.objects.get(id=user_id, is_active=True)
                    # Properly authenticate the user
                    from django.contrib.auth import login
                    login(request, user)
                    logger.info(f"Session recovered for user {user.username}")
                except User.DoesNotExist:
                    # Clear invalid session
                    request.session.flush()
                    logger.warning(f"Invalid session for user_id {user_id}, session cleared")
                except Exception as e:
                    logger.error(f"Error recovering session: {e}")
            
        except Exception as e:
            logger.error(f"SessionAuthMiddleware error: {e}")

    def process_response(self, request, response):
        """Process response to maintain session health"""
        try:
            # Update session activity for authenticated users
            if request.user.is_authenticated and hasattr(request, 'session'):
                request.session['last_activity'] = timezone.now().isoformat()
                request.session.modified = True
                
        except Exception as e:
            logger.error(f"Error updating session activity: {e}")
        
        return response


class SessionHealthMiddleware:
    """
    Middleware to monitor and maintain session health
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add session health headers for debugging
        if hasattr(request, 'session') and request.user.is_authenticated:
            try:
                session_key = request.session.session_key
                if session_key:
                    session = Session.objects.get(session_key=session_key)
                    time_remaining = (session.expire_date - timezone.now()).total_seconds()
                    
                    # Add session info to response headers for debugging
                    response['X-Session-Expires'] = str(int(time_remaining))
                    response['X-Session-Key'] = session_key[:8] + '...'
                    
            except Exception as e:
                logger.error(f"Error checking session health: {e}")
        
        return response
