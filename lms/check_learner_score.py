#!/usr/bin/env python
"""
Script to check SCORM scores for learner1_branch1_test
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.contrib.auth import get_user_model
from scorm.models import ScormAttempt, ScormPackage
from courses.models import TopicProgress

User = get_user_model()

# Find the user
username = 'learner1_branch1_test'
print(f"\n{'='*80}")
print(f"Checking SCORM data for user: {username}")
print(f"{'='*80}\n")

try:
    user = User.objects.filter(username=username).first()
    
    if not user:
        print(f"❌ User '{username}' not found in the database!")
        sys.exit(1)
    
    print(f"✅ User found: {user.username} (ID: {user.id})")
    print(f"   Name: {user.get_full_name()}")
    print(f"   Email: {user.email}\n")
    
    # Get all SCORM attempts for this user
    attempts = ScormAttempt.objects.filter(user=user).select_related('scorm_package__topic').order_by('-last_accessed')
    
    print(f"📊 Total SCORM attempts: {attempts.count()}\n")
    
    if attempts.count() == 0:
        print("⚠️  No SCORM attempts found for this user!")
        sys.exit(0)
    
    # Check for the specific SCORM topic with ID 168
    scorm_168_attempts = attempts.filter(scorm_package__topic__id=168)
    
    print(f"{'='*80}")
    print(f"Checking SCORM Topic ID 168 (https://staging.nexsy.io/scorm/view/168/)")
    print(f"{'='*80}\n")
    
    if scorm_168_attempts.exists():
        print(f"✅ Found {scorm_168_attempts.count()} attempt(s) for SCORM Topic ID 168\n")
        
        for attempt in scorm_168_attempts:
            print(f"{'─'*80}")
            print(f"Attempt #{attempt.attempt_number} (ID: {attempt.id})")
            print(f"{'─'*80}")
            print(f"Topic: {attempt.scorm_package.topic.title}")
            print(f"Package Version: {attempt.scorm_package.version}")
            print(f"Lesson Status: {attempt.lesson_status}")
            print(f"Completion Status: {attempt.completion_status}")
            print(f"Success Status: {attempt.success_status}")
            print(f"\n📈 SCORE INFORMATION:")
            print(f"   Score Raw: {attempt.score_raw}")
            print(f"   Score Min: {attempt.score_min}")
            print(f"   Score Max: {attempt.score_max}")
            print(f"   Score Scaled: {attempt.score_scaled}")
            print(f"   Progress %: {attempt.progress_percentage}")
            print(f"\n⏱️  TIME TRACKING:")
            print(f"   Total Time: {attempt.total_time}")
            print(f"   Session Time: {attempt.session_time}")
            print(f"   Time Spent (seconds): {attempt.time_spent_seconds}")
            print(f"\n📅 TIMESTAMPS:")
            print(f"   Started: {attempt.started_at}")
            print(f"   Last Accessed: {attempt.last_accessed}")
            print(f"   Completed: {attempt.completed_at}")
            print(f"\n📍 BOOKMARK DATA:")
            print(f"   Lesson Location: {attempt.lesson_location}")
            print(f"   Last Visited Slide: {attempt.last_visited_slide}")
            print(f"   Suspend Data (first 100 chars): {attempt.suspend_data[:100] if attempt.suspend_data else 'None'}...")
            
            # Check CMI data for scores
            if attempt.cmi_data:
                print(f"\n🔍 CMI DATA INSPECTION:")
                score_keys = [k for k in attempt.cmi_data.keys() if 'score' in k.lower()]
                if score_keys:
                    print(f"   Score-related keys found:")
                    for key in score_keys:
                        print(f"      {key}: {attempt.cmi_data[key]}")
                else:
                    print(f"   ⚠️  No score-related keys found in CMI data")
                    print(f"   CMI data keys: {list(attempt.cmi_data.keys())[:10]}")
            
            # Check TopicProgress
            topic_progress = TopicProgress.objects.filter(
                user=user,
                topic=attempt.scorm_package.topic
            ).first()
            
            if topic_progress:
                print(f"\n📊 TOPIC PROGRESS (Backend):")
                print(f"   Last Score: {topic_progress.last_score}")
                print(f"   Best Score: {topic_progress.best_score}")
                print(f"   Completed: {topic_progress.completed}")
                print(f"   Attempts: {topic_progress.attempts}")
                print(f"   Last Accessed: {topic_progress.last_accessed}")
                
                # Compare scores
                if attempt.score_raw != topic_progress.last_score:
                    print(f"\n⚠️  SCORE MISMATCH DETECTED!")
                    print(f"   ScormAttempt.score_raw: {attempt.score_raw}")
                    print(f"   TopicProgress.last_score: {topic_progress.last_score}")
                    print(f"\n   This indicates the score was NOT properly saved to the backend!")
                else:
                    print(f"\n✅ Scores match - data is synchronized correctly")
            else:
                print(f"\n❌ NO TOPIC PROGRESS FOUND!")
                print(f"   This means the score was never saved to the backend TopicProgress table!")
            
            print(f"\n")
    else:
        print(f"❌ No attempts found for SCORM Topic ID 168")
        print(f"\nShowing all SCORM attempts for this user:\n")
        
        for attempt in attempts:
            print(f"Attempt ID: {attempt.id}")
            print(f"  Topic ID: {attempt.scorm_package.topic.id}")
            print(f"  Topic: {attempt.scorm_package.topic.title}")
            print(f"  Score: {attempt.score_raw}")
            print(f"  Status: {attempt.lesson_status}")
            print(f"  Last Accessed: {attempt.last_accessed}")
            print()

except Exception as e:
    print(f"\n❌ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"{'='*80}")
print("Database check completed!")
print(f"{'='*80}\n")

