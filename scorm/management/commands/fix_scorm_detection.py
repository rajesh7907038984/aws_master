#!/usr/bin/env python3
"""
Management command to fix SCORM package detection
Reprocesses existing SCORM packages to properly detect authoring tools
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from scorm.models import ScormPackage
from scorm.parser import ScormParser
from django.core.files.base import ContentFile
import io

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM package detection by reprocessing packages to detect authoring tools'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix detection for specific SCORM package ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing even if already detected as authoring tool'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔧 SCORM Package Detection Fix'))
        self.stdout.write('=' * 50)
        
        dry_run = options['dry_run']
        force = options['force']
        package_id = options.get('package_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        # Get packages to process
        if package_id:
            try:
                packages = [ScormPackage.objects.get(id=package_id)]
            except ScormPackage.DoesNotExist:
                raise CommandError(f'SCORM package with ID {package_id} not found')
        else:
            # Get packages that might need fixing (currently stored as SCORM version instead of authoring tool)
            scorm_versions = ['1.1', '1.2', '2004']
            packages = ScormPackage.objects.filter(version__in=scorm_versions)
            
            if not force:
                # Only process packages that aren't already detected as authoring tools
                authoring_tools = ['storyline', 'captivate', 'lectora', 'html5', 'xapi', 'legacy', 'unknown']
                packages = packages.exclude(version__in=authoring_tools)
        
        if not packages:
            self.stdout.write(self.style.WARNING('No packages found to process'))
            return
        
        self.stdout.write(f'Found {len(packages)} package(s) to process')
        
        fixed_count = 0
        error_count = 0
        
        for package in packages:
            try:
                self.stdout.write(f'\n📦 Processing package {package.id}: {package.title}')
                self.stdout.write(f'   Current version: {package.version}')
                self.stdout.write(f'   Launch URL: {package.launch_url}')
                
                if not package.package_file:
                    self.stdout.write(self.style.ERROR('   ❌ No package file found'))
                    error_count += 1
                    continue
                
                # Read the package file
                try:
                    package.package_file.open('rb')
                    package_content = package.package_file.read()
                    package.package_file.close()
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'   ❌ Error reading package file: {e}'))
                    error_count += 1
                    continue
                
                # Create a file-like object for the parser
                package_file = ContentFile(package_content)
                
                # Parse with the new detection logic
                try:
                    parser = ScormParser(package_file)
                    package_data = parser.parse(skip_validation=True)
                    
                    new_version = package_data['version']
                    self.stdout.write(f'   🎯 Detected version: {new_version}')
                    
                    if new_version != package.version:
                        if not dry_run:
                            # Update the package
                            package.version = new_version
                            package.save()
                            self.stdout.write(self.style.SUCCESS(f'   ✅ Updated version: {package.version} -> {new_version}'))
                        else:
                            self.stdout.write(self.style.WARNING(f'   🔍 Would update version: {package.version} -> {new_version}'))
                        fixed_count += 1
                    else:
                        self.stdout.write(f'   ℹ️  Version already correct: {new_version}')
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'   ❌ Error parsing package: {e}'))
                    error_count += 1
                    continue
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error processing package {package.id}: {e}'))
                error_count += 1
                continue
        
        # Summary
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS(f'✅ Processing complete!'))
        self.stdout.write(f'   Fixed: {fixed_count}')
        self.stdout.write(f'   Errors: {error_count}')
        self.stdout.write(f'   Total: {len(packages)}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 This was a dry run - no changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')
