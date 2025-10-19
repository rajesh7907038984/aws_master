"""
Django management command to fix SCORM package issues
Specifically targets problematic packages and provides permanent solutions
"""

from django.core.management.base import BaseCommand, CommandError
from scorm.models import ELearningPackage
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix SCORM package issues with permanent solutions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-ids',
            nargs='+',
            type=int,
            help='Fix specific topic IDs (e.g., --topic-ids 324 329 326 328)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fix all SCORM packages',
        )
        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Only validate packages without fixing',
        )

    def handle(self, *args, **options):
        topic_ids = options.get('topic_ids', [])
        fix_all = options.get('all', False)
        validate_only = options.get('validate_only', False)
        
        if not topic_ids and not fix_all:
            self.stdout.write(self.style.ERROR("❌ Please specify --topic-ids or --all"))
            return
        
        if topic_ids:
            self.fix_specific_packages(topic_ids, validate_only)
        elif fix_all:
            self.fix_all_packages(validate_only)

    def fix_specific_packages(self, topic_ids, validate_only=False):
        """Fix specific problematic packages"""
        self.stdout.write(f"🔧 {'Validating' if validate_only else 'Fixing'} specific packages: {topic_ids}")
        self.stdout.write("=" * 60)
        
        fixed_count = 0
        failed_count = 0
        
        for topic_id in topic_ids:
            try:
                package = ELearningPackage.objects.get(topic_id=topic_id)
                self.stdout.write(f"\n📦 Topic {topic_id}: {package.topic.title}")
                
                # Validate package
                is_valid, issues = package.validate_extraction()
                
                if is_valid:
                    self.stdout.write("✅ Package is already valid")
                    fixed_count += 1
                else:
                    self.stdout.write("❌ Issues found:")
                    for issue in issues:
                        self.stdout.write(f"  - {issue}")
                    
                    if not validate_only:
                        self.stdout.write("🔧 Attempting to fix...")
                        if package.fix_extraction():
                            # Re-validate after fix
                            is_valid_after, issues_after = package.validate_extraction()
                            if is_valid_after:
                                self.stdout.write("✅ Package fixed successfully")
                                fixed_count += 1
                            else:
                                self.stdout.write("❌ Package still has issues after fix:")
                                for issue in issues_after:
                                    self.stdout.write(f"  - {issue}")
                                failed_count += 1
                        else:
                            self.stdout.write("❌ Failed to fix package")
                            failed_count += 1
                    else:
                        failed_count += 1
                        
            except ELearningPackage.DoesNotExist:
                self.stdout.write(f"❌ Topic {topic_id}: No SCORM package found")
                failed_count += 1
            except Exception as e:
                self.stdout.write(f"❌ Topic {topic_id}: Error - {e}")
                failed_count += 1
        
        # Summary
        self.stdout.write(f"\n📊 Results:")
        self.stdout.write(f"✅ {'Valid' if validate_only else 'Fixed'}: {fixed_count}")
        self.stdout.write(f"❌ Failed: {failed_count}")

    def fix_all_packages(self, validate_only=False):
        """Fix all SCORM packages"""
        packages = ELearningPackage.objects.all()
        total_packages = packages.count()
        
        self.stdout.write(f"🔧 {'Validating' if validate_only else 'Fixing'} all {total_packages} SCORM packages...")
        self.stdout.write("=" * 60)
        
        fixed_count = 0
        failed_count = 0
        
        for package in packages:
            try:
                self.stdout.write(f"\n📦 Topic {package.topic.id}: {package.topic.title}")
                
                # Validate package
                is_valid, issues = package.validate_extraction()
                
                if is_valid:
                    self.stdout.write("✅ Package is valid")
                    fixed_count += 1
                else:
                    self.stdout.write("❌ Issues found:")
                    for issue in issues:
                        self.stdout.write(f"  - {issue}")
                    
                    if not validate_only:
                        self.stdout.write("🔧 Attempting to fix...")
                        if package.fix_extraction():
                            # Re-validate after fix
                            is_valid_after, issues_after = package.validate_extraction()
                            if is_valid_after:
                                self.stdout.write("✅ Package fixed successfully")
                                fixed_count += 1
                            else:
                                self.stdout.write("❌ Package still has issues after fix")
                                failed_count += 1
                        else:
                            self.stdout.write("❌ Failed to fix package")
                            failed_count += 1
                    else:
                        failed_count += 1
                        
            except Exception as e:
                self.stdout.write(f"❌ Error with topic {package.topic.id}: {e}")
                failed_count += 1
        
        # Summary
        self.stdout.write(f"\n📊 Results:")
        self.stdout.write(f"✅ {'Valid' if validate_only else 'Fixed'}: {fixed_count}")
        self.stdout.write(f"❌ Failed: {failed_count}")
        self.stdout.write(f"📈 Success rate: {(fixed_count/(fixed_count+failed_count))*100:.1f}%")
