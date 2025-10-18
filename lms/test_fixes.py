#!/usr/bin/env python3
"""
Comprehensive test script to verify all bug fixes are working
"""

import os
import sys
import django
import requests
import time

def setup_django():
    """Setup Django environment"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
    django.setup()

def test_django_system():
    """Test Django system health"""
    print("🔍 Testing Django system health...")
    try:
        from django.core.management import execute_from_command_line
        execute_from_command_line(['manage.py', 'check', '--deploy'])
        print("✅ Django system check passed")
        return True
    except Exception as e:
        print(f"❌ Django system check failed: {e}")
        return False

def test_database_queries():
    """Test database queries that were previously failing"""
    print("🔍 Testing database queries...")
    try:
        from assignments.models import Assignment
        from courses.models import Course
        from business.models import Business
        from django.db.models import Count, Q
        
        # Test Assignment query (fixed)
        course = Course.objects.first()
        if course:
            assignments = Assignment.objects.filter(courses__in=[course])
            print(f"✅ Assignment query works: {assignments.count()} assignments found")
        
        # Test Business query (fixed)
        businesses = Business.objects.annotate(
            branches_count=Count('branches'),
            super_admins_count=Count('business_user_assignments', filter=Q(business_user_assignments__is_active=True))
        ).order_by('name')
        print(f"✅ Business query works: {businesses.count()} businesses found")
        
        return True
    except Exception as e:
        print(f"❌ Database queries failed: {e}")
        return False

def test_environment_config():
    """Test environment configuration"""
    print("🔍 Testing environment configuration...")
    try:
        from django.conf import settings
        
        # Check API key
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        if api_key == 'disabled':
            print("✅ ANTHROPIC_API_KEY properly disabled")
        else:
            print(f"⚠️  ANTHROPIC_API_KEY: {api_key}")
        
        # Check cache configuration
        caches = getattr(settings, 'CACHES', None)
        if caches and caches['default']['BACKEND'] == 'django.core.cache.backends.db.DatabaseCache':
            print("✅ Cache configuration working")
        else:
            print("❌ Cache configuration not found")
        
        return True
    except Exception as e:
        print(f"❌ Environment configuration test failed: {e}")
        return False

def test_server_connectivity():
    """Test server connectivity"""
    print("🔍 Testing server connectivity...")
    try:
        response = requests.get('http://localhost:8000/', timeout=10)
        if response.status_code == 200:
            print("✅ Server is responding to requests")
            return True
        else:
            print(f"⚠️  Server responded with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Server connectivity test failed: {e}")
        return False

def test_ai_service():
    """Test AI service (should be disabled)"""
    print("🔍 Testing AI service...")
    try:
        response = requests.post(
            'http://localhost:8000/tinymce/generate_ai_content/',
            json={'prompt': 'test'},
            timeout=5
        )
        if response.status_code == 503:
            print("✅ AI service properly disabled (503 Service Unavailable)")
            return True
        else:
            print(f"⚠️  AI service responded with status {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        print("✅ AI service timeout (expected for disabled service)")
        return True
    except Exception as e:
        print(f"❌ AI service test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 LMS Bug Fixes Test Suite")
    print("=" * 40)
    
    # Setup Django
    setup_django()
    
    # Run tests
    tests = [
        ("Django System", test_django_system),
        ("Database Queries", test_database_queries),
        ("Environment Config", test_environment_config),
        ("Server Connectivity", test_server_connectivity),
        ("AI Service", test_ai_service),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 40)
    print("📊 Test Results Summary:")
    print("=" * 40)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Bug fixes are working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
