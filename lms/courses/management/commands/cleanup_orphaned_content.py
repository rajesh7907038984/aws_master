import os
import shutil
from django.core.management.base import BaseCommand
from django.conf import settings
from courses.models import Course
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up orphaned course content and media files'

    def handle(self, *args, **options):
        try:
            # Get base content directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            course_content_dir = os.path.join(base_dir, 'course_content')
            
            if not os.path.exists(course_content_dir):
                self.stdout.write(self.style.WARNING('No course content directory found.'))
                return
            
            # Get all valid course IDs
            valid_course_ids = set(Course.objects.values_list('id', flat=True))
            
            # Clean up main course content directories
            for item in os.listdir(course_content_dir):
                item_path = os.path.join(course_content_dir, item)
                
                # Skip if it's not a directory or is 'topics' directory
                if not os.path.isdir(item_path) or item == 'topics':
                    continue
                
                try:
                    # Check if directory name is a course ID
                    course_id = int(item)
                    if course_id not in valid_course_ids:
                        shutil.rmtree(item_path)
                        self.stdout.write(
                            self.style.SUCCESS(f'Removed orphaned course content directory: {item_path}')
                        )
                except ValueError:
                    # Not a course ID directory, skip
                    continue
            
            # Clean up topics directory
            topics_dir = os.path.join(course_content_dir, 'topics')
            if os.path.exists(topics_dir):
                for item in os.listdir(topics_dir):
                    item_path = os.path.join(topics_dir, item)
                    if not os.path.isdir(item_path):
                        continue
                        
                    try:
                        course_id = int(item)
                        if course_id not in valid_course_ids:
                            shutil.rmtree(item_path)
                            self.stdout.write(
                                self.style.SUCCESS(f'Removed orphaned topics directory: {item_path}')
                            )
                    except ValueError:
                        continue
                
                # Remove topics directory if empty
                if os.path.exists(topics_dir) and not os.listdir(topics_dir):
                    os.rmdir(topics_dir)
                    self.stdout.write(
                        self.style.SUCCESS('Removed empty topics directory')
                    )
            
            self.stdout.write(self.style.SUCCESS('Successfully cleaned up orphaned content'))
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            self.stdout.write(self.style.ERROR(f'Error during cleanup: {str(e)}')) 