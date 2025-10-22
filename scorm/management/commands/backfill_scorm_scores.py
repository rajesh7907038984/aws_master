"""
Management command to backfill SCORM scores from attempts to TopicProgress
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ScormAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backfill SCORM scores from attempts to TopicProgress records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get all SCORM attempts with scores
        attempts_with_scores = ScormAttempt.objects.filter(
            score_raw__isnull=False
        ).select_related('user', 'scorm_package__topic')
        
        updated_count = 0
        created_count = 0
        
        with transaction.atomic():
            for attempt in attempts_with_scores:
                try:
                    # Get or create TopicProgress
                    progress, created = TopicProgress.objects.get_or_create(
                        user=attempt.user,
                        topic=attempt.scorm_package.topic
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(f'Created TopicProgress for {attempt.user.username} on {attempt.scorm_package.topic.title}')
                    
                    # Update scores
                    if not dry_run:
                        progress.last_score = attempt.score_raw
                        
                        # Update best score if this is better
                        if progress.best_score is None or attempt.score_raw > progress.best_score:
                            progress.best_score = attempt.score_raw
                        
                        # Update completion status
                        if attempt.lesson_status in ['completed', 'passed']:
                            progress.completed = True
                            progress.completion_method = 'scorm'
                        
                        # Update progress data
                        progress.progress_data.update({
                            'scorm_attempt_id': attempt.id,
                            'lesson_status': attempt.lesson_status,
                            'completion_status': attempt.completion_status,
                            'success_status': attempt.success_status,
                            'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                            'score_max': float(attempt.score_max) if attempt.score_max else None,
                            'score_min': float(attempt.score_min) if attempt.score_min else None,
                            'score_scaled': float(attempt.score_scaled) if attempt.score_scaled else None,
                            'total_time': attempt.total_time,
                            'session_time': attempt.session_time,
                            'lesson_location': attempt.lesson_location,
                            'suspend_data': attempt.suspend_data,
                            'entry': attempt.entry,
                            'exit_mode': attempt.exit_mode,
                        })
                        
                        progress.save()
                    
                    updated_count += 1
                    
                    if updated_count % 100 == 0:
                        self.stdout.write(f'Processed {updated_count} attempts...')
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error processing attempt {attempt.id}: {str(e)}')
                    )
                    continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Backfill completed: {updated_count} attempts processed, '
                f'{created_count} new TopicProgress records created'
            )
        )
