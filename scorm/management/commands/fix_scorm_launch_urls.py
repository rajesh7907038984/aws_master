#!/usr/bin/env python3
"""
Management command to fix SCORM package launch URLs.

This command identifies and fixes SCORM packages that are using content files
(story.html) instead of SCORM API wrapper files (index_lms.html) as launch URLs.

Usage: python manage.py fix_scorm_launch_urls
"""

from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from scorm.models import ScormPackage


class Command(BaseCommand):
    help = 'Fix SCORM package launch URLs to use SCORM API wrapper files instead of content files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix only a specific SCORM package ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        package_id = options.get('package_id')
        
        self.stdout.write("🔧 SCORM Launch URL Fix Tool")
        self.stdout.write("=" * 50)
        
        # Get packages to fix
        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            if not packages.exists():
                self.stdout.write(self.style.ERROR(f"❌ SCORM package {package_id} not found"))
                return
        else:
            packages = ScormPackage.objects.all()
        
        fixed_count = 0
        total_count = packages.count()
        
        self.stdout.write(f"📦 Found {total_count} SCORM package(s) to check")
        self.stdout.write("")
        
        for package in packages:
            self.stdout.write(f"🔍 Checking package {package.id}: {package.title}")
            
            # Check current launch URL
            current_url = package.launch_url
            self.stdout.write(f"   Current launch URL: {current_url}")
            
            # Check if it's using a content file instead of SCORM API wrapper
            content_files = ['story.html', 'index.html', 'launch.html', 'start.html', 'main.html']
            is_content_file = any(content_file in current_url.lower() for content_file in content_files)
            
            if is_content_file:
                # Look for indexAPI.html specifically
                scorm_api_wrappers = ['indexAPI.html']
                found_wrapper = None
                
                # Get list of files in the package directory
                try:
                    files_in_package = default_storage.listdir(package.extracted_path)[1]
                    for wrapper in scorm_api_wrappers:
                        if wrapper in files_in_package:
                            found_wrapper = wrapper
                            break
                except Exception as e:
                    self.stdout.write(f"   ⚠️  Error checking package files: {e}")
                    # Fallback to individual file checks
                    for wrapper in scorm_api_wrappers:
                        wrapper_path = f"{package.extracted_path}/{wrapper}"
                        if default_storage.exists(wrapper_path):
                            found_wrapper = wrapper
                            break
                
                if found_wrapper:
                    self.stdout.write(f"   ✅ Found SCORM API wrapper: {found_wrapper}")
                    
                    if dry_run:
                        self.stdout.write(f"   🔄 Would change: {current_url} → {found_wrapper}")
                    else:
                        package.launch_url = found_wrapper
                        package.save()
                        self.stdout.write(f"   ✅ Fixed: {current_url} → {found_wrapper}")
                        fixed_count += 1
                else:
                    self.stdout.write(f"   ⚠️  No SCORM API wrapper found, keeping: {current_url}")
            else:
                self.stdout.write(f"   ✅ Already using SCORM API wrapper: {current_url}")
            
            self.stdout.write("")
        
        # Summary
        self.stdout.write("=" * 50)
        if dry_run:
            self.stdout.write(f"🔍 Dry run complete - would fix {fixed_count} package(s)")
        else:
            self.stdout.write(f"✅ Fixed {fixed_count} out of {total_count} package(s)")
        
        if fixed_count > 0:
            self.stdout.write("")
            self.stdout.write("🎉 SCORM packages should now work correctly with proper API integration!")
            self.stdout.write("   The exit button and SCORM tracking should function properly.")
