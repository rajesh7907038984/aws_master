"""
Management command to sync total_time_spent from progress_data for video and audio content.

This command fixes historical data where time was being tracked in progress_data['total_viewing_time']
but not in the total_time_spent field that's used for reporting.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from courses.models import TopicProgress


class Command(BaseCommand):
    help = 'Sync total_time_spent field from progress_data for video and audio topics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode without making changes',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Only sync data for a specific user ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options.get('user_id')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY-RUN mode - no changes will be made'))
        
        # Get all TopicProgress records for video and audio content
        queryset = TopicProgress.objects.filter(
            Q(topic__content_type='Video') | 
            Q(topic__content_type='EmbedVideo') | 
            Q(topic__content_type='Audio')
        ).select_related('topic', 'user')
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
            self.stdout.write(f'Filtering for user ID: {user_id}')
        
        total_records = queryset.count()
        self.stdout.write(f'Found {total_records} video/audio progress records to check')
        
        updated_count = 0
        video_time_synced = 0
        audio_time_synced = 0
        
        for progress in queryset:
            updated = False
            content_type = progress.topic.content_type
            
            # For video content, check if we have total_viewing_time in progress_data
            if content_type in ['Video', 'EmbedVideo']:
                if progress.progress_data and isinstance(progress.progress_data, dict):
                    total_viewing_time = progress.progress_data.get('total_viewing_time', 0)
                    
                    # If we have viewing time tracked but total_time_spent is 0 or less than viewing time
                    if total_viewing_time > 0 and progress.total_time_spent < total_viewing_time:
                        time_to_add = int(total_viewing_time - progress.total_time_spent)
                        
                        if not dry_run:
                            progress.total_time_spent = int(total_viewing_time)
                            progress.save(update_fields=['total_time_spent'])
                        
                        self.stdout.write(
                            f'[Video] {progress.user.username} - Topic: {progress.topic.title[:50]} - '
                            f'Added {time_to_add}s (was: {progress.total_time_spent}s, now: {int(total_viewing_time)}s)'
                        )
                        updated = True
                        video_time_synced += time_to_add
            
            # For audio content, check if we have last_audio_position
            elif content_type == 'Audio':
                if progress.last_audio_position and progress.last_audio_position > 0:
                    # If total_time_spent is 0 or significantly less than position, 
                    # estimate based on audio position
                    if progress.total_time_spent == 0:
                        # Conservative estimate: use the audio position as time spent
                        estimated_time = int(progress.last_audio_position)
                        
                        if not dry_run:
                            progress.total_time_spent = estimated_time
                            progress.save(update_fields=['total_time_spent'])
                        
                        self.stdout.write(
                            f'[Audio] {progress.user.username} - Topic: {progress.topic.title[:50]} - '
                            f'Set time_spent to {estimated_time}s based on position'
                        )
                        updated = True
                        audio_time_synced += estimated_time
            
            if updated:
                updated_count += 1
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Summary ==='))
        self.stdout.write(f'Total records checked: {total_records}')
        self.stdout.write(f'Records updated: {updated_count}')
        self.stdout.write(f'Video time synced: {video_time_synced}s ({video_time_synced // 3600}h {(video_time_synced % 3600) // 60}m)')
        self.stdout.write(f'Audio time synced: {audio_time_synced}s ({audio_time_synced // 3600}h {(audio_time_synced % 3600) // 60}m)')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY-RUN complete - no changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('\nSync complete!'))

