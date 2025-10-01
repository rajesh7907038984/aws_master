import os
import shutil
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Copies media files from a source directory to the configured MEDIA_ROOT'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            help='Source directory to copy files from',
            default='backup/media'
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Overwrite existing files in the destination',
        )

    def handle(self, *args, **options):
        source_dir = options['source']
        dest_dir = settings.MEDIA_ROOT
        overwrite = options['overwrite']
        
        self.stdout.write(f"Source directory: {source_dir}")
        self.stdout.write(f"Destination directory: {dest_dir}")
        
        if not os.path.exists(source_dir):
            self.stdout.write(self.style.ERROR(f"Source directory '{source_dir}' does not exist"))
            return
            
        if not os.path.exists(dest_dir):
            self.stdout.write(f"Creating destination directory '{dest_dir}'")
            os.makedirs(dest_dir, exist_ok=True)
            
        # Copy files recursively
        self._copy_dir(source_dir, dest_dir, overwrite)
        
        self.stdout.write(self.style.SUCCESS(f"Successfully copied media files to {dest_dir}"))
            
    def _copy_dir(self, src, dst, overwrite):
        """
        Recursively copy files from src to dst
        """
        count = 0
        skipped = 0
        
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            
            if os.path.isdir(s):
                if not os.path.exists(d):
                    os.makedirs(d, exist_ok=True)
                    os.chmod(d, 0o755)
                results = self._copy_dir(s, d, overwrite)
                count += results[0]
                skipped += results[1]
            else:
                if not os.path.exists(d) or overwrite:
                    try:
                        shutil.copy2(s, d)
                        os.chmod(d, 0o644)
                        count += 1
                        if count % 100 == 0:
                            self.stdout.write(f"Copied {count} files...")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error copying {s} to {d}: {str(e)}"))
                else:
                    skipped += 1
                    
        self.stdout.write(f"Copied {count} files, skipped {skipped} existing files from {src}")
        return (count, skipped) 