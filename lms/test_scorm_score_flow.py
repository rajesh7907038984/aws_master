#!/usr/bin/env python
"""
Test script to verify SCORM score flow from API to Gradebook
This simulates what happens when a learner completes SCORM content with a score
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from decimal import Decimal
from scorm.models import ScormAttempt, ScormPackage
from scorm.api_handler_enhanced import ScormAPIHandlerEnhanced
from courses.models import TopicProgress, Topic
from django.contrib.auth import get_user_model

User = get_user_model()

def test_score_flow():
    """Test the complete flow of SCORM score from content to gradebook"""
    
    print("=" * 80)
    print("SCORM SCORE FLOW TEST")
    print("=" * 80)
    
    # Get a test attempt (most recent one)
    attempt = ScormAttempt.objects.order_by('-last_accessed').first()
    
    if not attempt:
        print("❌ No SCORM attempts found in database")
        return False
    
    print(f"\n📊 Testing with Attempt ID: {attempt.id}")
    print(f"   User: {attempt.user.username}")
    print(f"   Topic: {attempt.scorm_package.topic.title}")
    print(f"   Current Score: {attempt.score_raw}")
    
    # Create API handler
    handler = ScormAPIHandlerEnhanced(attempt)
    
    # Initialize
    print("\n🔄 Step 1: Initialize SCORM API")
    result = handler.initialize()
    print(f"   Result: {result}")
    
    if result != 'true':
        print("   ❌ Failed to initialize")
        return False
    print("   ✅ Initialized successfully")
    
    # Set a test score
    test_score = "85.5"
    print(f"\n🔄 Step 2: Set Score to {test_score}")
    
    # Determine the correct CMI element based on version
    if handler.version == '1.2':
        score_element = 'cmi.core.score.raw'
    else:
        score_element = 'cmi.score.raw'
    
    result = handler.set_value(score_element, test_score)
    print(f"   SetValue({score_element}, {test_score}) = {result}")
    
    if result != 'true':
        print("   ❌ Failed to set score")
        return False
    print("   ✅ Score set successfully")
    
    # Verify score is in attempt object
    attempt.refresh_from_db()
    print(f"   Attempt.score_raw (after SetValue): {attempt.score_raw}")
    print(f"   CMI Data score: {attempt.cmi_data.get(score_element, 'NOT SET')}")
    
    # Set lesson status to completed
    print(f"\n🔄 Step 3: Set Lesson Status to 'completed'")
    if handler.version == '1.2':
        status_element = 'cmi.core.lesson_status'
    else:
        status_element = 'cmi.completion_status'
    
    result = handler.set_value(status_element, 'completed')
    print(f"   SetValue({status_element}, completed) = {result}")
    
    if result != 'true':
        print("   ❌ Failed to set status")
        return False
    print("   ✅ Status set successfully")
    
    # Commit the data
    print(f"\n🔄 Step 4: Commit Data")
    result = handler.commit()
    print(f"   Commit() = {result}")
    
    if result != 'true':
        print("   ❌ Failed to commit")
        return False
    print("   ✅ Committed successfully")
    
    # Verify data is saved
    print(f"\n🔄 Step 5: Verify Data Persistence")
    attempt.refresh_from_db()
    print(f"   ScormAttempt.score_raw: {attempt.score_raw}")
    print(f"   ScormAttempt.lesson_status: {attempt.lesson_status}")
    
    if attempt.score_raw is None or float(attempt.score_raw) != float(test_score):
        print(f"   ❌ Score not saved correctly! Expected {test_score}, got {attempt.score_raw}")
        return False
    print(f"   ✅ Score saved correctly in ScormAttempt")
    
    # Check TopicProgress
    print(f"\n🔄 Step 6: Verify TopicProgress Update")
    topic = attempt.scorm_package.topic
    topic_progress = TopicProgress.objects.filter(
        user=attempt.user,
        topic=topic
    ).first()
    
    if not topic_progress:
        print("   ❌ TopicProgress record not found!")
        return False
    
    print(f"   TopicProgress.last_score: {topic_progress.last_score}")
    print(f"   TopicProgress.best_score: {topic_progress.best_score}")
    print(f"   TopicProgress.completed: {topic_progress.completed}")
    
    if topic_progress.last_score is None or float(topic_progress.last_score) != float(test_score):
        print(f"   ❌ Score not synced to TopicProgress! Expected {test_score}, got {topic_progress.last_score}")
        return False
    print(f"   ✅ Score synced correctly to TopicProgress")
    
    # Terminate
    print(f"\n🔄 Step 7: Terminate SCORM Session")
    result = handler.terminate()
    print(f"   Terminate() = {result}")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    print("=" * 80)
    print("\n📊 Summary:")
    print(f"   - Score was set to: {test_score}")
    print(f"   - ScormAttempt.score_raw: {attempt.score_raw}")
    print(f"   - TopicProgress.last_score: {topic_progress.last_score}")
    print(f"   - Data is properly synchronized!")
    print("\n🎯 The score should now appear in the gradebook at:")
    print(f"   https://staging.nexsy.io/gradebook/course/{attempt.scorm_package.topic.coursetopic_set.first().course.id}/")
    
    return True

if __name__ == '__main__':
    try:
        success = test_score_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

