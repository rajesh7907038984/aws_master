from django.core.management.base import BaseCommand
from django.conf import settings
from courses.models import Topic
import os

class Command(BaseCommand):
    help = 'Diagnose media file issues for a specific topic'

    def add_arguments(self, parser):
        parser.add_argument('topic_id', type=int, help='Topic ID to diagnose')

    def handle(self, *args, **options):
        topic_id = options['topic_id']
        
        try:
            topic = Topic.objects.get(id=topic_id)
            self.stdout.write(self.style.SUCCESS(f'Found topic: {topic.title}'))
            self.stdout.write(f'Content type: {topic.content_type}')
            
            if topic.content_file:
                self.stdout.write(f'Content file: {topic.content_file}')
                self.stdout.write(f'Content file URL: {topic.content_file.url}')
                
                # Check if using S3 storage
                if settings.MEDIA_ROOT is None:
                    self.stdout.write(self.style.SUCCESS('☁️  Using S3 storage'))
                    # Check if file exists in S3
                    from django.core.files.storage import default_storage
                    try:
                        if default_storage.exists(topic.content_file.name):
                            self.stdout.write(self.style.SUCCESS(f'File exists in S3: {topic.content_file.name}'))
                            # Try to get file size
                            try:
                                size = default_storage.size(topic.content_file.name)
                                self.stdout.write(f'File size: {size} bytes')
                            except:
                                self.stdout.write('Could not determine file size from S3')
                        else:
                            self.stdout.write(self.style.ERROR(f'File does NOT exist in S3: {topic.content_file.name}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error checking S3: {str(e)}'))
                else:
                    # Local storage
                    file_path = os.path.join(settings.MEDIA_ROOT, str(topic.content_file))
                    if os.path.exists(file_path):
                        self.stdout.write(self.style.SUCCESS(f'File exists at: {file_path}'))
                        self.stdout.write(f'File size: {os.path.getsize(file_path)} bytes')
                    else:
                        self.stdout.write(self.style.ERROR(f'File does NOT exist at: {file_path}'))
                        
                    # Check directory permissions
                    dir_path = os.path.dirname(file_path)
                    if os.path.exists(dir_path):
                        self.stdout.write(f'Directory exists: {dir_path}')
                        self.stdout.write(f'Directory permissions: {oct(os.stat(dir_path).st_mode & 0o777)}')
                    else:
                        self.stdout.write(self.style.ERROR(f'Directory does NOT exist: {dir_path}'))
            else:
                self.stdout.write(self.style.WARNING('Topic has no content file!'))
                
            # Check course/topic directory structure
            expected_dir = f'media/courses/{topic.course.id}/topics/{topic.id}'
            if os.path.exists(expected_dir):
                self.stdout.write(self.style.SUCCESS(f'Directory exists: {expected_dir}'))
                self.stdout.write(f'Contents: {os.listdir(expected_dir)}')
            else:
                self.stdout.write(self.style.WARNING(f'Expected directory does not exist: {expected_dir}'))
                
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Topic with ID {topic_id} does not exist!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}')) 