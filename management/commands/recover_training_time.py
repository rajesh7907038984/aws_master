"""
Django management command to recover training time data
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import sys
import os

# Add the scripts directory to the path
sys.path.append('/home/ec2-user/lms/scripts')

from recover_training_time import TrainingTimeRecoveryService

class Command(BaseCommand):
    help = 'Recover training time data from SCORM session data and fix TopicProgress records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode to see what would be changed without making changes',
        )
        parser.add_argument(
            '--user-email',
            type=str,
            help='Recover data for a specific user email',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Training Time Recovery Process')
        )
        
        start_time = timezone.now()
        
        # Initialize the recovery service
        recovery_service = TrainingTimeRecoveryService()
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('🔍 Running in DRY-RUN mode - no changes will be made')
            )
            # TODO: Implement dry-run functionality
            return
        
        if options['user_email']:
            self.stdout.write(
                self.style.SUCCESS(f'👤 Recovering data for user: {options["user_email"]}')
            )
            # TODO: Implement user-specific recovery
        
        # Run the full recovery process
        try:
            results = recovery_service.run_full_recovery()
            
            # Display results
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎉 Recovery Process Complete!\n'
                    f'✅ SCORM attempts recovered: {results["recovered_attempts"]}\n'
                    f'✅ TopicProgress records updated: {results["updated_progress"]}\n'
                    f'❌ Errors encountered: {results["errors"]}\n'
                    f'⏱️  Duration: {results["duration"]}'
                )
            )
            
            if results['errors'] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  {results["errors"]} errors were encountered during recovery'
                    )
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Recovery process failed: {str(e)}')
            )
            raise
