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
            self.stdout.write(self.style.SUCCESS("Found topic: {{topic.title}}"))
            self.stdout.write("Content type: {{topic.content_type}}")
            
            if topic.content_file:
                self.stdout.write("Content file: {{topic.content_file}}")
                self.stdout.write("Content file URL: {{topic.content_file.url}}")
                
                # S3 storage - no local file existence check needed
                self.stdout.write("S3 storage - no local file existence check needed")
                self.stdout.write("S3 URL: {{topic.content_file.url}}")
                    
                # Check directory permissions
                dir_path = os.path.dirname(file_path)
                if os.path.exists(dir_path):
                    self.stdout.write("Directory exists: {{dir_path}}")
                    self.stdout.write("Directory permissions: {{oct(os.stat(dir_path).st_mode & 0o777)}}")
                else:
                    self.stdout.write(self.style.ERROR("Directory does NOT exist: {{dir_path}}"))
            else:
                self.stdout.write(self.style.WARNING('Topic has no content file!'))
                
            # Check course/topic directory structure
            expected_dir = "media/courses/{{topic.course.id}}/topics/{{topic.id}}"
            if os.path.exists(expected_dir):
                self.stdout.write(self.style.SUCCESS("Directory exists: {{expected_dir}}"))
                self.stdout.write("Contents: {{os.listdir(expected_dir)}}")
            else:
                self.stdout.write(self.style.WARNING("Expected directory does not exist: {{expected_dir}}"))
                
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR("Topic with ID {{topic_id}} does not exist!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR("Error: {{str(e)}}")) 