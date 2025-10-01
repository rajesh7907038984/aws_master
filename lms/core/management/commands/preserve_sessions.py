"""
Django management command to preserve user sessions during deployment
Prevents auto-logout after deployment by extending active sessions
"""

from django.core.management.base import BaseCommand
from core.session_utils import preserve_sessions_during_deployment, check_session_health


class Command(BaseCommand):
    help = 'Preserve user sessions during deployment to prevent auto-logout'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check session health without extending sessions',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Number of hours to extend sessions by (default: 24)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 Checking session configuration...')
        )
        
        # Check session health
        health = check_session_health()
        if health:
            self.stdout.write(f"📊 Session Health Report:")
            self.stdout.write(f"   Redis Connection: {'✅ OK' if health['redis_connection'] else '❌ Failed'}")
            self.stdout.write(f"   Active Sessions: {health['database_sessions']}")
            self.stdout.write(f"   Session Engine: {health['session_engine']}")
            self.stdout.write(f"   Cache Alias: {health['session_cache_alias']}")
            self.stdout.write(f"   Cookie Age: {health['session_cookie_age']} seconds")
        
        if options['check_only']:
            self.stdout.write(
                self.style.SUCCESS('✅ Session health check completed')
            )
            return
        
        # Preserve sessions
        self.stdout.write(
            self.style.SUCCESS('🛡️  Preserving user sessions...')
        )
        
        result = preserve_sessions_during_deployment()
        if result:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Session preservation completed:\n"
                    f"   Extended sessions: {result['extended_sessions']}\n"
                    f"   Cleared expired: {result['cleared_sessions']}\n"
                    f"   Active sessions: {result['active_sessions']}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Failed to preserve sessions')
            )
