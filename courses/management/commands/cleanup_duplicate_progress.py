"""
Management command to clean up duplicate TopicProgress records
Usage: python manage.py cleanup_duplicate_progress
"""
from django.core.management.base import BaseCommand
from django.db.models import Count
from courses.models import TopicProgress

class Command(BaseCommand):
    help = 'Clean up duplicate TopicProgress records (same user + topic)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('CLEANING UP DUPLICATE TOPIC PROGRESS RECORDS'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        if dry_run:
            self.stdout.write(self.style.NOTICE('\n[DRY RUN MODE - No actual deletions will occur]\n'))
        
        # Find duplicates (same user + same topic)
        duplicates = TopicProgress.objects.values('user', 'topic').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        if duplicates.count() == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ No duplicate records found!\n'))
            return
        
        self.stdout.write(self.style.WARNING(f'\n⚠️  Found {duplicates.count()} duplicate combinations!\n'))
        
        total_deleted = 0
        
        for dup in duplicates:
            records = TopicProgress.objects.filter(
                user_id=dup['user'], 
                topic_id=dup['topic']
            ).order_by('-last_accessed', '-id')  # Keep the most recent one
            
            user = records.first().user
            topic = records.first().topic
            
            self.stdout.write(f"\nUser: {user.username} ({user.email})")
            self.stdout.write(f"Topic: {topic.title} (ID: {topic.id})")
            self.stdout.write(f"Found {dup['count']} records:")
            
            # Keep the first one (most recent), delete the rest
            to_keep = records.first()
            to_delete = records.exclude(id=to_keep.id)
            
            self.stdout.write(f"  KEEP: ID {to_keep.id} - Completed: {to_keep.completed}, Last accessed: {to_keep.last_accessed}")
            
            for rec in to_delete:
                self.stdout.write(self.style.ERROR(
                    f"  DELETE: ID {rec.id} - Completed: {rec.completed}, Last accessed: {rec.last_accessed}"
                ))
                
                if not dry_run:
                    rec.delete()
                    total_deleted += 1
        
        if dry_run:
            self.stdout.write(self.style.NOTICE(f'\n[DRY RUN] Would delete {total_deleted} duplicate records'))
            self.stdout.write(self.style.NOTICE('Run without --dry-run to actually delete them\n'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Deleted {total_deleted} duplicate records\n'))
        
        # Verify unique constraint exists
        self.stdout.write(self.style.WARNING('\nVerifying unique_together constraint...'))
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Check if unique constraint exists (PostgreSQL)
            if connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM pg_constraint
                    WHERE conname LIKE '%topicprogress%'
                    AND contype = 'u'
                """)
                constraint_count = cursor.fetchone()[0]
                
                if constraint_count > 0:
                    self.stdout.write(self.style.SUCCESS('✓ Unique constraint exists'))
                else:
                    self.stdout.write(self.style.ERROR('⚠️  Unique constraint NOT found'))
                    self.stdout.write(self.style.NOTICE('Run: python manage.py makemigrations && python manage.py migrate'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Cleanup complete!\n'))

