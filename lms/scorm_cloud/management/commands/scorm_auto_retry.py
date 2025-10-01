from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from scorm_cloud.models import SCORMCloudContent
from courses.models import Topic
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Automatically retry failed SCORM uploads (run this as a scheduled task)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-retries',
            type=int,
            default=3,
            help='Maximum number of retries per topic',
        )
        parser.add_argument(
            '--retry-delay',
            type=int,
            default=3600,  # 1 hour
            help='Delay between retries in seconds',
        )

    def handle(self, *args, **options):
        max_retries = options['max_retries']
        retry_delay = options['retry_delay']
        
        self.stdout.write("=== SCORM Auto Retry System ===")
        
        # Find topics with placeholder SCORM content
        failed_topics = []
        for scorm_content in SCORMCloudContent.objects.filter(content_type='topic'):
            if scorm_content.package and 'PLACEHOLDER' in scorm_content.package.cloud_id:
                topic = Topic.objects.filter(id=int(scorm_content.content_id)).first()
                if topic:
                    failed_topics.append(topic)
        
        self.stdout.write(f"Found {len(failed_topics)} failed uploads")
        
        retried_count = 0
        for topic in failed_topics:
            # Check if we should retry this topic
            cache_key = f"scorm_retry_count_{topic.id}"
            retry_count = cache.get(cache_key, 0)
            
            if retry_count < max_retries:
                # Check if enough time has passed since last retry
                last_retry_key = f"scorm_last_retry_{topic.id}"
                last_retry = cache.get(last_retry_key)
                
                if not last_retry or (timezone.now() - last_retry).total_seconds() > retry_delay:
                    self.stdout.write(f"Retrying topic {topic.id}: {topic.title}")
                    
                    # Increment retry count
                    cache.set(cache_key, retry_count + 1, 86400)  # 24 hours
                    cache.set(last_retry_key, timezone.now(), 86400)  # 24 hours
                    
                    # Queue for retry (this would trigger the actual retry)
                    self._queue_topic_for_retry(topic)
                    retried_count += 1
                else:
                    self.stdout.write(f"Skipping topic {topic.id} - too soon since last retry")
            else:
                self.stdout.write(f"Skipping topic {topic.id} - max retries exceeded")
        
        self.stdout.write(f"Queued {retried_count} topics for retry")
        
        # Log the auto retry activity
        logger.info(f"SCORM auto retry: {retried_count} topics queued for retry")

    def _queue_topic_for_retry(self, topic):
        """Queue a topic for retry processing"""
        # This would integrate with your existing retry system
        # For now, just log it
        logger.info(f"Queued topic {topic.id} for SCORM retry")
        
        # You could also add to a retry queue in cache or database
        retry_queue_key = f"scorm_retry_queue_{topic.id}"
        cache.set(retry_queue_key, {
            'topic_id': topic.id,
            'queued_at': timezone.now().isoformat(),
            'retry_reason': 'auto_retry_system'
        }, 86400)  # 24 hours
