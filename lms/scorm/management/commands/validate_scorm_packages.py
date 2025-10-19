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
            self.stdout.write("Validating SCORM package for topic {{topic_id}}: {{topic.title}}")
            
            if not hasattr(topic, 'elearning_package'):
                self.stdout.write(self.style.ERROR("❌ Topic {{topic_id}} has no SCORM package"))
                return False
            
            package = topic.elearning_package
            return self.validate_package(package, fix_issues)
            
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ Topic {{topic_id}} not found"))
            return False

    def validate_all_packages(self, fix_issues=False):
        """Validate all SCORM packages"""
        packages = ELearningPackage.objects.all()
        total_packages = packages.count()
        
        self.stdout.write("Validating {{total_packages}} SCORM packages...")
        
        valid_count = 0
        invalid_count = 0
        
        for package in packages:
            if self.validate_package(package, fix_issues):
                valid_count += 1
            else:
                invalid_count += 1
        
        self.stdout.write("\n📊 Validation Results:")
        self.stdout.write("✅ Valid packages: {{valid_count}}")
        self.stdout.write("❌ Invalid packages: {{invalid_count}}")
        self.stdout.write("📈 Success rate: {{(valid_count/total_packages)*100:.1f}}%")

    def validate_package(self, package, fix_issues=False):
        """Validate a single SCORM package with enhanced checks"""
        self.stdout.write(f"\n🔍 Validating package for topic {package.topic.id}: {package.topic.title}")
        
        # Use the new validation method
        is_valid, issues = package.validate_extraction()
        
        if is_valid:
            self.stdout.write(self.style.SUCCESS("✅ Package is valid"))
            return True
        else:
            self.stdout.write(self.style.ERROR("❌ Issues found:"))
            for issue in issues:
                self.stdout.write(f"  ❌ {issue}")
            
            if fix_issues:
                self.stdout.write("🔧 Attempting to fix package...")
                try:
                    if package.fix_extraction():
                        self.stdout.write("✅ Package fixed successfully")
                        return True
                    else:
                        self.stdout.write("❌ Package fix failed")
                        return False
                except Exception as e:
                    self.stdout.write(f"❌ Package fix error: {str(e)}")
                    return False
            
            return False
