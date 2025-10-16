"""
Django management command to diagnose session configuration issues
Helps troubleshoot auto-logout problems after server restarts
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
import os
from datetime import timedelta

User = get_user_model()


class Command(BaseCommand):
    help = 'Diagnose session configuration to prevent auto-logout issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix-issues',
            action='store_true',
            help='Attempt to fix common session issues automatically',
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed session information',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 LMS Session Configuration Diagnostic')
        )
        self.stdout.write('=' * 50)
        
        # Check SECRET_KEY configuration
        self._check_secret_key()
        
        # Check session engine and storage
        self._check_session_engine()
        
        # Check session cookies configuration
        self._check_session_cookies()
        
        # Check database sessions
        self._check_database_sessions()
        
        # Check Redis/cache connection
        self._check_cache_connection()
        
        # Check active sessions
        self._check_active_sessions(options['detailed'])
        
        # Check for common issues
        self._check_common_issues()
        
        # Fix issues if requested
        if options['fix_issues']:
            self._fix_common_issues()
        
        self.stdout.write('=' * 50)
        self.stdout.write(
            self.style.SUCCESS('✅ Session diagnostic completed')
        )

    def _check_secret_key(self):
        """Check SECRET_KEY configuration"""
        self.stdout.write('\n🔑 SECRET_KEY Configuration:')
        
        secret_key = settings.SECRET_KEY
        if secret_key:
            self.stdout.write(f'   Status: ✅ SECRET_KEY is set')
            self.stdout.write(f'   Length: {len(secret_key)} characters')
            self.stdout.write(f'   Starts with: {secret_key[:10]}...')
            
            # Check if it's the persistent key
            if secret_key == 'azz$+s@(b7vaxopd=^6tly^a7om!8^bo2ebgpi-fj^21*8cr46':
                self.stdout.write('   Type: 🔒 Persistent SECRET_KEY (prevents logout)')
            else:
                self.stdout.write('   Type: ⚠️  Custom SECRET_KEY')
        else:
            self.stdout.write('   Status: ❌ SECRET_KEY is not set!')

    def _check_session_engine(self):
        """Check session engine configuration"""
        self.stdout.write('\n🗄️  Session Engine:')
        
        session_engine = settings.SESSION_ENGINE
        self.stdout.write(f'   Engine: {session_engine}')
        
        if 'db' in session_engine:
            self.stdout.write('   Status: ✅ Database sessions (persistent)')
        elif 'cache' in session_engine:
            self.stdout.write('   Status: ⚠️  Cache sessions (may not persist)')
        else:
            self.stdout.write('   Status: ❓ Unknown session engine')

    def _check_session_cookies(self):
        """Check session cookie configuration"""
        self.stdout.write('\n🍪 Session Cookies:')
        
        self.stdout.write(f'   Cookie Age: {settings.SESSION_COOKIE_AGE} seconds ({settings.SESSION_COOKIE_AGE // 3600} hours)')
        self.stdout.write(f'   Save Every Request: {settings.SESSION_SAVE_EVERY_REQUEST}')
        self.stdout.write(f'   Expire at Browser Close: {settings.SESSION_EXPIRE_AT_BROWSER_CLOSE}')
        self.stdout.write(f'   Cookie Name: {settings.SESSION_COOKIE_NAME}')
        self.stdout.write(f'   Secure: {settings.SESSION_COOKIE_SECURE}')
        self.stdout.write(f'   SameSite: {settings.SESSION_COOKIE_SAMESITE}')
        
        # Check for potential issues
        if settings.SESSION_COOKIE_AGE < 3600:  # Less than 1 hour
            self.stdout.write('   ⚠️  Warning: Session cookie age is very short')
        
        if not settings.SESSION_SAVE_EVERY_REQUEST:
            self.stdout.write('   ⚠️  Warning: SESSION_SAVE_EVERY_REQUEST is False')

    def _check_database_sessions(self):
        """Check database session storage"""
        self.stdout.write('\n🗃️  Database Sessions:')
        
        try:
            # Count total sessions
            total_sessions = Session.objects.count()
            self.stdout.write(f'   Total Sessions: {total_sessions}')
            
            # Count active sessions
            active_sessions = Session.objects.filter(expire_date__gt=timezone.now()).count()
            self.stdout.write(f'   Active Sessions: {active_sessions}')
            
            # Count expired sessions
            expired_sessions = Session.objects.filter(expire_date__lt=timezone.now()).count()
            self.stdout.write(f'   Expired Sessions: {expired_sessions}')
            
            if active_sessions > 0:
                self.stdout.write('   Status: ✅ Database sessions are working')
            else:
                self.stdout.write('   Status: ⚠️  No active sessions found')
                
        except Exception as e:
            self.stdout.write(f'   Status: ❌ Database error: {e}')

    def _check_cache_connection(self):
        """Check cache/Redis connection"""
        self.stdout.write('\n⚡ Cache Connection:')
        
        try:
            # Test cache connection
            cache.set('session_test', 'ok', 10)
            test_value = cache.get('session_test')
            
            if test_value == 'ok':
                self.stdout.write('   Status: ✅ Cache connection working')
            else:
                self.stdout.write('   Status: ❌ Cache test failed')
                
        except Exception as e:
            self.stdout.write(f'   Status: ❌ Cache error: {e}')

    def _check_active_sessions(self, detailed=False):
        """Check active sessions and users"""
        self.stdout.write('\n👥 Active Sessions:')
        
        try:
            active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
            user_sessions = {}
            
            for session in active_sessions:
                try:
                    session_data = session.get_decoded()
                    user_id = session_data.get('_auth_user_id')
                    if user_id:
                        if user_id not in user_sessions:
                            user_sessions[user_id] = 0
                        user_sessions[user_id] += 1
                except Exception:
                    # Session data is corrupted
                    pass
            
            self.stdout.write(f'   Active User Sessions: {len(user_sessions)}')
            
            if detailed and user_sessions:
                self.stdout.write('   User Session Details:')
                for user_id, count in user_sessions.items():
                    try:
                        user = User.objects.get(id=user_id)
                        self.stdout.write(f'     - {user.username} ({user.email}): {count} sessions')
                    except User.DoesNotExist:
                        self.stdout.write(f'     - User ID {user_id}: {count} sessions (user not found)')
                        
        except Exception as e:
            self.stdout.write(f'   Status: ❌ Error checking sessions: {e}')

    def _check_common_issues(self):
        """Check for common session issues"""
        self.stdout.write('\n🔍 Common Issues Check:')
        
        issues_found = []
        
        # Check SECRET_KEY consistency
        if not hasattr(settings, 'SECRET_KEY') or not settings.SECRET_KEY:
            issues_found.append('SECRET_KEY is not set')
        
        # Check session engine
        if 'cache' in settings.SESSION_ENGINE and not settings.SESSION_SAVE_EVERY_REQUEST:
            issues_found.append('Cache sessions without SESSION_SAVE_EVERY_REQUEST may cause logout')
        
        # Check cookie age
        if settings.SESSION_COOKIE_AGE < 3600:
            issues_found.append('Session cookie age is very short (< 1 hour)')
        
        # Check for environment variables
        if not os.environ.get('DJANGO_SECRET_KEY'):
            issues_found.append('DJANGO_SECRET_KEY environment variable not set')
        
        if issues_found:
            self.stdout.write('   Issues Found:')
            for issue in issues_found:
                self.stdout.write(f'     ❌ {issue}')
        else:
            self.stdout.write('   Status: ✅ No common issues detected')

    def _fix_common_issues(self):
        """Attempt to fix common session issues"""
        self.stdout.write('\n🔧 Attempting to fix common issues...')
        
        try:
            # Clear expired sessions
            expired_count = Session.objects.filter(expire_date__lt=timezone.now()).count()
            if expired_count > 0:
                Session.objects.filter(expire_date__lt=timezone.now()).delete()
                self.stdout.write(f'   ✅ Cleared {expired_count} expired sessions')
            
            # Clear corrupted sessions
            corrupted_count = 0
            for session in Session.objects.filter(expire_date__gt=timezone.now()):
                try:
                    session.get_decoded()
                except Exception:
                    session.delete()
                    corrupted_count += 1
            
            if corrupted_count > 0:
                self.stdout.write(f'   ✅ Cleared {corrupted_count} corrupted sessions')
            
            # Extend sessions that are close to expiry
            near_expiry = Session.objects.filter(
                expire_date__lt=timezone.now() + timedelta(hours=2),
                expire_date__gt=timezone.now()
            )
            extended_count = 0
            for session in near_expiry:
                session.expire_date = timezone.now() + timedelta(days=7)
                session.save()
                extended_count += 1
            
            if extended_count > 0:
                self.stdout.write(f'   ✅ Extended {extended_count} sessions')
            
            self.stdout.write('   ✅ Common issues fixed')
            
        except Exception as e:
            self.stdout.write(f'   ❌ Error fixing issues: {e}')
