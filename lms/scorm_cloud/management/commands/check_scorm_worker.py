"""
Django management command to check and restart the SCORM upload worker
"""
from django.core.management.base import BaseCommand
from scorm_cloud.utils.async_uploader import health_check, get_worker_status


class Command(BaseCommand):
    help = 'Check and restart the SCORM upload worker if needed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status-only',
            action='store_true',
            help='Only show status without attempting restart',
        )

    def handle(self, *args, **options):
        if options['status_only']:
            # Just show status
            status = get_worker_status()
            self.stdout.write(
                self.style.SUCCESS(f"SCORM Worker Status: {status}")
            )
        else:
            # Perform health check and restart if needed
            self.stdout.write("Performing SCORM worker health check...")
            
            if health_check():
                self.stdout.write(
                    self.style.SUCCESS("SCORM worker is healthy")
                )
            else:
                self.stdout.write(
                    self.style.WARNING("SCORM worker was restarted")
                )
