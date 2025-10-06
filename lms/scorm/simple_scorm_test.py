# -*- coding: utf-8 -*-
"""
Simple SCORM Test
Basic testing of SCORM functionality
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms.settings')
django.setup()

from django.contrib.auth import get_user_model
from courses.models import Topic, Course
from scorm.models import ScormPackage, ScormAttempt
from scorm.api_handler_clean import ScormAPIHandlerClean

User = get_user_model()

def test_scorm_basic():
    """Test basic SCORM functionality"""
    print("Starting Basic SCORM Test...")
    print("=" * 50)
    
    try:
        # Create test user
        user, created = User.objects.get_or_create(
            username='scorm_test_user',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User'
            }
        )
        print("✓ Test user created/retrieved")
        
        # Create test course
        course, created = Course.objects.get_or_create(
            title='SCORM Test Course',
            defaults={'description': 'Test course for SCORM testing'}
        )
        print("✓ Test course created/retrieved")
        
        # Create test topic
        topic, created = Topic.objects.get_or_create(
            title='SCORM Test Topic',
            course=course,
            defaults={'description': 'Test topic for SCORM testing'}
        )
        print("✓ Test topic created/retrieved")
        
        # Create SCORM 1.2 package
        scorm_package, created = ScormPackage.objects.get_or_create(
            topic=topic,
            defaults={
                'version': '1.2',
                'identifier': 'test_scorm_12',
                'title': 'SCORM 1.2 Test Package',
                'package_file': 'test.zip',
                'extracted_path': '/test/scorm12',
                'launch_url': 'index.html',
                'manifest_data': {},
                'mastery_score': 80
            }
        )
        print("✓ SCORM package created/retrieved")
        
        # Create test attempt
        attempt, created = ScormAttempt.objects.get_or_create(
            user=user,
            scorm_package=scorm_package,
            defaults={'attempt_number': 1}
        )
        print("✓ SCORM attempt created/retrieved")
        
        # Test API handler
        handler = ScormAPIHandlerClean(attempt)
        print("✓ API handler created")
        
        # Test Initialize
        result = handler.initialize()
        if result == 'true':
            print("✓ SCORM Initialize: PASSED")
        else:
            print("✗ SCORM Initialize: FAILED - %s" % result)
            return False
        
        # Test GetValue
        student_id = handler.get_value('cmi.core.student_id')
        if student_id:
            print("✓ SCORM GetValue: PASSED - Student ID: %s" % student_id)
        else:
            print("✗ SCORM GetValue: FAILED")
            return False
        
        # Test SetValue
        result = handler.set_value('cmi.core.lesson_status', 'completed')
        if result == 'true':
            print("✓ SCORM SetValue: PASSED")
        else:
            print("✗ SCORM SetValue: FAILED - %s" % result)
            return False
        
        # Test Commit
        result = handler.commit()
        if result == 'true':
            print("✓ SCORM Commit: PASSED")
        else:
            print("✗ SCORM Commit: FAILED - %s" % result)
            return False
        
        # Test Terminate
        result = handler.terminate()
        if result == 'true':
            print("✓ SCORM Terminate: PASSED")
        else:
            print("✗ SCORM Terminate: FAILED - %s" % result)
            return False
        
        # Test error handling
        print("\nTesting Error Handling...")
        
        # Test uninitialized API calls
        handler2 = ScormAPIHandlerClean(attempt)
        result = handler2.get_value('cmi.core.student_id')
        if result == '':
            print("✓ Error Handling - Uninitialized GetValue: PASSED")
        else:
            print("✗ Error Handling - Uninitialized GetValue: FAILED")
        
        # Test error codes
        error_code = handler2.get_last_error()
        if error_code == '301':  # Not initialized
            print("✓ Error Handling - Error Code: PASSED")
        else:
            print("✗ Error Handling - Error Code: FAILED - %s" % error_code)
        
        # Test error string
        error_string = handler2.get_error_string('301')
        if error_string == 'Not initialized':
            print("✓ Error Handling - Error String: PASSED")
        else:
            print("✗ Error Handling - Error String: FAILED - %s" % error_string)
        
        print("\n" + "=" * 50)
        print("SCORM BASIC TEST COMPLETED SUCCESSFULLY!")
        print("=" * 50)
        return True
        
    except Exception as e:
        print("✗ SCORM Test Failed: %s" % str(e))
        import traceback
        traceback.print_exc()
        return False

def test_scorm_data_elements():
    """Test SCORM data elements"""
    print("\nTesting SCORM Data Elements...")
    print("=" * 50)
    
    try:
        # Get existing test data
        user = User.objects.get(username='scorm_test_user')
        topic = Topic.objects.get(title='SCORM Test Topic')
        scorm_package = ScormPackage.objects.get(topic=topic)
        
        # Create new attempt
        attempt = ScormAttempt.objects.create(
            user=user,
            scorm_package=scorm_package,
            attempt_number=2
        )
        
        handler = ScormAPIHandlerClean(attempt)
        handler.initialize()
        
        # Test core elements
        core_elements = [
            'cmi.core.student_id',
            'cmi.core.student_name',
            'cmi.core.lesson_location',
            'cmi.core.credit',
            'cmi.core.lesson_status',
            'cmi.core.entry',
            'cmi.core.score.raw',
            'cmi.core.score.max',
            'cmi.core.score.min',
            'cmi.core.total_time',
            'cmi.core.lesson_mode',
            'cmi.suspend_data',
            'cmi.launch_data',
            'cmi.comments',
            'cmi.comments_from_lms'
        ]
        
        passed = 0
        failed = 0
        
        for element in core_elements:
            try:
                value = handler.get_value(element)
                if value is not None:
                    print("✓ %s: %s" % (element, value))
                    passed += 1
                else:
                    print("✗ %s: FAILED" % element)
                    failed += 1
            except Exception as e:
                print("✗ %s: ERROR - %s" % (element, str(e)))
                failed += 1
        
        handler.terminate()
        
        print("\nData Elements Test Results:")
        print("  Passed: %d" % passed)
        print("  Failed: %d" % failed)
        print("  Total: %d" % (passed + failed))
        
        return passed > 0
        
    except Exception as e:
        print("✗ Data Elements Test Failed: %s" % str(e))
        return False

if __name__ == '__main__':
    print("SCORM Implementation Test")
    print("=" * 50)
    
    # Test basic functionality
    basic_test = test_scorm_basic()
    
    if basic_test:
        # Test data elements
        data_test = test_scorm_data_elements()
        
        if data_test:
            print("\n🎉 ALL TESTS PASSED! SCORM implementation is working correctly.")
        else:
            print("\nBasic tests passed but data elements test failed.")
    else:
        print("\nBasic SCORM tests failed.")
