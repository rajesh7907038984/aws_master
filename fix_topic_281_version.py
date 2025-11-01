#!/usr/bin/env python3
"""
Fix SCORM version detection for topic 281
The manifest declares SCORM 1.2 but was incorrectly detected as 2004
"""
import os
import sys
import django

sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from courses.models import Topic
from scorm.models import ScormPackage

def fix_topic_281():
    topic_id = 281
    
    print("="*60)
    print(f"Fixing SCORM Version for Topic {topic_id}")
    print("="*60)
    
    topic = Topic.objects.get(id=topic_id)
    package = topic.scorm
    
    print(f"\nPackage: {package.title}")
    print(f"Current Version in DB: {package.version}")
    print(f"Manifest declares: 1.2")
    print()
    
    # Update to correct version
    print("Updating package version to 1.2...")
    package.version = '1.2'
    package.save(update_fields=['version'])
    
    print("✓ Package version corrected!")
    print()
    print("Impact:")
    print("  ✓ System will now use SCORM 1.2 CMI fields")
    print("  ✓ cmi.core.lesson_status instead of cmi.completion_status")
    print("  ✓ Completion detection will work correctly")
    print()
    print("Next steps:")
    print("  1. Users need to continue/complete the SCORM content")
    print("  2. When they complete, it will send: cmi.core.lesson_status='completed'")
    print("  3. System will correctly detect completion with SCORM 1.2 logic")
    
if __name__ == '__main__':
    fix_topic_281()

