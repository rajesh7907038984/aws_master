from django.core.management.base import BaseCommand
from scorm.models import ELearningTracking, ELearningPackage
from courses.models import Topic
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix SCORM data synchronization issues for specific topics or all topics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--topic-id',
            type=int,
            help='Specific topic ID to fix (optional)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fix all SCORM tracking records',
        )

    def handle(self, *args, **options):
        from scorm.views import _sync_tracking_data
        
        if options['topic_id']:
            # Fix specific topic
            try:
                topic = Topic.objects.get(id=options['topic_id'])
                package = ELearningPackage.objects.get(topic=topic)
                tracking_records = ELearningTracking.objects.filter(elearning_package=package)
                
                self.stdout.write(f'Fixing SCORM data for topic {options["topic_id"]}: {topic.title}')
                self.stdout.write(f'Found {tracking_records.count()} tracking records')
                
                for tracking in tracking_records:
                    self.stdout.write(f'Fixing data for user: {tracking.user.username}')
                    
                    # Show before state
                    self.stdout.write(f'  Before - Score: {tracking.score_raw}, Time: {tracking.total_time}')
                    self.stdout.write(f'  Raw data keys: {list(tracking.raw_data.keys())}')
                    
                    # Sync data
                    _sync_tracking_data(tracking)
                    
                    # Refresh from database
                    tracking.refresh_from_db()
                    
                    # Show after state
                    self.stdout.write(f'  After - Score: {tracking.score_raw}, Time: {tracking.total_time}')
                    self.stdout.write('')
                
                self.stdout.write(self.style.SUCCESS(f'Successfully fixed SCORM data for topic {options["topic_id"]}'))
                
            except Topic.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Topic {options["topic_id"]} does not exist'))
            except ELearningPackage.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'No SCORM package found for topic {options["topic_id"]}'))
                
        elif options['all']:
            # Fix all SCORM tracking records
            tracking_records = ELearningTracking.objects.all()
            
            self.stdout.write(f'Fixing SCORM data for all {tracking_records.count()} tracking records')
            
            fixed_count = 0
            for tracking in tracking_records:
                try:
                    _sync_tracking_data(tracking)
                    fixed_count += 1
                    if fixed_count % 10 == 0:
                        self.stdout.write(f'Processed {fixed_count} records...')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error fixing tracking record {tracking.id}: {str(e)}'))
            
            self.stdout.write(self.style.SUCCESS(f'Successfully processed {fixed_count} tracking records'))
            
        else:
            self.stdout.write(self.style.ERROR('Please specify --topic-id or --all'))
