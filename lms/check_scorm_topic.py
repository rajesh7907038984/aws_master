#!/usr/bin/env python
"""Check if topic 24 has a SCORM package"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from courses.models import Topic
from scorm.models import ScormPackage

# Check topic 28
topic_id = 28
topic = Topic.objects.filter(id=topic_id).first()

print(f"\n{'='*60}")
print(f"SCORM Topic Diagnostic for Topic ID: {topic_id}")
print(f"{'='*60}\n")

if not topic:
    print(f"❌ Topic {topic_id} does NOT exist in the database")
    print("\nAvailable topics with SCORM packages:")
    scorm_topics = Topic.objects.filter(scorm_package__isnull=False).values_list('id', 'title')
    for tid, title in scorm_topics[:10]:
        print(f"  - Topic {tid}: {title}")
else:
    print(f"✅ Topic {topic_id} exists")
    print(f"   Title: {topic.title}")
    print(f"   Description: {topic.description[:100] if topic.description else 'N/A'}...")
    
    # Check for SCORM package
    try:
        scorm_pkg = topic.scorm_package
        print(f"\n✅ Topic HAS a SCORM package linked")
        print(f"   SCORM ID: {scorm_pkg.id}")
        print(f"   SCORM Title: {scorm_pkg.title}")
        print(f"   SCORM Version: {scorm_pkg.version}")
        print(f"   Launch URL: {scorm_pkg.launch_url}")
        print(f"   Extracted Path: {scorm_pkg.extracted_path}")
        print(f"   Package File: {scorm_pkg.package_file}")
        print(f"   Created: {scorm_pkg.created_at}")
        print(f"   Updated: {scorm_pkg.updated_at}")
        
        # Check user access
        print(f"\n📋 Checking access permissions...")
        print(f"   Topic has user_has_access method: {hasattr(topic, 'user_has_access')}")
        
        # Check if there are any attempts
        attempts_count = scorm_pkg.attempts.count()
        print(f"\n📊 Attempts: {attempts_count} total attempts")
        if attempts_count > 0:
            recent = scorm_pkg.attempts.order_by('-started_at')[:5]
            print(f"   Recent attempts:")
            for attempt in recent:
                print(f"     - User: {attempt.user.username}, Status: {attempt.lesson_status}, Started: {attempt.started_at}")
        
    except ScormPackage.DoesNotExist:
        print(f"\n❌ Topic does NOT have a SCORM package linked")
        print(f"   This is the problem! The topic needs a SCORM package to display content.")
        print(f"\n💡 Solution: Upload a SCORM package for this topic in the admin panel")
    except Exception as e:
        print(f"\n❌ Error accessing SCORM package: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}\n")
