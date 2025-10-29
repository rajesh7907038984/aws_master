"""
Management command to fix SCORM time tracking data.

This command recalculates the cumulative time for all SCORM enrollments
and updates TopicProgress records to reflect accurate time spent values.

Usage:
    python manage.py fix_scorm_time [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum
from scorm.models import ScormEnrollment, ScormAttempt
from courses.models import TopicProgress


class Command(BaseCommand):
    help = 'Recalculate and fix SCORM time tracking data for all enrollments'

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
        
        # Get all SCORM enrollments
        enrollments = ScormEnrollment.objects.all()
        total_enrollments = enrollments.count()
        
        if total_enrollments == 0:
            self.stdout.write(self.style.WARNING('No SCORM enrollments found.'))
            return
        
        self.stdout.write(f'Processing {total_enrollments} SCORM enrollments...\n')
        
        updated_count = 0
        error_count = 0
        
        for enrollment in enrollments:
            try:
                # Calculate total time from all attempts
                total_time_all_attempts = ScormAttempt.objects.filter(
                    enrollment=enrollment
                ).aggregate(total=Sum('total_time_seconds'))['total'] or 0
                
                old_time = enrollment.total_time_seconds
                new_time = total_time_all_attempts
                
                # Check if update is needed
                if old_time != new_time:
                    old_h, old_m, old_s = old_time // 3600, (old_time % 3600) // 60, old_time % 60
                    new_h, new_m, new_s = new_time // 3600, (new_time % 3600) // 60, new_time % 60
                    self.stdout.write(
                        f'  User: {enrollment.user.username} | '
                        f'Topic: {enrollment.topic.title[:50]} | '
                        f'Old: {old_time}s ({old_h}h {old_m}m {old_s}s) | '
                        f'New: {new_time}s ({new_h}h {new_m}m {new_s}s)'
                    )
                    
                    if not dry_run:
                        # Update enrollment
                        enrollment.total_time_seconds = new_time
                        enrollment.save(update_fields=['total_time_seconds'])
                        
                        # Update corresponding TopicProgress
                        topic_progress = TopicProgress.objects.filter(
                            user=enrollment.user,
                            topic=enrollment.topic
                        ).first()
                        
                        if topic_progress:
                            topic_progress.total_time_spent = new_time
                            topic_progress.save(update_fields=['total_time_spent'])
                            self.stdout.write(
                                self.style.SUCCESS(f'    ✓ Updated enrollment and TopicProgress')
                            )
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(f'    ✓ Updated enrollment (no TopicProgress found)')
                            )
                    
                    updated_count += 1
                    
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f'  Error processing enrollment {enrollment.id}: {str(e)}'
                    )
                )
                error_count += 1
        
        # Summary
        self.stdout.write('\n' + '=' * 70)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'Would update {updated_count} enrollments'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} enrollments'))
        
        self.stdout.write(f'No changes needed: {total_enrollments - updated_count - error_count}')
        
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        self.stdout.write('=' * 70 + '\n')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('Run without --dry-run to apply changes')
            )

