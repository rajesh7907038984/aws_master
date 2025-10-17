"""
Django management command to fix SCORM S3 path issues
Fixes double prefixing and validates all SCORM packages
"""

from django.core.management.base import BaseCommand
from scorm.models import ELearningPackage
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix SCORM S3 path issues for all packages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Fix specific topic ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        dry_run = options.get('dry_run', False)
        
        if topic_id:
            self.fix_single_package(topic_id, dry_run)
        else:
            self.fix_all_packages(dry_run)

    def fix_single_package(self, topic_id, dry_run=False):
        """Fix a single SCORM package"""
        try:
            package = ELearningPackage.objects.get(topic_id=topic_id)
            self.stdout.write(f"Fixing SCORM package for topic {topic_id}")
            
            if package.extracted_path and package.extracted_path.startswith('elearning/'):
                old_path = package.extracted_path
                new_path = package.extracted_path.replace('elearning/', '')
                
                if not dry_run:
                    package.extracted_path = new_path
                    package.save()
                    self.stdout.write(f"✅ Fixed: {old_path} -> {new_path}")
                else:
                    self.stdout.write(f"🔍 Would fix: {old_path} -> {new_path}")
            else:
                self.stdout.write(f"✅ No fix needed for topic {topic_id}")
                
        except ELearningPackage.DoesNotExist:
            self.stdout.write(f"❌ No SCORM package found for topic {topic_id}")

    def fix_all_packages(self, dry_run=False):
        """Fix all SCORM packages"""
        packages = ELearningPackage.objects.filter(extracted_path__isnull=False)
        fixed_count = 0
        
        self.stdout.write(f"Found {packages.count()} SCORM packages to check")
        
        for package in packages:
            if package.extracted_path and package.extracted_path.startswith('elearning/'):
                old_path = package.extracted_path
                new_path = package.extracted_path.replace('elearning/', '')
                
                if not dry_run:
                    package.extracted_path = new_path
                    package.save()
                    fixed_count += 1
                    self.stdout.write(f"✅ Fixed topic {package.topic.id}: {old_path} -> {new_path}")
                else:
                    self.stdout.write(f"🔍 Would fix topic {package.topic.id}: {old_path} -> {new_path}")
        
        if not dry_run:
            self.stdout.write(f"✅ Fixed {fixed_count} SCORM packages")
        else:
            self.stdout.write(f"🔍 Would fix {fixed_count} SCORM packages")
