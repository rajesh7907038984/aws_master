#!/usr/bin/env python3
"""
Django management command to clean up expired and stale quiz attempts.

This command should be run periodically (e.g., via cron) to maintain system performance
and clean up old quiz attempt data.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from quiz.models import QuizAttempt, UserAnswer
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up expired and stale quiz attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually doing it'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup even if there are many attempts'
        )
        parser.add_argument(
            '--stale-hours',
            type=int,
            default=2,
            help='Hours after which inactive attempts are considered stale (default: 2)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
        parser.add_argument(
            '--quiz-id',
            type=int,
            help='Clean up attempts for specific quiz only'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Clean up attempts for specific user only'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        stale_hours = options['stale_hours']
        verbose = options['verbose']
        quiz_id = options.get('quiz_id')
        user_id = options.get('user_id')

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        self.stdout.write(self.style.SUCCESS('🧹 Starting quiz attempt cleanup...'))

        try:
            # Clean up expired attempts
            expired_count = self._cleanup_expired_attempts(dry_run, verbose, quiz_id, user_id)
            
            # Clean up stale attempts
            stale_count = self._cleanup_stale_attempts(dry_run, verbose, stale_hours, quiz_id, user_id)
            
            # Clean up orphaned user answers
            orphaned_count = self._cleanup_orphaned_answers(dry_run, verbose)
            
            total_cleaned = expired_count + stale_count + orphaned_count
            
            # Check if cleanup threshold is exceeded
            if not force and total_cleaned > 100:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Would clean up {total_cleaned} attempts. Use --force to proceed.'
                    )
                )
                return
            
            # Summary
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f'🔍 DRY RUN: Would clean up {expired_count} expired, '
                        f'{stale_count} stale attempts, and {orphaned_count} orphaned answers'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f' Cleaned up {expired_count} expired, {stale_count} stale attempts, '
                        f'and {orphaned_count} orphaned answers'
                    )
                )

        except Exception as e:
            logger.error(f"Quiz cleanup failed: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f' Quiz cleanup failed: {str(e)}')
            )
            return 1

    def _cleanup_expired_attempts(self, dry_run, verbose, quiz_id=None, user_id=None):
        """Clean up quiz attempts that have exceeded their time limit"""
        
        # Build queryset
        queryset = QuizAttempt.objects.filter(is_completed=False)
        
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        expired_attempts = []
        for attempt in queryset.select_related('quiz'):
            if attempt.is_expired():
                expired_attempts.append(attempt)
        
        if verbose:
            self.stdout.write(f'📅 Found {len(expired_attempts)} expired attempts')
        
        if not dry_run and expired_attempts:
            with transaction.atomic():
                # Delete associated answers first
                attempt_ids = [attempt.id for attempt in expired_attempts]
                UserAnswer.objects.filter(attempt_id__in=attempt_ids).delete()
                
                # Delete the attempts
                QuizAttempt.objects.filter(id__in=attempt_ids).delete()
                
                if verbose:
                    for attempt in expired_attempts:
                        self.stdout.write(f'   Deleted expired attempt {attempt.id} for quiz "{attempt.quiz.title}"')
        
        return len(expired_attempts)
    
    def _cleanup_stale_attempts(self, dry_run, verbose, stale_hours, quiz_id=None, user_id=None):
        """Clean up attempts that haven't had activity for specified hours"""
        
        stale_time = timezone.now() - timedelta(hours=stale_hours)
        
        # Build queryset
        queryset = QuizAttempt.objects.filter(
            is_completed=False,
            last_activity__lt=stale_time
        )
        
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        stale_attempts = queryset.select_related('quiz', 'user')
        count = stale_attempts.count()
        
        if verbose:
            self.stdout.write(f'⏰ Found {count} stale attempts (inactive for >{stale_hours}h)')
        
        if not dry_run and count > 0:
            with transaction.atomic():
                # Delete associated answers first
                UserAnswer.objects.filter(attempt__in=stale_attempts).delete()
                
                # Delete the attempts
                deleted_count = stale_attempts.delete()[0]
                
                if verbose:
                    self.stdout.write(f'  🗑️  Deleted {deleted_count} stale attempts')
        
        return count
    
    def _cleanup_orphaned_answers(self, dry_run, verbose):
        """Clean up user answers that don't have corresponding attempts"""
        
        # Find answers where the attempt no longer exists
        orphaned_answers = UserAnswer.objects.filter(attempt__isnull=True)
        count = orphaned_answers.count()
        
        if verbose:
            self.stdout.write(f'🔗 Found {count} orphaned user answers')
        
        if not dry_run and count > 0:
            orphaned_answers.delete()
            if verbose:
                self.stdout.write(f'  🗑️  Deleted {count} orphaned answers')
        
        return count
