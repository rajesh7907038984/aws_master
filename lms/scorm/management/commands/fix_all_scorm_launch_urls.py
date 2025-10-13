"""
Management command to re-analyze and fix launch URLs for all SCORM packages
Uses the updated UniversalSCORMHandler with correct priority order
"""
from django.core.management.base import BaseCommand
from scorm.models import ScormPackage
from scorm.s3_direct import scorm_s3
from scorm.universal_scorm_handler import UniversalSCORMHandler
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Re-analyze all SCORM packages and fix launch URLs with correct priority'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix only a specific package ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        package_id = options.get('package_id')
        
        self.stdout.write(self.style.SUCCESS('='*80))
        self.stdout.write(self.style.SUCCESS('SCORM Launch URL Fix - Automatic Re-analysis'))
        self.stdout.write(self.style.SUCCESS('='*80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        self.stdout.write('')
        
        # Get packages to process
        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            if not packages.exists():
                self.stdout.write(self.style.ERROR(f'Package {package_id} not found'))
                return
        else:
            packages = ScormPackage.objects.all()
        
        total = packages.count()
        self.stdout.write(f'Found {total} SCORM package(s) to analyze\n')
        
        fixed_count = 0
        no_change_count = 0
        error_count = 0
        
        for i, package in enumerate(packages, 1):
            try:
                self.stdout.write(f'[{i}/{total}] Processing Package ID: {package.id}')
                self.stdout.write(f'   Topic ID: {package.topic_id}')
                self.stdout.write(f'   Title: {package.title}')
                self.stdout.write(f'   Current Launch URL: {package.launch_url}')
                
                # Get package files from S3
                try:
                    package_files = scorm_s3.list_package_files(package)
                    self.stdout.write(f'   Files found: {len(package_files)}')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'    Error listing files: {str(e)}'))
                    error_count += 1
                    continue
                
                # Detect correct launch file using updated handler
                detected_launch = UniversalSCORMHandler.detect_launch_file(package_files)
                
                if not detected_launch:
                    self.stdout.write(self.style.WARNING(f'     No launch file detected'))
                    error_count += 1
                    continue
                
                self.stdout.write(f'   Detected Launch URL: {detected_launch}')
                
                # Check if change is needed
                if package.launch_url == detected_launch:
                    self.stdout.write(self.style.SUCCESS(f'    No change needed'))
                    no_change_count += 1
                else:
                    # Show the change
                    self.stdout.write(self.style.WARNING(f'    CHANGE:'))
                    self.stdout.write(f'      OLD: {package.launch_url}')
                    self.stdout.write(f'      NEW: {detected_launch}')
                    
                    # Apply change if not dry run
                    if not dry_run:
                        old_launch = package.launch_url
                        package.launch_url = detected_launch
                        package.save(update_fields=['launch_url'])
                        self.stdout.write(self.style.SUCCESS(f'    Updated successfully'))
                        fixed_count += 1
                    else:
                        self.stdout.write(self.style.WARNING(f'     Would update (dry run)'))
                        fixed_count += 1
                
                self.stdout.write('')
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'    Error processing package: {str(e)}'))
                error_count += 1
                self.stdout.write('')
                continue
        
        # Summary
        self.stdout.write('='*80)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('='*80)
        self.stdout.write(f'Total packages: {total}')
        self.stdout.write(self.style.SUCCESS(f'Fixed/Would fix: {fixed_count}'))
        self.stdout.write(f'No change needed: {no_change_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('DRY RUN completed - No actual changes made'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(' All changes applied successfully!'))
            self.stdout.write('')
            self.stdout.write('Next steps:')
            self.stdout.write('1. Restart the server: bash restart_server.sh')
            self.stdout.write('2. Test SCORM content playback')
            self.stdout.write('3. Verify URLs are correct in browser console')

