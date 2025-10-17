"""
Django management command to validate SCORM packages
Checks if SCORM packages are properly extracted and accessible
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from scorm.models import ELearningPackage
from courses.models import Topic
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Validate SCORM packages for proper extraction and accessibility'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Validate specific topic ID',
        )
        parser.add_argument(
            '--fix-issues',
            action='store_true',
            help='Attempt to fix common issues',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        fix_issues = options.get('fix_issues', False)
        
        if topic_id:
            self.validate_single_package(topic_id, fix_issues)
        else:
            self.validate_all_packages(fix_issues)

    def validate_single_package(self, topic_id, fix_issues=False):
        """Validate a single SCORM package"""
        try:
            topic = Topic.objects.get(id=topic_id)
            self.stdout.write(f"Validating SCORM package for topic {topic_id}: {topic.title}")
            
            if not hasattr(topic, 'elearning_package'):
                self.stdout.write(self.style.ERROR(f"❌ Topic {topic_id} has no SCORM package"))
                return False
            
            package = topic.elearning_package
            return self.validate_package(package, fix_issues)
            
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Topic {topic_id} not found"))
            return False

    def validate_all_packages(self, fix_issues=False):
        """Validate all SCORM packages"""
        packages = ELearningPackage.objects.all()
        total_packages = packages.count()
        
        self.stdout.write(f"Validating {total_packages} SCORM packages...")
        
        valid_count = 0
        invalid_count = 0
        
        for package in packages:
            if self.validate_package(package, fix_issues):
                valid_count += 1
            else:
                invalid_count += 1
        
        self.stdout.write(f"\n📊 Validation Results:")
        self.stdout.write(f"✅ Valid packages: {valid_count}")
        self.stdout.write(f"❌ Invalid packages: {invalid_count}")
        self.stdout.write(f"📈 Success rate: {(valid_count/total_packages)*100:.1f}%")

    def validate_package(self, package, fix_issues=False):
        """Validate a single SCORM package"""
        self.stdout.write(f"\n🔍 Validating package for topic {package.topic.id}: {package.topic.title}")
        
        issues = []
        
        # Check 1: Package file exists
        if not package.package_file:
            issues.append("❌ No package file uploaded")
        elif not package.package_file.storage.exists(package.package_file.name):
            issues.append("❌ Package file not found in storage")
        
        # Check 2: Package is extracted
        if not package.is_extracted:
            issues.append("❌ Package not extracted")
            if fix_issues:
                self.stdout.write("🔧 Attempting to extract package...")
                try:
                    if package.extract_package():
                        self.stdout.write("✅ Package extraction successful")
                    else:
                        issues.append("❌ Package extraction failed")
                except Exception as e:
                    issues.append(f"❌ Package extraction error: {str(e)}")
        
        # Check 3: Launch file exists
        if package.launch_file:
            launch_url = package.get_content_url()
            if not launch_url:
                issues.append("❌ Launch file URL not accessible")
        else:
            issues.append("❌ No launch file specified")
        
        # Check 4: Extracted path exists
        if package.extracted_path:
            # Check if files exist in S3
            try:
                storage = package.package_file.storage
                if hasattr(storage, 'bucket_name'):
                    # Check if extracted path exists in S3
                    if not storage.exists(package.extracted_path):
                        issues.append("❌ Extracted path not found in S3")
            except Exception as e:
                issues.append(f"❌ Error checking extracted path: {str(e)}")
        
        # Check 5: Package type is set
        if not package.package_type:
            issues.append("❌ Package type not specified")
        
        # Report results
        if issues:
            self.stdout.write(self.style.ERROR(f"❌ Issues found:"))
            for issue in issues:
                self.stdout.write(f"  {issue}")
            return False
        else:
            self.stdout.write(self.style.SUCCESS("✅ Package is valid"))
            return True
