"""
Management command to backfill storage tracking for existing files
This registers all existing uploaded files in the FileStorageUsage model
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from core.models import FileStorageUsage
from core.utils.storage_manager import StorageManager
from django.core.files.storage import default_storage
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Backfill storage tracking for all existing uploaded files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be tracked without actually creating records',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-registration even if already tracked',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('  BACKFILL STORAGE TRACKING FOR EXISTING FILES'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - No changes will be made\n'))
        
        total_tracked = 0
        total_skipped = 0
        total_errors = 0
        
        # Track all model types
        total_tracked += self.backfill_user_profile_images(dry_run, force)
        total_tracked += self.backfill_certificate_templates(dry_run, force)
        total_tracked += self.backfill_issued_certificates(dry_run, force)
        total_tracked += self.backfill_scorm_packages(dry_run, force)
        total_tracked += self.backfill_assignment_submissions(dry_run, force)
        total_tracked += self.backfill_file_iterations(dry_run, force)
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('  BACKFILL COMPLETE'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'\n✅ Total files tracked: {total_tracked}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  This was a dry run. Run without --dry-run to actually track files.\n'))

    def backfill_user_profile_images(self, dry_run, force):
        """Backfill user profile images"""
        self.stdout.write(self.style.HTTP_INFO('\n📸 Processing User Profile Images...'))
        
        from users.models import CustomUser
        
        users_with_images = CustomUser.objects.filter(
            profile_image__isnull=False
        ).exclude(profile_image='')
        
        count = 0
        for user in users_with_images:
            if not user.branch:
                self.stdout.write(self.style.WARNING(f'  ⚠️  Skipping {user.username} - no branch assigned'))
                continue
            
            try:
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=user.profile_image.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = 0
                try:
                    if hasattr(user.profile_image, 'size'):
                        file_size = user.profile_image.size
                    else:
                        file_size = default_storage.size(user.profile_image.name)
                except Exception:
                    file_size = 0
                
                if file_size == 0:
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Skipping {user.username} - file size is 0'))
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=user,
                        file_path=user.profile_image.name,
                        original_filename=user.profile_image.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type='image/jpeg',
                        source_app='users',
                        source_model='CustomUser',
                        source_object_id=user.id
                    )
                
                self.stdout.write(f'  ✅ Tracked profile image for {user.username} ({file_size} bytes)')
                count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Error tracking {user.username}: {str(e)}'))
        
        self.stdout.write(f'  📊 Total: {count} profile images')
        return count

    def backfill_certificate_templates(self, dry_run, force):
        """Backfill certificate templates"""
        self.stdout.write(self.style.HTTP_INFO('\n🎓 Processing Certificate Templates...'))
        
        from certificates.models import CertificateTemplate
        
        templates = CertificateTemplate.objects.filter(
            image__isnull=False
        ).exclude(image='')
        
        count = 0
        for template in templates:
            if not template.created_by or not template.created_by.branch:
                self.stdout.write(self.style.WARNING(f'  ⚠️  Skipping {template.name} - no creator or branch'))
                continue
            
            try:
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=template.image.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = 0
                try:
                    if hasattr(template.image, 'size'):
                        file_size = template.image.size
                    else:
                        file_size = default_storage.size(template.image.name)
                except Exception:
                    file_size = 0
                
                if file_size == 0:
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=template.created_by,
                        file_path=template.image.name,
                        original_filename=template.name,
                        file_size_bytes=file_size,
                        content_type='image/jpeg',
                        source_app='certificates',
                        source_model='CertificateTemplate',
                        source_object_id=template.id
                    )
                
                self.stdout.write(f'  ✅ Tracked template: {template.name} ({file_size} bytes)')
                count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Error tracking {template.name}: {str(e)}'))
        
        self.stdout.write(f'  📊 Total: {count} certificate templates')
        return count

    def backfill_issued_certificates(self, dry_run, force):
        """Backfill issued certificates"""
        self.stdout.write(self.style.HTTP_INFO('\n📜 Processing Issued Certificates...'))
        
        from certificates.models import IssuedCertificate
        
        certificates = IssuedCertificate.objects.filter(
            certificate_file__isnull=False
        ).exclude(certificate_file='')
        
        count = 0
        for cert in certificates:
            if not cert.recipient or not cert.recipient.branch:
                continue
            
            try:
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=cert.certificate_file.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = 0
                try:
                    if hasattr(cert.certificate_file, 'size'):
                        file_size = cert.certificate_file.size
                    else:
                        file_size = default_storage.size(cert.certificate_file.name)
                except Exception:
                    file_size = 0
                
                if file_size == 0:
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=cert.recipient,
                        file_path=cert.certificate_file.name,
                        original_filename=f"Certificate_{cert.certificate_number}.pdf",
                        file_size_bytes=file_size,
                        content_type='application/pdf',
                        source_app='certificates',
                        source_model='IssuedCertificate',
                        source_object_id=cert.id
                    )
                
                self.stdout.write(f'  ✅ Tracked certificate: {cert.certificate_number} ({file_size} bytes)')
                count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Error tracking {cert.certificate_number}: {str(e)}'))
        
        self.stdout.write(f'  📊 Total: {count} issued certificates')
        return count

    def backfill_scorm_packages(self, dry_run, force):
        """Backfill SCORM packages"""
        self.stdout.write(self.style.HTTP_INFO('\n📦 Processing SCORM Packages...'))
        
        from scorm.models import ScormPackage
        from courses.models import Topic
        
        packages = ScormPackage.objects.filter(
            package_zip__isnull=False
        ).exclude(package_zip='')
        
        count = 0
        for package in packages:
            try:
                # Try to find uploader
                uploader = None
                topic = Topic.objects.filter(scorm_id=package.id).first()
                if topic:
                    # Get course from topic's courses relationship
                    course = topic.courses.first()
                    if course and course.instructor:
                        uploader = course.instructor
                
                if not uploader or not uploader.branch:
                    # Try alternate method - check who created the package (if field exists)
                    self.stdout.write(self.style.WARNING(f'  ⚠️  Skipping {package.title} - no uploader found'))
                    continue
                
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=package.package_zip.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = 0
                try:
                    if hasattr(package.package_zip, 'size'):
                        file_size = package.package_zip.size
                    else:
                        file_size = default_storage.size(package.package_zip.name)
                except Exception:
                    file_size = 0
                
                if file_size == 0:
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=uploader,
                        file_path=package.package_zip.name,
                        original_filename=package.title or package.package_zip.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type='application/zip',
                        source_app='scorm',
                        source_model='ScormPackage',
                        source_object_id=package.id
                    )
                
                self.stdout.write(f'  ✅ Tracked SCORM: {package.title} ({file_size / (1024*1024):.1f} MB)')
                count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Error tracking {package.title}: {str(e)}'))
        
        self.stdout.write(f'  📊 Total: {count} SCORM packages')
        return count

    def backfill_assignment_submissions(self, dry_run, force):
        """Backfill assignment submissions"""
        self.stdout.write(self.style.HTTP_INFO('\n📝 Processing Assignment Submissions...'))
        
        from assignments.models import AssignmentSubmission
        
        submissions = AssignmentSubmission.objects.filter(
            submission_file__isnull=False
        ).exclude(submission_file='')
        
        count = 0
        for submission in submissions:
            if not submission.user or not submission.user.branch:
                continue
            
            try:
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=submission.submission_file.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = 0
                try:
                    if hasattr(submission.submission_file, 'size'):
                        file_size = submission.submission_file.size
                    else:
                        file_size = default_storage.size(submission.submission_file.name)
                except Exception:
                    file_size = 0
                
                if file_size == 0:
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=submission.user,
                        file_path=submission.submission_file.name,
                        original_filename=submission.submission_file.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type=submission.content_type or 'application/octet-stream',
                        source_app='assignments',
                        source_model='AssignmentSubmission',
                        source_object_id=submission.id
                    )
                
                count += 1
                
            except Exception as e:
                pass  # Silent error for submissions
        
        self.stdout.write(f'  📊 Total: {count} assignment submissions')
        return count

    def backfill_file_iterations(self, dry_run, force):
        """Backfill file submission iterations"""
        self.stdout.write(self.style.HTTP_INFO('\n🔄 Processing File Submission Iterations...'))
        
        from assignments.models import FileSubmissionIteration
        
        iterations = FileSubmissionIteration.objects.filter(
            file__isnull=False
        ).exclude(file='')
        
        count = 0
        for iteration in iterations:
            if not iteration.submission or not iteration.submission.user or not iteration.submission.user.branch:
                continue
            
            try:
                # Check if already tracked
                if not force:
                    existing = FileStorageUsage.objects.filter(
                        file_path=iteration.file.name,
                        is_deleted=False
                    ).exists()
                    
                    if existing:
                        continue
                
                # Get file size
                file_size = iteration.file_size or 0
                
                if file_size == 0:
                    try:
                        if hasattr(iteration.file, 'size'):
                            file_size = iteration.file.size
                        else:
                            file_size = default_storage.size(iteration.file.name)
                    except Exception:
                        file_size = 0
                
                if file_size == 0:
                    continue
                
                if not dry_run:
                    FileStorageUsage.objects.create(
                        user=iteration.submission.user,
                        file_path=iteration.file.name,
                        original_filename=iteration.file_name or iteration.file.name.split('/')[-1],
                        file_size_bytes=file_size,
                        content_type=iteration.content_type or 'application/octet-stream',
                        source_app='assignments',
                        source_model='FileSubmissionIteration',
                        source_object_id=iteration.id
                    )
                
                count += 1
                
            except Exception as e:
                pass  # Silent error for iterations
        
        self.stdout.write(f'  📊 Total: {count} file iterations')
        return count

