"""
Security Audit Management Command
Performs comprehensive security auditing and hardening
"""

from django.core.management.base import BaseCommand
from core.security.hardening import validate_security_settings, apply_security_hardening
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
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
