"""
Management command to clear quiz-related cache entries.
Helps resolve Redis conflicts between environments.
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings
from quiz.models import QuizAttempt
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Clear quiz-related cache entries to resolve Redis conflicts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--pattern',
            type=str,
            default='quiz_attempt_',
            help='Cache key pattern to clear (default: quiz_attempt_)'
        )
        parser.add_argument(
            '--all-quiz-cache',
            action='store_true',
            help='Clear all quiz-related cache entries'
        )
        parser.add_argument(
            '--expired-only',
            action='store_true',
            help='Only clear cache for expired quiz attempts'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleared without actually clearing'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting quiz cache cleanup...')
        )

        if options['all_quiz_cache']:
            self.clear_all_quiz_cache(options['dry_run'])
        elif options['expired_only']:
            self.clear_expired_attempt_cache(options['dry_run'])
        else:
            self.clear_pattern_cache(options['pattern'], options['dry_run'])

    def clear_all_quiz_cache(self, dry_run=False):
        """Clear all quiz-related cache entries"""
        patterns = [
            'quiz_attempt_',
            'quiz_progress_',
            'quiz_results_',
            'quiz_stats_',
            'user_quiz_attempts_',
        ]
        
        total_cleared = 0
        for pattern in patterns:
            cleared = self.clear_pattern_cache(pattern, dry_run)
            total_cleared += cleared

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would clear {total_cleared} quiz cache entries')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully cleared {total_cleared} quiz cache entries')
            )

    def clear_expired_attempt_cache(self, dry_run=False):
        """Clear cache only for expired quiz attempts"""
        cleared_count = 0
        
        # Get all quiz attempts that are expired
        expired_attempts = []
        for attempt in QuizAttempt.objects.filter(is_completed=False).select_related('quiz'):
            if attempt.is_expired():
                expired_attempts.append(attempt.id)

        for attempt_id in expired_attempts:
            cache_key = f'quiz_attempt_{attempt_id}'
            if dry_run:
                self.stdout.write(f'Would clear cache key: {cache_key}')
            else:
                try:
                    cache.delete(cache_key)
                    cleared_count += 1
                except Exception as e:
                    logger.warning(f"Failed to clear cache key {cache_key}: {str(e)}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'DRY RUN: Would clear {len(expired_attempts)} expired attempt cache entries')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully cleared {cleared_count} expired attempt cache entries')
            )

    def clear_pattern_cache(self, pattern, dry_run=False):
        """Clear cache entries matching a specific pattern"""
        cleared_count = 0
        
        try:
            # Check if we can access Redis directly for key listing
            if hasattr(cache, '_cache') and hasattr(cache._cache, 'get_client'):
                redis_client = cache._cache.get_client()
                
                # Get cache key prefix if configured
                key_prefix = getattr(settings, 'CACHE_KEY_PREFIX', '')
                if hasattr(settings, 'CACHES') and 'default' in settings.CACHES:
                    key_prefix = settings.CACHES['default'].get('KEY_PREFIX', key_prefix)
                
                # Search for keys with pattern
                search_pattern = f"{key_prefix}{pattern}*"
                matching_keys = redis_client.keys(search_pattern)
                
                for key in matching_keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                    # Remove prefix for Django cache deletion
                    django_key = key_str.replace(key_prefix, '') if key_prefix else key_str
                    
                    if dry_run:
                        self.stdout.write(f'Would clear cache key: {django_key}')
                        cleared_count += 1
                    else:
                        try:
                            cache.delete(django_key)
                            cleared_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to clear cache key {django_key}: {str(e)}")
            else:
                # Fallback: try to clear common quiz attempt IDs
                self.stdout.write(
                    self.style.WARNING('Cannot list cache keys. Attempting fallback cleanup...')
                )
                
                # Get all active quiz attempt IDs
                active_attempts = QuizAttempt.objects.filter(is_completed=False).values_list('id', flat=True)
                
                for attempt_id in active_attempts:
                    cache_key = f'{pattern}{attempt_id}'
                    if dry_run:
                        self.stdout.write(f'Would clear cache key: {cache_key}')
                        cleared_count += 1
                    else:
                        try:
                            cache.delete(cache_key)
                            cleared_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to clear cache key {cache_key}: {str(e)}")
                            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during cache cleanup: {str(e)}')
            )
            return 0

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully cleared {cleared_count} cache entries with pattern "{pattern}"')
            )
        
        return cleared_count

    def get_cache_info(self):
        """Get information about current cache configuration"""
        cache_info = {
            'backend': getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', 'Unknown'),
            'location': getattr(settings, 'CACHES', {}).get('default', {}).get('LOCATION', 'Unknown'),
            'key_prefix': getattr(settings, 'CACHES', {}).get('default', {}).get('KEY_PREFIX', 'None'),
        }
        
        self.stdout.write(
            self.style.SUCCESS('Cache Configuration:')
        )
        for key, value in cache_info.items():
            self.stdout.write(f'  {key}: {value}')
        
        return cache_info
