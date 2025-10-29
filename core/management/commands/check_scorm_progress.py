from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from courses.models import TopicProgress, Topic
import json


class Command(BaseCommand):
    help = 'Check for recently added SCORM-related tracking data in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Number of hours to look back (default: 24)'
        )
        parser.add_argument(
            '--topic-ids',
            type=str,
            help='Comma-separated list of topic IDs to check specifically (e.g., 235,236)'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        recent = timezone.now() - timedelta(hours=hours)
        
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS(
            f"RECENT SCORM PROGRESS RECORDS (Last {hours} Hours)"
        ))
        self.stdout.write("=" * 80)

        # Get all SCORM topic progress records updated in last N hours
        scorm_records = TopicProgress.objects.filter(
            topic__content_type='SCORM',
            last_updated__gte=recent
        ).select_related('user', 'topic').order_by('-last_updated')

        count = scorm_records.count()
        self.stdout.write(f"\nTotal SCORM records found: {count}\n")

        if count == 0:
            self.stdout.write(self.style.WARNING(
                "⚠️  No recent SCORM progress records found."
            ))
            self.stdout.write("   Possible reasons:")
            self.stdout.write("   - Fix hasn't been deployed to this environment yet")
            self.stdout.write("   - No one has launched SCORM content recently")
            self.stdout.write("   - Progress tracking is still not working")
            
            # Check for any recent progress
            self.stdout.write("\nChecking for ANY recent topic progress records...")
            all_recent = TopicProgress.objects.filter(
                last_updated__gte=recent
            ).select_related('user', 'topic')[:10]
            
            self.stdout.write(f"Found {all_recent.count()} recent progress records (all types):")
            for r in all_recent:
                self.stdout.write(
                    f"  - {r.user.username} on Topic {r.topic.id} "
                    f"({r.topic.content_type}) - Updated: {r.last_updated}"
                )
        else:
            # Display each SCORM record in detail
            for idx, record in enumerate(scorm_records[:20], 1):
                self.stdout.write("\n" + "-" * 80)
                self.stdout.write(f"RECORD {idx}")
                self.stdout.write("-" * 80)
                self.stdout.write(f"User:          {record.user.username} (ID: {record.user.id})")
                self.stdout.write(f"Topic:         {record.topic.id} - {record.topic.title}")
                self.stdout.write(f"Last Updated:  {record.last_updated}")
                self.stdout.write(f"First Accessed:{record.first_accessed}")
                self.stdout.write(f"Completed:     {record.completed}")
                self.stdout.write(f"Completion:    {record.completion_method}")
                self.stdout.write(f"Last Score:    {record.last_score}")
                self.stdout.write(f"Best Score:     {record.best_score}")
                self.stdout.write(f"Time Spent:    {record.total_time_spent} seconds")
                self.stdout.write(f"Attempts:      {record.attempts}")
                
                # Progress Data Analysis
                self.stdout.write("\n📊 Progress Data:")
                if record.progress_data:
                    pd = record.progress_data
                    scorm_fields = [k for k in pd.keys() if 'scorm' in k.lower()]
                    if scorm_fields:
                        self.stdout.write(self.style.SUCCESS(
                            f"   ✅ SCORM-specific fields found: {', '.join(scorm_fields)}"
                        ))
                        for field in scorm_fields:
                            value = pd[field]
                            if isinstance(value, (dict, list)):
                                self.stdout.write(
                                    f"     {field}: {type(value).__name__} ({len(value)} items)"
                                )
                            else:
                                self.stdout.write(f"     {field}: {value}")
                    else:
                        self.stdout.write(self.style.WARNING(
                            "   ⚠️  No SCORM-specific fields in progress_data"
                        ))
                        if pd:
                            self.stdout.write(
                                f"   Available fields: {', '.join(list(pd.keys())[:10])}"
                            )
                    # Check for raw CMI data
                    if 'scorm_raw_cmi_data' in pd:
                        self.stdout.write(self.style.SUCCESS(
                            "   ✅ Has raw SCORM CMI data (full tracking)"
                        ))
                else:
                    self.stdout.write(self.style.WARNING(
                        "   ⚠️  progress_data is empty or None"
                    ))
                
                # Bookmark Analysis
                self.stdout.write("\n🔖 Bookmark Data:")
                if record.bookmark:
                    self.stdout.write(f"   Available fields: {', '.join(record.bookmark.keys())}")
                    if 'lesson_location' in record.bookmark:
                        self.stdout.write(
                            f"   Lesson Location: {record.bookmark['lesson_location']}"
                        )
                    if 'suspend_data' in record.bookmark:
                        suspend = record.bookmark['suspend_data']
                        preview = suspend[:100] if len(str(suspend)) > 100 else suspend
                        self.stdout.write(f"   Suspend Data: {preview}...")
                else:
                    self.stdout.write("   No bookmark data")
                
                # Completion Data
                if record.completion_data:
                    self.stdout.write("\n✅ Completion Data:")
                    cd_str = json.dumps(record.completion_data, indent=2)[:200]
                    self.stdout.write(f"   {cd_str}...")

        # Check specific topics if requested
        topic_ids_str = options.get('topic_ids')
        if topic_ids_str:
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write("CHECKING SPECIFIC TEST TOPICS")
            self.stdout.write("=" * 80)
            
            topic_ids = [int(tid.strip()) for tid in topic_ids_str.split(',')]
            for topic_id in topic_ids:
                try:
                    topic = Topic.objects.get(id=topic_id)
                    progress_records = TopicProgress.objects.filter(
                        topic=topic
                    ).select_related('user').order_by('-last_updated')
                    
                    self.stdout.write(f"\n📚 Topic {topic_id}: {topic.title}")
                    self.stdout.write(f"   Content Type: {topic.content_type}")
                    self.stdout.write(f"   Progress Records: {progress_records.count()}")
                    
                    for pr in progress_records[:5]:
                        self.stdout.write(f"\n   User: {pr.user.username}")
                        self.stdout.write(f"   Last Updated: {pr.last_updated}")
                        self.stdout.write(f"   Completed: {pr.completed}")
                        self.stdout.write(f"   Score: {pr.last_score}")
                        if pr.progress_data and any('scorm' in k.lower() for k in pr.progress_data.keys()):
                            self.stdout.write(self.style.SUCCESS("   ✅ Has SCORM tracking data"))
                        else:
                            self.stdout.write(self.style.WARNING("   ⚠️  No SCORM tracking data"))
                except Topic.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"\n⚠️  Topic {topic_id} not found"))

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("Check complete!"))

