"""
Management command to sync SCORM scores to gradebook
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from scorm.models import ELearningTracking, ELearningPackage
from courses.models import Course
from users.models import CustomUser
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync SCORM scores to gradebook system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--course-id',
            type=int,
            help='Sync scores for a specific course only',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync scores for a specific user only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    def handle(self, *args, **options):
        course_id = options.get('course_id')
        user_id = options.get('user_id')
        dry_run = options.get('dry_run')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        try:
            # Get SCORM tracking records to sync
            tracking_records = ELearningTracking.objects.filter(
                score_raw__isnull=False
            ).select_related(
                'user', 'elearning_package', 'elearning_package__topic'
            ).prefetch_related(
                'elearning_package__topic__courses'
            )

            if course_id:
                tracking_records = tracking_records.filter(
                    elearning_package__topic__courses__id=course_id
                )

            if user_id:
                tracking_records = tracking_records.filter(user_id=user_id)

            total_records = tracking_records.count()
            self.stdout.write(f'Found {total_records} SCORM tracking records to sync')

            if total_records == 0:
                self.stdout.write(self.style.SUCCESS('No SCORM scores to sync'))
                return

            synced_count = 0
            error_count = 0

            for tracking in tracking_records:
                try:
                    # Get the course for this SCORM package
                    course = tracking.elearning_package.topic.courses.first()
                    if not course:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Skipping tracking {tracking.id}: No course found for SCORM package {tracking.elearning_package.id}'
                            )
                        )
                        continue

                    if dry_run:
                        self.stdout.write(
                            f'Would sync: User {tracking.user.username} - '
                            f'SCORM {tracking.elearning_package.title} - '
                            f'Score: {tracking.score_raw}/{tracking.score_max} - '
                            f'Course: {course.title}'
                        )
                        synced_count += 1
                    else:
                        # The gradebook system will automatically pick up SCORM scores
                        # from the ELearningTracking model, so no explicit sync is needed
                        # Just log the successful processing
                        self.stdout.write(
                            f'Processed: User {tracking.user.username} - '
                            f'SCORM {tracking.elearning_package.title} - '
                            f'Score: {tracking.score_raw}/{tracking.score_max} - '
                            f'Course: {course.title}'
                        )
                        synced_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f'Error processing tracking {tracking.id}: {str(e)}')
                    self.stdout.write(
                        self.style.ERROR(f'Error processing tracking {tracking.id}: {str(e)}')
                    )

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'DRY RUN: Would sync {synced_count} SCORM scores, {error_count} errors'
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully processed {synced_count} SCORM scores, {error_count} errors'
                    )
                )

        except Exception as e:
            logger.error(f'Error in sync_scorm_scores command: {str(e)}')
            self.stdout.write(
                self.style.ERROR(f'Error in sync_scorm_scores command: {str(e)}')
            )
            raise
