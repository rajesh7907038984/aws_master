from django.core.management.base import BaseCommand
import logging
from django.apps import apps
from django.db.models import Q

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up orphaned SCORM content records that are linked to courses that no longer exist'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        try:
            # Get models dynamically to avoid import issues
            SCORMCloudContent = apps.get_model('scorm_cloud', 'SCORMCloudContent')
            SCORMPackage = apps.get_model('scorm_cloud', 'SCORMPackage')
            Course = apps.get_model('courses', 'Course')
            
            # Find SCORM content records linked to courses
            self.stdout.write('Finding orphaned SCORM content records linked to non-existent courses...')
            
            # Get all SCORM content records linked to courses
            course_content = SCORMCloudContent.objects.filter(
                content_type='course'
            )
            
            # List of orphaned content records
            orphaned_content = []
            
            for content in course_content:
                if content.content_id:
                    try:
                        # Check if the course still exists
                        Course.objects.get(id=content.content_id)
                    except Course.DoesNotExist:
                        # Course doesn't exist, this is orphaned content
                        orphaned_content.append(content)
                        self.stdout.write(f"  - Orphaned course content: {content.id} - {content.title} (linked to course {content.content_id})")
                else:
                    # No content_id means this is probably orphaned too
                    orphaned_content.append(content)
                    self.stdout.write(f"  - Orphaned course content (no content_id): {content.id} - {content.title}")
            
            if not orphaned_content:
                self.stdout.write(self.style.SUCCESS('No orphaned course SCORM content found!'))
                return
            
            # Show summary
            self.stdout.write(f'\nFound {len(orphaned_content)} orphaned course SCORM content records')
            
            if not options['force'] and not options['dry_run']:
                confirm = input(f'\nDelete these {len(orphaned_content)} orphaned course SCORM content records? [y/N]: ')
                if confirm.lower() != 'y':
                    self.stdout.write(self.style.WARNING('Operation cancelled.'))
                    return
            
            # Delete orphaned content
            deleted_count = 0
            for content in orphaned_content:
                try:
                    if options['dry_run']:
                        self.stdout.write(f"Would delete course content: {content.id} - {content.title} (linked to course {content.content_id})")
                    else:
                        # Get package for cleanup
                        package = content.package
                        
                        # Delete cloud package if it exists and this is the only content using it
                        if package and package.cloud_contents.count() <= 1:
                            try:
                                from scorm_cloud.utils.api import get_scorm_client
                                scorm_client = get_scorm_client()
                                self.stdout.write(f"Deleting cloud package: {package.cloud_id}")
                                if scorm_client:
                                    scorm_client.delete_course(package.cloud_id)
                                package.delete()
                                self.stdout.write(self.style.SUCCESS(f"Deleted package: {package.cloud_id}"))
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"Error deleting package {package.cloud_id}: {str(e)}"))
                        
                        # Now delete the content record
                        self.stdout.write(f"Deleting course content: {content.id}")
                        content.delete()
                        deleted_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error deleting content {content.id}: {str(e)}'))
            
            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS(f'Dry run complete. Would have deleted {len(orphaned_content)} course content records.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted_count} of {len(orphaned_content)} orphaned course content records.'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Command failed: {str(e)}'))
            logger.error(f'cleanup_orphaned_course_scorm command error: {str(e)}')
            raise 