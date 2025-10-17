"""
Management command to sync local media files to MediaFile model
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from media_library.models import MediaFile
from django.conf import settings
import os
import mimetypes
from datetime import datetime

User = get_user_model()


class Command(BaseCommand):
    help = 'Sync local media files to MediaFile model'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually creating records',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit the number of files to process',
        )
        parser.add_argument(
            '--path',
            type=str,
            default='/home/ec2-user/lms/media_local',
            help='Path to scan for local media files',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        scan_path = options['path']
        
        self.stdout.write(f'Starting local file sync from {scan_path}...')
        
        if not os.path.exists(scan_path):
            self.stdout.write(
                self.style.ERROR(f'Path {scan_path} does not exist')
            )
            return
        
        try:
            # Get a system user for uploads
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                system_user = User.objects.first()
            
            if not system_user:
                self.stdout.write(
                    self.style.ERROR('No users found in the system. Cannot sync files.')
                )
                return
            
            synced_count = 0
            skipped_count = 0
            error_count = 0
            
            # Walk through the directory
            for root, dirs, files in os.walk(scan_path):
                for file in files:
                    if limit and synced_count >= limit:
                        break
                    
                    file_path = os.path.join(root, file)
                    
                    # Skip hidden files and temp files
                    if file.startswith('.') or file.endswith('.temp'):
                        continue
                    
                    try:
                        # Get file stats
                        stat = os.stat(file_path)
                        file_size = stat.st_size
                        modified_time = datetime.fromtimestamp(stat.st_mtime)
                        
                        # Get relative path from scan_path
                        relative_path = os.path.relpath(file_path, scan_path)
                        
                        # Check if file already exists
                        existing_file = MediaFile.objects.filter(
                            file_path=relative_path,
                            storage_type='local'
                        ).first()
                        
                        if existing_file:
                            skipped_count += 1
                            continue
                        
                        # Determine file type
                        file_type = self.get_file_type(file_path)
                        
                        # Get MIME type
                        mime_type, _ = mimetypes.guess_type(file_path)
                        mime_type = mime_type or 'application/octet-stream'
                        
                        if dry_run:
                            self.stdout.write(f'Would sync: {relative_path} ({file_size} bytes, {file_type})')
                            synced_count += 1
                        else:
                            MediaFile.objects.create(
                                filename=file,
                                original_filename=file,
                                file_path=relative_path,
                                file_size=file_size,
                                file_type=file_type,
                                mime_type=mime_type,
                                storage_type='local',
                                uploaded_by=system_user,
                                uploaded_at=modified_time,
                                source_app='local_sync',
                                source_model='LocalFile',
                                description=f'Local file: {relative_path}',
                                is_active=True,
                                is_public=True
                            )
                            synced_count += 1
                            
                            if synced_count % 100 == 0:
                                self.stdout.write(f'Synced {synced_count} files...')
                                
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error processing {file_path}: {str(e)}')
                        )
                        error_count += 1
                
                if limit and synced_count >= limit:
                    break
            
            # Update statistics
            if not dry_run:
                from media_library.views import update_storage_statistics
                update_storage_statistics()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sync completed! Synced: {synced_count}, Skipped: {skipped_count}, Errors: {error_count}'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during sync: {str(e)}')
            )

    def get_file_type(self, file_path):
        """Determine file type from file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico']
        video_exts = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']
        document_exts = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx']
        archive_exts = ['.zip', '.rar', '.tar', '.gz', '.7z', '.bz2']
        
        if ext in image_exts:
            return 'image'
        elif ext in video_exts:
            return 'video'
        elif ext in audio_exts:
            return 'audio'
        elif ext in document_exts:
            return 'document'
        elif ext in archive_exts:
            return 'archive'
        else:
            return 'other'
