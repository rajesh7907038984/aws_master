"""
Management command to track SCORM packages for branches using them
Assigns SCORM storage to branches based on course enrollment
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import FileStorageUsage
from scorm.models import ScormPackage
from courses.models import Topic, CourseEnrollment
from django.core.files.storage import default_storage
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Track SCORM packages for branches using them in courses'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be tracked without actually creating records',
        )
        parser.add_argument(
            '--branch',
            type=str,
            help='Only process SCORM for specific branch',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        branch_filter = options.get('branch')
        
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('  TRACK SCORM PACKAGES FOR CONSUMING BRANCHES'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
        
        # Get all SCORM packages with files
        scorm_packages = ScormPackage.objects.filter(
            package_zip__isnull=False
        ).exclude(package_zip='')
        
        total_tracked = 0
        total_skipped = 0
        branch_stats = {}
        
        for scorm in scorm_packages:
            # Find topics using this SCORM package
            topics = Topic.objects.filter(scorm_id=scorm.id)
            
            if not topics.exists():
                self.stdout.write(f'  ⚠️  Skipping {scorm.title[:50]} - not linked to any topics')
                total_skipped += 1
                continue
            
            # Find courses using these topics
            course_ids = set()
            for topic in topics:
                course_ids.update(topic.courses.values_list('id', flat=True))
            
            if not course_ids:
                self.stdout.write(f'  ⚠️  Skipping {scorm.title[:50]} - no courses found')
                total_skipped += 1
                continue
            
            # Find branches with users enrolled in these courses
            enrollments = CourseEnrollment.objects.filter(
                course_id__in=course_ids
            ).select_related('user__branch')
            
            branches_using = {}
            for enrollment in enrollments:
                if enrollment.user and enrollment.user.branch:
                    branch = enrollment.user.branch
                    if branch_filter and branch.name != branch_filter:
                        continue
                    
                    if branch.id not in branches_using:
                        branches_using[branch.id] = {
                            'branch': branch,
                            'users': []
                        }
                    branches_using[branch.id]['users'].append(enrollment.user)
            
            if not branches_using:
                self.stdout.write(f'  ⚠️  Skipping {scorm.title[:50]} - no branch users enrolled')
                total_skipped += 1
                continue
            
            # Get file size
            file_size = 0
            try:
                if hasattr(scorm.package_zip, 'size'):
                    file_size = scorm.package_zip.size
                else:
                    file_size = default_storage.size(scorm.package_zip.name)
            except Exception:
                file_size = 0
            
            if file_size == 0:
                self.stdout.write(f'  ⚠️  Skipping {scorm.title[:50]} - file size is 0')
                total_skipped += 1
                continue
            
            # Track for each branch using it
            for branch_id, data in branches_using.items():
                branch = data['branch']
                # Use the first user from this branch as the tracking user
                user = data['users'][0]
                
                # Check if already tracked for this branch
                existing = FileStorageUsage.objects.filter(
                    user__branch=branch,
                    file_path=scorm.package_zip.name,
                    source_app='scorm',
                    is_deleted=False
                ).exists()
                
                if existing:
                    self.stdout.write(f'  ℹ️  Already tracked for {branch.name}: {scorm.title[:40]}')
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=user,
                        file_path=scorm.package_zip.name,
                        original_filename=scorm.title or scorm.package_zip.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type='application/zip',
                        source_app='scorm',
                        source_model='ScormPackage',
                        source_object_id=scorm.id
                    )
                
                size_mb = file_size / (1024 * 1024)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✅ Tracked for {branch.name}: {scorm.title[:40]} ({size_mb:.1f} MB)'
                    )
                )
                
                total_tracked += 1
                
                if branch.name not in branch_stats:
                    branch_stats[branch.name] = {'count': 0, 'size': 0}
                branch_stats[branch.name]['count'] += 1
                branch_stats[branch.name]['size'] += file_size
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('  TRACKING COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        if branch_stats:
            self.stdout.write('\n📊 SCORM Storage by Branch:')
            self.stdout.write('-' * 80)
            for branch_name, stats in sorted(branch_stats.items()):
                size_mb = stats['size'] / (1024 * 1024)
                size_gb = size_mb / 1024
                if size_gb >= 1:
                    size_str = f'{size_gb:.2f} GB'
                else:
                    size_str = f'{size_mb:.1f} MB'
                self.stdout.write(f'  {branch_name}: {stats["count"]} packages, {size_str}')
        
        self.stdout.write(f'\n✅ Total SCORM packages tracked: {total_tracked}')
        self.stdout.write(f'⚠️  Total skipped: {total_skipped}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a dry run. Run without --dry-run to actually track files.\n'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ SCORM packages now tracked for consuming branches!\n'))

