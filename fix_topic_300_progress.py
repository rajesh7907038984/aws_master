#!/usr/bin/env python
"""
Script to fix incorrectly completed topic progress for topic 300
Run this to reset the green tick issue
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_main.settings')
django.setup()

from courses.models import Topic, TopicProgress

# Find topic 300
topic = Topic.objects.filter(id=300).first()

if topic:
    print(f"Found topic: {topic.title} (ID: {topic.id})")
    print(f"Content type: {topic.content_type}")
    
    # Find all progress records for this topic
    progress_records = TopicProgress.objects.filter(topic=topic)
    print(f"\nFound {progress_records.count()} progress record(s):")
    
    for progress in progress_records:
        print(f"  - User: {progress.user.username}")
        print(f"    Completed: {progress.completed}")
        print(f"    Completion method: {progress.completion_method}")
        print(f"    Created: {progress.first_accessed}")
        print(f"    Completed at: {progress.completed_at}")
        
        # Ask to delete
        delete = input(f"\n  Delete this progress record? (y/n): ")
        if delete.lower() == 'y':
            progress.delete()
            print(f"  ✓ Deleted progress for user {progress.user.username}")
        else:
            print(f"  Skipped")
    
    print("\n✓ Done!")
else:
    print("Topic 300 not found")

