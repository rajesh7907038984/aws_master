"""
Management command to clear dashboard cache for troubleshooting data consistency issues
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from core.utils.dashboard_cache import DashboardCache
from core.utils.cache_invalidation import CacheInvalidationManager


class Command(BaseCommand):
    help = 'Clear dashboard cache to ensure data consistency between reports and dashboard'

    def add_arguments(self, parser):
        parser.add_argument(
            '--branch-id',
            type=int,
            help='Clear cache for specific branch ID'
        )
        parser.add_argument(
            '--business-id', 
            type=int,
            help='Clear cache for specific business ID'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear all dashboard cache'
        )
        parser.add_argument(
            '--progress-only',
            action='store_true',
            help='Clear only progress-related cache'
        )
        parser.add_argument(
            '--activity-only',
            action='store_true',
            help='Clear only activity-related cache'
        )

    def handle(self, *args, **options):
        branch_id = options.get('branch_id')
        business_id = options.get('business_id')
        clear_all = options.get('all')
        progress_only = options.get('progress_only')
        activity_only = options.get('activity_only')

        try:
            if clear_all:
                self.stdout.write('Clearing all dashboard cache...')
                DashboardCache.clear_all_dashboard_cache()
                self.stdout.write(
                    self.style.SUCCESS('Successfully cleared all dashboard cache')
                )
                
            elif progress_only:
                self.stdout.write('Clearing progress cache...')
                DashboardCache.clear_progress_cache(branch_id, business_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully cleared progress cache for branch_id={branch_id}, business_id={business_id}'
                    )
                )
                
            elif activity_only:
                self.stdout.write('Clearing activity cache...')
                DashboardCache.clear_activity_cache(branch_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully cleared activity cache for branch_id={branch_id}'
                    )
                )
                
            else:
                # Default: invalidate dashboard data with filters
                self.stdout.write('Clearing dashboard cache with filters...')
                CacheInvalidationManager.invalidate_dashboard_data(
                    branch_id=branch_id,
                    business_id=business_id
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully invalidated dashboard cache for branch_id={branch_id}, business_id={business_id}'
                    )
                )

            # Provide usage instructions
            self.stdout.write('\nCache cleared successfully!')
            self.stdout.write('Data consistency between reports overview and dashboard should now be restored.')
            self.stdout.write('\nUsage examples:')
            self.stdout.write('  python manage.py clear_dashboard_cache --all')
            self.stdout.write('  python manage.py clear_dashboard_cache --branch-id 123')
            self.stdout.write('  python manage.py clear_dashboard_cache --progress-only')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error clearing dashboard cache: {e}')
            )
            raise