from django.core.management.base import BaseCommand
from scorm_cloud.models import SCORMCloudContent, SCORMPackage
from courses.models import Topic
from scorm_cloud.utils.api import get_scorm_client
from django.contrib.auth import get_user_model
import os
import uuid
import time

User = get_user_model()

class Command(BaseCommand):
    help = 'Retry failed SCORM uploads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Retry specific topic ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Retry all failed uploads',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be retried without actually doing it',
        )

    def handle(self, *args, **options):
        if options['topic_id']:
            self.retry_topic(options['topic_id'], options['dry_run'])
        elif options['all']:
            self.retry_all_failed(options['dry_run'])
        else:
            self.stdout.write("Use --topic-id <id> or --all to retry failed uploads")

    def retry_topic(self, topic_id, dry_run=False):
        """Retry a specific topic"""
        try:
            topic = Topic.objects.get(id=topic_id)
            self.stdout.write(f"Retrying topic {topic_id}: {topic.title}")
            
            if dry_run:
                self.stdout.write("DRY RUN: Would retry this topic")
                return
            
            self._process_topic(topic)
            
        except Topic.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Topic {topic_id} not found"))

    def retry_all_failed(self, dry_run=False):
        """Retry all failed uploads"""
        failed_topics = []
        
        # Find topics with placeholder SCORM content
        for scorm_content in SCORMCloudContent.objects.filter(content_type='topic'):
            if scorm_content.package and 'PLACEHOLDER' in scorm_content.package.cloud_id:
                topic = Topic.objects.filter(id=int(scorm_content.content_id)).first()
                if topic:
                    failed_topics.append(topic)
        
        self.stdout.write(f"Found {len(failed_topics)} failed uploads")
        
        if dry_run:
            for topic in failed_topics:
                self.stdout.write(f"DRY RUN: Would retry topic {topic.id}: {topic.title}")
            return
        
        for topic in failed_topics:
            self.stdout.write(f"Retrying topic {topic.id}: {topic.title}")
            self._process_topic(topic)
            time.sleep(5)  # Wait between retries

    def _process_topic(self, topic):
        """Process a topic for SCORM upload"""
        try:
            # Get branch and user
            branch = topic.course.branch if topic.course else None
            branch_user = User.objects.filter(branch=branch).first() if branch else None
            
            if not branch_user:
                self.stdout.write(self.style.ERROR(f"No user found for branch {branch.name if branch else 'None'}"))
                return
            
            # Get SCORM client
            scorm_client = get_scorm_client(user=branch_user, branch=branch)
            
            if not scorm_client or not scorm_client.is_configured:
                self.stdout.write(self.style.ERROR(f"SCORM client not configured for branch {branch.name}"))
                return
            
            # Check if content file exists
            if not topic.content_file or not os.path.exists(topic.content_file.path):
                self.stdout.write(self.style.ERROR(f"Content file not found for topic {topic.id}"))
                return
            
            # Delete existing placeholder content
            SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic.id)
            ).delete()
            
            # Generate new course ID
            unique_id = uuid.uuid4().hex[:8]
            course_id = f"LMS_{topic.id}_{unique_id}"
            
            # Upload to SCORM Cloud
            file_path = topic.content_file.path
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024*1024)
            
            self.stdout.write(f"Uploading file: {file_size_mb:.2f} MB")
            
            # Set timeout for large files
            if file_size > 100 * 1024 * 1024:  # > 100MB
                scorm_client.request_timeout = 1800  # 30 minutes
                self.stdout.write("Large file detected, using extended timeout")
            
            response = scorm_client.upload_package(
                file_path,
                course_id=course_id,
                title=topic.title
            )
            
            if response:
                self.stdout.write(self.style.SUCCESS(f"✅ Upload successful for topic {topic.id}"))
                
                # Create SCORM package
                package = SCORMPackage.objects.create(
                    cloud_id=course_id,
                    title=topic.title,
                    description=topic.title,
                    version=0,
                    launch_mode='new_window'
                )
                
                # Create SCORM content
                SCORMCloudContent.objects.create(
                    content_type='topic',
                    content_id=str(topic.id),
                    package=package,
                    title=topic.title
                )
                
                # Generate launch URL with dynamic BASE_URL
                try:
                    from django.conf import settings
                    from django.urls import reverse
                    
                    # Use BASE_URL from settings for redirect
                    base_url = getattr(settings, 'BASE_URL', 'https://localhost')
                    topic_path = reverse('courses:topic_view', args=[topic.id])
                    redirect_url = f"{base_url}{topic_path}"
                    
                    launch_url = scorm_client.get_direct_launch_url(
                        course_id=course_id,
                        redirect_url=redirect_url
                    )
                    
                    package.launch_url = launch_url
                    package.save()
                    
                    self.stdout.write(self.style.SUCCESS(f"✅ Launch URL generated for topic {topic.id}"))
                    
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"⚠️ Launch URL generation failed: {e}"))
                
            else:
                self.stdout.write(self.style.ERROR(f"❌ Upload failed for topic {topic.id}"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing topic {topic.id}: {e}"))
