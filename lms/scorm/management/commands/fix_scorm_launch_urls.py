"""
Management command to fix SCORM launch URLs for existing packages
"""
import logging
from django.core.management.base import BaseCommand
from scorm.models import ScormPackage
from scorm.s3_direct import scorm_s3
from scorm.universal_scorm_handler import UniversalSCORMHandler

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix SCORM launch URLs for existing packages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--package-id',
            type=int,
            help='Fix a specific package by ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-detection even if launch URL already exists'
        )

    def handle(self, *args, **options):
        package_id = options.get('package_id')
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)

        if package_id:
            packages = ScormPackage.objects.filter(id=package_id)
            self.stdout.write(f"Checking package ID {package_id}")
        else:
            packages = ScormPackage.objects.all()
            self.stdout.write(f"Checking all {packages.count()} SCORM packages")

        fixed_count = 0
        error_count = 0
        skipped_count = 0

        for package in packages:
            self.stdout.write(f"\nPackage {package.id}: {package.title}")
            self.stdout.write(f"  Current launch URL: {package.launch_url}")

            # Skip if launch URL exists and not forcing
            if package.launch_url and not force:
                self.stdout.write(self.style.WARNING(f"  Skipping - launch URL already exists"))
                skipped_count += 1
                continue

            try:
                # Get package files from S3
                package_files = scorm_s3.list_package_files(package)
                self.stdout.write(f"  Found {len(package_files)} files in package")

                # Detect correct launch file
                detected_launch_file = UniversalSCORMHandler.detect_launch_file(package_files)

                if detected_launch_file:
                    self.stdout.write(self.style.SUCCESS(f"  ✅ Detected launch file: {detected_launch_file}"))

                    # Check if current launch URL is correct
                    if package.launch_url != detected_launch_file:
                        self.stdout.write(self.style.WARNING(f"  ⚠️ Launch URL mismatch detected!"))
                        self.stdout.write(f"  Current: {package.launch_url}")
                        self.stdout.write(f"  Detected: {detected_launch_file}")

                        if not dry_run:
                            # Update the launch URL
                            old_launch_url = package.launch_url
                            package.launch_url = detected_launch_file
                            package.save()
                            self.stdout.write(self.style.SUCCESS(f"  ✅ Fixed launch URL: {old_launch_url} → {detected_launch_file}"))
                            fixed_count += 1
                        else:
                            self.stdout.write(self.style.WARNING(f"  [DRY RUN] Would update launch URL to: {detected_launch_file}"))
                            fixed_count += 1
                    else:
                        self.stdout.write(self.style.SUCCESS(f"  ✅ Launch URL is already correct: {package.launch_url}"))
                        skipped_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f"  ❌ Could not detect launch file"))
                    error_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Error processing package: {str(e)}"))
                error_count += 1

        # Print summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"SUMMARY: Processed {len(packages)} packages")
        self.stdout.write(f"  ✅ Fixed: {fixed_count}")
        self.stdout.write(f"  ⚠️ Skipped: {skipped_count}")
        self.stdout.write(f"  ❌ Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nThis was a dry run. No changes were made."))
            self.stdout.write(self.style.WARNING("Run without --dry-run to apply the changes."))
