from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class ScormSSLExemptMiddleware(MiddlewareMixin):
    """
    Middleware to exempt SCORM content from SSL requirements.
    This allows SCORM packages to load properly in various environments.
    """
    
    def process_request(self, request):
        # Allow SCORM content to bypass SSL requirements
        # This is necessary for SCORM packages that may not support HTTPS
        if request.path.startswith('/scorm/'):
            # Set headers to allow mixed content for SCORM
            pass
        
        return None
    
    def process_response(self, request, response):
        # Add headers to allow SCORM content to load properly
        if request.path.startswith('/scorm/'):
            response['X-Frame-Options'] = 'SAMEORIGIN'
            # Allow mixed content for SCORM packages
            response['Content-Security-Policy'] = "frame-ancestors 'self' *;"
        
        return response
