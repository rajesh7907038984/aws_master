"""
Domain Fix Middleware
Handles URLs with trailing dots after the domain name (FQDN format)
Redirects from https://vle.nexsy.io./path to https://vle.nexsy.io/path
"""

from django.http import HttpResponsePermanentRedirect
import logging

logger = logging.getLogger(__name__)


class DomainFixMiddleware:
    """
    Middleware to fix URLs with trailing dots after the domain name.
    
    Trailing dots in domain names (e.g., vle.nexsy.io.) are technically valid
    as Fully Qualified Domain Names (FQDNs), but they can cause issues with
    cookies, CSRF tokens, and user experience. This middleware redirects
    such requests to the correct URL without the trailing dot.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Get the host from the request
        host = request.get_host()
        
        # Check if the host ends with a dot (excluding port if present)
        if ':' in host:
            domain, port = host.rsplit(':', 1)
            if domain.endswith('.'):
                # Remove the trailing dot and reconstruct the URL
                corrected_domain = domain.rstrip('.')
                corrected_host = f"{corrected_domain}:{port}"
                corrected_url = f"{request.scheme}://{corrected_host}{request.get_full_path()}"
                
                logger.warning(
                    f"Redirecting URL with trailing dot: {request.scheme}://{host}{request.get_full_path()} "
                    f"-> {corrected_url}"
                )
                
                return HttpResponsePermanentRedirect(corrected_url)
        else:
            if host.endswith('.'):
                # Remove the trailing dot and reconstruct the URL
                corrected_host = host.rstrip('.')
                corrected_url = f"{request.scheme}://{corrected_host}{request.get_full_path()}"
                
                logger.warning(
                    f"Redirecting URL with trailing dot: {request.scheme}://{host}{request.get_full_path()} "
                    f"-> {corrected_url}"
                )
                
                return HttpResponsePermanentRedirect(corrected_url)
        
        # No fix needed, continue with normal request processing
        response = self.get_response(request)
        return response

