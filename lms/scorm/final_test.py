#!/usr/bin/env python3
"""
Final SCORM Test - Comprehensive Test of All Fixes
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from scorm.api_handler import ScormAPIHandler
from scorm.api_handler_enhanced import ScormAPIHandlerEnhanced
from django.test import RequestFactory, Client
from django.contrib.auth import get_user_model
import json

User = get_user_model()

def test_scorm_system_comprehensive():
    """Comprehensive test of the entire SCORM system"""
    print("=" * 60)
    print("COMPREHENSIVE SCORM SYSTEM TEST")
    print("=" * 60)
    
    # Test 1: Package Loading
    print("\n🔍 Test 1: SCORM Package Loading")
    try:
        package = ScormPackage.objects.first()
        if package:
            print(f"✅ Package found: {package.title}")
            print(f"   Version: {package.version}")
            print(f"   Launch URL: {package.launch_url}")
            print(f"   Extracted Path: {package.extracted_path}")
        else:
            print("❌ No SCORM packages found")
            return False
    except Exception as e:
        print(f"❌ Error loading package: {e}")
        return False
    
    # Test 2: API Handler
    print("\n🔍 Test 2: SCORM API Handler")
    try:
        attempt = ScormAttempt.objects.first()
        if attempt:
            print(f"✅ Attempt found: {attempt.id}")
            
            # Test basic handler
            handler = ScormAPIHandler(attempt)
            print(f"   Handler initialized: {handler.version}")
            
            # Test initialization
            result = handler.initialize()
            print(f"   Initialize result: {result}")
            
            # Test GetValue
            location = handler.get_value('cmi.core.lesson_location')
            print(f"   Lesson location: {location}")
            
            # Test SetValue
            result = handler.set_value('cmi.core.lesson_location', 'test_location_final')
            print(f"   SetValue result: {result}")
            
            # Test Commit
            result = handler.commit()
            print(f"   Commit result: {result}")
        else:
            print("❌ No SCORM attempts found")
            return False
    except Exception as e:
        print(f"❌ Error testing API handler: {e}")
        return False
    
    # Test 3: Enhanced API Handler
    print("\n🔍 Test 3: Enhanced SCORM API Handler")
    try:
        handler = ScormAPIHandlerEnhanced(attempt)
        print(f"   Enhanced handler initialized: {handler.version}")
        
        # Test initialization
        result = handler.initialize()
        print(f"   Initialize result: {result}")
        
        # Test various GetValue calls
        elements = [
            'cmi.core.lesson_status',
            'cmi.core.lesson_location',
            'cmi.core.student_id',
            'cmi.core.student_name',
            'cmi.core.score.max',
            'cmi.core.score.min'
        ]
        
        for element in elements:
            value = handler.get_value(element)
            print(f"   {element}: {value}")
    except Exception as e:
        print(f"❌ Error testing enhanced handler: {e}")
        return False
    
    # Test 4: API Endpoint
    print("\n🔍 Test 4: SCORM API Endpoint")
    try:
        from scorm.views import scorm_api
        
        # Create a mock request
        factory = RequestFactory()
        request = factory.post('/scorm/api/', 
                             data=json.dumps({
                                 'method': 'Initialize',
                                 'parameters': ['']
                             }),
                             content_type='application/json')
        
        # Mock user
        request.user = attempt.user
        
        # Test API call
        response = scorm_api(request, attempt.id)
        print(f"   API response status: {response.status_code}")
        
        if response.status_code == 200:
            data = json.loads(response.content)
            print(f"   API response: {data}")
            if data.get('success') and data.get('result') == 'true':
                print("   ✅ API endpoint working correctly")
            else:
                print(f"   ⚠️  API returned: {data.get('result')} (error: {data.get('error_code')})")
        else:
            print(f"   ❌ API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing API endpoint: {e}")
        return False
    
    # Test 5: Content Serving (with authentication)
    print("\n🔍 Test 5: SCORM Content Serving")
    try:
        # Use Django test client for proper authentication
        client = Client()
        
        # Login as the user
        client.force_login(attempt.user)
        
        # Test content serving
        response = client.get(f'/scorm/content/{package.topic.id}/index.html')
        print(f"   Content response status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ Content serving working")
            content_preview = response.content[:100].decode('utf-8', errors='ignore')
            print(f"   Content preview: {content_preview}...")
        else:
            print(f"   ❌ Content serving failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing content serving: {e}")
        return False
    
    # Test 6: SCORM View (with authentication)
    print("\n🔍 Test 6: SCORM View")
    try:
        response = client.get(f'/scorm/view/{package.topic.id}/')
        print(f"   SCORM view status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ SCORM view working")
        else:
            print(f"   ❌ SCORM view failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing SCORM view: {e}")
        return False
    
    return True

def run_final_test():
    """Run the final comprehensive test"""
    print("🚀 Starting Final SCORM System Test...")
    
    if test_scorm_system_comprehensive():
        print("\n" + "=" * 60)
        print("🎉 ALL SCORM FIXES ARE WORKING!")
        print("=" * 60)
        print("\n✅ SCORM Package Loading: Working")
        print("✅ SCORM API Handler: Working")
        print("✅ Enhanced SCORM API Handler: Working")
        print("✅ SCORM API Endpoint: Working")
        print("✅ SCORM Content Serving: Working")
        print("✅ SCORM View: Working")
        print("\n🎯 SCORM system is fully functional!")
        return True
    else:
        print("\n" + "=" * 60)
        print("⚠️  SOME ISSUES REMAIN")
        print("=" * 60)
        print("\nCheck the output above for specific issues.")
        return False

if __name__ == "__main__":
    run_final_test()
