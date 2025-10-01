#!/usr/bin/env python3
"""
Django management command to clean up expired sessions and fix session corruption issues.

This command should be run periodically (e.g., via cron) to maintain session health.
"""

from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up expired sessions and fix session corruption issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually doing it'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup even if there are active sessions'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        verbose = options['verbose']

        self.stdout.write(self.style.SUCCESS('🧹 Starting session cleanup...'))

        try:
            # Clean up expired sessions
            expired_count = self._cleanup_expired_sessions(dry_run, verbose)
            
            # Clean up corrupted sessions
            corrupted_count = self._cleanup_corrupted_sessions(dry_run, verbose)
            
            # Clear session cache if using cached sessions
            if not dry_run:
                self._clear_session_cache(verbose)
            
            # Summary
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'🔍 DRY RUN: Would clean up {expired_count} expired '
                        f'and {corrupted_count} corrupted sessions'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Cleaned up {expired_count} expired '
                        f'and {corrupted_count} corrupted sessions'
                    )
                )

        except Exception as e:
            logger.error(f"Session cleanup failed: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'❌ Session cleanup failed: {str(e)}')
            )
            return 1

    def _cleanup_expired_sessions(self, dry_run, verbose):
        """Clean up sessions that have expired"""
        try:
            # Get current time
            now = timezone.now()
            
            # Find expired sessions
            expired_sessions = Session.objects.filter(expire_date__lt=now)
            count = expired_sessions.count()
            
            if verbose:
                self.stdout.write(f'📅 Found {count} expired sessions')
            
            if not dry_run and count > 0:
                with transaction.atomic():
                    deleted_count, _ = expired_sessions.delete()
                    if verbose:
                        self.stdout.write(f'🗑️  Deleted {deleted_count} expired sessions')
                    return deleted_count
            
            return count

        except Exception as e:
            logger.error(f"Error cleaning expired sessions: {str(e)}")
            if verbose:
                self.stdout.write(self.style.ERROR(f'Error cleaning expired sessions: {str(e)}'))
            return 0

    def _cleanup_corrupted_sessions(self, dry_run, verbose):
        """Clean up sessions with corrupted data"""
        try:
            corrupted_sessions = []
            total_sessions = Session.objects.count()
            
            if verbose:
                self.stdout.write(f'🔍 Checking {total_sessions} sessions for corruption...')
            
            # Check each session for corruption
            for session in Session.objects.all():
                try:
                    # Try to decode session data - this is what triggers corruption warnings
                    decoded_data = session.get_decoded()
                    
                    # Additional corruption checks
                    if not isinstance(decoded_data, dict):
                        raise ValueError("Session data is not a dictionary")
                    
                    # Check for common corruption patterns
                    if '_auth_user_id' in decoded_data:
                        user_id = decoded_data['_auth_user_id']
                        if not isinstance(user_id, (int, str)) or str(user_id).strip() == '':
                            raise ValueError("Invalid user ID in session")
                
                except Exception as e:
                    corrupted_sessions.append(session.session_key)  # Use session_key instead of pk
                    if verbose:
                        self.stdout.write(
                            f'🚨 Corrupted session found: {session.session_key[:8]}... - {str(e)}'
                        )
            
            count = len(corrupted_sessions)
            if verbose:
                self.stdout.write(f'🔧 Found {count} corrupted sessions')
            
            if not dry_run and count > 0:
                with transaction.atomic():
                    # Use session_key for deletion
                    deleted_count, _ = Session.objects.filter(session_key__in=corrupted_sessions).delete()
                    if verbose:
                        self.stdout.write(f'🗑️  Deleted {deleted_count} corrupted sessions')
                    return deleted_count
            
            return count

        except Exception as e:
            logger.error(f"Error cleaning corrupted sessions: {str(e)}")
            if verbose:
                self.stdout.write(self.style.ERROR(f'Error cleaning corrupted sessions: {str(e)}'))
            return 0

    def _clear_session_cache(self, verbose):
        """Clear session-related cache entries"""
        try:
            # Clear session cache entries
            # This is useful when using cached_db sessions
            cache.delete_many([
                key for key in cache._cache.keys() 
                if key.startswith('session:') or key.startswith('django.contrib.sessions')
            ])
            
            if verbose:
                self.stdout.write('🗑️  Cleared session cache entries')

        except Exception as e:
            logger.warning(f"Could not clear session cache: {str(e)}")
            if verbose:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Could not clear session cache: {str(e)}')
                )
