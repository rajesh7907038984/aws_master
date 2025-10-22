"""
Management command to fix missing PDF files by uploading them to S3 storage
"""
import os
import logging
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from courses.models import Topic

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix missing PDF files by uploading them to S3 storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Specific topic ID to fix',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        topic_id = options.get('topic_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get topics with missing files
        if topic_id:
            topics = Topic.objects.filter(id=topic_id)
        else:
            # Find all Document type topics
            topics = Topic.objects.filter(content_type='Document')
        
        fixed_count = 0
        error_count = 0
        
        for topic in topics:
            try:
                self.stdout.write(f'Processing topic {topic.id}: {topic.title}')
                
                # Check if file exists in S3
                if topic.content_file and topic.content_file.name:
                    try:
                        # Try to access the file
                        if default_storage.exists(topic.content_file.name):
                            self.stdout.write(f'  ✓ File exists in S3: {topic.content_file.name}')
                            continue
                        else:
                            self.stdout.write(f'  ✗ File missing from S3: {topic.content_file.name}')
                    except Exception as e:
                        self.stdout.write(f'  ✗ Error checking file: {str(e)}')
                
                # Look for the file in local storage
                local_paths = [
                    f'/home/ec2-user/lms/media_local/{topic.content_file.name}' if topic.content_file else None,
                    f'/home/ec2-user/lms/media_local/courses/{topic.course.id}/topics/{topic.id}/website_development_proposal_jc5Ky29.pdf',
                    f'/home/ec2-user/lms/scorm_uploads/topic_uploads/48190fe7.pdf',  # Found PDF file
                ]
                
                local_file = None
                for path in local_paths:
                    if path and os.path.exists(path):
                        local_file = path
                        self.stdout.write(f'  ✓ Found local file: {path}')
                        break
                
                if not local_file:
                    self.stdout.write(f'  ✗ No local file found for topic {topic.id}')
                    error_count += 1
                    continue
                
                if not dry_run:
                    # Upload to S3
                    with open(local_file, 'rb') as f:
                        # Use the existing file path from the database
                        if topic.content_file and topic.content_file.name:
                            s3_path = topic.content_file.name
                        else:
                            # Generate new path
                            filename = os.path.basename(local_file)
                            s3_path = f"courses/{topic.course.id}/topics/{topic.id}/{filename}"
                        
                        # Upload to S3
                        saved_path = default_storage.save(s3_path, f)
                        self.stdout.write(f'  ✓ Uploaded to S3: {saved_path}')
                        
                        # Update the topic's content_file if needed
                        if not topic.content_file or topic.content_file.name != saved_path:
                            topic.content_file.name = saved_path
                            topic.save()
                            self.stdout.write(f'  ✓ Updated topic file path')
                
                fixed_count += 1
                
            except Exception as e:
                self.stdout.write(f'  ✗ Error processing topic {topic.id}: {str(e)}')
                error_count += 1
                logger.error(f'Error processing topic {topic.id}: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Completed: {fixed_count} topics fixed, {error_count} errors'
            )
        )
