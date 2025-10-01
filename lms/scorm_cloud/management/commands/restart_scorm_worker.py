"""
Management command to restart the SCORM upload worker
"""
from django.core.management.base import BaseCommand
from scorm_cloud.utils.async_uploader import restart_worker_if_needed, get_worker_status
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Restart the SCORM upload worker if needed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force restart the worker even if it appears to be running',
        )

    def handle(self, *args, **options):
        self.stdout.write('Checking SCORM worker status...')
        
        # Get current status
        status = get_worker_status()
        self.stdout.write(f'Current status: {status}')
        
        if options['force']:
            self.stdout.write('Force restart requested...')
            # Kill existing worker and restart
            global worker_running, worker_thread
            from scorm_cloud.utils.async_uploader import worker_running, worker_thread
            worker_running = False
            if worker_thread:
                worker_thread.join(timeout=5)
            
        # Restart worker if needed
        if restart_worker_if_needed():
            self.stdout.write(
                self.style.SUCCESS('SCORM worker restarted successfully')
            )
        else:
            self.stdout.write(
                self.style.ERROR('Failed to restart SCORM worker')
            )
        
        # Show final status
        final_status = get_worker_status()
        self.stdout.write(f'Final status: {final_status}')
