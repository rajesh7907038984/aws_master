"""
Django management command to clean up expired and corrupted sessions.
This helps prevent session corruption issues.
"""

from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up expired and corrupted sessions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup even if there are many sessions',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write("🧹 Starting session cleanup...")
        
        # Get current time
        now = timezone.now()
        
        # Count total sessions
        total_sessions = Session.objects.count()
        self.stdout.write("📊 Total sessions: {{total_sessions}}")
        
        if total_sessions == 0:
            self.stdout.write("✅ No sessions to clean up")
            return
        
        # Find expired sessions
        expired_sessions = Session.objects.filter(expire_date__lt=now)
        expired_count = expired_sessions.count()
        
        self.stdout.write("⏰ Expired sessions: {{expired_count}}")
        
        # Find potentially corrupted sessions (empty session data)
        corrupted_sessions = Session.objects.filter(session_data='')
        corrupted_count = corrupted_sessions.count()
        
        self.stdout.write("💥 Corrupted sessions: {{corrupted_count}}")
        
        # Find sessions with invalid session data
        invalid_sessions = Session.objects.exclude(session_data='').exclude(session_data__isnull=True)
        invalid_count = 0
        
        for session in invalid_sessions:
            try:
                session.get_decoded()
            except Exception:
                invalid_count += 1
        
        self.stdout.write("🚫 Invalid sessions: {{invalid_count}}")
        
        total_to_delete = expired_count + corrupted_count + invalid_count
        
        if total_to_delete == 0:
            self.stdout.write("✅ No sessions need cleanup")
            return
        
        if not force and total_to_delete > 1000:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  Found {{total_to_delete}} sessions to delete. "
                    "Use --force to proceed with large cleanup."
                )
            )
            return
        
        if dry_run:
            self.stdout.write("🔍 DRY RUN: Would delete {{total_to_delete}} sessions")
            return
        
        # Perform cleanup
        deleted_count = 0
        
        with transaction.atomic():
            # Delete expired sessions
            if expired_count > 0:
                deleted_expired = expired_sessions.delete()[0]
                deleted_count += deleted_expired
                self.stdout.write("🗑️  Deleted {{deleted_expired}} expired sessions")
            
            # Delete corrupted sessions
            if corrupted_count > 0:
                deleted_corrupted = corrupted_sessions.delete()[0]
                deleted_count += deleted_corrupted
                self.stdout.write("🗑️  Deleted {{deleted_corrupted}} corrupted sessions")
            
            # Delete invalid sessions
            if invalid_count > 0:
                invalid_sessions_list = []
                for session in Session.objects.exclude(session_data='').exclude(session_data__isnull=True):
                    try:
                        session.get_decoded()
                    except Exception:
                        invalid_sessions_list.append(session.pk)
                
                if invalid_sessions_list:
                    deleted_invalid = Session.objects.filter(pk__in=invalid_sessions_list).delete()[0]
                    deleted_count += deleted_invalid
                    self.stdout.write("🗑️  Deleted {{deleted_invalid}} invalid sessions")
        
        self.stdout.write(
            self.style.SUCCESS(
                "✅ Session cleanup completed! Deleted {{deleted_count}} sessions"
            )
        )
        
        # Show remaining sessions
        remaining = Session.objects.count()
        self.stdout.write("📊 Remaining sessions: {{remaining}}")
