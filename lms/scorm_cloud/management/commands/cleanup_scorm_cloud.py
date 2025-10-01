from django.core.management.base import BaseCommand
import logging
from scorm_cloud.utils.api import get_scorm_client, SCORMCloudError
from scorm_cloud.models import SCORMPackage
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleans up orphaned SCORM packages from SCORM Cloud'

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
            # Get all packages from SCORM Cloud
            self.stdout.write('Fetching packages from SCORM Cloud...')
            scorm_client = get_scorm_client()
            if not scorm_client:
                self.stdout.write(self.style.ERROR('No SCORM client available. Please configure SCORM Cloud integration.'))
                return
            cloud_packages = scorm_client.get_all_courses()
            
            if not cloud_packages:
                self.stdout.write(self.style.WARNING('No packages found in SCORM Cloud or failed to fetch packages.'))
                return
                
            self.stdout.write(self.style.SUCCESS(f'Found {len(cloud_packages)} packages in SCORM Cloud'))
            
            # Get all package IDs from the database
            db_package_ids = set(SCORMPackage.objects.values_list('cloud_id', flat=True))
            self.stdout.write(self.style.SUCCESS(f'Found {len(db_package_ids)} packages in the database'))
            
            # Find orphaned packages
            orphaned_packages = []
            for cloud_package in cloud_packages:
                if 'id' in cloud_package and cloud_package['id'] not in db_package_ids:
                    orphaned_packages.append(cloud_package)
            
            if not orphaned_packages:
                self.stdout.write(self.style.SUCCESS('No orphaned packages found. Everything is in sync.'))
                return
                
            self.stdout.write(self.style.WARNING(f'Found {len(orphaned_packages)} orphaned packages in SCORM Cloud:'))
            for package in orphaned_packages:
                self.stdout.write(f"- {package.get('id', 'Unknown ID')}: {package.get('title', 'Untitled')}")
            
            # Confirm deletion
            if not options['force'] and not options['dry_run']:
                confirm = input(f'\nDelete these {len(orphaned_packages)} orphaned packages from SCORM Cloud? [y/N]: ')
                if confirm.lower() != 'y':
                    self.stdout.write(self.style.WARNING('Operation cancelled.'))
                    return
            
            # Delete orphaned packages
            deleted_count = 0
            for package in orphaned_packages:
                package_id = package.get('id')
                if not package_id:
                    self.stdout.write(self.style.ERROR(f'Missing ID for package: {package}'))
                    continue
                    
                try:
                    if options['dry_run']:
                        self.stdout.write(f"Would delete package: {package_id} - {package.get('title', 'Untitled')}")
                    else:
                        self.stdout.write(f"Deleting package: {package_id} - {package.get('title', 'Untitled')}")
                        result = scorm_client.delete_course(package_id)
                        deleted_count += 1
                        # Add a small delay to avoid API rate limits
                        time.sleep(0.5)
                except SCORMCloudError as e:
                    self.stdout.write(self.style.ERROR(f'Error deleting package {package_id}: {str(e)}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Unexpected error for package {package_id}: {str(e)}'))
            
            if options['dry_run']:
                self.stdout.write(self.style.SUCCESS(f'Dry run complete. Would have deleted {len(orphaned_packages)} packages.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted_count} of {len(orphaned_packages)} orphaned packages.'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Unexpected error: {str(e)}')) 