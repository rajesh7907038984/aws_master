from django.core.management.base import BaseCommand
from django.db.models import Count
from scorm_cloud.models import SCORMCloudContent
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up duplicate SCORMCloudContent records'

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup of duplicate SCORMCloudContent records...')
        
        # Find duplicates based on content_type and content_id
        duplicates = SCORMCloudContent.objects.values('content_type', 'content_id') \
            .annotate(count=Count('id')) \
            .filter(count__gt=1)
            
        total_duplicates = 0
        
        for duplicate in duplicates:
            content_type = duplicate['content_type']
            content_id = duplicate['content_id']
            
            if not content_id:  # Skip empty content_id
                continue
                
            self.stdout.write(f'Found {duplicate["count"]} duplicates for {content_type}/{content_id}')
            
            # Get all duplicates ordered by ID (to keep the most recent)
            records = SCORMCloudContent.objects.filter(
                content_type=content_type,
                content_id=content_id
            ).order_by('id')
            
            # Keep the most recent record (highest ID) and delete others
            keep_record = records.last()
            records_to_delete = records.exclude(id=keep_record.id)
            
            self.stdout.write(f'  Keeping record {keep_record.id} and deleting {records_to_delete.count()} others')
            
            # Delete the duplicates
            for record in records_to_delete:
                self.stdout.write(f'  Deleting record {record.id}')
                record.delete()
                total_duplicates += 1
        
        if total_duplicates > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted {total_duplicates} duplicate records'))
        else:
            self.stdout.write('No duplicate records found') 