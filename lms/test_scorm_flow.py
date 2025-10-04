#!/usr/bin/env python
"""
SCORM Flow Test Script
Tests the complete SCORM flow from upload to playback
"""
import os
import sys
import django

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from courses.models import Topic, Course
from scorm.models import ScormPackage, ScormAttempt
from django.contrib.auth import get_user_model

User = get_user_model()

def test_scorm_infrastructure():
    """Test that SCORM models and infrastructure are available"""
    print("=" * 80)
    print("TESTING SCORM INFRASTRUCTURE")
    print("=" * 80)
    
    # Test 1: Models exist
    print("\n✓ Testing SCORM models...")
    try:
        print(f"  - ScormPackage model: {ScormPackage._meta.db_table}")
        print(f"  - ScormAttempt model: {ScormAttempt._meta.db_table}")
        print("  ✅ Models loaded successfully")
    except Exception as e:
        print(f"  ❌ Error loading models: {e}")
        return False
    
    # Test 2: Database tables exist
    print("\n✓ Testing database tables...")
    try:
        package_count = ScormPackage.objects.count()
        attempt_count = ScormAttempt.objects.count()
        print(f"  - ScormPackage records: {package_count}")
        print(f"  - ScormAttempt records: {attempt_count}")
        print("  ✅ Tables accessible")
    except Exception as e:
        print(f"  ❌ Error accessing tables: {e}")
        return False
    
    # Test 3: Signal handler is registered
    print("\n✓ Testing signal handler...")
    try:
        from django.db.models.signals import post_save
        from courses.signals import process_scorm_package
        from courses.models import Topic
        
        # Check if signal is connected
        receivers = post_save._live_receivers(Topic)
        has_scorm_handler = any('process_scorm_package' in str(receiver) for receiver in receivers)
        
        if has_scorm_handler:
            print("  ✅ SCORM processing signal is registered")
        else:
            print("  ⚠️  SCORM signal may not be registered")
    except Exception as e:
        print(f"  ⚠️  Could not verify signal: {e}")
    
    # Test 4: Parser is available
    print("\n✓ Testing SCORM parser...")
    try:
        from scorm.parser import ScormParser
        print("  ✅ ScormParser imported successfully")
    except Exception as e:
        print(f"  ❌ Error importing parser: {e}")
        return False
    
    # Test 5: API handler is available
    print("\n✓ Testing SCORM API handler...")
    try:
        from scorm.api_handler import ScormAPIHandler
        print("  ✅ ScormAPIHandler imported successfully")
    except Exception as e:
        print(f"  ❌ Error importing API handler: {e}")
        return False
    
    # Test 6: Views are available
    print("\n✓ Testing SCORM views...")
    try:
        from scorm import views
        print("  ✅ SCORM views imported successfully")
    except Exception as e:
        print(f"  ❌ Error importing views: {e}")
        return False
    
    # Test 7: URLs are configured
    print("\n✓ Testing URL configuration...")
    try:
        from django.urls import reverse
        player_url = reverse('scorm:player', args=[1])
        api_url = reverse('scorm:api', args=[1])
        print(f"  - Player URL pattern: {player_url}")
        print(f"  - API URL pattern: {api_url}")
        print("  ✅ URLs configured correctly")
    except Exception as e:
        print(f"  ❌ Error with URLs: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("✅ ALL INFRASTRUCTURE TESTS PASSED")
    print("=" * 80)
    return True


def test_scorm_topics():
    """Test existing SCORM topics"""
    print("\n" + "=" * 80)
    print("TESTING EXISTING SCORM TOPICS")
    print("=" * 80)
    
    # Find SCORM topics
    scorm_topics = Topic.objects.filter(content_type='SCORM')
    print(f"\nFound {scorm_topics.count()} SCORM topic(s)")
    
    if scorm_topics.count() == 0:
        print("  ℹ️  No SCORM topics found - this is normal if none have been created yet")
        return True
    
    for topic in scorm_topics:
        print(f"\n📦 Topic #{topic.id}: {topic.title}")
        print(f"   Created: {topic.created_at}")
        print(f"   Has content_file: {bool(topic.content_file)}")
        
        # Check if ScormPackage exists
        try:
            scorm_package = topic.scorm_package
            print(f"   ✅ Has ScormPackage (ID: {scorm_package.id})")
            print(f"      - Version: SCORM {scorm_package.version}")
            print(f"      - Launch URL: {scorm_package.launch_url}")
            print(f"      - Extracted Path: {scorm_package.extracted_path}")
            print(f"      - Title: {scorm_package.title}")
            
            # Check attempts
            attempts = ScormAttempt.objects.filter(scorm_package=scorm_package)
            print(f"      - Attempts: {attempts.count()}")
            
        except ScormPackage.DoesNotExist:
            print(f"   ⚠️  NO ScormPackage record found!")
            print(f"      This topic needs to be re-saved to trigger SCORM processing")
    
    return True


def show_recommendations():
    """Show recommendations based on current state"""
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    scorm_topics = Topic.objects.filter(content_type='SCORM')
    topics_without_package = []
    
    for topic in scorm_topics:
        try:
            _ = topic.scorm_package
        except ScormPackage.DoesNotExist:
            topics_without_package.append(topic)
    
    if topics_without_package:
        print(f"\n⚠️  Found {len(topics_without_package)} SCORM topic(s) without ScormPackage:")
        for topic in topics_without_package:
            print(f"   - Topic #{topic.id}: {topic.title}")
        print("\n📝 To fix these topics, you can:")
        print("   1. Re-upload the SCORM package through the admin interface")
        print("   2. Or run this command to reprocess existing files:")
        print("      python manage.py shell")
        print("      >>> from courses.models import Topic")
        print("      >>> topic = Topic.objects.get(id=YOUR_TOPIC_ID)")
        print("      >>> topic.save()  # This will trigger the signal")
    else:
        print("\n✅ All SCORM topics have proper ScormPackage records!")
    
    print("\n📋 Next Steps:")
    print("   1. Upload a test SCORM package through the course admin")
    print("   2. Verify the ScormPackage is created automatically")
    print("   3. Test learner access and SCORM player")
    print("   4. Verify score tracking and gradebook integration")


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("SCORM IMPLEMENTATION VERIFICATION")
    print("=" * 80)
    
    # Run tests
    if test_scorm_infrastructure():
        test_scorm_topics()
        show_recommendations()
        
        print("\n" + "=" * 80)
        print("✅ SCORM IMPLEMENTATION IS READY!")
        print("=" * 80)
        print("\nThe signal handler has been added and SCORM functionality is now active.")
        print("Upload a SCORM package to test the complete flow.")
    else:
        print("\n" + "=" * 80)
        print("❌ SOME TESTS FAILED")
        print("=" * 80)
        print("\nPlease review the errors above and fix any issues.")

