#!/usr/bin/env python
"""
Check SCORM Resume Bug for Topic 34
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from courses.models import Topic, TopicProgress
from django.utils import timezone
from datetime import timedelta

def check_scorm_topic_34():
    print("="*80)
    print("SCORM RESUME BUG ANALYSIS - Topic 34")
    print("="*80)
    
    # Get topic
    topic = Topic.objects.filter(id=34).first()
    if not topic:
        print("❌ Topic 34 NOT FOUND")
        return
    
    print(f"\n✅ Topic Found:")
    print(f"   ID: {topic.id}")
    print(f"   Title: {topic.title}")
    
    # Get SCORM package
    try:
        sp = topic.scorm_package
        print(f"\n✅ SCORM Package:")
        print(f"   ID: {sp.id}")
        print(f"   Title: {sp.title}")
        print(f"   Version: {sp.version}")
        print(f"   Launch URL: {sp.launch_url}")
    except:
        print(f"\n❌ No SCORM Package found for topic 34")
        return
    
    # Get recent attempts
    attempts = ScormAttempt.objects.filter(
        scorm_package=sp
    ).select_related('user').order_by('-last_accessed')[:10]
    
    print(f"\n📊 Recent Attempts (last 10):")
    print("="*80)
    
    if not attempts:
        print("   No attempts found")
        return
    
    for i, a in enumerate(attempts, 1):
        print(f"\n{i}. User: {a.user.username} (ID: {a.user.id})")
        print(f"   Attempt Number: {a.attempt_number}")
        print(f"   Status: {a.lesson_status}")
        print(f"   Completion Status: {a.completion_status}")
        print(f"   Success Status: {a.success_status}")
        print(f"   Score: {a.score_raw}")
        print(f"   Entry Mode: {a.entry}")
        print(f"   Exit Mode: {a.exit_mode}")
        print(f"   Lesson Location: '{a.lesson_location}'")
        print(f"   Suspend Data Length: {len(a.suspend_data) if a.suspend_data else 0} chars")
        if a.suspend_data:
            print(f"   Suspend Data Preview: {a.suspend_data[:100]}...")
        print(f"   Started: {a.started_at}")
        print(f"   Last Accessed: {a.last_accessed}")
        print(f"   Completed: {a.completed_at}")
        
        # Check CMI data
        if a.cmi_data:
            print(f"   CMI Data Keys: {len(a.cmi_data.keys())} keys")
            # Check for resume-related data in CMI
            if sp.version == '1.2':
                location_key = 'cmi.core.lesson_location'
                suspend_key = 'cmi.suspend_data'
                entry_key = 'cmi.core.entry'
            else:
                location_key = 'cmi.location'
                suspend_key = 'cmi.suspend_data'
                entry_key = 'cmi.entry'
            
            cmi_location = a.cmi_data.get(location_key, '')
            cmi_suspend = a.cmi_data.get(suspend_key, '')
            cmi_entry = a.cmi_data.get(entry_key, '')
            
            print(f"   CMI Entry: '{cmi_entry}'")
            print(f"   CMI Location: '{cmi_location}'")
            print(f"   CMI Suspend Length: {len(cmi_suspend) if cmi_suspend else 0}")
        else:
            print(f"   ⚠️  No CMI Data stored")
        
        # Check TopicProgress
        try:
            tp = TopicProgress.objects.filter(user=a.user, topic=topic).first()
            if tp:
                print(f"   TopicProgress: completed={tp.completed}, last_score={tp.last_score}")
            else:
                print(f"   ⚠️  No TopicProgress found")
        except Exception as e:
            print(f"   ⚠️  Error checking TopicProgress: {e}")
    
    # Analyze the issue
    print(f"\n\n🔍 ANALYSIS:")
    print("="*80)
    
    # Check if there are incomplete attempts with suspend data
    incomplete_with_suspend = [a for a in attempts if a.lesson_status not in ['completed', 'passed'] and a.suspend_data]
    
    if incomplete_with_suspend:
        print(f"\n✅ Found {len(incomplete_with_suspend)} incomplete attempts WITH suspend data")
        print("   This means learners have been exiting mid-session and bookmark data IS being saved.")
        
        for a in incomplete_with_suspend[:3]:
            print(f"\n   User: {a.user.username}")
            print(f"   - Entry mode: {a.entry}")
            print(f"   - Location: {a.lesson_location}")
            print(f"   - Suspend data: {len(a.suspend_data)} chars")
            
            # Check if CMI data has resume data
            if sp.version == '1.2':
                cmi_location = a.cmi_data.get('cmi.core.lesson_location', '')
                cmi_suspend = a.cmi_data.get('cmi.suspend_data', '')
            else:
                cmi_location = a.cmi_data.get('cmi.location', '')
                cmi_suspend = a.cmi_data.get('cmi.suspend_data', '')
            
            if a.lesson_location and not cmi_location:
                print(f"   ⚠️  ISSUE: lesson_location in DB but NOT in CMI data!")
            if a.suspend_data and not cmi_suspend:
                print(f"   ⚠️  ISSUE: suspend_data in DB but NOT in CMI data!")
    else:
        print("\n⚠️  No incomplete attempts with suspend data found")
        print("   Possible reasons:")
        print("   1. Learners haven't exited mid-session recently")
        print("   2. Suspend data is not being saved properly")
        print("   3. All attempts are complete")
    
    # Check most recent attempt for detailed analysis
    if attempts:
        recent = attempts[0]
        print(f"\n\n📋 MOST RECENT ATTEMPT DETAILED CHECK:")
        print("="*80)
        print(f"User: {recent.user.username}")
        print(f"Last accessed: {recent.last_accessed}")
        
        has_resume_data = bool(recent.lesson_location or recent.suspend_data)
        print(f"\nHas Resume Data in DB: {has_resume_data}")
        
        if has_resume_data:
            print(f"  ✅ Lesson Location: '{recent.lesson_location}'")
            print(f"  ✅ Suspend Data: {len(recent.suspend_data)} chars")
            
            # Check if it will be loaded on next access
            if recent.lesson_status not in ['completed', 'passed']:
                print(f"\n✅ Status is '{recent.lesson_status}' - should resume on next access")
                
                # Check CMI data
                if sp.version == '1.2':
                    cmi_loc = recent.cmi_data.get('cmi.core.lesson_location', '')
                    cmi_susp = recent.cmi_data.get('cmi.suspend_data', '')
                else:
                    cmi_loc = recent.cmi_data.get('cmi.location', '')
                    cmi_susp = recent.cmi_data.get('cmi.suspend_data', '')
                
                if recent.lesson_location != cmi_loc:
                    print(f"  ⚠️  MISMATCH: DB location '{recent.lesson_location}' != CMI location '{cmi_loc}'")
                else:
                    print(f"  ✅ CMI location matches DB")
                
                if recent.suspend_data != cmi_susp:
                    print(f"  ⚠️  MISMATCH: DB suspend data != CMI suspend data")
                else:
                    print(f"  ✅ CMI suspend data matches DB")
            else:
                print(f"\n✅ Status is '{recent.lesson_status}' - new attempt will be created")
        else:
            print(f"  ⚠️  No resume data in database")

if __name__ == '__main__':
    check_scorm_topic_34()

