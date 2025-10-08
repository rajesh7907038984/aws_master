#!/usr/bin/env python
"""
Check if learner1_branch1_test's score for topic 34 was saved
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress, Topic
from django.contrib.auth import get_user_model

User = get_user_model()

def check_score():
    print("=" * 80)
    print("CHECKING LEARNER1_BRANCH1_TEST SCORE FOR TOPIC 34")
    print("=" * 80)
    
    # Get the user
    try:
        user = User.objects.get(username='learner1_branch1_test')
        print(f"\n✅ Found user: {user.username} (ID: {user.id})")
    except User.DoesNotExist:
        print("\n❌ User 'learner1_branch1_test' not found")
        return
    
    # Get topic 34
    try:
        topic = Topic.objects.get(id=34)
        print(f"✅ Found topic: {topic.title} (ID: {topic.id})")
    except Topic.DoesNotExist:
        print("\n❌ Topic 34 not found")
        return
    
    # Check for SCORM package
    try:
        scorm_package = topic.scorm_package
        print(f"✅ Found SCORM package: {scorm_package.title}")
    except:
        print("\n❌ No SCORM package linked to topic 34")
        return
    
    # Get all attempts for this user and SCORM package
    attempts = ScormAttempt.objects.filter(
        user=user,
        scorm_package=scorm_package
    ).order_by('-last_accessed')
    
    print(f"\n📊 Found {attempts.count()} SCORM attempts")
    print("-" * 80)
    
    for attempt in attempts:
        print(f"\n  Attempt ID: {attempt.id}")
        print(f"  Last Accessed: {attempt.last_accessed}")
        print(f"  Lesson Status: {attempt.lesson_status}")
        print(f"  Score Raw: {attempt.score_raw}")
        print(f"  Score Max: {attempt.score_max}")
        print(f"  CMI score: {attempt.cmi_data.get('cmi.core.score.raw') or attempt.cmi_data.get('cmi.score.raw', 'NOT SET')}")
        
        if attempt.score_raw:
            percentage = (float(attempt.score_raw) / float(attempt.score_max or 100)) * 100
            print(f"  Percentage: {percentage:.1f}%")
    
    # Check TopicProgress
    print("\n" + "=" * 80)
    print("TOPIC PROGRESS CHECK")
    print("=" * 80)
    
    topic_progress = TopicProgress.objects.filter(
        user=user,
        topic=topic
    ).first()
    
    if topic_progress:
        print(f"\n✅ TopicProgress exists")
        print(f"  Last Score: {topic_progress.last_score}")
        print(f"  Best Score: {topic_progress.best_score}")
        print(f"  Completed: {topic_progress.completed}")
        print(f"  Last Accessed: {topic_progress.last_accessed}")
        
        # Check progress_data
        if topic_progress.progress_data:
            print(f"  Progress Data score_raw: {topic_progress.progress_data.get('score_raw', 'NOT SET')}")
    else:
        print("\n❌ No TopicProgress record found")
    
    # Check if it would appear in gradebook
    print("\n" + "=" * 80)
    print("GRADEBOOK VISIBILITY")
    print("=" * 80)
    
    # Get course
    course_topic = topic.coursetopic_set.first()
    if course_topic:
        course = course_topic.course
        print(f"\n✅ Course: {course.title} (ID: {course.id})")
        print(f"   Gradebook URL: https://staging.nexsy.io/gradebook/course/{course.id}/")
        
        if attempts.exists():
            latest_attempt = attempts.first()
            if latest_attempt.score_raw:
                print(f"\n✅ Score SHOULD appear in gradebook: {latest_attempt.score_raw}")
            else:
                print(f"\n⚠️  Score NOT saved - will NOT appear in gradebook")
        else:
            print(f"\n⚠️  No attempts found - will NOT appear in gradebook")
    else:
        print("\n❌ Topic not linked to any course")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check_score()

