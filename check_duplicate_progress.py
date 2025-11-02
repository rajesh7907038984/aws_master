#!/usr/bin/env python
"""
Check for duplicate TopicProgress records that might cause issues
"""
import os
import django
from django.db.models import Count

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_main.settings')
django.setup()

from courses.models import Topic, TopicProgress
from users.models import CustomUser

print("=" * 60)
print("CHECKING FOR DUPLICATE TOPIC PROGRESS RECORDS")
print("=" * 60)

# Find duplicates (same user + same topic)
duplicates = TopicProgress.objects.values('user', 'topic').annotate(
    count=Count('id')
).filter(count__gt=1)

if duplicates.count() > 0:
    print(f"\n⚠️  Found {duplicates.count()} duplicate combinations!\n")
    
    for dup in duplicates:
        user = CustomUser.objects.get(id=dup['user'])
        topic = Topic.objects.get(id=dup['topic'])
        
        print(f"User: {user.username}, Topic: {topic.title} (ID: {topic.id})")
        print(f"  {dup['count']} records found:")
        
        records = TopicProgress.objects.filter(user=user, topic=topic).order_by('id')
        for idx, rec in enumerate(records, 1):
            print(f"    #{idx} - ID: {rec.id}, Completed: {rec.completed}, Created: {rec.first_accessed}")
        
        # Ask to delete duplicates
        delete = input(f"\n  Keep only the LATEST record and delete older duplicates? (y/n): ")
        if delete.lower() == 'y':
            # Keep the last one, delete the rest
            to_delete = list(records)[:-1]
            for rec in to_delete:
                rec.delete()
                print(f"    ✓ Deleted record ID {rec.id}")
        print()
else:
    print("\n✓ No duplicate records found!\n")

# Check specific topic 300
print("=" * 60)
print("CHECKING TOPIC 300 SPECIFICALLY")
print("=" * 60)

topic_300 = Topic.objects.filter(id=300).first()
if topic_300:
    print(f"\nTopic 300: {topic_300.title} ({topic_300.content_type})")
    progress_300 = TopicProgress.objects.filter(topic=topic_300)
    print(f"Progress records: {progress_300.count()}\n")
    
    for prog in progress_300:
        print(f"  User: {prog.user.username}")
        print(f"  Completed: {prog.completed}")
        print(f"  Method: {prog.completion_method}")
        print(f"  Manually completed: {prog.manually_completed}")
        print(f"  Created: {prog.first_accessed}")
        print(f"  Completed at: {prog.completed_at}")
        print(f"  Progress data: {prog.progress_data}")
        print()
        
        if prog.completed:
            reset = input(f"  Reset this to incomplete? (y/n): ")
            if reset.lower() == 'y':
                prog.completed = False
                prog.manually_completed = False
                prog.completed_at = None
                prog.save()
                print(f"  ✓ Reset to incomplete")
else:
    print("\nTopic 300 not found")

print("\n✓ Done!")

