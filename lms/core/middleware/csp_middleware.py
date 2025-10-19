"""
Content Security Policy (CSP) Middleware
Sets secure CSP headers while maintaining compatibility with SCORM content and third-party libraries
"""

from django.http import HttpRequest, HttpResponse


class CSPMiddleware:
    """
    Middleware to set Content Security Policy headers
    
    Security Features:
    - Prevents XSS attacks by restricting script sources
    - Allows necessary third-party content (S3, SCORM vendors)
    - Uses 'unsafe-inline' for styles (required for TinyMCE and dynamic styling)
    - Does NOT use 'unsafe-eval' (good security practice)
    
    Third-Party Sources Allowed:
    - AWS S3 for media and SCORM content
    - Articulate, Adobe, Captivate for SCORM content
    - Google Fonts for typography
    - CDN libraries (cdnjs, jQuery CDN)
    
    Note: 'unsafe-inline' is required for:
    - TinyMCE rich text editor
    - Dynamic CSS from SCORM packages
    - Inline event handlers (being phased out)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        
        # Set more secure CSP header with minimal unsafe directives
        # Only allow unsafe-eval for specific SCORM content and TinyMCE
        csp_policy = (
            "default-src 'self' data: blob:; "
            "frame-src 'self' *.amazonaws.com *.s3.amazonaws.com https://lms-staging-nexsy-io.s3.eu-west-2.amazonaws.com; "
            "script-src 'self' 'unsafe-inline' *.amazonaws.com *.s3.amazonaws.com *.articulate.com *.adobe.com *.captivate.com *.googleapis.com *.gstatic.com; "
            "style-src 'self' 'unsafe-inline' data: blob: *.amazonaws.com *.s3.amazonaws.com fonts.googleapis.com *.gstatic.com cdnjs.cloudflare.com code.jquery.com; "
            "img-src 'self' data: blob: *.amazonaws.com *.s3.amazonaws.com *.articulate.com *.adobe.com *.captivate.com; "
            "font-src 'self' data: blob: *.amazonaws.com *.s3.amazonaws.com fonts.gstatic.com fonts.googleapis.com; "
            "connect-src 'self' *.amazonaws.com *.s3.amazonaws.com metrics.articulate.com *.articulate.com *.adobe.com *.captivate.com https://metrics.articulate.com *.googleapis.com; "
            "worker-src 'self' blob:; "
            "object-src 'self' data: blob:; "
            "base-uri 'self';"
        )
        
        # Only set CSP if not already set by the view
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = csp_policy
        
        return response
