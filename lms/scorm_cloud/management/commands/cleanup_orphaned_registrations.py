from django.core.management.base import BaseCommand
from scorm_cloud.models import SCORMRegistration
from courses.models import Topic
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up orphaned SCORM registrations that reference non-existent topics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes',
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete orphaned registrations (use with caution)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delete = options['delete']
        
        self.stdout.write(self.style.HTTP_INFO('Starting orphaned registration cleanup...'))
        
        orphaned_registrations = []
        
        # Find orphaned registrations
        for registration in SCORMRegistration.objects.all():
            topic_id = None
            try:
                # Try to extract topic ID from registration ID (format: REG_{topic_id}_{user_id}_{hash})
                if registration.registration_id.startswith('REG_'):
                    parts = registration.registration_id.split('_')
                    if len(parts) >= 3:
                        topic_id = int(parts[1])
            except (ValueError, IndexError):
                continue
            
            if topic_id:
                # Check if topic exists
                if not Topic.objects.filter(id=topic_id).exists():
                    orphaned_registrations.append(registration)
        
        if not orphaned_registrations:
            self.stdout.write(self.style.SUCCESS('No orphaned registrations found'))
            return
        
        self.stdout.write(self.style.WARNING(f'Found {len(orphaned_registrations)} orphaned registrations:'))
        
        for reg in orphaned_registrations:
            self.stdout.write(f'  - {reg.registration_id} (User: {reg.user}, Package: {reg.package})')
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry run complete - no changes made'))
            return
        
        if not delete:
            self.stdout.write(self.style.WARNING('Use --delete flag to actually remove orphaned registrations'))
            return
        
        # Delete orphaned registrations
        deleted_count = 0
        for reg in orphaned_registrations:
            try:
                reg.delete()
                deleted_count += 1
                self.stdout.write(self.style.SUCCESS(f'Deleted orphaned registration: {reg.registration_id}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error deleting {reg.registration_id}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(f'Cleanup complete - deleted {deleted_count} orphaned registrations'))
