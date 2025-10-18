"""
Management command to sync S3 files to MediaFile model
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from media_library.models import MediaFile
from django.conf import settings
import boto3
import os
from datetime import datetime

User = get_user_model()


class Command(BaseCommand):
    help = 'Sync S3 files to MediaFile model'

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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        
        self.stdout.write('Starting S3 file sync...')
        
        try:
            # Initialize S3 client
            s3 = boto3.client('s3')
            bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
            if not bucket_name:
                self.stdout.write(
                    self.style.ERROR('AWS_STORAGE_BUCKET_NAME not configured')
                )
                return
            
            # Get a system user for uploads
            system_user = User.objects.filter(is_superuser=True).first()
            if not system_user:
                system_user = User.objects.first()
            
            if not system_user:
                self.stdout.write(
                    self.style.ERROR('No users found in the system. Cannot sync files.')
                )
                return
            
            # List all objects in the media/ prefix
            paginator = s3.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix='media/')
            
            synced_count = 0
            skipped_count = 0
            error_count = 0
            
            for page in page_iterator:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    if limit and synced_count >= limit:
                        break
                        
                    key = obj['Key']
                    size = obj['Size']
                    last_modified = obj['LastModified']
                    
                    # Skip directories and hidden files
                    if key.endswith('/') or key.startswith('.'):
                        continue
                    
                    # Skip .gitkeep files
                    if key.endswith('.gitkeep'):
                        continue
                    
                    # Check if file already exists
                    existing_file = MediaFile.objects.filter(
                        file_path=key,
                        storage_type='s3'
                    ).first()
                    
                    if existing_file:
                        skipped_count += 1
                        continue
                    
                    # Determine file type
                    file_type = self.get_file_type(key)
                    
                    # Get file URL
                    region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2')
                    file_url = "https://{{bucket_name}}.s3.{{region}}.amazonaws.com/{{key}}"
                    
                    if dry_run:
                        self.stdout.write("Would sync: {{key}} ({{size}} bytes, {{file_type}})")
                        synced_count += 1
                    else:
                        try:
                            MediaFile.objects.create(
                                filename=os.path.basename(key),
                                original_filename=os.path.basename(key),
                                file_path=key,
                                file_url=file_url,
                                file_size=size,
                                file_type=file_type,
                                mime_type=self.get_mime_type(key),
                                storage_type='s3',
                                uploaded_by=system_user,
                                uploaded_at=last_modified,
                                source_app='s3_sync',
                                source_model='S3Object',
                                description="S3 file: {{key}}",
                                is_active=True,
                                is_public=True
                            )
                            synced_count += 1
                            
                            if synced_count % 100 == 0:
                                self.stdout.write("Synced {{synced_count}} files...")
                                
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR("Error syncing {{key}}: {{str(e)}}")
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
                    "Sync completed! Synced: {{synced_count}}, Skipped: {{skipped_count}}, Errors: {{error_count}}"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR("Error during sync: {{str(e)}}")
            )

    def get_file_type(self, file_path):
        """Determine file type from file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        
        image_exts = ['.jpg', '.jpeg', '.png', '.gi", ".bmp', '.webp', '.svg', '.ico']
        video_exts = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']
        document_exts = ['.pd", ".doc', '.docx', '.txt', '.rt", ".odt', '.xls', '.xlsx', '.ppt', '.pptx']
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

    def get_mime_type(self, file_path):
        """Get MIME type from file extension"""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'
