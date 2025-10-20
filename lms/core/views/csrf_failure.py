"""
CSRF Failure Handler
Provides proper handling of CSRF failures with user-friendly messages
"""

import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

def csrf_failure(request, reason=""):
    """
    Handle CSRF failures with appropriate response based on request type
    
    Args:
        request: Django request object
        reason: CSRF failure reason from Django
    """
    user_message = _("Session expired. Please refresh the page and try again.")
    
    # Log CSRF failure for security monitoring
    user_id = getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') else 'anonymous'
    ip_address = request.META.get('REMOTE_ADDR', 'unknown')
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    
    logger.warning(
        f"CSRF failure for user {user_id} from IP {ip_address}: {reason}",
        extra={
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'reason': reason,
            'path': request.path,
            'method': request.method
        }
    )
    
    # Check if this is an AJAX/API request
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.content_type == 'application/json' or
        'application/json' in request.headers.get('Accept', '') or
        request.path.startswith('/api/')
    )
    
    if is_ajax:
        return JsonResponse({
            'success': False,
            'error': user_message,
            'error_type': 'csrf_error',
            'action_required': 'refresh',
            'reason': reason,
            'csrf_token_required': True
        }, status=403)
    
    # For regular page requests, show a user-friendly error page
    context = {
        'error_message': user_message,
        'error_type': 'csrf_error',
        'reason': reason,
        'can_retry': True
    }
    
    # Try to render the error page template, fallback to basic template if needed
    try:
        return render(request, 'core/error_pages/csrf_error.html', context, status=403)
    except Exception as template_error:
        logger.error(f"CSRF error template failed: {template_error}")
        # Fallback to basic CSRF error template
        try:
            return render(request, 'core/csrf_failure.html', context, status=403)
        except Exception as fallback_error:
            logger.error(f"CSRF fallback template failed: {fallback_error}")
            # Final fallback - return basic HTML
            from django.http import HttpResponse
            return HttpResponse("""
            <!DOCTYPE html>
            <html>
            <head><title>Security Error</title></head>
            <body>
                <h1>Security Verification Failed</h1>
                <p>Your session has expired. Please refresh the page and try again.</p>
                <button onclick="window.location.reload()">Refresh Page</button>
                <button onclick="history.back()">Go Back</button>
            </body>
            </html>
            """, status=403)

@csrf_exempt
@require_http_methods(["GET"])
def csrf_token_info(request):
    """
    Get information about CSRF token requirements
    Useful for debugging and frontend development
    """
    try:
        return JsonResponse({
            'success': True,
            'csrf_required': True,
            'header_name': 'X-CSRFToken',
            'cookie_name': 'csrftoken',
            'meta_tag_name': 'csrf-token',
            'endpoints': {
                'info': '/api/csrf/info/'
            }
        })
    except Exception as e:
        logger.error(f"Failed to get CSRF info: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get CSRF information'
        }, status=500)
