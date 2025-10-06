"""
Session Management API Views
Handles session heartbeat, warnings, and extensions for auto-logout prevention
"""

import json
import logging
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

@csrf_protect
@require_http_methods(["POST"])
def session_heartbeat(request):
    """
    API endpoint for session heartbeat
    Extends session if user is active
    """
    try:
        user = request.user
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({
                'success': False,
                'error': 'No active session'
            }, status=400)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
        
        # Update user activity timestamp
        activity_key = f"user_activity_{user.id}"
        cache.set(activity_key, timezone.now().timestamp(), timeout=28800)  # 8 hours
        
        # Check if session needs extension
        session = Session.objects.get(session_key=session_key)
        time_until_expiry = (session.expire_date - timezone.now()).total_seconds()
        
        # Extend session if it expires in less than 1 hour
        if time_until_expiry < 3600:
            new_expiry = timezone.now() + timedelta(hours=2)
            session.expire_date = new_expiry
            session.save()
            
            logger.info(f" Session extended for user {user.id}")
            
            return JsonResponse({
                'success': True,
                'message': 'Session extended',
                'expires_at': new_expiry.isoformat(),
                'extended': True
            })
        else:
            return JsonResponse({
                'success': True,
                'message': 'Session active',
                'expires_at': session.expire_date.isoformat(),
                'extended': False
            })
            
    except Session.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Session not found'
        }, status=404)
    except Exception as e:
        logger.error(f" Heartbeat failed for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def session_warning(request):
    """
    API endpoint to check if session warning is needed
    """
    try:
        user = request.user
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({
                'warning_needed': False,
                'error': 'No active session'
            })
        
        session = Session.objects.get(session_key=session_key)
        time_until_expiry = (session.expire_date - timezone.now()).total_seconds()
        
        # Show warning if session expires in less than 10 minutes
        warning_threshold = 600  # 10 minutes
        
        if time_until_expiry < warning_threshold:
            return JsonResponse({
                'warning_needed': True,
                'time_remaining': time_until_expiry,
                'expires_at': session.expire_date.isoformat(),
                'message': f'Session expires in {int(time_until_expiry / 60)} minutes'
            })
        else:
            return JsonResponse({
                'warning_needed': False,
                'time_remaining': time_until_expiry,
                'expires_at': session.expire_date.isoformat()
            })
            
    except Session.DoesNotExist:
        return JsonResponse({
            'warning_needed': False,
            'error': 'Session not found'
        })
    except Exception as e:
        logger.error(f" Warning check failed for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'warning_needed': False,
            'error': 'Internal server error'
        })

@login_required
@require_http_methods(["POST"])
def session_extend(request):
    """
    API endpoint to manually extend session
    """
    try:
        user = request.user
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({
                'success': False,
                'error': 'No active session'
            }, status=400)
        
        # Parse request data
        try:
            data = json.loads(request.body)
            extend = data.get('extend', False)
        except json.JSONDecodeError:
            extend = False
        
        if not extend:
            return JsonResponse({
                'success': False,
                'error': 'Extension not requested'
            }, status=400)
        
        # Extend session
        with transaction.atomic():
            session = Session.objects.get(session_key=session_key)
            new_expiry = timezone.now() + timedelta(hours=2)
            session.expire_date = new_expiry
            session.save()
            
            # Update activity timestamp
            activity_key = f"user_activity_{user.id}"
            cache.set(activity_key, timezone.now().timestamp(), timeout=28800)
            
            logger.info(f" Session manually extended for user {user.id}")
            
            return JsonResponse({
                'success': True,
                'message': 'Session extended successfully',
                'expires_at': new_expiry.isoformat(),
                'extended_by': '2 hours'
            })
            
    except Session.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Session not found'
        }, status=404)
    except Exception as e:
        logger.error(f" Session extension failed for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def session_status(request):
    """
    API endpoint to get current session status
    """
    try:
        user = request.user
        session_key = request.session.session_key
        
        if not session_key:
            return JsonResponse({
                'active': False,
                'error': 'No active session'
            })
        
        session = Session.objects.get(session_key=session_key)
        time_until_expiry = (session.expire_date - timezone.now()).total_seconds()
        
        # Check user activity
        activity_key = f"user_activity_{user.id}"
        last_activity = cache.get(activity_key)
        
        return JsonResponse({
            'active': True,
            'expires_at': session.expire_date.isoformat(),
            'time_remaining': time_until_expiry,
            'last_activity': last_activity,
            'user_id': user.id,
            'username': user.username
        })
        
    except Session.DoesNotExist:
        return JsonResponse({
            'active': False,
            'error': 'Session not found'
        })
    except Exception as e:
        logger.error(f" Status check failed for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'active': False,
            'error': 'Internal server error'
        })
