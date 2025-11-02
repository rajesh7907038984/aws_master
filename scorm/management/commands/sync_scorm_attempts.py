"""
Management command to sync SCORM attempts from ScormEnrollment to TopicProgress.

This fixes historical data where attempts were tracked in ScormEnrollment
but not synced to TopicProgress (used for reporting).
"""

from django.core.management.base import BaseCommand
from scorm.models import ScormEnrollment
from courses.models import TopicProgress


class Command(BaseCommand):
    help = 'Sync SCORM attempts from ScormEnrollment to TopicProgress'

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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options.get('user_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY-RUN mode - no changes will be made'))
        
        # Get all SCORM enrollments that have attempts
        queryset = ScormEnrollment.objects.filter(total_attempts__gt=0).select_related('user', 'topic')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
            self.stdout.write(f'Filtering for user ID: {user_id}')
        
        total_records = queryset.count()
        self.stdout.write(f'Found {total_records} SCORM enrollments with attempts to sync\n')
        
        updated_count = 0
        
        for scorm_enrollment in queryset:
            # Find corresponding TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=scorm_enrollment.user,
                topic=scorm_enrollment.topic
            ).first()
            
            if not topic_progress:
                self.stdout.write(
                    self.style.WARNING(
                        f'No TopicProgress found for {scorm_enrollment.user.username} - '
                        f'{scorm_enrollment.topic.title[:50]}'
                    )
                )
                continue
            
            # Check if update is needed
            if topic_progress.attempts != scorm_enrollment.total_attempts:
                old_attempts = topic_progress.attempts
                new_attempts = scorm_enrollment.total_attempts
                
                self.stdout.write(
                    f'User: {scorm_enrollment.user.username} | '
                    f'Topic: {scorm_enrollment.topic.title[:50]} | '
                    f'Attempts: {old_attempts} → {new_attempts}'
                )
                
                if not dry_run:
                    topic_progress.attempts = new_attempts
                    topic_progress.save(update_fields=['attempts'])
                
                updated_count += 1
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Summary ==='))
        self.stdout.write(f'Total records checked: {total_records}')
        self.stdout.write(f'Records updated: {updated_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY-RUN complete - no changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('\nSync complete!'))

