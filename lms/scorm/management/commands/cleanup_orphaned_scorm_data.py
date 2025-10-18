"""
Management command to clean up orphaned SCORM data.
This command identifies and removes orphaned SCORM tracking records,
packages, and S3 files that are no longer associated with valid topics or courses.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import logging

from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course
from scorm.storage import SCORMS3Storage

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up orphaned SCORM data and S3 files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        verbose = options['verbose']
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        self.stdout.write(
            self.style.SUCCESS('Starting SCORM orphaned data cleanup...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No data will be deleted')
            )
        
        try:
            with transaction.atomic():
                # 1. Clean up orphaned SCORM tracking records
                orphaned_tracking = self.cleanup_orphaned_tracking(dry_run, verbose)
                
                # 2. Clean up orphaned SCORM packages
                orphaned_packages = self.cleanup_orphaned_packages(dry_run, verbose)
                
                # 3. Clean up orphaned S3 files
                orphaned_s3_files = self.cleanup_orphaned_s3_files(dry_run, verbose)
                
                # 4. Clean up orphaned course progress records
                orphaned_progress = self.cleanup_orphaned_progress(dry_run, verbose)
                
                # Summary
                total_cleaned = orphaned_tracking + orphaned_packages + orphaned_s3_files + orphaned_progress
                
                if dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "DRY RUN COMPLETE: Would clean up {{total_cleaned}} orphaned records"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "CLEANUP COMPLETE: Cleaned up {{total_cleaned}} orphaned records"
                        )
                    )
                
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS('All orphaned SCORM data has been cleaned up successfully.')
                    )
                
        except Exception as e:
            logger.error("Error during SCORM cleanup: {{str(e)}}")
            raise CommandError("Cleanup failed: {{str(e)}}")

    def cleanup_orphaned_tracking(self, dry_run=False, verbose=False):
        """Clean up orphaned SCORM tracking records"""
        self.stdout.write('Checking for orphaned SCORM tracking records...')
        
        # Find tracking records with invalid user references
        orphaned_tracking = ELearningTracking.objects.filter(
            user__isnull=True
        )
        
        # Find tracking records with invalid package references
        orphaned_tracking |= ELearningTracking.objects.filter(
            elearning_package__isnull=True
        )
        
        # Find tracking records with packages that have invalid topic references
        orphaned_tracking |= ELearningTracking.objects.filter(
            elearning_package__topic__isnull=True
        )
        
        count = orphaned_tracking.count()
        
        if count > 0:
            if verbose:
                self.stdout.write("Found {{count}} orphaned tracking records")
                for tracking in orphaned_tracking[:10]:  # Show first 10
                    self.stdout.write("  - User: {{tracking.user}}, Package: {{tracking.elearning_package}}")
            
            if not dry_run:
                if not self.confirm_deletion("Delete {{count}} orphaned tracking records?"):
                    return 0
                
                orphaned_tracking.delete()
                self.stdout.write(
                    self.style.SUCCESS("Deleted {{count}} orphaned tracking records")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("Would delete {{count}} orphaned tracking records")
                )
        
        return count

    def cleanup_orphaned_packages(self, dry_run=False, verbose=False):
        """Clean up orphaned SCORM packages"""
        self.stdout.write('Checking for orphaned SCORM packages...')
        
        # Find packages with invalid topic references
        orphaned_packages = ELearningPackage.objects.filter(
            topic__isnull=True
        )
        
        count = orphaned_packages.count()
        
        if count > 0:
            if verbose:
                self.stdout.write("Found {{count}} orphaned packages")
                for package in orphaned_packages[:10]:  # Show first 10
                    self.stdout.write("  - Package: {{package.title}}, Type: {{package.package_type}}")
            
            if not dry_run:
                if not self.confirm_deletion("Delete {{count}} orphaned packages?"):
                    return 0
                
                # Clean up S3 files for each package before deletion
                for package in orphaned_packages:
                    self.cleanup_package_s3_files(package)
                
                orphaned_packages.delete()
                self.stdout.write(
                    self.style.SUCCESS("Deleted {{count}} orphaned packages")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("Would delete {{count}} orphaned packages")
                )
        
        return count

    def cleanup_orphaned_s3_files(self, dry_run=False, verbose=False):
        """Clean up orphaned S3 files"""
        self.stdout.write('Checking for orphaned S3 files...')
        
        try:
            storage = SCORMS3Storage()
            orphaned_files = []
            
            # Check for orphaned package files
            package_files = storage.listdir('elearning/packages/')
            for file in package_files[0]:  # files
                file_path = "elearning/packages/{{file}}"
                
                # Check if this file is referenced by any package
                if not ELearningPackage.objects.filter(package_file=file_path).exists():
                    orphaned_files.append(file_path)
            
            # Check for orphaned extracted content
            extracted_dirs = storage.listdir('elearning/extracted/')
            for dir_name in extracted_dirs[1]:  # directories
                dir_path = "elearning/extracted/{{dir_name}}"
                
                # Check if this directory is referenced by any package
                if not ELearningPackage.objects.filter(extracted_path=dir_path).exists():
                    orphaned_files.append(dir_path)
            
            count = len(orphaned_files)
            
            if count > 0:
                if verbose:
                    self.stdout.write("Found {{count}} orphaned S3 files")
                    for file in orphaned_files[:10]:  # Show first 10
                        self.stdout.write("  - {{file}}")
                
                if not dry_run:
                    if not self.confirm_deletion("Delete {{count}} orphaned S3 files?"):
                        return 0
                    
                    for file in orphaned_files:
                        try:
                            storage.delete(file)
                            self.stdout.write("Deleted S3 file: {{file}}")
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR("Error deleting {{file}}: {{str(e)}}")
                            )
                    
                    self.stdout.write(
                        self.style.SUCCESS("Deleted {{count}} orphaned S3 files")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("Would delete {{count}} orphaned S3 files")
                    )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR("Error checking S3 files: {{str(e)}}")
            )
            return 0
        
        return count

    def cleanup_orphaned_progress(self, dry_run=False, verbose=False):
        """Clean up orphaned course progress records"""
        self.stdout.write('Checking for orphaned course progress records...')
        
        try:
            from courses.models import TopicProgress
            
            # Find progress records with invalid user references
            orphaned_progress = TopicProgress.objects.filter(
                user__isnull=True
            )
            
            # Find progress records with invalid topic references
            orphaned_progress |= TopicProgress.objects.filter(
                topic__isnull=True
            )
            
            count = orphaned_progress.count()
            
            if count > 0:
                if verbose:
                    self.stdout.write("Found {{count}} orphaned progress records")
                    for progress in orphaned_progress[:10]:  # Show first 10
                        self.stdout.write("  - User: {{progress.user}}, Topic: {{progress.topic}}")
                
                if not dry_run:
                    if not self.confirm_deletion("Delete {{count}} orphaned progress records?"):
                        return 0
                    
                    orphaned_progress.delete()
                    self.stdout.write(
                        self.style.SUCCESS("Deleted {{count}} orphaned progress records")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING("Would delete {{count}} orphaned progress records")
                    )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR("Error checking progress records: {{str(e)}}")
            )
            return 0
        
        return count

    def cleanup_package_s3_files(self, package):
        """Clean up S3 files for a specific package"""
        try:
            storage = SCORMS3Storage()
            
            # Delete package file
            if package.package_file:
                storage.delete(package.package_file.name)
                self.stdout.write("Deleted package file: {{package.package_file.name}}")
            
            # Delete extracted content
            if package.extracted_path:
                try:
                    files, dirs = storage.listdir(package.extracted_path)
                    
                    # Delete all files
                    for file in files:
                        file_path = "{{package.extracted_path}}/{{file}}"
                        storage.delete(file_path)
                        self.stdout.write("Deleted extracted file: {{file_path}}")
                    
                    # Delete subdirectories recursively
                    for dir_name in dirs:
                        dir_path = "{{package.extracted_path}}/{{dir_name}}"
                        self.cleanup_directory_recursive(storage, dir_path)
                    
                    self.stdout.write("Cleaned up extracted directory: {{package.extracted_path}}")
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR("Error cleaning up extracted directory {{package.extracted_path}}: {{str(e)}}")
                    )
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR("Error cleaning up S3 files for package {{package.id}}: {{str(e)}}")
            )

    def cleanup_directory_recursive(self, storage, dir_path):
        """Recursively delete a directory and all its contents from S3"""
        try:
            files, dirs = storage.listdir(dir_path)
            
            # Delete all files in current directory
            for file in files:
                file_path = "{{dir_path}}/{{file}}"
                storage.delete(file_path)
                self.stdout.write("Deleted file: {{file_path}}")
            
            # Recursively delete subdirectories
            for dir_name in dirs:
                subdir_path = "{{dir_path}}/{{dir_name}}"
                self.cleanup_directory_recursive(storage, subdir_path)
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR("Error cleaning up directory {{dir_path}}: {{str(e)}}")
            )

    def confirm_deletion(self, message):
        """Ask for confirmation before deletion"""
        response = input("{{message}} (y/N): ")
        return response.lower() in ['y', 'yes']
