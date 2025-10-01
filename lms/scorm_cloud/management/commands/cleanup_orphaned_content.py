from django.core.management.base import BaseCommand
import logging
from django.apps import apps
from django.db.models import Q

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up orphaned SCORM content records that are not linked to topics'

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
            Topic = apps.get_model('courses', 'Topic')
            
            # Find SCORM content records linked to topics
            self.stdout.write('Finding orphaned SCORM content records...')
            
            # Get all SCORM content records linked to topics
            topic_content = SCORMCloudContent.objects.filter(
                content_type='topic'
            )
            
            # List of orphaned content records
            orphaned_content = []
            
            # Check each record to see if the topic exists
            for content in topic_content:
                try:
                    topic_id = content.content_id
                    # Skip if topic_id is not set
                    if not topic_id:
                        continue
                        
                    # Try to find the topic
                    topic_exists = Topic.objects.filter(id=topic_id).exists()
                    
                    if not topic_exists:
                        orphaned_content.append(content)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error checking content {content.id}: {str(e)}'))
            
            # Report findings
            if not orphaned_content:
                self.stdout.write(self.style.SUCCESS('No orphaned content records found.'))
                return
                
            self.stdout.write(self.style.WARNING(f'Found {len(orphaned_content)} orphaned content records:'))
            for content in orphaned_content:
                package_id = content.package.cloud_id if content.package else 'No package'
                self.stdout.write(f"- Content ID: {content.id}, Topic ID: {content.content_id}, Package: {package_id}")
            
            # Confirm deletion
            if not options['force'] and not options['dry_run']:
                confirm = input(f'\nDelete these {len(orphaned_content)} orphaned content records? [y/N]: ')
                if confirm.lower() != 'y':
                    self.stdout.write(self.style.WARNING('Operation cancelled.'))
                    return
            
            # Delete orphaned content
            deleted_count = 0
            for content in orphaned_content:
                try:
                    if options['dry_run']:
                        self.stdout.write(f"Would delete content: {content.id} - linked to topic {content.content_id}")
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
                        self.stdout.write(f"Deleting content: {content.id}")
                        content.delete()
                        deleted_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error deleting content {content.id}: {str(e)}'))
            
            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS(f'Dry run complete. Would have deleted {len(orphaned_content)} content records.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted_count} of {len(orphaned_content)} orphaned content records.'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Unexpected error: {str(e)}')) 