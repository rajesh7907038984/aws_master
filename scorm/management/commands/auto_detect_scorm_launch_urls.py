"""
Management command to automatically detect and fix SCORM package launch URLs
"""
from django.core.management.base import BaseCommand, CommandError
from scorm.models import ScormPackage
from scorm.universal_scorm_handler import UniversalSCORMHandler
from scorm.s3_direct import scorm_s3
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Automatically detect and fix SCORM package launch URLs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix the launch URLs (default is dry run)',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix specific package ID only',
        )

    def handle(self, *args, **options):
        fix_mode = options['fix']
        package_id = options.get('package_id')
        
        if fix_mode:
            self.stdout.write(self.style.WARNING(' FIX MODE: Will update launch URLs'))
        else:
            self.stdout.write(self.style.SUCCESS(' DRY RUN MODE: Will only detect issues'))
        
        # Get packages to process
        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            if not packages.exists():
                raise CommandError(f'Package {package_id} not found')
        else:
            packages = ScormPackage.objects.all()
        
        self.stdout.write(f'Processing {packages.count()} SCORM packages...')
        
        issues_found = 0
        fixes_applied = 0
        
        for package in packages:
            self.stdout.write(f'\n📦 Package {package.id}: {package.title}')
            self.stdout.write(f'   Current launch URL: {package.launch_url}')
            self.stdout.write(f'   Topic: {package.topic.id}')
            self.stdout.write(f'   Version: {package.version}')
            
            try:
                # Get package files from S3
                package_files = scorm_s3.list_package_files(package)
                self.stdout.write(f'   Files in package: {len(package_files)}')
                
                # Detect correct launch file
                detected_launch_file = UniversalSCORMHandler.detect_launch_file(package_files)
                
                if detected_launch_file:
                    self.stdout.write(f'    Detected launch file: {detected_launch_file}')
                    
                    # Check if current launch URL is correct
                    if package.launch_url != detected_launch_file:
                        self.stdout.write(
                            self.style.WARNING(f'     Launch URL mismatch!')
                        )
                        self.stdout.write(f'   Current: {package.launch_url}')
                        self.stdout.write(f'   Detected: {detected_launch_file}')
                        
                        issues_found += 1
                        
                        if fix_mode:
                            # Update the launch URL
                            old_launch_url = package.launch_url
                            package.launch_url = detected_launch_file
                            package.save()
                            
                            self.stdout.write(
                                self.style.SUCCESS(f'    Fixed launch URL')
                            )
                            self.stdout.write(f'   Old: {old_launch_url}')
                            self.stdout.write(f'   New: {detected_launch_file}')
                            fixes_applied += 1
                    else:
                        self.stdout.write(f'    Launch URL is correct')
                else:
                    self.stdout.write(
                        self.style.ERROR('    Could not detect launch file')
                    )
                    issues_found += 1
                
                # Validate package structure
                validation = UniversalSCORMHandler.validate_package_structure(
                    package_files, package.launch_url
                )
                
                if validation['is_valid']:
                    self.stdout.write(f'    Package structure is valid')
                else:
                    self.stdout.write(f'     Package structure issues:')
                    for key, value in validation.items():
                        if key != 'is_valid':
                            status = '' if value else ''
                            self.stdout.write(f'     {status} {key}: {value}')
                
                # Get package type
                package_type = UniversalSCORMHandler.get_package_type(package.launch_url)
                self.stdout.write(f'    Package type: {package_type}')
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'    Error processing package: {e}')
                )
                issues_found += 1
        
        # Summary
        self.stdout.write(f'\n SUMMARY:')
        self.stdout.write(f'   Packages processed: {packages.count()}')
        self.stdout.write(f'   Issues found: {issues_found}')
        
        if fix_mode:
            self.stdout.write(f'   Fixes applied: {fixes_applied}')
            if fixes_applied > 0:
                self.stdout.write(
                    self.style.SUCCESS(' Launch URLs have been updated!')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(' No fixes needed - all packages are correct!')
                )
        else:
            self.stdout.write(f'   Issues that would be fixed: {issues_found}')
            if issues_found > 0:
                self.stdout.write(
                    self.style.WARNING('  Run with --fix to apply fixes')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(' All packages are correct!')
                )
