"""
Content Security Policy (CSP) Middleware
Sets permissive CSP headers to allow eval() and other JavaScript features
"""

from django.http import HttpRequest, HttpResponse


class CSPMiddleware:
    """
    Middleware to set permissive Content Security Policy headers
    Allows unsafe-eval for JavaScript compatibility
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        
        # Set comprehensive CSP header to allow eval() and other JavaScript features
        # This is necessary for SCORM content, TinyMCE editor, and other JavaScript libraries
        csp_policy = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "frame-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' *.amazonaws.com *.articulate.com *.adobe.com *.captivate.com *.googleapis.com *.gstatic.com; "
            "style-src 'self' 'unsafe-inline' *.amazonaws.com fonts.googleapis.com *.gstatic.com; "
            "img-src 'self' data: blob: *.amazonaws.com *.articulate.com *.adobe.com *.captivate.com; "
            "font-src 'self' *.amazonaws.com fonts.gstatic.com fonts.googleapis.com; "
            "connect-src 'self' *.amazonaws.com metrics.articulate.com *.articulate.com *.adobe.com *.captivate.com https://metrics.articulate.com *.googleapis.com; "
            "worker-src 'self' blob:; "
            "object-src 'self' data: blob:; "
            "base-uri 'self';"
        )
        
        # Only set CSP if not already set by the view
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = csp_policy
        
        return response
