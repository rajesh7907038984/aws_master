from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manage SCORM Cloud upload worker with robust error handling'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['start', 'stop', 'status', 'restart'],
            help='Action to perform on the worker'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force restart even if worker appears to be running'
        )

    def handle(self, *args, **options):
        action = options['action']
        
        if action == 'start':
            self.start_worker()
        elif action == 'stop':
            self.stop_worker()
        elif action == 'status':
            self.show_status()
        elif action == 'restart':
            self.restart_worker(options.get('force', False))

    def start_worker(self):
        """Start the SCORM upload worker with robust error handling"""
        try:
            from scorm_cloud.utils.async_uploader import ensure_worker_running, get_queue_status
            
            # Check current status first
            status = get_queue_status()
            if status['worker_running'] and status['worker_alive']:
                self.stdout.write(
                    self.style.WARNING('Worker is already running')
                )
                return
            
            # Start the worker
            success = ensure_worker_running()
            if success:
                self.stdout.write(
                    self.style.SUCCESS('SCORM upload worker started successfully')
                )
                
                # Show updated status
                status = get_queue_status()
                self.stdout.write(f'Queue size: {status["upload_queue_size"]}')
                self.stdout.write(f'Retry queue size: {status["retry_queue_size"]}')
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to start SCORM upload worker')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error starting worker: {str(e)}')
            )
            logger.exception("Worker start error details:")

    def stop_worker(self):
        """Stop the SCORM upload worker"""
        try:
            from scorm_cloud.utils.async_uploader import worker_running, worker_thread
            
            if worker_running:
                worker_running = False
                if worker_thread and worker_thread.is_alive():
                    worker_thread.join(timeout=5)
                
                self.stdout.write(
                    self.style.SUCCESS('SCORM upload worker stopped')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Worker is not running')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error stopping worker: {str(e)}')
            )

    def show_status(self):
        """Show current worker status"""
        try:
            from scorm_cloud.utils.async_uploader import get_queue_status
            from scorm_cloud.models import SCORMPackage
            from courses.models import Topic
            
            # Get queue status
            status = get_queue_status()
            
            self.stdout.write("=== SCORM Worker Status ===")
            self.stdout.write(f"Worker running: {status['worker_running']}")
            self.stdout.write(f"Worker thread alive: {status['worker_alive']}")
            self.stdout.write(f"Upload queue size: {status['upload_queue_size']}")
            self.stdout.write(f"Retry queue size: {status['retry_queue_size']}")
            
            # Get SCORM content status
            scorm_topics = Topic.objects.filter(content_type='SCORM')
            synced_content = SCORMPackage.objects.filter(cloud_id__isnull=False)
            unsynced_content = SCORMPackage.objects.filter(cloud_id__isnull=True)
            
            self.stdout.write("")
            self.stdout.write("=== SCORM Content Status ===")
            self.stdout.write(f"Total SCORM topics: {scorm_topics.count()}")
            self.stdout.write(f"SCORM content synced: {synced_content.count()}")
            self.stdout.write(f"Unsynced topics: {unsynced_content.count()}")
            
            # Get cache status
            from scorm_cloud.utils.redis_fallback import get_robust_fallback
            fallback_cache = get_robust_fallback()
            
            self.stdout.write("")
            self.stdout.write("=== Cache Status ===")
            self.stdout.write(f"Active processing locks: 0")  # Would need to track this
            self.stdout.write(f"Queued cache entries: 0")  # Would need to track this
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error getting status: {str(e)}')
            )
            logger.exception("Status error details:")

    def restart_worker(self, force=False):
        """Restart the SCORM upload worker"""
        self.stdout.write("Restarting SCORM upload worker...")
        self.stop_worker()
        import time
        time.sleep(2)
        self.start_worker()
