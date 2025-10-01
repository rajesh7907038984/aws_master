from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
import logging

from conferences.models import Conference, ConferenceSyncLog
from conferences.views import sync_zoom_meeting_data, sync_teams_meeting_data

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync conference data from video conferencing platforms'

    def add_arguments(self, parser):
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Sync data for a specific conference ID',
        )
        parser.add_argument(
            '--platform',
            type=str,
            choices=['zoom', 'teams'],
            help='Sync data only for specific platform',
        )
        parser.add_argument(
            '--auto-sync',
            action='store_true',
            help='Automatically sync conferences that ended in the last 24 hours',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if already completed',
        )

    def handle(self, *args, **options):
        conference_id = options.get('conference_id')
        platform = options.get('platform')
        auto_sync = options.get('auto_sync')
        force = options.get('force')

        if conference_id:
            # Sync specific conference
            try:
                conference = Conference.objects.get(id=conference_id)
                self.sync_single_conference(conference, force)
            except Conference.DoesNotExist:
                raise CommandError(f'Conference with ID {conference_id} does not exist')
                
        elif auto_sync:
            # Auto-sync conferences that ended recently
            self.auto_sync_conferences(platform, force)
            
        else:
            self.stdout.write(
                self.style.ERROR('Please specify either --conference-id or --auto-sync')
            )

    def sync_single_conference(self, conference, force=False):
        """Sync data for a single conference"""
        self.stdout.write(f'Syncing conference: {conference.title}')
        
        # Check if already synced and not forcing
        if conference.data_sync_status == 'completed' and not force:
            self.stdout.write(
                self.style.WARNING(f'Conference {conference.id} already synced. Use --force to resync.')
            )
            return
        
        # Update sync status
        conference.data_sync_status = 'in_progress'
        conference.save()
        
        # Create sync log
        sync_log = ConferenceSyncLog.objects.create(
            conference=conference,
            sync_type='full',
            status='started'
        )
        
        try:
            # Sync based on platform
            if conference.meeting_platform == 'zoom':
                result = sync_zoom_meeting_data(conference)
            elif conference.meeting_platform == 'teams':
                result = sync_teams_meeting_data(conference)
            else:
                result = {'success': False, 'error': f'Unsupported platform: {conference.meeting_platform}'}
            
            # Update sync log
            sync_log.status = 'completed' if result.get('success') else 'failed'
            sync_log.items_processed = result.get('items_processed', 0)
            sync_log.items_failed = result.get('items_failed', 0)
            sync_log.error_message = result.get('error')
            sync_log.platform_response = result.get('platform_response', {})
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            # Update conference
            conference.data_sync_status = 'completed' if result.get('success') else 'failed'
            conference.last_sync_at = timezone.now()
            conference.save()
            
            if result.get('success'):
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully synced {result.get("items_processed", 0)} items for conference {conference.id}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to sync conference {conference.id}: {result.get("error")}')
                )
                
        except Exception as e:
            logger.exception(f"Error syncing conference {conference.id}")
            
            # Update sync log with error
            sync_log.status = 'failed'
            sync_log.error_message = str(e)
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            # Update conference
            conference.data_sync_status = 'failed'
            conference.save()
            
            self.stdout.write(
                self.style.ERROR(f'Error syncing conference {conference.id}: {str(e)}')
            )

    def auto_sync_conferences(self, platform=None, force=False):
        """Auto-sync conferences that ended recently"""
        # Get conferences that ended in the last 24 hours
        yesterday = timezone.now() - timedelta(hours=24)
        
        # Build query
        query = Conference.objects.filter(
            meeting_status='ended',
            date__gte=yesterday.date()
        )
        
        if platform:
            query = query.filter(meeting_platform=platform)
            
        if not force:
            query = query.exclude(data_sync_status='completed')
        
        conferences = query.order_by('-date', '-start_time')
        
        self.stdout.write(f'Found {conferences.count()} conferences to sync')
        
        synced_count = 0
        failed_count = 0
        
        for conference in conferences:
            try:
                self.sync_single_conference(conference, force)
                synced_count += 1
            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Failed to sync conference {conference.id}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Auto-sync completed. Synced: {synced_count}, Failed: {failed_count}'
            )
        ) 