"""
Management command to sync quiz time from QuizAttempt to TopicProgress.

This command backfills time data for existing quiz attempts that may not have
had their time synced to TopicProgress. It can also be used to fix any missing
time data.

Usage:
    python manage.py sync_quiz_time_to_topic_progress
    python manage.py sync_quiz_time_to_topic_progress --user-id 123
    python manage.py sync_quiz_time_to_topic_progress --quiz-id 456
    python manage.py sync_quiz_time_to_topic_progress --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from quiz.models import QuizAttempt
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync quiz time from QuizAttempt to TopicProgress for existing completed attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making changes',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Only sync data for a specific user ID',
        )
        parser.add_argument(
            '--quiz-id',
            type=int,
            help='Only sync data for a specific quiz ID',
        )
        parser.add_argument(
            '--attempt-id',
            type=int,
            help='Only sync data for a specific attempt ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-sync even if already synced (use with caution)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options.get('user_id')
        quiz_id = options.get('quiz_id')
        attempt_id = options.get('attempt_id')
        force = options.get('force', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY-RUN mode - no changes will be made'))

        # Get all completed quiz attempts
        queryset = QuizAttempt.objects.filter(
            is_completed=True,
            end_time__isnull=False
        ).select_related('quiz', 'user')

        # Apply filters
        if user_id:
            queryset = queryset.filter(user_id=user_id)
            self.stdout.write(f'Filtering for user ID: {user_id}')

        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)
            self.stdout.write(f'Filtering for quiz ID: {quiz_id}')

        if attempt_id:
            queryset = queryset.filter(id=attempt_id)
            self.stdout.write(f'Filtering for attempt ID: {attempt_id}')

        total_attempts = queryset.count()
        self.stdout.write(f'\nFound {total_attempts} completed quiz attempts to process\n')

        if total_attempts == 0:
            self.stdout.write(self.style.WARNING('No quiz attempts found to sync'))
            return

        synced_count = 0
        skipped_count = 0
        error_count = 0
        total_time_synced = 0

        for attempt in queryset:
            try:
                # Check if already synced (unless force is True)
                if not force:
                    # Check if this attempt's time was already synced
                    from courses.models import Topic
                    topics = Topic.objects.filter(quiz=attempt.quiz)
                    already_synced = False
                    
                    for topic in topics:
                        topic_progress = TopicProgress.objects.filter(
                            user=attempt.user,
                            topic=topic
                        ).first()
                        
                        if topic_progress and topic_progress.progress_data:
                            synced_attempts = topic_progress.progress_data.get('synced_quiz_attempts', [])
                            if attempt.id in synced_attempts:
                                already_synced = True
                                break
                    
                    if already_synced:
                        skipped_count += 1
                        continue

                # Sync time using the model method
                if hasattr(attempt, 'sync_time_to_topic_progress'):
                    synced = attempt.sync_time_to_topic_progress()
                    
                    if synced:
                        synced_count += 1
                        quiz_time = attempt.active_time_seconds or 0
                        if quiz_time == 0 and attempt.start_time and attempt.end_time:
                            time_diff = attempt.end_time - attempt.start_time
                            quiz_time = int(time_diff.total_seconds())
                        total_time_synced += quiz_time
                        
                        if not dry_run:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✓ Synced attempt {attempt.id} (Quiz: {attempt.quiz.title}, '
                                    f'User: {attempt.user.username}, Time: {quiz_time}s)'
                                )
                            )
                        else:
                            self.stdout.write(
                                f'[DRY-RUN] Would sync attempt {attempt.id} (Quiz: {attempt.quiz.title}, '
                                f'User: {attempt.user.username}, Time: {quiz_time}s)'
                            )
                    else:
                        skipped_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠ Skipped attempt {attempt.id} - no time to sync or no topics found'
                            )
                        )
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ Error: sync_time_to_topic_progress method not found for attempt {attempt.id}'
                        )
                    )

            except Exception as e:
                error_count += 1
                logger.error(f"Error syncing attempt {attempt.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(f'✗ Error syncing attempt {attempt.id}: {str(e)}')
                )

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('SYNC SUMMARY'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total attempts processed: {total_attempts}')
        self.stdout.write(self.style.SUCCESS(f'Successfully synced: {synced_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if total_time_synced > 0:
            hours = total_time_synced // 3600
            minutes = (total_time_synced % 3600) // 60
            seconds = total_time_synced % 60
            self.stdout.write(
                self.style.SUCCESS(
                    f'Total time synced: {hours}h {minutes}m {seconds}s ({total_time_synced} seconds)'
                )
            )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nThis was a DRY-RUN - no changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nSync completed!'))

