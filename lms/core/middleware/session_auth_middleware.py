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
    Simplified middleware to handle session authentication issues
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
        """Process request to ensure proper authentication state with memory optimization"""
        try:
            # Skip session recovery for logout requests
            if request.path == '/logout/' and request.method == 'POST':
                return
            
            # Skip if already authenticated
            if hasattr(request, 'user') and request.user.is_authenticated:
                return
            
            # Optimized session recovery with memory management
            user_id = request.session.get('_auth_user_id')
            if user_id:
                try:
                    # Use select_for_update to prevent race conditions with memory optimization
                    from django.db import transaction
                    with transaction.atomic():
                        # Only fetch essential fields to reduce memory usage
                        user = User.objects.select_for_update().only(
                            'id', 'username', 'is_active', 'is_staff', 'is_superuser'
                        ).get(id=user_id, is_active=True)
                        
                        from django.contrib.auth import login
                        login(request, user)
                        
                        # Log with minimal memory footprint
                        logger.info(f"Session recovered for user {user.id}")
                        request.session.modified = True
                        
                        # Clear user object from memory after use
                        del user
                        
                except User.DoesNotExist:
                    request.session.flush()
                    logger.warning(f"Invalid session for user_id {user_id}, session cleared")
                except Exception as e:
                    logger.error(f"Error recovering session: {e}")
                    # Don't flush session on unexpected errors - could be temporary
                    # Log the error but don't break the request flow
            
        except Exception as e:
            logger.error(f"SessionAuthMiddleware error: {e}")
            # Ensure memory cleanup on errors
            try:
                import gc
                gc.collect()
            except Exception as gc_error:
                logger.error(f"Error during garbage collection: {gc_error}")

    def process_response(self, request, response):
        """Process response to maintain session health with memory optimization"""
        try:
            # Update session activity for authenticated users with memory management
            if request.user.is_authenticated and hasattr(request, 'session'):
                # Use minimal data for session activity tracking
                request.session['last_activity'] = timezone.now().isoformat()
                request.session.modified = True
                
                # Clean up session data periodically to prevent memory bloat
                if hasattr(request, 'session') and len(request.session.keys()) > 20:
                    # Keep only essential session keys
                    essential_keys = ['_auth_user_id', 'last_activity', '_auth_user_backend', '_auth_user_hash']
                    keys_to_remove = [key for key in request.session.keys() if key not in essential_keys]
                    for key in keys_to_remove[:5]:  # Remove max 5 keys per request
                        if key in request.session:
                            del request.session[key]
                
        except Exception as e:
            logger.error(f"Error updating session activity: {e}")
            # Memory cleanup on errors
            import gc
            gc.collect()
        
        return response


