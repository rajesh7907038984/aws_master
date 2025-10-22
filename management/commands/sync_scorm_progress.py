"""
Management command to sync SCORM progress data
Fixes data synchronization issues between ScormAttempt and TopicProgress
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from courses.models import TopicProgress
from scorm.models import ScormAttempt
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync SCORM progress data between ScormAttempt and TopicProgress models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Sync progress for specific topic ID'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync progress for specific user ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes'
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Build query filters
        filters = {}
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        if user_id:
            filters['user_id'] = user_id
        
        # Get SCORM attempts that need syncing
        scorm_attempts = ScormAttempt.objects.filter(**filters).select_related(
            'user', 'scorm_package__topic'
        ).order_by('user', 'scorm_package__topic', '-id')
        
        if not scorm_attempts.exists():
            self.stdout.write(self.style.WARNING('No SCORM attempts found matching criteria'))
            return
        
        self.stdout.write(f'Found {scorm_attempts.count()} SCORM attempts to process')
        
        synced_count = 0
        created_count = 0
        updated_count = 0
        
        # Group by user and topic to get latest attempt for each
        processed = set()
        
        for attempt in scorm_attempts:
            key = (attempt.user.id, attempt.scorm_package.topic.id)
            
            # Skip if we already processed this user-topic combination
            if key in processed:
                continue
            
            processed.add(key)
            
            try:
                # Get or create topic progress
                progress, created = TopicProgress.objects.get_or_create(
                    user=attempt.user,
                    topic=attempt.scorm_package.topic,
                    defaults={'completed': False, 'progress_data': {}}
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(f'Created TopicProgress for user {attempt.user.username}, topic {attempt.scorm_package.topic.id}')
                else:
                    updated_count += 1
                
                # Initialize progress_data if not exists
                if not isinstance(progress.progress_data, dict):
                    progress.progress_data = {}
                
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
                    'last_updated': timezone.now().isoformat(),
                    'scorm_sync': True,
                })
                
                # Sync completion status
                is_completed = attempt.lesson_status in ['completed', 'passed']
                
                if is_completed:
                    if not progress.completed:
                        progress.completed = True
                        progress.completion_method = 'scorm'
                        if not progress.completed_at:
                            progress.completed_at = timezone.now()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✅ Marked topic {attempt.scorm_package.topic.id} as completed for user {attempt.user.username}'
                            )
                        )
                
                # Sync scores
                if attempt.score_raw is not None:
                    progress.last_score = attempt.score_raw
                    if progress.best_score is None or attempt.score_raw > progress.best_score:
                        progress.best_score = attempt.score_raw
                
                # Update attempts counter
                progress.attempts = ScormAttempt.objects.filter(
                    user=attempt.user,
                    scorm_package__topic=attempt.scorm_package.topic
                ).count()
                
                if not dry_run:
                    progress.save()
                
                synced_count += 1
                
                self.stdout.write(
                    f'{"[DRY RUN] " if dry_run else ""}Synced: User {attempt.user.username}, '
                    f'Topic {attempt.scorm_package.topic.id}, '
                    f'Status: {attempt.lesson_status}, '
                    f'Score: {attempt.score_raw or "N/A"}'
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error syncing user {attempt.user.username}, topic {attempt.scorm_package.topic.id}: {str(e)}'
                    )
                )
                logger.error(f'Error syncing SCORM progress: {str(e)}')
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('SYNC SUMMARY:')
        self.stdout.write(f'Total processed: {synced_count}')
        self.stdout.write(f'Created: {created_count}')
        self.stdout.write(f'Updated: {updated_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETED - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('SCORM progress sync completed successfully!'))
