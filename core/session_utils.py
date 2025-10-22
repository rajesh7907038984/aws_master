"""
Session Management Utilities for LMS
Handles session persistence and prevents auto-logout after deployment
"""

import logging
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)
User = get_user_model()


def extend_user_sessions(user_id=None, hours=24):
    """
    Extend active sessions for users to prevent auto-logout after deployment
    
    Args:
        user_id: Specific user ID to extend sessions for (None for all users)
        hours: Number of hours to extend sessions by
    """
    try:
        # Get all active sessions
        active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
        
        if user_id:
            # Filter sessions for specific user
            user_sessions = []
            for session in active_sessions:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') == str(user_id):
                    user_sessions.append(session)
            sessions_to_extend = user_sessions
        else:
            sessions_to_extend = active_sessions
        
        extended_count = 0
        for session in sessions_to_extend:
            # Extend session expiry
            new_expire_date = timezone.now() + timedelta(hours=hours)
            session.expire_date = new_expire_date
            session.save()
            extended_count += 1
        
        logger.info(f"Extended {extended_count} sessions by {hours} hours")
        return extended_count
        
    except Exception as e:
        logger.error(f"Error extending sessions: {e}")
        return 0


def clear_expired_sessions():
    """
    Clean up expired sessions from the database
    """
    try:
        expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired_sessions.count()
        expired_sessions.delete()
        logger.info(f"Cleared {count} expired sessions")
        return count
    except Exception as e:
        logger.error(f"Error clearing expired sessions: {e}")
        return 0


def get_active_session_count():
    """
    Get the number of currently active sessions
    """
    try:
        return Session.objects.filter(expire_date__gt=timezone.now()).count()
    except Exception as e:
        logger.error(f"Error getting active session count: {e}")
        return 0


def preserve_sessions_during_deployment():
    """
    Preserve user sessions during deployment by extending them
    This should be called before deployment to prevent auto-logout
    """
    try:
        # Extend all active sessions by 24 hours
        extended_count = extend_user_sessions(hours=24)
        
        # Clear old expired sessions to keep database clean
        cleared_count = clear_expired_sessions()
        
        logger.info(f"Deployment session preservation: Extended {extended_count} sessions, cleared {cleared_count} expired sessions")
        return {
            'extended_sessions': extended_count,
            'cleared_sessions': cleared_count,
            'active_sessions': get_active_session_count()
        }
        
    except Exception as e:
        logger.error(f"Error preserving sessions during deployment: {e}")
        return None


def check_session_health():
    """
    Check the health of session storage and Redis connection
    """
    try:
        # Test Redis connection
        cache.set('session_health_check', 'ok', 10)
        redis_ok = cache.get('session_health_check') == 'ok'
        
        # Test database session storage
        active_sessions = get_active_session_count()
        
        return {
            'redis_connection': redis_ok,
            'database_sessions': active_sessions,
            'session_engine': settings.SESSION_ENGINE,
            'session_cache_alias': getattr(settings, 'SESSION_CACHE_ALIAS', 'default'),
            'session_cookie_age': settings.SESSION_COOKIE_AGE,
        }
        
    except Exception as e:
        logger.error(f"Error checking session health: {e}")
        return None
