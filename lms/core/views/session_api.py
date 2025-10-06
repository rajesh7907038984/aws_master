"""
Session API Views
Provides endpoints for session health monitoring and management
"""

import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.sessions.models import Session
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def session_health(request):
    """Check session health and return status"""
    try:
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({
                'active': False,
                'message': 'No active session'
            }, status=401)
        
        # Get session from database
        try:
            session = Session.objects.get(session_key=session_key)
            time_remaining = (session.expire_date - timezone.now()).total_seconds()
            
            # Check if session is expired
            if time_remaining <= 0:
                return JsonResponse({
                    'active': False,
                    'message': 'Session expired'
                }, status=401)
            
            # Check if warning is needed (less than 10 minutes remaining)
            warning_threshold = 600  # 10 minutes
            warning_needed = time_remaining < warning_threshold
            
            return JsonResponse({
                'active': True,
                'time_remaining': time_remaining,
                'expires_at': session.expire_date.isoformat(),
                'warning_needed': warning_needed,
                'warning_threshold': warning_threshold
            })
            
        except Session.DoesNotExist:
            return JsonResponse({
                'active': False,
                'message': 'Session not found'
            }, status=401)
            
    except Exception as e:
        logger.error(f"Session health check error: {e}")
        return JsonResponse({
            'error': 'Session health check failed'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def extend_session(request):
    """Extend user session"""
    try:
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({
                'success': False,
                'error': 'No active session'
            }, status=401)
        
        # Get session and extend it
        try:
            session = Session.objects.get(session_key=session_key)
            new_expire_date = timezone.now() + timedelta(hours=2)
            session.expire_date = new_expire_date
            session.save()
            
            # Update cache if using cache backend
            try:
                cache.set(f'session:{session_key}', session.session_data, timeout=7200)
            except Exception as e:
                logger.warning(f"Failed to update cache: {e}")
            
            logger.info(f"Session extended for user {request.user.username}")
            
            return JsonResponse({
                'success': True,
                'message': 'Session extended successfully',
                'expires_at': new_expire_date.isoformat()
            })
            
        except Session.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Session not found'
            }, status=401)
            
    except Exception as e:
        logger.error(f"Session extension error: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to extend session'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def session_info(request):
    """Get detailed session information"""
    try:
        session_key = request.session.session_key
        if not session_key:
            return JsonResponse({
                'session_key': None,
                'active': False
            })
        
        try:
            session = Session.objects.get(session_key=session_key)
            time_remaining = (session.expire_date - timezone.now()).total_seconds()
            
            return JsonResponse({
                'session_key': session_key[:8] + '...',
                'active': time_remaining > 0,
                'expires_at': session.expire_date.isoformat(),
                'time_remaining': time_remaining,
                'user_id': request.user.id,
                'username': request.user.username,
                'last_activity': request.session.get('last_activity', 'Unknown')
            })
            
        except Session.DoesNotExist:
            return JsonResponse({
                'session_key': session_key[:8] + '...',
                'active': False,
                'error': 'Session not found in database'
            })
            
    except Exception as e:
        logger.error(f"Session info error: {e}")
        return JsonResponse({
            'error': 'Failed to get session info'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def clear_expired_sessions(request):
    """Clear expired sessions (admin only)"""
    try:
        # Check if user is admin
        if not (request.user.is_authenticated and hasattr(request.user, 'role') and 
                request.user.role in ['admin', 'superadmin', 'globaladmin']):
            return JsonResponse({
                'error': 'Permission denied'
            }, status=403)
        
        # Clear expired sessions
        expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired_sessions.count()
        expired_sessions.delete()
        
        logger.info(f"Cleared {count} expired sessions by {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'cleared_count': count,
            'message': f'Cleared {count} expired sessions'
        })
        
    except Exception as e:
        logger.error(f"Clear expired sessions error: {e}")
        return JsonResponse({
            'error': 'Failed to clear expired sessions'
        }, status=500)
