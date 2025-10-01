import os
import shutil
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Migrates media files from old deployment path to the new path'

    def add_arguments(self, parser):
        parser.add_argument(
            '--old-path',
            type=str,
            help='Old media path to migrate from',
            default='/var/www/media'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing files in the destination',
        )

    def handle(self, *args, **options):
        old_path = options['old_path']
        new_path = settings.MEDIA_ROOT
        force = options['force']
        
        self.stdout.write(f"Old media path: {old_path}")
        self.stdout.write(f"New media path: {new_path}")
        
        if not os.path.exists(old_path):
            self.stdout.write(self.style.ERROR(f"Old path does not exist: {old_path}"))
            return
            
        if not os.path.exists(new_path):
            self.stdout.write(f"Creating new path: {new_path}")
            os.makedirs(new_path, exist_ok=True)
            
        # Migrate files
        self._migrate_files(old_path, new_path, force)
        
        self.stdout.write(self.style.SUCCESS(f"Successfully migrated media files to {new_path}"))
        
    def _migrate_files(self, old_path, new_path, force):
        """Migrate all files from old path to new path"""
        # Walk through all files and directories in the old path
        for root, dirs, files in os.walk(old_path):
            # Create the corresponding directory in the new path
            rel_path = os.path.relpath(root, old_path)
            new_dir = os.path.join(new_path, rel_path) if rel_path != '.' else new_path
            
            os.makedirs(new_dir, exist_ok=True)
            self.stdout.write(f"Created directory: {new_dir}")
            
            # Copy all files
            for file in files:
                old_file = os.path.join(root, file)
                new_file = os.path.join(new_dir, file)
                
                if not os.path.exists(new_file) or force:
                    shutil.copy2(old_file, new_file)
                    os.chmod(new_file, 0o644)  # Set proper permissions
                    self.stdout.write(f"Copied file: {old_file} -> {new_file}")
                else:
                    self.stdout.write(f"File already exists (skipping): {new_file}") 