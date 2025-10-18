"""
Management command to fix SCORM data integrity issues
"""
from django.core.management.base import BaseCommand
from scorm.models import ELearningPackage
from core.utils.file_validation import validate_storage_consistency
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix SCORM data integrity issues by checking file existence and updating database records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--fix-missing',
            action='store_true',
            help='Mark packages with missing files as not extracted',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix_missing = options['fix_missing']
        
        self.stdout.write("Checking SCORM data integrity...")
        
        packages = ELearningPackage.objects.all()
        total_packages = packages.count()
        missing_files = 0
        fixed_packages = 0
        
        self.stdout.write("Found {{total_packages}} SCORM packages")
        
        for package in packages:
            if not package.package_file:
                self.stdout.write("Package {{package.id}} ({{package.title}}): No file attached")
                continue
                
            # Check if file exists in storage using improved validation
            validation = validate_storage_consistency(package.package_file)
            file_exists = validation['valid']
            
            if not file_exists:
                missing_files += 1
                self.stdout.write(
                    self.style.WARNING(
                        "Package {{package.id}} ({{package.title}}): {{validation['error']}}"
                    )
                )
                
                if fix_missing and not dry_run:
                    # Mark as not extracted and clear extraction data
                    package.is_extracted = False
                    package.extraction_error = validation['error']
                    package.extracted_path = ""
                    package.manifest_path = ""
                    package.launch_file = ""
                    package.save()
                    fixed_packages += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Fixed package {{package.id}}: Marked as not extracted"
                        )
                    )
            else:
                if package.is_extracted:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Package {{package.id}} ({{package.title}}): File exists and marked as extracted"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Package {{package.id}} ({{package.title}}): File exists but not marked as extracted"
                        )
                    )
        
        self.stdout.write("\nSummary:")
        self.stdout.write("Total packages: {{total_packages}}")
        self.stdout.write("Missing files: {{missing_files}}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: No changes made"))
        elif fix_missing:
            self.stdout.write("Fixed packages: {{fixed_packages}}")
        else:
            self.stdout.write("Use --fix-missing to fix missing file issues")
