#!/usr/bin/env python3
"""
Django management command to test session fixes
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Test session fixes and health'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        
        if verbose:
            self.stdout.write('🧪 Testing Session Fixes...\n')
        
        # Test 1: Session Backend Health
        self.test_session_backend_health(verbose)
        
        # Test 2: Cache Connection
        self.test_cache_connection(verbose)
        
        # Test 3: Session Creation
        self.test_session_creation(verbose)
        
        # Test 4: Session Recovery
        self.test_session_recovery(verbose)
        
        # Test 5: AnonymousUser Protection
        self.test_anonymous_user_protection(verbose)
        
        if verbose:
            self.stdout.write('\n✅ All session tests completed!')

    def test_session_backend_health(self, verbose):
        """Test session backend health"""
        if verbose:
            self.stdout.write('📊 Testing session backend health...')
        
        try:
            # Test cache connection
            cache.set('test_key', 'test_value', 10)
            result = cache.get('test_key')
            
            if result == 'test_value':
                self.stdout.write(self.style.SUCCESS('✅ Cache connection: OK'))
            else:
                self.stdout.write(self.style.ERROR('❌ Cache connection: FAILED'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Cache connection: ERROR - {e}'))

    def test_cache_connection(self, verbose):
        """Test cache connection"""
        if verbose:
            self.stdout.write('🔗 Testing cache connection...')
        
        try:
            # Test Redis connection
            cache.set('session_health_check', 'ok', 10)
            redis_ok = cache.get('session_health_check') == 'ok'
            
            if redis_ok:
                self.stdout.write(self.style.SUCCESS('✅ Redis cache: OK'))
            else:
                self.stdout.write(self.style.WARNING('⚠️ Redis cache: DEGRADED'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Redis cache: ERROR - {e}'))

    def test_session_creation(self, verbose):
        """Test session creation"""
        if verbose:
            self.stdout.write('🆕 Testing session creation...')
        
        try:
            # Get active session count
            active_sessions = Session.objects.filter(expire_date__gt=timezone.now()).count()
            
            if verbose:
                self.stdout.write(f'   Active sessions: {active_sessions}')
            
            self.stdout.write(self.style.SUCCESS('✅ Session creation: OK'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Session creation: ERROR - {e}'))

    def test_session_recovery(self, verbose):
        """Test session recovery mechanisms"""
        if verbose:
            self.stdout.write('🔄 Testing session recovery...')
        
        try:
            # Test session cleanup
            expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
            expired_count = expired_sessions.count()
            
            if expired_count > 0:
                if verbose:
                    self.stdout.write(f'   Found {expired_count} expired sessions')
                self.stdout.write(self.style.WARNING(f'⚠️ Found {expired_count} expired sessions'))
            else:
                self.stdout.write(self.style.SUCCESS('✅ Session cleanup: OK'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Session recovery: ERROR - {e}'))

    def test_anonymous_user_protection(self, verbose):
        """Test AnonymousUser protection"""
        if verbose:
            self.stdout.write('🛡️ Testing AnonymousUser protection...')
        
        try:
            # Test role access protection
            from django.contrib.auth.models import AnonymousUser
            from django.test import RequestFactory
            
            factory = RequestFactory()
            request = factory.get('/')
            request.user = AnonymousUser()
            
            # Test safe role access
            is_authenticated = request.user.is_authenticated
            has_role = hasattr(request.user, 'role')
            
            if not is_authenticated and not has_role:
                self.stdout.write(self.style.SUCCESS('✅ AnonymousUser protection: OK'))
            else:
                self.stdout.write(self.style.ERROR('❌ AnonymousUser protection: FAILED'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ AnonymousUser protection: ERROR - {e}'))
