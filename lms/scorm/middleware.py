"""
SCORM Middleware
Handle SCORM-specific headers and CSP policies
"""
from django.utils.deprecation import MiddlewareMixin


class ScormCSPMiddleware(MiddlewareMixin):
    """
    Set permissive Content Security Policy for SCORM content
    """
    
    def process_response(self, request, response):
        """
        Add permissive CSP headers for SCORM player pages
        """
        # Only apply to SCORM player URLs
        if request.path.startswith('/scorm/player/'):
            # Remove restrictive CSP for SCORM content
            if 'Content-Security-Policy' in response:
                del response['Content-Security-Policy']
            
            # Set permissive CSP
            response['Content-Security-Policy'] = (
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "script-src * 'unsafe-inline' 'unsafe-eval'; "
                "style-src * 'unsafe-inline'; "
                "img-src * data: blob:; "
                "font-src * data:; "
                "connect-src *; "
                "frame-src *; "
                "object-src *;"
            )
            
            # Allow framing from same origin
            response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response


class ScormCORSMiddleware(MiddlewareMixin):
    """
    Handle CORS for SCORM API endpoints
    """
    
    def process_response(self, request, response):
        """
        Add CORS headers for SCORM API endpoints
        """
        # Only apply to SCORM API URLs
        if request.path.startswith('/scorm/api/'):
            response['Access-Control-Allow-Origin'] = request.META.get('HTTP_ORIGIN', '*')
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        
        return response

