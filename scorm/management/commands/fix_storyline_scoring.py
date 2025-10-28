"""
Management command to fix incorrect Storyline SCORM scoring
Removes incorrect partial scores for incomplete attempts
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix incorrect Storyline SCORM scoring for incomplete attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix only specific SCORM package ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        package_id = options.get('package_id')
        
        self.stdout.write(
            self.style.SUCCESS('🔧 Starting Storyline SCORM scoring fix...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Find attempts that might have incorrect scores
        attempts_query = ScormAttempt.objects.filter(
            scorm_package__version__in=['storyline', '2004', '1.2']
        ).select_related('scorm_package', 'user')
        
        if package_id:
            attempts_query = attempts_query.filter(scorm_package_id=package_id)
        
        fixed_count = 0
        total_checked = 0
        
        for attempt in attempts_query:
            total_checked += 1
            
            # Check if this attempt has an incorrect partial score
            if self._has_incorrect_partial_score(attempt):
                self.stdout.write(
                    f'Found incorrect score: Attempt {attempt.id} - '
                    f'User: {attempt.user.username}, '
                    f'Score: {attempt.score_raw}, '
                    f'Status: {attempt.lesson_status}'
                )
                
                if not dry_run:
                    self._fix_attempt_score(attempt)
                
                fixed_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Fix complete! Checked {total_checked} attempts, '
                f'fixed {fixed_count} incorrect scores'
            )
        )

    def _has_incorrect_partial_score(self, attempt):
        """Check if an attempt has an incorrect partial score"""
        
        # Check if score looks like a calculated percentage (20%, 40%, etc.)
        if attempt.score_raw is None:
            return False
            
        score = float(attempt.score_raw)
        
        # Check for common calculated percentages that shouldn't exist
        suspicious_scores = [20.0, 40.0, 60.0, 80.0]  # Common slide-based calculations
        
        if score in suspicious_scores:
            # Check if this is likely a calculated score based on slides
            if attempt.suspend_data:
                visited_count = attempt.suspend_data.count('Visited')
                if visited_count > 0:
                    # Check if this matches a slide-based calculation
                    calculated_score = (visited_count / 5) * 100
                    if abs(score - calculated_score) < 0.1:  # Very close match
                        return True
        
        # Check for incomplete attempts with scores but no completion evidence
        if attempt.lesson_status in ['incomplete', 'not_attempted']:
            if attempt.suspend_data:
                has_completion_evidence = (
                    'complete' in attempt.suspend_data.lower() or
                    'finished' in attempt.suspend_data.lower() or
                    'done' in attempt.suspend_data.lower() or
                    'passed' in attempt.suspend_data.lower() or
                    'failed' in attempt.suspend_data.lower() or
                    '"qd"true' in attempt.suspend_data or
                    'qd":true' in attempt.suspend_data or
                    'qd"true' in attempt.suspend_data
                )
                
                if not has_completion_evidence and score > 0:
                    return True
        
        return False

    def _fix_attempt_score(self, attempt):
        """Fix an incorrect attempt score"""
        try:
            with transaction.atomic():
                # Clear the incorrect score
                old_score = attempt.score_raw
                attempt.score_raw = None
                attempt.lesson_status = 'incomplete'
                attempt.save()
                
                # Update TopicProgress to remove the incorrect score
                try:
                    topic_progress = TopicProgress.objects.get(
                        user=attempt.user,
                        topic=attempt.scorm_package.topic
                    )
                    
                    # Only clear if the score matches what we're removing
                    if topic_progress.last_score == old_score:
                        topic_progress.last_score = None
                        topic_progress.completed = False
                        topic_progress.completion_method = None
                        topic_progress.completed_at = None
                        topic_progress.save()
                        
                        logger.info(
                            f'Fixed TopicProgress for user {attempt.user.username}, '
                            f'topic {attempt.scorm_package.topic.title}'
                        )
                        
                except TopicProgress.DoesNotExist:
                    pass  # No TopicProgress to fix
                
                logger.info(
                    f'Fixed attempt {attempt.id}: '
                    f'removed incorrect score {old_score}'
                )
                
        except Exception as e:
            logger.error(f'Failed to fix attempt {attempt.id}: {str(e)}')
