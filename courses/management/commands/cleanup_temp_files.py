"""
Management command to clean up orphaned temporary files
"""

from django.core.management.base import BaseCommand
from courses.models import cleanup_orphaned_temp_files
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up orphaned temporary files from file uploads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually deleting files',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No files will be deleted')
            )
        
        try:
            # Import the cleanup function
            from courses.models import cleanup_orphaned_temp_files
            
            if dry_run:
                # For dry run, we'll just show what would be cleaned
                import os
                import glob
                import time
                
                temp_dirs = ["temp_uploads/", "topic_uploads/"]
                current_time = time.time()
                max_age = 3600  # 1 hour
                
                total_files = 0
                total_size = 0
                
                for temp_dir in temp_dirs:
                    if os.path.exists(temp_dir):
                        for file_path in glob.glob(os.path.join(temp_dir, "**/*"), recursive=True):
                            if os.path.isfile(file_path):
                                file_age = current_time - os.path.getmtime(file_path)
                                if file_age > max_age:
                                    file_size = os.path.getsize(file_path)
                                    total_files += 1
                                    total_size += file_size
                                    self.stdout.write(f"Would delete: {file_path} ({file_size} bytes, {file_age/3600:.1f} hours old)")
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Would clean up {total_files} files totaling {total_size/1024/1024:.2f} MB'
                    )
                )
            else:
                # Actually clean up files
                cleanup_orphaned_temp_files()
                self.stdout.write(
                    self.style.SUCCESS('Successfully cleaned up orphaned temporary files')
                )
                
        except Exception as e:
            logger.error(f"Error during temp file cleanup: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error during cleanup: {str(e)}')
            )
