"""
Management command to re-extract SCORM packages that are marked as extracted
but don't have content in S3 storage.
"""

from django.core.management.base import BaseCommand
from scorm.models import ELearningPackage
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Re-extract SCORM packages that are marked as extracted but missing content in S3'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Re-extract specific topic ID only',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-extraction even if content appears to exist',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        force = options.get('force', False)
        
        if topic_id:
            packages = ELearningPackage.objects.filter(topic_id=topic_id)
        else:
            packages = ELearningPackage.objects.filter(is_extracted=True)
        
        self.stdout.write("Found {{packages.count()}} SCORM packages to check")
        
        re_extracted_count = 0
        error_count = 0
        
        for package in packages:
            try:
                self.stdout.write("Checking package for topic {{package.topic.id}}...")
                
                # Check if content exists in S3
                content_exists = False
                if hasattr(package.package_file.storage, 'bucket_name'):
                    # S3 storage - check if launch file exists
                    launch_file_path = "{{package.extracted_path}}/{{package.launch_file}}"
                    content_exists = package.package_file.storage.exists(launch_file_path)
                
                if not content_exists or force:
                    self.stdout.write("Re-extracting package for topic {{package.topic.id}}...")
                    
                    # Reset extraction status
                    package.is_extracted = False
                    package.extraction_error = ""
                    package.save()
                    
                    # Re-extract the package
                    success = package.extract_package()
                    
                    if success:
                        self.stdout.write(
                            self.style.SUCCESS("Successfully re-extracted package for topic {{package.topic.id}}")
                        )
                        re_extracted_count += 1
                    else:
                        self.stdout.write(
                            self.style.ERROR("Failed to re-extract package for topic {{package.topic.id}}: {{package.extraction_error}}")
                        )
                        error_count += 1
                else:
                    self.stdout.write("Package for topic {{package.topic.id}} already has content in S3, skipping...")
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR("Error processing package for topic {{package.topic.id}}: {{e}}")
                )
                error_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                "Re-extraction completed. Successfully re-extracted: {{re_extracted_count}}, Errors: {{error_count}}"
            )
        )
