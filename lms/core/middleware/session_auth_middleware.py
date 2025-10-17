"""
Session Authentication Middleware
Handles session recovery and authentication state management
"""

import logging
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone

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
        """Process request to ensure proper authentication state with enhanced recovery"""
        try:
            # Skip session recovery for logout requests
            if request.path == '/logout/' and request.method == 'POST':
                return
            
            # Skip if already authenticated
            if request.user.is_authenticated:
                return
            
            # Enhanced session recovery for SECRET_KEY changes
            user_id = request.session.get('_auth_user_id')
            if user_id:
                try:
                    user = User.objects.get(id=user_id, is_active=True)
                    # Properly authenticate the user
                    from django.contrib.auth import login
                    login(request, user)
                    logger.info(f"✅ Session recovered for user {user.username}")
                    
                    # Mark session as modified to ensure it's saved with new SECRET_KEY
                    request.session.modified = True
                    
                except User.DoesNotExist:
                    # Clear invalid session
                    request.session.flush()
                    logger.warning(f"❌ Invalid session for user_id {user_id}, session cleared")
                except Exception as e:
                    logger.error(f"❌ Error recovering session: {e}")
                    
                    # Try alternative recovery method for SECRET_KEY issues
                    self._try_alternative_session_recovery(request, user_id)
            
            # Additional check: if session exists but user is not authenticated
            # This handles cases where session data exists but authentication failed
            elif hasattr(request, 'session') and request.session.session_key:
                self._handle_orphaned_session(request)
            
        except Exception as e:
            logger.error(f"❌ SessionAuthMiddleware error: {e}")

    def _try_alternative_session_recovery(self, request, user_id):
        """Alternative session recovery for SECRET_KEY change scenarios"""
        try:
            # Try to find user by ID and create a fresh session
            user = User.objects.get(id=user_id, is_active=True)
            
            # Create new session for the user
            request.session.create()
            request.session['_auth_user_id'] = str(user.id)
            request.session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
            request.session.modified = True
            
            # Authenticate the user
            from django.contrib.auth import login
            login(request, user)
            
            logger.info(f"🔄 Alternative session recovery successful for user {user.username}")
            
        except User.DoesNotExist:
            logger.warning(f"❌ User {user_id} not found during alternative recovery")
        except Exception as e:
            logger.error(f"❌ Alternative session recovery failed: {e}")

    def _handle_orphaned_session(self, request):
        """Handle sessions that exist but have no valid authentication"""
        try:
            # Check if session has any user data
            session_data = request.session
            if '_auth_user_id' in session_data:
                user_id = session_data.get('_auth_user_id')
                try:
                    user = User.objects.get(id=user_id, is_active=True)
                    # Re-authenticate the user
                    from django.contrib.auth import login
                    login(request, user)
                    logger.info(f"🔄 Orphaned session recovered for user {user.username}")
                except User.DoesNotExist:
                    # Clear the orphaned session
                    request.session.flush()
                    logger.info(f"🧹 Cleared orphaned session for non-existent user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error handling orphaned session: {e}")

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
