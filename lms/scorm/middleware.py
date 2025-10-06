"""
SCORM Middleware
Handles SCORM-specific request processing
"""
import re
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponsePermanentRedirect


class ScormSSLExemptMiddleware(MiddlewareMixin):
    """
    Middleware to exempt SCORM content from SSL redirects and apply permissive CSP
    This prevents mixed content issues when serving SCORM resources
    """
    
    def process_request(self, request):
        """
        Mark SCORM content requests to bypass SSL redirect
        """
        import logging
        logger = logging.getLogger(__name__)
        
        path = request.path_info.lstrip('/')
        
        # Check if this is a SCORM content request
        if path.startswith('scorm/content/') or path.startswith('scorm/player/'):
            logger.info(f"🎯 SCORM Middleware process_request: Detected SCORM request: {path}")
            # Mark the request to skip SSL redirect
            request._skip_ssl_redirect = True
            request._is_scorm_request = True
            # Force the request to appear as HTTPS to prevent redirects
            request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
            logger.info(f"SCORM Middleware: Set _is_scorm_request flag for {path}")
        
        return None
    
    def process_response(self, request, response):
        """
        Prevent SSL redirects for SCORM content and set permissive CSP headers
        """
        import logging
        logger = logging.getLogger(__name__)
        
        path = request.path_info.lstrip('/')
        
        # REMOVE ALL SECURITY HEADERS and SET PERMISSIVE CSP for SCORM player and content
        if hasattr(request, '_is_scorm_request') and request._is_scorm_request:
            logger.info(f"🎯 SCORM Middleware: Processing SCORM request: {path}")
            
            # AGGRESSIVELY REMOVE ALL CSP HEADERS
            csp_headers = ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']
            for header in csp_headers:
                if header in response:
                    del response[header]
                    logger.info(f"🔓 Removed {header} from response")
            
            # SIMPLE CSP FOR MAXIMUM CROSS-BROWSER COMPATIBILITY
            response['Content-Security-Policy'] = (
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "script-src * 'unsafe-inline' 'unsafe-eval'; "
                "worker-src * blob: data:; "
                "style-src * 'unsafe-inline'; "
                "img-src * data: blob:; "
                "font-src * data:; "
                "connect-src *; "
                "media-src * data: blob:; "
                "frame-src *"
            )
            logger.info(f"Set permissive CSP with unsafe-eval for SCORM request: {path}")
            
            # Allow iframe embedding for SCORM content
            response['X-Frame-Options'] = 'SAMEORIGIN'
            
            if 'X-Content-Type-Options' in response:
                del response['X-Content-Type-Options']
                logger.info("🔓 Removed X-Content-Type-Options from response")
            
            # Disable XSS protection for SCORM content
            response['X-XSS-Protection'] = '0'
            
            # Add permissive CORS headers
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = '*'
            response['Access-Control-Allow-Headers'] = '*'
            
            logger.info(f"✅ SCORM Middleware: Applied permissive security policy for {path}")
        
        # If this is a redirect response for SCORM content, allow it through without HTTPS
        if hasattr(request, '_skip_ssl_redirect') and request._skip_ssl_redirect:
            # If SecurityMiddleware tried to redirect to HTTPS, we prevent it here
            if isinstance(response, HttpResponsePermanentRedirect):
                if path.startswith('scorm/content/'):
                    # Don't redirect SCORM content
                    return None
        
        return response

