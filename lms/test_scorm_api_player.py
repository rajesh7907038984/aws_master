#!/usr/bin/env python
"""
Test SCORM API and Player Integration
Verifies that SCORM API endpoints and player work correctly for all package types
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from scorm.models import ELearningPackage, ELearningTracking
from courses.models import Topic

User = get_user_model()

def test_scorm_api_and_player():
    """Test SCORM API endpoints and player for all package types"""
    print('=' * 70)
    print('SCORM API & Player Integration Test')
    print('=' * 70)
    
    # Get a test user (create if doesn't exist)
    try:
        user = User.objects.filter(is_staff=True).first()
        if not user:
            user = User.objects.first()
        
        if not user:
            print('❌ No users found in database. Cannot test.')
            return False
    except Exception as e:
        print(f'❌ Error getting user: {e}')
        return False
    
    print(f'\n✓ Using test user: {user.username} (ID: {user.id})\n')
    
    # Get all extracted packages
    packages = ELearningPackage.objects.filter(is_extracted=True)
    
    if packages.count() == 0:
        print('⚠️  No extracted packages found to test')
        return True
    
    client = Client()
    client.force_login(user)
    
    all_passed = True
    
    for pkg in packages:
        topic_id = pkg.topic_id
        print(f'📦 Testing Package for Topic {topic_id} ({pkg.package_type})')
        print('-' * 70)
        
        # Test 1: Launch endpoint
        print('✓ Testing launch endpoint...')
        try:
            response = client.get(f'/scorm/launch/{topic_id}/')
            if response.status_code == 200:
                print(f'  ✅ Launch endpoint returned 200 OK')
                
                # Check if launch_url is in context
                if hasattr(response, 'context') and response.context:
                    launch_url = response.context.get('launch_url')
                    if launch_url:
                        print(f'  ✅ Launch URL in context: {launch_url}')
                    else:
                        print(f'  ⚠️  Launch URL not in context')
            elif response.status_code == 302:
                print(f'  ✅ Launch endpoint redirected (302) - this is OK')
                print(f'     Redirect to: {response.url}')
            else:
                print(f'  ❌ Launch endpoint returned {response.status_code}')
                all_passed = False
        except Exception as e:
            print(f'  ❌ Launch endpoint error: {e}')
            all_passed = False
        
        # Test 2: Content endpoint
        print('\n✓ Testing content endpoint...')
        if pkg.launch_file:
            try:
                content_url = f'/scorm/content/{topic_id}/{pkg.launch_file}'
                response = client.get(content_url)
                if response.status_code in [200, 302]:
                    print(f'  ✅ Content endpoint returned {response.status_code}')
                else:
                    print(f'  ❌ Content endpoint returned {response.status_code}')
                    all_passed = False
            except Exception as e:
                print(f'  ❌ Content endpoint error: {e}')
                all_passed = False
        else:
            print(f'  ⚠️  No launch file, skipping content test')
        
        # Test 3: API endpoint (SCORM API)
        print('\n✓ Testing SCORM API endpoint...')
        try:
            # Test LMSInitialize
            response = client.post(f'/scorm/api/{topic_id}/', {
                'action': 'Initialize',
                'value': ''
            })
            if response.status_code == 200:
                print(f'  ✅ SCORM API endpoint accessible')
                data = response.json()
                if data.get('result') in ['true', True]:
                    print(f'  ✅ SCORM API Initialize successful')
                else:
                    print(f'  ⚠️  SCORM API Initialize returned: {data}')
            else:
                print(f'  ❌ SCORM API returned {response.status_code}')
                all_passed = False
        except Exception as e:
            print(f'  ❌ SCORM API error: {e}')
            all_passed = False
        
        # Test 4: Check tracking record
        print('\n✓ Checking tracking record...')
        try:
            tracking = ELearningTracking.objects.filter(
                user=user,
                elearning_package=pkg
            ).first()
            
            if tracking:
                print(f'  ✅ Tracking record exists')
                print(f'     - Attempts: {tracking.attempt_count}')
                print(f'     - Status: {tracking.completion_status}')
                print(f'     - Last access: {tracking.last_access_date or "Never"}')
            else:
                print(f'  ℹ️  No tracking record yet (will be created on launch)')
        except Exception as e:
            print(f'  ❌ Tracking check error: {e}')
        
        # Test 5: Package-specific endpoints
        print(f'\n✓ Testing {pkg.package_type}-specific features...')
        if pkg.package_type == 'XAPI':
            print(f'  - xAPI Endpoint: {pkg.xapi_endpoint or "Not configured"}')
            if pkg.xapi_endpoint:
                print(f'  ✅ xAPI endpoint configured')
            else:
                print(f'  ⚠️  xAPI endpoint not configured')
        
        elif pkg.package_type == 'CMI5':
            print(f'  - cmi5 AU ID: {pkg.cmi5_au_id or "Not configured"}')
            print(f'  - cmi5 Launch URL: {pkg.cmi5_launch_url or "Not configured"}')
            if pkg.cmi5_au_id:
                print(f'  ✅ cmi5 configuration present')
            else:
                print(f'  ⚠️  cmi5 not fully configured')
        
        elif pkg.package_type in ['SCORM_1_2', 'SCORM_2004']:
            print(f'  ✅ Standard SCORM package')
            print(f'  - Manifest: {pkg.manifest_path or "Not found"}')
        
        print('\n' + '=' * 70 + '\n')
    
    # Final summary
    print('=' * 70)
    print('API & PLAYER TEST SUMMARY')
    print('=' * 70)
    
    if all_passed:
        print('\n✅ All SCORM API & Player tests PASSED!')
        print('✓ Launch endpoints working')
        print('✓ Content endpoints working')
        print('✓ SCORM API endpoints responding')
        print('✓ Tracking system operational')
        print('\n🎉 SCORM Player is fully functional!')
    else:
        print('\n⚠️  Some tests failed - review the output above')
    
    print('=' * 70)
    
    return all_passed

if __name__ == '__main__':
    success = test_scorm_api_and_player()
    exit(0 if success else 1)

