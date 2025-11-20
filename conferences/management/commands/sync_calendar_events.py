"""
Management command to sync time slot selections to Outlook calendar.
This is useful for:
1. Retrying failed calendar additions
2. Adding calendar events for selections that were made before calendar sync was implemented
3. Syncing events for conferences that changed meeting platforms
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from conferences.models import ConferenceTimeSlotSelection, Conference
from conferences.views import add_to_outlook_calendar
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync conference time slot selections to Outlook calendar'

    def add_arguments(self, parser):
        parser.add_argument(
            '--conference-id',
            type=int,
            help='Sync only for a specific conference'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync only for a specific user'
        )
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Retry only selections that previously failed'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Sync all selections, even those already synced'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing'
        )

    def handle(self, *args, **options):
        conference_id = options.get('conference_id')
        user_id = options.get('user_id')
        retry_failed = options.get('retry_failed')
        sync_all = options.get('all')
        dry_run = options.get('dry_run')

        # Build query
        query = ConferenceTimeSlotSelection.objects.select_related(
            'user', 'time_slot', 'conference'
        )

        if conference_id:
            query = query.filter(conference_id=conference_id)
            self.stdout.write(f'Filtering by conference ID: {conference_id}')

        if user_id:
            query = query.filter(user_id=user_id)
            self.stdout.write(f'Filtering by user ID: {user_id}')

        if retry_failed:
            # Only retry selections that failed or have errors
            query = query.filter(
                calendar_added=False,
                calendar_add_attempted_at__isnull=False
            )
            self.stdout.write('Retrying only failed calendar additions')
        elif not sync_all:
            # By default, only sync selections that haven't been synced yet
            query = query.filter(calendar_added=False)
            self.stdout.write('Syncing only unsynced selections')
        else:
            self.stdout.write('Syncing ALL selections (including already synced)')

        # Get selections
        selections = query.order_by('-selected_at')
        total_count = selections.count()

        self.stdout.write(f'\nFound {total_count} selections to sync')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN MODE ==='))
            for selection in selections[:10]:  # Show first 10
                self.stdout.write(
                    f'Would sync: {selection.user.get_full_name()} - '
                    f'{selection.conference.title} - '
                    f'{selection.time_slot.date} {selection.time_slot.start_time}'
                )
            if total_count > 10:
                self.stdout.write(f'... and {total_count - 10} more')
            return

        # Perform sync
        success_count = 0
        failed_count = 0
        skipped_count = 0

        self.stdout.write('\nStarting calendar sync...\n')

        for i, selection in enumerate(selections, 1):
            try:
                # Check if conference has time slot
                if not selection.conference.use_time_slots:
                    skipped_count += 1
                    if i % 10 == 0:
                        self.stdout.write(f'Progress: {i}/{total_count}')
                    continue

                # Try to add to calendar
                self.stdout.write(
                    f'[{i}/{total_count}] Syncing: {selection.user.username} - '
                    f'{selection.conference.title} - '
                    f'{selection.time_slot.date} {selection.time_slot.start_time}'
                )

                result = add_to_outlook_calendar(
                    selection.user,
                    selection.time_slot,
                    selection
                )

                if result:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Success')
                    )
                else:
                    failed_count += 1
                    error_msg = selection.calendar_error or 'Unknown error'
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed: {error_msg}')
                    )

            except Exception as e:
                failed_count += 1
                logger.error(
                    f"Error syncing selection {selection.id}: {str(e)}"
                )
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Exception: {str(e)}')
                )

        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('\nSync Summary:'))
        self.stdout.write(f'Total selections: {total_count}')
        self.stdout.write(
            self.style.SUCCESS(f'Successfully synced: {success_count}')
        )
        if failed_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Failed: {failed_count}')
            )
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(f'Skipped: {skipped_count}')
            )
        self.stdout.write('='*60 + '\n')

