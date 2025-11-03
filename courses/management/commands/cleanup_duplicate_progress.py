"""
Management command to clean up duplicate TopicProgress records
"""
from django.core.management.base import BaseCommand
from django.db.models import Count
from courses.models import TopicProgress


class Command(BaseCommand):
    help = 'Clean up duplicate TopicProgress records, keeping the most recent one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write("Checking for duplicate TopicProgress records...")
        
        # Find duplicates (same user + topic combination)
        duplicates = (
            TopicProgress.objects
            .values('user_id', 'topic_id')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate records found!'))
            return
        
        self.stdout.write(
            self.style.WARNING(f'Found {len(duplicates)} sets of duplicate records')
        )
        
        total_deleted = 0
        
        for dup in duplicates:
            user_id = dup['user_id']
            topic_id = dup['topic_id']
            count = dup['count']
            
            # Get all records for this user+topic, ordered by most recent first
            records = TopicProgress.objects.filter(
                user_id=user_id,
                topic_id=topic_id
            ).order_by('-updated_at', '-created_at', '-id')
            
            # Keep the most recent one, delete the rest
            keep_record = records.first()
            delete_records = records.exclude(id=keep_record.id)
            
            self.stdout.write(
                f'\nUser {user_id}, Topic {topic_id}: {count} records'
            )
            self.stdout.write(f'  Keeping: ID {keep_record.id} (updated: {keep_record.updated_at})')
            
            for record in delete_records:
                self.stdout.write(
                    f'  Deleting: ID {record.id} (updated: {record.updated_at})'
                )
                if not dry_run:
                    record.delete()
                    total_deleted += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\nDry run complete. Would have deleted {total_deleted} duplicate records.'
                )
            )
            self.stdout.write('Run without --dry-run to actually delete.')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSuccessfully deleted {total_deleted} duplicate records!'
                )
            )
