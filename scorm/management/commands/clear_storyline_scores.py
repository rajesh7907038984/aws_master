"""
Management command to remove all old Storyline SCORM scores
This will clear all scores and let the system re-score them properly
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove all old Storyline SCORM scores to allow proper re-scoring'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleared without making changes',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Clear only specific SCORM package ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force clear all Storyline scores regardless of status',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        package_id = options.get('package_id')
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS('🧹 Starting Storyline SCORM score cleanup...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Find all Storyline attempts
        attempts_query = ScormAttempt.objects.filter(
            scorm_package__version='storyline'
        ).select_related('scorm_package', 'user')
        
        if package_id:
            attempts_query = attempts_query.filter(scorm_package_id=package_id)
        
        cleared_count = 0
        total_checked = 0
        
        for attempt in attempts_query:
            total_checked += 1
            
            # Check if this attempt should be cleared
            should_clear = force or self._should_clear_attempt(attempt)
            
            if should_clear:
                self.stdout.write(
                    f'Will clear: Attempt {attempt.id} - '
                    f'User: {attempt.user.username}, '
                    f'Score: {attempt.score_raw}, '
                    f'Status: {attempt.lesson_status}'
                )
                
                if not dry_run:
                    self._clear_attempt_score(attempt)
                
                cleared_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Cleanup complete! Checked {total_checked} attempts, '
                f'cleared {cleared_count} scores'
            )
        )
        
        if not dry_run and cleared_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    '🔄 Scores have been cleared. Users will need to retake '
                    'Storyline SCORM content to get proper scores.'
                )
            )

    def _should_clear_attempt(self, attempt):
        """Determine if an attempt score should be cleared"""
        
        # Clear if no score (already clean)
        if attempt.score_raw is None:
            return False
            
        score = float(attempt.score_raw)
        
        # Clear suspicious scores (20%, 40%, 60%, 80%)
        suspicious_scores = [20.0, 40.0, 60.0, 80.0]
        if score in suspicious_scores:
            return True
        
        # Clear incomplete attempts with scores
        if attempt.lesson_status in ['incomplete', 'not_attempted']:
            return True
        
        # Clear failed attempts that might be incomplete
        if attempt.lesson_status == 'failed':
            if attempt.suspend_data:
                visited_count = attempt.suspend_data.count('Visited')
                # If user visited few slides but got a low score, likely incomplete
                if visited_count < 5 and score < 50:
                    return True
        
        # Clear attempts without proper completion evidence
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
            
            if not has_completion_evidence:
                return True
        
        return False

    def _clear_attempt_score(self, attempt):
        """Clear an attempt score and related data"""
        try:
            with transaction.atomic():
                # Clear the score
                old_score = attempt.score_raw
                attempt.score_raw = None
                attempt.lesson_status = 'incomplete'
                attempt.completion_status = 'incomplete'
                attempt.success_status = 'unknown'
                attempt.save()
                
                # Clear TopicProgress scores
                try:
                    topic_progress = TopicProgress.objects.get(
                        user=attempt.user,
                        topic=attempt.scorm_package.topic
                    )
                    
                    # Clear scores but keep attempts count
                    topic_progress.last_score = None
                    topic_progress.best_score = None
                    topic_progress.completed = False
                    topic_progress.completion_method = 'auto'  # Set default value instead of None
                    topic_progress.completed_at = None
                    
                    # Clear progress data
                    if topic_progress.progress_data:
                        topic_progress.progress_data.pop('score_raw', None)
                        topic_progress.progress_data.pop('scorm_attempt_id', None)
                        topic_progress.progress_data.pop('lesson_status', None)
                        topic_progress.progress_data.pop('storyline_completed', None)
                    
                    topic_progress.save()
                    
                    logger.info(
                        f'Cleared TopicProgress for user {attempt.user.username}, '
                        f'topic {attempt.scorm_package.topic.title}'
                    )
                    
                except TopicProgress.DoesNotExist:
                    pass  # No TopicProgress to clear
                
                logger.info(
                    f'Cleared attempt {attempt.id}: '
                    f'removed score {old_score}'
                )
                
        except Exception as e:
            logger.error(f'Failed to clear attempt {attempt.id}: {str(e)}')
