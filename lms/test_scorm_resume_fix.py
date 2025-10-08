#!/usr/bin/env python
"""
Test SCORM Resume Fix
Verifies that the resume functionality is working correctly after the fix
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from courses.models import Topic
from django.contrib.auth import get_user_model

User = get_user_model()

def test_resume_functionality():
    print("="*80)
    print("SCORM RESUME FIX - VERIFICATION TEST")
    print("="*80)
    
    # Test with topic 34
    topic_id = 34
    topic = Topic.objects.filter(id=topic_id).first()
    
    if not topic:
        print(f"\n❌ Topic {topic_id} not found")
        return False
    
    print(f"\n✅ Topic Found: {topic.title} (ID: {topic.id})")
    
    # Get SCORM package
    try:
        sp = topic.scorm_package
        print(f"✅ SCORM Package: {sp.title} (Version: {sp.version})")
    except:
        print(f"❌ No SCORM package found")
        return False
    
    # Get recent attempts with resume data
    attempts_with_resume = ScormAttempt.objects.filter(
        scorm_package=sp,
        lesson_status__in=['not_attempted', 'incomplete']
    ).exclude(
        lesson_location='', suspend_data=''
    ).order_by('-last_accessed')[:5]
    
    if not attempts_with_resume.exists():
        print(f"\n⚠️  No incomplete attempts with resume data found")
        print(f"   This is expected if all users completed their attempts")
        print(f"   To test resume functionality:")
        print(f"   1. Have a learner start the SCORM content")
        print(f"   2. Answer some questions (e.g., 10-20 questions)")
        print(f"   3. Click 'Exit Assessment' button")
        print(f"   4. Return to the SCORM content")
        print(f"   5. Verify it resumes from where they left off")
        return True
    
    print(f"\n📊 Found {attempts_with_resume.count()} attempts with resume data:")
    print("="*80)
    
    all_valid = True
    
    for i, attempt in enumerate(attempts_with_resume, 1):
        print(f"\n{i}. User: {attempt.user.username}")
        print(f"   Attempt ID: {attempt.id}")
        print(f"   Status: {attempt.lesson_status}")
        print(f"   Entry Mode: {attempt.entry}")
        
        # Check if entry mode should be 'resume'
        has_bookmark = bool(attempt.lesson_location or attempt.suspend_data)
        should_be_resume = has_bookmark and attempt.lesson_status not in ['completed', 'passed']
        
        if should_be_resume and attempt.entry != 'resume':
            print(f"   ❌ ISSUE: Has bookmark data but entry mode is '{attempt.entry}' (should be 'resume')")
            all_valid = False
        else:
            print(f"   ✅ Entry mode is correct")
        
        # Check bookmark data
        if attempt.lesson_location:
            print(f"   ✅ Lesson Location: '{attempt.lesson_location[:80]}...'")
        else:
            print(f"   ⚠️  No lesson_location (but has suspend_data)")
        
        if attempt.suspend_data:
            print(f"   ✅ Suspend Data: {len(attempt.suspend_data)} chars")
        else:
            print(f"   ⚠️  No suspend_data")
        
        # Check CMI data consistency
        if sp.version == '1.2':
            cmi_location = attempt.cmi_data.get('cmi.core.lesson_location', '')
            cmi_suspend = attempt.cmi_data.get('cmi.suspend_data', '')
            cmi_entry = attempt.cmi_data.get('cmi.core.entry', '')
        else:
            cmi_location = attempt.cmi_data.get('cmi.location', '')
            cmi_suspend = attempt.cmi_data.get('cmi.suspend_data', '')
            cmi_entry = attempt.cmi_data.get('cmi.entry', '')
        
        # Verify CMI data matches DB fields
        if attempt.lesson_location and attempt.lesson_location != cmi_location:
            print(f"   ❌ CMI location mismatch!")
            print(f"      DB: '{attempt.lesson_location[:50]}'")
            print(f"      CMI: '{cmi_location[:50]}'")
            all_valid = False
        else:
            print(f"   ✅ CMI location matches DB")
        
        if attempt.suspend_data and attempt.suspend_data != cmi_suspend:
            print(f"   ❌ CMI suspend_data mismatch!")
            all_valid = False
        else:
            print(f"   ✅ CMI suspend_data matches DB")
    
    print("\n" + "="*80)
    
    if all_valid:
        print("✅ ALL CHECKS PASSED - Resume data is consistent")
        print("\n📋 Next Steps:")
        print("1. Test in browser: Have a learner access the SCORM content")
        print("2. Check browser console logs for '[SCORM API] ... -> NO CACHE (resume-critical)'")
        print("3. Verify the content resumes from the bookmarked location")
        print("4. Check server logs for '🔖 RESUME: Returning lesson_location' messages")
        return True
    else:
        print("❌ SOME CHECKS FAILED - Review the issues above")
        print("\n💡 Fixes Applied:")
        print("- Frontend: Disabled caching for resume-critical elements")
        print("- Backend: Added explicit logging for resume data")
        print("\n📋 To fix entry mode issues:")
        print("- Have users re-access the SCORM content")
        print("- The entry mode will be updated during initialization")
        return False

if __name__ == '__main__':
    test_resume_functionality()

