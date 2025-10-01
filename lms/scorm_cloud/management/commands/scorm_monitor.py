from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from scorm_cloud.models import SCORMCloudContent, SCORMPackage
from courses.models import Topic
import json

class Command(BaseCommand):
    help = 'Monitor SCORM upload progress and health'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current SCORM upload status',
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Check SCORM worker health',
        )
        parser.add_argument(
            '--failed',
            action='store_true',
            help='Show failed SCORM uploads',
        )

    def handle(self, *args, **options):
        if options['status']:
            self.show_upload_status()
        elif options['health']:
            self.check_health()
        elif options['failed']:
            self.show_failed_uploads()
        else:
            self.show_all_status()

    def show_upload_status(self):
        """Show current SCORM upload status"""
        self.stdout.write("=== SCORM Upload Status ===")
        
        # Check for active uploads
        active_uploads = []
        for i in range(1000):  # Check first 1000 possible topic IDs
            cache_key = f"scorm_upload_progress_{i}"
            progress = cache.get(cache_key)
            if progress:
                active_uploads.append(progress)
        
        if active_uploads:
            self.stdout.write(f"Active uploads: {len(active_uploads)}")
            for upload in active_uploads:
                self.stdout.write(f"  Topic {upload['topic_id']}: Attempt {upload['attempt']}/{upload['max_retries']}, Size: {upload['file_size_mb']:.2f} MB")
        else:
            self.stdout.write("No active uploads")

    def check_health(self):
        """Check SCORM worker health"""
        self.stdout.write("=== SCORM Worker Health ===")
        
        # Direct upload system - no worker health check needed
        self.stdout.write(self.style.SUCCESS("✅ Direct upload system active - no worker needed"))

    def show_failed_uploads(self):
        """Show failed SCORM uploads"""
        self.stdout.write("=== Failed SCORM Uploads ===")
        
        # Find topics with placeholder SCORM content
        failed_topics = []
        for scorm_content in SCORMCloudContent.objects.filter(content_type='topic'):
            if scorm_content.package and 'PLACEHOLDER' in scorm_content.package.cloud_id:
                topic = Topic.objects.filter(id=int(scorm_content.content_id)).first()
                if topic:
                    failed_topics.append({
                        'topic_id': topic.id,
                        'title': topic.title,
                        'course': topic.course.title if topic.course else 'Unknown',
                        'package_id': scorm_content.package.cloud_id
                    })
        
        if failed_topics:
            self.stdout.write(f"Found {len(failed_topics)} failed uploads:")
            for topic in failed_topics:
                self.stdout.write(f"  Topic {topic['topic_id']}: {topic['title']} (Course: {topic['course']})")
        else:
            self.stdout.write("No failed uploads found")

    def show_all_status(self):
        """Show comprehensive SCORM status"""
        self.stdout.write("=== SCORM System Status ===")
        
        # Total SCORM content
        total_scorm = SCORMCloudContent.objects.filter(content_type='topic').count()
        self.stdout.write(f"Total SCORM topics: {total_scorm}")
        
        # Working SCORM content
        working_scorm = SCORMCloudContent.objects.filter(
            content_type='topic',
            package__launch_url__isnull=False
        ).exclude(package__cloud_id__icontains='PLACEHOLDER').count()
        self.stdout.write(f"Working SCORM topics: {working_scorm}")
        
        # Failed SCORM content
        failed_scorm = SCORMCloudContent.objects.filter(
            content_type='topic',
            package__cloud_id__icontains='PLACEHOLDER'
        ).count()
        self.stdout.write(f"Failed SCORM topics: {failed_scorm}")
        
        # Health check
        self.check_health()
        
        # Active uploads
        self.show_upload_status()
