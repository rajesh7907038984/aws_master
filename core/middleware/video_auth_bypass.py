"""
Video Authentication Bypass Middleware
Bypasses authentication for video streaming URLs to prevent redirect loops
"""

import logging
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class VideoAuthBypassMiddleware(MiddlewareMixin):
    """
    Middleware to bypass authentication for video streaming URLs
    """
    
    def process_request(self, request):
        """Process request to bypass authentication for video URLs"""
        # Check if this is a video streaming request
        if request.path.startswith('/courses/video/'):
            # Set a flag to bypass authentication
            request._video_streaming = True
            logger.info(f"Video streaming request detected: {request.path}")
        
        return None
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """Process view to handle video streaming authentication bypass"""
        # If this is a video streaming request, bypass authentication
        if hasattr(request, '_video_streaming') and request._video_streaming:
            # Temporarily set user as authenticated for video streaming
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                # Create a minimal user object for video streaming
                from django.contrib.auth.models import AnonymousUser
                request.user = AnonymousUser()
                request.user.is_authenticated = False
                logger.info(f"Video streaming authentication bypassed for: {request.path}")
        
        return None
