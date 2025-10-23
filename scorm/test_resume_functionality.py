#!/usr/bin/env python
"""
Test SCORM Resume Functionality
Comprehensive test to verify resume functionality works across different package types
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from scorm.enhanced_resume_handler import handle_scorm_resume
from courses.templatetags.course_filters import has_scorm_resume
from courses.models import Topic
from django.contrib.auth import get_user_model

User = get_user_model()


def test_resume_functionality():
    """Test resume functionality across different SCORM package types"""
    print("🧪 SCORM Resume Functionality Test")
    print("=" * 50)
    
    # Test 1: Check all SCORM packages
    packages = ScormPackage.objects.all()
    print(f"📦 Found {packages.count()} SCORM packages")
    
    for package in packages:
        print(f"\n📦 Package {package.id}: {package.title} (Version: {package.version})")
        print(f"   Topic ID: {package.topic.id}")
        print(f"   Launch URL: {package.launch_url}")
        
        # Test attempts for this package
        attempts = ScormAttempt.objects.filter(scorm_package=package)
        print(f"   Attempts: {attempts.count()}")
        
        for attempt in attempts:
            print(f"     Attempt {attempt.id}: User {attempt.user.username}")
            print(f"       Status: {attempt.lesson_status}")
            print(f"       Entry: {attempt.entry}")
            print(f"       Location: {attempt.lesson_location or 'None'}")
            print(f"       Suspend Data: {len(attempt.suspend_data) if attempt.suspend_data else 0} chars")
            
            # Test resume functionality
            can_resume = attempt.lesson_status in ['incomplete', 'not_attempted']
            has_proper_entry = attempt.entry == 'resume'
            has_cmi_entry = (
                attempt.cmi_data and 
                (
                    (package.version == '1.2' and 'cmi.core.entry' in attempt.cmi_data) or
                    (package.version == '2004' and 'cmi.entry' in attempt.cmi_data)
                )
            )
            
            print(f"       Can Resume: {can_resume}")
            print(f"       Has Proper Entry: {has_proper_entry}")
            print(f"       Has CMI Entry: {has_cmi_entry}")
            
            # Test template filter
            try:
                should_show_resume = has_scorm_resume(package.topic, attempt.user)
                print(f"       Should Show Resume Button: {should_show_resume}")
            except Exception as e:
                print(f"       Template Filter Error: {str(e)}")
            
            # Test enhanced resume handler
            try:
                handler_result = handle_scorm_resume(attempt)
                print(f"       Enhanced Handler Result: {handler_result}")
            except Exception as e:
                print(f"       Enhanced Handler Error: {str(e)}")
            
            print()
    
    # Test 2: Test specific problematic package (ID 21, Topic 34)
    print("\n🎯 Testing Specific Problematic Package")
    print("-" * 40)
    
    try:
        package_21 = ScormPackage.objects.get(id=21)
        topic_34 = Topic.objects.get(id=34)
        user_joe = User.objects.get(username='Joe')
        
        print(f"Package: {package_21.title} (Version: {package_21.version})")
        print(f"Topic: {topic_34.title}")
        print(f"User: {user_joe.username}")
        
        # Test template filter
        should_show_resume = has_scorm_resume(topic_34, user_joe)
        print(f"Should show resume button: {should_show_resume}")
        
        # Test attempt
        attempt = ScormAttempt.objects.filter(
            scorm_package=package_21,
            user=user_joe
        ).first()
        
        if attempt:
            print(f"Attempt ID: {attempt.id}")
            print(f"Entry: {attempt.entry}")
            print(f"CMI Entry: {attempt.cmi_data.get('cmi.core.entry', 'Not set') if attempt.cmi_data else 'No CMI data'}")
            print(f"Lesson Status: {attempt.lesson_status}")
            
            # Test enhanced resume handler
            handler_result = handle_scorm_resume(attempt)
            print(f"Enhanced Handler Result: {handler_result}")
        else:
            print("No attempt found")
            
    except Exception as e:
        print(f"Error testing specific package: {str(e)}")
    
    print("\n✅ Resume Functionality Test Complete")


if __name__ == '__main__':
    test_resume_functionality()
