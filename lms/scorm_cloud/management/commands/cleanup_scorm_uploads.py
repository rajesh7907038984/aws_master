"""
Management command to clean up old SCORM upload files from root folder
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from core.scorm_storage import SCORMRootStorage
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clean up old SCORM upload files from root folder'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=getattr(settings, 'SCORM_CLEANUP_MAX_AGE_HOURS', 24),
            help='Maximum age of files in hours (default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        max_age_hours = options['max_age_hours']
        dry_run = options['dry_run']
        
        self.stdout.write(f"Starting SCORM upload cleanup (max age: {max_age_hours} hours)")
        
        if dry_run:
            self.stdout.write("DRY RUN MODE - No files will be deleted")
        
        try:
            scorm_storage = SCORMRootStorage()
            
            if dry_run:
                # For dry run, we'll manually check files
                import os
                from datetime import datetime, timedelta
                from django.utils import timezone
                
                scorm_root = scorm_storage.location
                current_time = timezone.now()
                max_age = timedelta(hours=max_age_hours)
                files_to_delete = []
                
                for root, dirs, files in os.walk(scorm_root):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                            file_age = current_time - file_mtime.replace(tzinfo=timezone.utc)
                            
                            if file_age > max_age:
                                files_to_delete.append((file_path, file_age))
                        except Exception as e:
                            self.stdout.write(f"Error checking file {file_path}: {str(e)}")
                
                if files_to_delete:
                    self.stdout.write(f"Found {len(files_to_delete)} files to delete:")
                    for file_path, age in files_to_delete:
                        self.stdout.write(f"  - {file_path} (age: {age})")
                else:
                    self.stdout.write("No files found for deletion")
            else:
                # Actual cleanup
                deleted_count = scorm_storage.cleanup_old_uploads(max_age_hours)
                self.stdout.write(f"Cleanup completed: {deleted_count} files removed")
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error during cleanup: {str(e)}")
            )
            logger.error(f"SCORM cleanup error: {str(e)}")
