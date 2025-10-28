"""
Management command to fix SCORM tracking issues
Applies the enhanced completion detection and score extraction to existing attempts
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from scorm.models import ScormAttempt
from courses.models import TopicProgress
from scorm.signals import _extract_score_from_data, _decode_suspend_data, _update_topic_progress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM tracking issues for existing attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Fix specific attempt ID',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Fix attempts for specific user',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force fix even if attempt appears to be working',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        
        if options['attempt_id']:
            attempts = ScormAttempt.objects.filter(id=options['attempt_id'])
        elif options['user']:
            attempts = ScormAttempt.objects.filter(user__username=options['user'])
        else:
            # Get recent attempts that might have issues
            attempts = ScormAttempt.objects.filter(
                started_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).order_by('-started_at')
        
        if not attempts.exists():
            self.stdout.write(self.style.WARNING('No attempts found to fix'))
            return
        
        self.stdout.write(f'Found {attempts.count()} attempts to process')
        
        fixed_count = 0
        for attempt in attempts:
            if self.fix_attempt(attempt):
                fixed_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully fixed {fixed_count} out of {attempts.count()} attempts')
        )

    def fix_attempt(self, attempt):
        """Fix a single SCORM attempt"""
        self.stdout.write(f'\n--- Processing Attempt ID: {attempt.id} ---')
        self.stdout.write(f'User: {attempt.user.username}')
        self.stdout.write(f'Package: {attempt.scorm_package.title}')
        self.stdout.write(f'Current Status: {attempt.lesson_status}')
        self.stdout.write(f'Current Score: {attempt.score_raw}')
        self.stdout.write(f'Progress %: {attempt.progress_percentage}')
        
        changes_made = False
        
        # Check if attempt needs fixing
        needs_fixing = (
            attempt.lesson_status in ['incomplete', 'not_attempted'] or
            attempt.score_raw is None or
            attempt.progress_percentage == 0
        )
        
        if not needs_fixing and not self.force:
            self.stdout.write(self.style.WARNING('  Attempt appears to be working correctly'))
            return False
        
        # Try to extract score from suspend data
        if attempt.suspend_data:
            self.stdout.write('  Checking suspend data for completion evidence...')
            
            decoded_data = _decode_suspend_data(attempt.suspend_data)
            if decoded_data:
                self.stdout.write(f'  Suspend data length: {len(decoded_data)} chars')
                
                # Check for completion evidence
                completion_keywords = ['complete', 'done', 'qd', 'finished', 'passed', 'failed']
                found_keywords = [kw for kw in completion_keywords if kw in decoded_data.lower()]
                
                if found_keywords:
                    self.stdout.write(f'  Found completion keywords: {found_keywords}')
                    
                    # Try to extract score
                    extracted_score = _extract_score_from_data(decoded_data)
                    if extracted_score is not None:
                        self.stdout.write(f'  Extracted score: {extracted_score}')
                        
                        if not self.dry_run:
                            # Update attempt with extracted score
                            attempt.score_raw = extracted_score
                            
                            # Determine completion status
                            mastery_score = attempt.scorm_package.mastery_score or 70
                            if extracted_score >= mastery_score:
                                attempt.lesson_status = 'passed'
                            else:
                                attempt.lesson_status = 'failed'
                            
                            # Update progress percentage
                            attempt.progress_percentage = 100.0
                            attempt.completed_at = timezone.now()
                            
                            attempt.save()
                            changes_made = True
                            
                            self.stdout.write(self.style.SUCCESS(f'  ✅ Updated attempt - Score: {extracted_score}, Status: {attempt.lesson_status}'))
                        else:
                            self.stdout.write(self.style.WARNING(f'  [DRY RUN] Would update attempt - Score: {extracted_score}'))
                    else:
                        self.stdout.write('  No valid score found in suspend data')
                else:
                    self.stdout.write('  No completion evidence found in suspend data')
            else:
                self.stdout.write('  Could not decode suspend data')
        else:
            self.stdout.write('  No suspend data available')
        
        # Update TopicProgress if attempt was fixed
        if changes_made and not self.dry_run:
            try:
                topic_progress = TopicProgress.objects.get(
                    user=attempt.user,
                    topic=attempt.scorm_package.topic
                )
                
                # Update TopicProgress
                topic_progress.last_score = float(attempt.score_raw)
                if not topic_progress.best_score or float(attempt.score_raw) > topic_progress.best_score:
                    topic_progress.best_score = float(attempt.score_raw)
                
                topic_progress.completed = True
                topic_progress.completion_method = 'scorm'
                topic_progress.completed_at = attempt.completed_at
                topic_progress.save()
                
                self.stdout.write(self.style.SUCCESS('  ✅ Updated TopicProgress'))
                
            except TopicProgress.DoesNotExist:
                self.stdout.write(self.style.WARNING('  TopicProgress not found - creating new one'))
                _update_topic_progress(attempt, attempt.score_raw)
        
        return changes_made
