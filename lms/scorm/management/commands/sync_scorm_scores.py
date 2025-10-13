"""
Management command to synchronize SCORM scores between ScormAttempt and TopicProgress models.
This fixes discrepancies where scores exist in ScormAttempt but are missing in TopicProgress.

Usage:
    python manage.py sync_scorm_scores
    python manage.py sync_scorm_scores --dry-run  # Show what would be updated without making changes
    python manage.py sync_scorm_scores --topic-id 123  # Sync only specific topic
    python manage.py sync_scorm_scores --user-id 456  # Sync only specific user
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Synchronize SCORM scores between ScormAttempt and TopicProgress models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Sync only the specified topic ID',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync only the specified user ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if TopicProgress already has scores',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        topic_id = options.get('topic_id')
        user_id = options.get('user_id')
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🔄 Starting SCORM score synchronization {"(DRY RUN)" if dry_run else ""}'
            )
        )
        
        # Build query filters
        filters = {}
        if topic_id:
            filters['scorm_package__topic_id'] = topic_id
        if user_id:
            filters['user_id'] = user_id
            
        # Get all ScormAttempts with scores
        attempts_with_scores = ScormAttempt.objects.filter(
            score_raw__isnull=False,
            score_raw__gt=0,
            **filters
        ).select_related('user', 'scorm_package__topic').order_by('user', 'scorm_package__topic', '-started_at')
        
        total_attempts = attempts_with_scores.count()
        self.stdout.write(f"📊 Found {total_attempts} SCORM attempts with scores")
        
        if total_attempts == 0:
            self.stdout.write(self.style.WARNING("No SCORM attempts with scores found"))
            return
            
        updated_count = 0
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        # Group attempts by user and topic to get the latest score for each
        attempts_by_user_topic = {}
        for attempt in attempts_with_scores:
            key = (attempt.user.id, attempt.scorm_package.topic.id)
            if key not in attempts_by_user_topic:
                attempts_by_user_topic[key] = attempt
            # Keep the latest attempt (already ordered by -started_at)
        
        self.stdout.write(f"📋 Processing {len(attempts_by_user_topic)} unique user-topic combinations")
        
        for (user_id, topic_id), attempt in attempts_by_user_topic.items():
            try:
                with transaction.atomic():
                    # Get or create TopicProgress
                    topic_progress, created = TopicProgress.objects.get_or_create(
                        user_id=user_id,
                        topic_id=topic_id,
                        defaults={
                            'last_score': float(attempt.score_raw),
                            'best_score': float(attempt.score_raw),
                            'attempts': attempt.attempt_number,
                            'last_accessed': attempt.last_accessed,
                            'first_accessed': attempt.started_at,
                            'completed': attempt.lesson_status in ['completed', 'passed'],
                            'completion_method': 'scorm' if attempt.lesson_status in ['completed', 'passed'] else None,
                            'completed_at': attempt.completed_at if attempt.lesson_status in ['completed', 'passed'] else None,
                            'progress_data': {
                                'scorm_attempt_id': attempt.id,
                                'lesson_status': attempt.lesson_status,
                                'completion_status': attempt.completion_status,
                                'success_status': attempt.success_status,
                                'score_raw': float(attempt.score_raw),
                                'score_max': float(attempt.score_max) if attempt.score_max else 100,
                                'score_min': float(attempt.score_min) if attempt.score_min else 0,
                                'total_time': attempt.total_time,
                                'last_updated': timezone.now().isoformat(),
                                'sync_method': 'management_command',
                                'sync_timestamp': timezone.now().isoformat(),
                            }
                        }
                    )
                    
                    if created:
                        self.stdout.write(
                            f"✅ Created TopicProgress for user {attempt.user.username}, topic {attempt.scorm_package.topic.title} "
                            f"with score {attempt.score_raw}"
                        )
                        created_count += 1
                    else:
                        # Update existing TopicProgress
                        needs_update = False
                        old_last_score = topic_progress.last_score
                        old_best_score = topic_progress.best_score
                        
                        score_value = float(attempt.score_raw)
                        
                        # Update last_score if force flag is set or no score exists or this is a newer attempt
                        if force or topic_progress.last_score is None:
                            topic_progress.last_score = score_value
                            needs_update = True
                        elif topic_progress.last_score != score_value:
                            # Check if this attempt is newer than what we have
                            current_attempt_id = topic_progress.progress_data.get('scorm_attempt_id') if topic_progress.progress_data else None
                            if current_attempt_id != attempt.id:
                                topic_progress.last_score = score_value
                                needs_update = True
                        
                        # Update best_score if this is better
                        if topic_progress.best_score is None or score_value > topic_progress.best_score:
                            topic_progress.best_score = score_value
                            needs_update = True
                        
                        # Update completion status if needed
                        is_completed = attempt.lesson_status in ['completed', 'passed']
                        if is_completed and not topic_progress.completed:
                            topic_progress.completed = True
                            topic_progress.completion_method = 'scorm'
                            topic_progress.completed_at = attempt.completed_at or attempt.last_accessed
                            needs_update = True
                        
                        # Update progress data
                        if needs_update:
                            topic_progress.progress_data = {
                                'scorm_attempt_id': attempt.id,
                                'lesson_status': attempt.lesson_status,
                                'completion_status': attempt.completion_status,
                                'success_status': attempt.success_status,
                                'score_raw': float(attempt.score_raw),
                                'score_max': float(attempt.score_max) if attempt.score_max else 100,
                                'score_min': float(attempt.score_min) if attempt.score_min else 0,
                                'total_time': attempt.total_time,
                                'last_updated': timezone.now().isoformat(),
                                'sync_method': 'management_command',
                                'sync_timestamp': timezone.now().isoformat(),
                            }
                            topic_progress.last_accessed = attempt.last_accessed
                            topic_progress.attempts = max(topic_progress.attempts or 0, attempt.attempt_number)
                            
                            if not dry_run:
                                topic_progress.save()
                            
                            self.stdout.write(
                                f"🔄 Updated TopicProgress for user {attempt.user.username}, topic {attempt.scorm_package.topic.title} "
                                f"- last_score: {old_last_score} → {topic_progress.last_score}, "
                                f"best_score: {old_best_score} → {topic_progress.best_score}"
                            )
                            updated_count += 1
                        else:
                            self.stdout.write(
                                f"⏭️  Skipped TopicProgress for user {attempt.user.username}, topic {attempt.scorm_package.topic.title} "
                                f"(already up to date)"
                            )
                            skipped_count += 1
                            
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ Error processing attempt {attempt.id} for user {attempt.user.username}: {str(e)}"
                    )
                )
                error_count += 1
                logger.error(f"SCORM sync error for attempt {attempt.id}: {str(e)}")
        
        # Summary
        self.stdout.write(self.style.SUCCESS("\n📈 SCORM Score Synchronization Complete!"))
        self.stdout.write(f"  ✅ Created: {created_count}")
        self.stdout.write(f"  🔄 Updated: {updated_count}")
        self.stdout.write(f"  ⏭️  Skipped: {skipped_count}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  ❌ Errors: {error_count}"))
        
        total_processed = created_count + updated_count + skipped_count
        self.stdout.write(f"  📊 Total processed: {total_processed}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  This was a DRY RUN - no changes were made to the database"))
            self.stdout.write("Run without --dry-run to apply these changes")
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully synchronized {created_count + updated_count} SCORM scores"))
            
            # Clear caches
            from django.core.cache import cache
            cache.clear()
            self.stdout.write("🗑️  Cleared application caches")
