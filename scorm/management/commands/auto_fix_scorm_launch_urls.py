"""
Django management command to auto-detect and fix SCORM launch URLs
"""

from django.core.management.base import BaseCommand
from scorm.auto_launch_detector import launch_detector

class Command(BaseCommand):
    help = 'Auto-detect and fix SCORM launch URLs for all packages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix specific package ID only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )

    def handle(self, *args, **options):
        if options['package_id']:
            # Fix specific package
            from scorm.models import ScormPackage
            try:
                package = ScormPackage.objects.get(id=options['package_id'])
                self.stdout.write(f"Fixing package {package.id}: {package.title}")
                
                if options['dry_run']:
                    files = launch_detector.list_package_files(package)
                    package_type, suggested_files = launch_detector.detect_package_type(files)
                    best_file = launch_detector.find_best_launch_file(files, package_type, suggested_files)
                    
                    self.stdout.write(f"  Current launch URL: {package.launch_url}")
                    self.stdout.write(f"  Detected type: {package_type}")
                    self.stdout.write(f"  Suggested files: {suggested_files}")
                    self.stdout.write(f"  Best file: {best_file}")
                    self.stdout.write("  DRY RUN - No changes made")
                else:
                    launch_file, message = launch_detector.auto_detect_launch_url(package)
                    if launch_file:
                        self.stdout.write(self.style.SUCCESS(f"✅ Fixed: {launch_file} - {message}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"❌ Failed: {message}"))
                        
            except ScormPackage.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Package {options['package_id']} not found"))
        else:
            # Fix all packages
            self.stdout.write("Auto-detecting launch URLs for all SCORM packages...")
            
            if options['dry_run']:
                self.stdout.write("DRY RUN MODE - No changes will be made")
            
            results = launch_detector.fix_all_packages()
            
            # Display results
            success_count = 0
            for result in results:
                if result['success']:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Package {result['package_id']}: {result['title']} -> {result['launch_file']}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Package {result['package_id']}: {result['title']} - {result['message']}"
                        )
                    )
            
            self.stdout.write(f"\nSummary: {success_count}/{len(results)} packages fixed successfully")
