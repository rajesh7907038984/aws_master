from django.core.management.base import BaseCommand
from django.apps import apps
from scorm_cloud.models import SCORMPackage, SCORMCloudContent
from scorm_cloud.utils.api import get_scorm_client
from courses.models import Topic, Course
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Enhanced SCORM Cloud cleanup for orphaned content and packages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup even if SCORM Cloud deletion fails',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        verbose = options['verbose']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        self.stdout.write('🔍 Enhanced SCORM Cloud Cleanup')
        self.stdout.write('=' * 50)
        
        # 1. Find orphaned SCORM content
        orphaned_content = self.find_orphaned_content()
        self.stdout.write(f'📦 Found {len(orphaned_content)} orphaned SCORM content records')
        
        # 2. Find orphaned SCORM packages
        orphaned_packages = self.find_orphaned_packages()
        self.stdout.write(f'📦 Found {len(orphaned_packages)} orphaned SCORM packages')
        
        # 3. Find SCORM content for deleted topics
        deleted_topics_scorm = self.find_deleted_topics_scorm()
        self.stdout.write(f'📦 Found {len(deleted_topics_scorm)} SCORM content for deleted topics')
        
        total_issues = len(orphaned_content) + len(orphaned_packages) + len(deleted_topics_scorm)
        
        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS('✅ No SCORM cleanup issues found!'))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'Would clean up {total_issues} records'))
            return
        
        # 4. Clean up orphaned content
        cleaned_content = self.cleanup_orphaned_content(orphaned_content, force, verbose)
        
        # 5. Clean up orphaned packages
        cleaned_packages = self.cleanup_orphaned_packages(orphaned_packages, force, verbose)
        
        # 6. Clean up deleted topics SCORM
        cleaned_deleted = self.cleanup_deleted_topics_scorm(deleted_topics_scorm, force, verbose)
        
        total_cleaned = cleaned_content + cleaned_packages + cleaned_deleted
        
        self.stdout.write('')
        self.stdout.write('📊 Cleanup Summary:')
        self.stdout.write(f'   🧹 Content records cleaned: {cleaned_content}')
        self.stdout.write(f'   🧹 Packages cleaned: {cleaned_packages}')
        self.stdout.write(f'   🧹 Deleted topics cleaned: {cleaned_deleted}')
        self.stdout.write(f'   🧹 Total cleaned: {total_cleaned}')
        
        if total_cleaned > 0:
            self.stdout.write(self.style.SUCCESS('✅ SCORM cleanup completed successfully!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️ No records were cleaned up'))

    def find_orphaned_content(self):
        """Find SCORM content records that are orphaned"""
        orphaned = []
        
        for content in SCORMCloudContent.objects.all():
            if content.content_type == 'topic':
                try:
                    topic = Topic.objects.get(id=content.content_id)
                    if topic.content_type != 'SCORM':
                        orphaned.append(content)
                except Topic.DoesNotExist:
                    orphaned.append(content)
            elif content.content_type == 'course':
                try:
                    course = Course.objects.get(id=content.content_id)
                    # Check if course has any SCORM topics
                    has_scorm_topics = any(
                        topic.content_type == 'SCORM' 
                        for section in course.sections.all() 
                        for topic in section.topics.all()
                    )
                    if not has_scorm_topics:
                        orphaned.append(content)
                except Course.DoesNotExist:
                    orphaned.append(content)
        
        return orphaned

    def find_orphaned_packages(self):
        """Find SCORM packages that are orphaned"""
        orphaned = []
        
        for package in SCORMPackage.objects.all():
            if not SCORMCloudContent.objects.filter(package=package).exists():
                orphaned.append(package)
        
        return orphaned

    def find_deleted_topics_scorm(self):
        """Find SCORM content for deleted topics"""
        deleted_topics_scorm = []
        
        for content in SCORMCloudContent.objects.filter(content_type='topic'):
            try:
                topic = Topic.objects.get(id=content.content_id)
                if topic.content_type != 'SCORM':
                    deleted_topics_scorm.append(content)
            except Topic.DoesNotExist:
                deleted_topics_scorm.append(content)
        
        return deleted_topics_scorm

    def cleanup_orphaned_content(self, orphaned_content, force, verbose):
        """Clean up orphaned SCORM content records"""
        cleaned = 0
        
        for content in orphaned_content:
            try:
                if verbose:
                    self.stdout.write(f'🗑️ Deleting orphaned content: {content.id}')
                
                content.delete()
                cleaned += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error deleting content {content.id}: {e}')
                )
        
        return cleaned

    def cleanup_orphaned_packages(self, orphaned_packages, force, verbose):
        """Clean up orphaned SCORM packages"""
        cleaned = 0
        
        for package in orphaned_packages:
            try:
                if verbose:
                    self.stdout.write(f'🗑️ Deleting orphaned package: {package.id}')
                
                # Try to delete from SCORM Cloud if possible
                if package.cloud_id:
                    try:
                        User = get_user_model()
                        user = User.objects.filter(branch__scorm_integration_enabled=True).first()
                        
                        if user:
                            scorm_client = get_scorm_client(user=user, branch=user.branch)
                            if scorm_client:
                                result = scorm_client.delete_course(package.cloud_id)
                                if verbose:
                                    self.stdout.write(f'   ☁️ Cloud deletion result: {result}')
                            else:
                                if verbose:
                                    self.stdout.write('   ⚠️ No SCORM client available')
                        else:
                            if verbose:
                                self.stdout.write('   ⚠️ No user with SCORM access found')
                    except Exception as e:
                        if verbose:
                            self.stdout.write(f'   ⚠️ Cloud deletion failed: {e}')
                        if not force:
                            self.stdout.write(
                                self.style.WARNING(f'⚠️ Skipping package {package.id} due to cloud deletion failure')
                            )
                            continue
                
                package.delete()
                cleaned += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error deleting package {package.id}: {e}')
                )
        
        return cleaned

    def cleanup_deleted_topics_scorm(self, deleted_topics_scorm, force, verbose):
        """Clean up SCORM content for deleted topics"""
        cleaned = 0
        
        for content in deleted_topics_scorm:
            try:
                if verbose:
                    self.stdout.write(f'🗑️ Deleting SCORM content for deleted topic: {content.id}')
                
                content.delete()
                cleaned += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error deleting content {content.id}: {e}')
                )
        
        return cleaned
