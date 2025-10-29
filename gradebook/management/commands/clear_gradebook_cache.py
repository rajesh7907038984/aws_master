"""
Django management command to clear gradebook cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Clear gradebook cache to force recalculation of scores'

    def handle(self, *args, **options):
        try:
            cache.clear()
            self.stdout.write(
                self.style.SUCCESS('Successfully cleared gradebook cache')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error clearing cache: {str(e)}')
            )

