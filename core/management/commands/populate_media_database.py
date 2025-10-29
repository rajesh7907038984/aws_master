import os
import logging
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from lms_media.models import MediaFile
import mimetypes

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populate MediaFile database with existing files (for production deployment)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force rescan even if files are already tracked',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        
        self.stdout.write("=== POPULATING MEDIA DATABASE ===")
        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No database changes"))
        
        # Check environment
        is_render = os.environ.get('RENDER', False)
        self.stdout.write(f"Environment: {'Cloud deployment' if is_render else 'Local/Other'}")
        self.stdout.write(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        
        # Check if media root exists
        if not os.path.exists(settings.MEDIA_ROOT):
            self.stdout.write(self.style.ERROR(f"MEDIA_ROOT does not exist: {settings.MEDIA_ROOT}"))
            return
        
        self.stdout.write(f"MEDIA_ROOT exists: {os.path.exists(settings.MEDIA_ROOT)}")
        self.stdout.write(f"MEDIA_ROOT readable: {os.access(settings.MEDIA_ROOT, os.R_OK)}")
        
        # Initialize counters
        self.scanned_count = 0
        self.created_count = 0
        self.skipped_count = 0
        self.error_count = 0
        
        # Start scanning
        self._scan_media_files()
        
        # Print summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Scan completed!"))
        self.stdout.write(f"Files scanned: {self.scanned_count}")
        self.stdout.write(f"Records created: {self.created_count}")
        self.stdout.write(f"Files skipped: {self.skipped_count}")
        if self.error_count > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {self.error_count}"))

    def _scan_media_files(self):
        """Scan all files in MEDIA_ROOT"""
        media_root = Path(settings.MEDIA_ROOT)
        
        # Skip these directories and files
        skip_dirs = {'.', '..', '__pycache__', '.git', '.svn', 'temp', 'cache'}
        skip_files = {'.DS_Store', 'Thumbs.db', '.gitkeep', '.gitignore'}
        
        for file_path in media_root.rglob('*'):
            # Skip directories
            if file_path.is_dir():
                continue
                
            # Skip unwanted files
            if file_path.name in skip_files:
                continue
                
            # Skip files in unwanted directories
            if any(part in skip_dirs for part in file_path.parts):
                continue
                
            self._process_file(file_path)

    def _process_file(self, file_path):
        """Process a single file"""
        self.scanned_count += 1
        
        try:
            # Get relative path from media root
            media_root = Path(settings.MEDIA_ROOT)
            relative_path = file_path.relative_to(media_root)
            relative_path_str = str(relative_path).replace('\\', '/')
            
            # Check if already tracked
            if not self.force and MediaFile.objects.filter(file_path=relative_path_str).exists():
                self.skipped_count += 1
                return
            
            # Get file info
            stat = file_path.stat()
            filename = file_path.name
            file_size = stat.st_size
            file_extension = file_path.suffix.lower()
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            # Determine source type from path
            source_type = self._determine_source_type(relative_path_str)
            
            # Categorize file type
            file_type = self._categorize_file_type(file_extension, mime_type)
            
            if not self.dry_run:
                # Create or update MediaFile record
                media_file, created = MediaFile.objects.get_or_create(
                    file_path=relative_path_str,
                    defaults={
                        'filename': filename,
                        'file_size': file_size,
                        'mime_type': mime_type,
                        'file_extension': file_extension,
                        'file_type': file_type,
                        'source_type': source_type,
                        'uploaded_at': timezone.datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.get_current_timezone()
                        ),
                        'is_referenced': True,  # Assume files on disk are being used
                        'is_public': False,
                        'description': f'File found during media scan on {timezone.now().date()}',
                    }
                )
                
                if created:
                    self.created_count += 1
                    self.stdout.write(f"✓ Created: {relative_path_str}")
                else:
                    self.skipped_count += 1
            else:
                self.created_count += 1
                self.stdout.write(f"[DRY RUN] Would create: {relative_path_str}")
                
        except Exception as e:
            self.error_count += 1
            self.stdout.write(self.style.ERROR(f"Error processing {file_path}: {str(e)}"))

    def _determine_source_type(self, file_path):
        """Determine source type from file path"""
        path_lower = file_path.lower()
        
        if 'course_images' in path_lower or 'course_content' in path_lower:
            return 'course_content'
        elif 'assignment' in path_lower:
            return 'assignment_submission'
        elif 'editor_upload' in path_lower:
            return 'editor_upload'
        elif 'conference' in path_lower:
            return 'conference_file'
        elif 'message' in path_lower:
            return 'message_attachment'
        elif 'discussion' in path_lower:
            return 'discussion_attachment'
        elif 'certificate' in path_lower:
            return 'certificate'
        elif 'report' in path_lower:
            return 'report_attachment'
        elif 'profile' in path_lower or 'user' in path_lower:
            return 'user_profile'
        elif 'backup' in path_lower or 'import' in path_lower:
            return 'import_file'
        else:
            return 'other'

    def _categorize_file_type(self, extension, mime_type):
        """Categorize file type based on extension and mime type"""
        ext = extension.lower()
        
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}
        video_extensions = {'.mp4', '.avi', '.mov', '.wmv', '.webm', '.mkv', '.ogg'}
        audio_extensions = {'.mp3', '.wav', '.ogg', '.m4a', '.wma', '.aac'}
        document_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}
        archive_extensions = {'.zip', '.rar', '.tar', '.gz', '.7z'}
        
        if ext in image_extensions:
            return 'image'
        elif ext in video_extensions:
            return 'video'
        elif ext in audio_extensions:
            return 'audio'
        elif ext in document_extensions:
            return 'document'
        elif ext in archive_extensions:
            return 'archive'
        elif mime_type and mime_type.startswith('image/'):
            return 'image'
        elif mime_type and mime_type.startswith('video/'):
            return 'video'
        elif mime_type and mime_type.startswith('audio/'):
            return 'audio'
        else:
            return 'unknown' 