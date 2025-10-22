import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Ensures all necessary media directories exist with proper permissions'

    def handle(self, *args, **options):
        # List of directories to ensure exist
        directories = [
            os.path.join(settings.MEDIA_ROOT),
            os.path.join(settings.MEDIA_ROOT, 'temp'),
            os.path.join(settings.MEDIA_ROOT, 'course_images'),
            os.path.join(settings.MEDIA_ROOT, 'course_content'),
            os.path.join(settings.MEDIA_ROOT, 'course_content', 'course_images'),
            os.path.join(settings.MEDIA_ROOT, 'course_content', 'course_images', 'temp'),
        ]
        
        # Create directories and set permissions
        for directory in directories:
            try:
                if not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                    self.stdout.write(self.style.SUCCESS(f'Created directory: {directory}'))
                else:
                    self.stdout.write(f'Directory already exists: {directory}')
                
                # Set permissions
                os.chmod(directory, 0o755)
                self.stdout.write(self.style.SUCCESS(f'Set permissions on directory: {directory}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating/setting permissions on {directory}: {str(e)}'))
                logger.error(f'Error creating/setting permissions on {directory}: {str(e)}')
        
        self.stdout.write(self.style.SUCCESS('Successfully ensured all media directories exist with proper permissions')) 