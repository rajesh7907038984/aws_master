"""
Security Hardening Utilities
Provides comprehensive security hardening measures for the LMS
"""

import os
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from django.http import HttpRequest, HttpResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

class SecurityHardeningMiddleware(MiddlewareMixin):
    """Middleware for additional security hardening"""
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add security headers to all responses"""
        try:
            # Security headers
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
            
            # Content Security Policy (basic)
            if not response.get('Content-Security-Policy'):
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' *.amazonaws.com; "
                    "style-src 'self' 'unsafe-inline' *.amazonaws.com; "
                    "img-src 'self' data: *.amazonaws.com; "
                    "font-src 'self' *.amazonaws.com; "
                    "connect-src 'self' *.amazonaws.com; "
                    "frame-src 'self' *.amazonaws.com; "
                    "object-src 'none'; "
                    "base-uri 'self'; "
                    "form-action 'self'"
                )
                response['Content-Security-Policy'] = csp
            
            # HSTS for HTTPS
            if request.is_secure():
                response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
            
            return response
            
        except Exception as e:
            logger.error(f"Error in security hardening middleware: {e}")
            return response

def validate_security_settings():
    """Validate security settings and return recommendations"""
    issues = []
    recommendations = []
    
    # Check SECRET_KEY
    secret_key = getattr(settings, 'SECRET_KEY', '')
    if not secret_key or len(secret_key) < 50:
        issues.append("SECRET_KEY is too short or missing")
        recommendations.append("Generate a new SECRET_KEY with at least 50 characters")
    
    # Check DEBUG mode
    if getattr(settings, 'DEBUG', True):
        issues.append("DEBUG mode is enabled in production")
        recommendations.append("Set DEBUG=False in production settings")
    
    # Check ALLOWED_HOSTS
    allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
    if not allowed_hosts or '*' in allowed_hosts:
        issues.append("ALLOWED_HOSTS is not properly configured")
        recommendations.append("Configure ALLOWED_HOSTS with specific domains")
    
    # Check session security
    if not getattr(settings, 'SESSION_COOKIE_SECURE', False):
        issues.append("SESSION_COOKIE_SECURE is not enabled")
        recommendations.append("Enable SESSION_COOKIE_SECURE for HTTPS")
    
    if not getattr(settings, 'SESSION_COOKIE_HTTPONLY', True):
        issues.append("SESSION_COOKIE_HTTPONLY is not enabled")
        recommendations.append("Enable SESSION_COOKIE_HTTPONLY for XSS protection")
    
    # Check CSRF protection
    if not getattr(settings, 'CSRF_COOKIE_SECURE', False):
        issues.append("CSRF_COOKIE_SECURE is not enabled")
        recommendations.append("Enable CSRF_COOKIE_SECURE for HTTPS")
    
    # Check file upload security
    max_file_size = getattr(settings, 'FILE_UPLOAD_MAX_MEMORY_SIZE', 0)
    if max_file_size > 600 * 1024 * 1024:  # 600MB
        issues.append("File upload size limit is too high")
        recommendations.append("Consider reducing FILE_UPLOAD_MAX_MEMORY_SIZE")
    
    return {
        'issues': issues,
        'recommendations': recommendations,
        'security_score': max(0, 100 - len(issues) * 20)
    }

def apply_security_hardening():
    """Apply security hardening measures"""
    try:
        # Create security directories
        security_dirs = [
            '/home/ec2-user/lmslogs/security',
            '/home/ec2-user/lmslogs/audit',
            '/home/ec2-user/lmslogs/access'
        ]
        
        for dir_path in security_dirs:
            os.makedirs(dir_path, exist_ok=True)
            # Set secure permissions
            os.chmod(dir_path, 0o700)
        
        logger.info("Security directories created with secure permissions")
        
        # Validate security settings
        security_status = validate_security_settings()
        
        if security_status['issues']:
            logger.warning(f"Security issues found: {security_status['issues']}")
            logger.info(f"Recommendations: {security_status['recommendations']}")
        else:
            logger.info("Security settings validated successfully")
        
        return security_status
        
    except Exception as e:
        logger.error(f"Error applying security hardening: {e}")
        return {'error': str(e)}

class SecurityAuditCommand(BaseCommand):
    """Management command for security auditing"""
    
    help = 'Perform security audit and hardening'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Apply security fixes automatically',
        )
        parser.add_argument(
            '--report-only',
            action='store_true',
            help='Generate security report only',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting security audit...')
        
        # Perform security validation
        security_status = validate_security_settings()
        
        # Display results
        self.stdout.write(f"Security Score: {security_status['security_score']}/100")
        
        if security_status['issues']:
            self.stdout.write(self.style.WARNING("Security Issues Found:"))
            for issue in security_status['issues']:
                self.stdout.write(f"  - {issue}")
        
        if security_status['recommendations']:
            self.stdout.write(self.style.SUCCESS("Recommendations:"))
            for rec in security_status['recommendations']:
                self.stdout.write(f"  - {rec}")
        
        if options['fix']:
            self.stdout.write('Applying security hardening...')
            hardening_result = apply_security_hardening()
            if 'error' in hardening_result:
                self.stdout.write(self.style.ERROR(f"Hardening failed: {hardening_result['error']}"))
            else:
                self.stdout.write(self.style.SUCCESS("Security hardening applied successfully"))
        
        self.stdout.write('Security audit completed')
