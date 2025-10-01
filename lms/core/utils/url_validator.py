"""
URL validation utilities for the LMS project.
Provides secure URL validation and error handling for external API calls.
"""

import os
import re
import requests
from urllib.parse import urlparse
from django.conf import settings
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

class URLValidator:
    """Secure URL validator with comprehensive checks."""
    
    # Allowed protocols for production
    ALLOWED_PROTOCOLS = {'https', 'http'}
    
    # Production protocols only
    PRODUCTION_PROTOCOLS = {'https'}
    
    # Blocked domains for Session
    BLOCKED_DOMAINS = {
        '0.0.0.0',
        # Removed development tunnel domains for production security
    }
    
    def __init__(self, environment=None):
        self.environment = environment or os.environ.get('DJANGO_ENV', 'development')
        self.is_production = self.environment == 'production'
    
    def validate_url(self, url, allow_http=False):
        """
        Validate a URL for Session and correctness.
        
        Args:
            url (str): URL to validate
            allow_http (bool): Allow HTTP URLs (default: False for production)
            
        Returns:
            bool: True if URL is valid
            
        Raises:
            ValidationError: If URL is invalid or insecure
        """
        if not url or not isinstance(url, str):
            raise ValidationError("URL must be a non-empty string")
        
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise ValidationError(f"Invalid URL format: {e}")
        
        # Check protocol
        if parsed.scheme not in self.ALLOWED_PROTOCOLS:
            raise ValidationError(f"Invalid protocol: {parsed.scheme}")
        
        # Production Session checks
        if self.is_production:
            if parsed.scheme not in self.PRODUCTION_PROTOCOLS and not allow_http:
                raise ValidationError("HTTP URLs not allowed in production")
            
            # Check for blocked domains
            if self._is_blocked_domain(parsed.netloc):
                raise ValidationError(f"Blocked domain: {parsed.netloc}")
        
        # Check for suspicious patterns
        if self._has_suspicious_patterns(url):
            raise ValidationError("URL contains suspicious patterns")
        
        return True
    
    def _is_blocked_domain(self, domain):
        """Check if domain is in blocked list."""
        domain_lower = domain.lower()
        
        for blocked in self.BLOCKED_DOMAINS:
            if blocked.startswith('*.'):
                # Wildcard domain check
                if domain_lower.endswith(blocked[2:]):
                    return True
            elif domain_lower == blocked:
                return True
        
        return False
    
    def _has_suspicious_patterns(self, url):
        """Check for suspicious URL patterns."""
        suspicious_patterns = [
            r'javascript:',
            r'data:',
            r'vbscript:',
            r'file:',
            r'ftp:',
        ]
        
        url_lower = url.lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    def get_secure_url(self, url, fallback=None):
        """
        Get a secure version of a URL, converting HTTP to HTTPS when possible.
        
        Args:
            url (str): Original URL
            fallback (str): Fallback URL if conversion fails
            
        Returns:
            str: Secure URL or fallback
        """
        try:
            self.validate_url(url, allow_http=not self.is_production)
            
            # Convert HTTP to HTTPS in production
            if self.is_production and url.startswith('http://'):
                https_url = url.replace('http://', 'https://', 1)
                try:
                    # Test if HTTPS version works
                    response = requests.head(https_url, timeout=5)
                    if response.status_code < 400:
                        return https_url
                except:
                    pass
            
            return url
            
        except ValidationError:
            logger.warning(f"Invalid URL: {url}, using fallback: {fallback}")
            return fallback or url
    
    def validate_api_endpoint(self, url, required_methods=None):
        """
        Validate an API endpoint URL and optionally test it.
        
        Args:
            url (str): API endpoint URL
            required_methods (list): List of required HTTP methods
            
        Returns:
            dict: Validation result with status and details
        """
        result = {
            'valid': False,
            'url': url,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Basic URL validation
            self.validate_url(url)
            result['valid'] = True
            
            # Test endpoint if required methods provided
            if required_methods:
                for method in required_methods:
                    try:
                        response = requests.request(
                            method, url, 
                            timeout=10,
                            allow_redirects=False
                        )
                        if response.status_code >= 400:
                            result['warnings'].append(
                                f"{method} request returned {response.status_code}"
                            )
                    except requests.RequestException as e:
                        result['warnings'].append(f"{method} request failed: {e}")
            
        except ValidationError as e:
            result['errors'].append(str(e))
        
        return result


def get_secure_api_url(url_key, fallback=None):
    """
    Get a secure API URL from environment variables.
    
    Args:
        url_key (str): Environment variable key for the URL
        fallback (str): Fallback URL if environment variable not set
        
    Returns:
        str: Secure API URL
    """
    validator = URLValidator()
    url = os.environ.get(url_key, fallback)
    
    if not url:
        logger.error(f"API URL not configured: {url_key}")
        return fallback
    
    return validator.get_secure_url(url, fallback)


def validate_external_api_call(url, method='GET', timeout=30):
    """
    Safely make an external API call with validation and error handling.
    
    Args:
        url (str): API endpoint URL
        method (str): HTTP method
        timeout (int): Request timeout in seconds
        
    Returns:
        requests.Response: Response object or None if failed
    """
    validator = URLValidator()
    
    try:
        # Validate URL
        validator.validate_url(url)
        
        # Make request
        response = requests.request(
            method, url, 
            timeout=timeout,
            allow_redirects=True
        )
        
        # Log successful request
        logger.info(f"API call successful: {method} {url} -> {response.status_code}")
        
        return response
        
    except ValidationError as e:
        logger.error(f"URL validation failed: {e}")
        return None
        
    except requests.RequestException as e:
        logger.error(f"API call failed: {method} {url} -> {e}")
        return None
