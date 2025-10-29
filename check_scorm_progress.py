#!/usr/bin/env python
"""
Script to check for recent SCORM-related tracking data in the database
Run with: python manage.py shell < check_scorm_progress.py
Or: python -c "exec(open('check_scorm_progress.py').read())" (after setting up Django)
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from courses.models import TopicProgress, Topic
from django.utils import timezone
from datetime import timedelta
import json

# Check last 24 hours
recent = timezone.now() - timedelta(hours=24)

print("=" * 80)
print("RECENT SCORM PROGRESS RECORDS (Last 24 Hours)")
print("=" * 80)

# Get all SCORM topic progress records updated in last 24 hours
scorm_records = TopicProgress.objects.filter(
    topic__content_type='SCORM',
    last_updated__gte=recent
).select_related('user', 'topic').order_by('-last_updated')

print(f"\nTotal records found: {scorm_records.count()}\n")

if scorm_records.count() == 0:
    print("⚠️  No recent SCORM progress records found.")
    print("   This could mean:")
    print("   - Fix hasn't been deployed yet")
    print("   - No one has launched SCORM content in the last 24 hours")
    print("   - Progress tracking is still not working")
    print("\nChecking for ANY recent topic progress records...")
    
    all_recent = TopicProgress.objects.filter(
        last_updated__gte=recent
    ).select_related('user', 'topic')[:10]
    
    print(f"Found {all_recent.count()} recent progress records (all types):")
    for r in all_recent:
        print(f"  - {r.user.username} on Topic {r.topic.id} ({r.topic.content_type}) - Updated: {r.last_updated}")

# Display each SCORM record in detail
for idx, record in enumerate(scorm_records[:20], 1):
    print("\n" + "-" * 80)
    print(f"RECORD {idx}")
    print("-" * 80)
    print(f"User:          {record.user.username} (ID: {record.user.id})")
    print(f"Topic:         {record.topic.id} - {record.topic.title}")
    print(f"Last Updated:  {record.last_updated}")
    print(f"First Accessed:{record.first_accessed}")
    print(f"Completed:     {record.completed}")
    print(f"Completion:    {record.completion_method}")
    print(f"Last Score:    {record.last_score}")
    print(f"Best Score:   {record.best_score}")
    print(f"Time Spent:    {record.total_time_spent} seconds")
    print(f"Attempts:      {record.attempts}")
    
    # Progress Data Analysis
    print("\n📊 Progress Data:")
    if record.progress_data:
        pd = record.progress_data
        scorm_fields = [k for k in pd.keys() if 'scorm' in k.lower()]
        if scorm_fields:
            print(f"   SCORM-specific fields found: {', '.join(scorm_fields)}")
            for field in scorm_fields:
                value = pd[field]
                if isinstance(value, (dict, list)):
                    print(f"     {field}: {type(value).__name__} ({len(value)} items)")
                else:
                    print(f"     {field}: {value}")
        else:
            print("   ⚠️  No SCORM-specific fields in progress_data")
            print(f"   Available fields: {', '.join(list(pd.keys())[:10])}")
    else:
        print("   ⚠️  progress_data is empty or None")
    
    # Bookmark Analysis
    print("\n🔖 Bookmark Data:")
    if record.bookmark:
        print(f"   Available fields: {', '.join(record.bookmark.keys())}")
        if 'lesson_location' in record.bookmark:
            print(f"   Lesson Location: {record.bookmark['lesson_location']}")
        if 'suspend_data' in record.bookmark:
            suspend = record.bookmark['suspend_data']
            print(f"   Suspend Data: {suspend[:100] if len(str(suspend)) > 100 else suspend}...")
    else:
        print("   No bookmark data")
    
    # Completion Data
    if record.completion_data:
        print("\n✅ Completion Data:")
        print(f"   {json.dumps(record.completion_data, indent=2)[:200]}...")

print("\n" + "=" * 80)
print("CHECKING SPECIFIC TEST TOPICS (235 & 236)")
print("=" * 80)

# Check specific topics from our test
test_topics = [235, 236]
for topic_id in test_topics:
    try:
        topic = Topic.objects.get(id=topic_id)
        progress_records = TopicProgress.objects.filter(
            topic=topic
        ).select_related('user').order_by('-last_updated')
        
        print(f"\n📚 Topic {topic_id}: {topic.title}")
        print(f"   Content Type: {topic.content_type}")
        print(f"   Progress Records: {progress_records.count()}")
        
        for pr in progress_records[:5]:
            print(f"\n   User: {pr.user.username}")
            print(f"   Last Updated: {pr.last_updated}")
            print(f"   Completed: {pr.completed}")
            print(f"   Score: {pr.last_score}")
            if pr.progress_data and 'scorm' in str(pr.progress_data).lower():
                print(f"   ✅ Has SCORM tracking data")
            else:
                print(f"   ⚠️  No SCORM tracking data")
    except Topic.DoesNotExist:
        print(f"\n⚠️  Topic {topic_id} not found")

print("\n" + "=" * 80)

