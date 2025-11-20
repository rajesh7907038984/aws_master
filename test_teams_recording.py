#!/usr/bin/env python3
"""
Test script for Teams recording integration
Run this to verify the implementation is working correctly
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from conferences.models import Conference, ConferenceRecording
from account_settings.models import TeamsIntegration
from teams_integration.utils.onedrive_api import OneDriveAPI
from django.contrib.auth import get_user_model

User = get_user_model()

def test_teams_integration():
    """Test if Teams integration is configured"""
    print("\n=== Testing Teams Integration ===")
    integrations = TeamsIntegration.objects.filter(is_active=True)
    
    if not integrations.exists():
        print("❌ No active Teams integration found")
        print("   Please configure Teams integration in Account Settings")
        return False
    
    integration = integrations.first()
    print(f"✅ Found active Teams integration: {integration.name}")
    print(f"   Tenant ID: {integration.tenant_id[:8]}...")
    print(f"   Client ID: {integration.client_id[:8]}...")
    print(f"   Service Account: {integration.service_account_email or 'Not set'}")
    return True

def test_onedrive_api():
    """Test OneDrive API connection"""
    print("\n=== Testing OneDrive API ===")
    
    integration = TeamsIntegration.objects.filter(is_active=True).first()
    if not integration:
        print("❌ No Teams integration available for testing")
        return False
    
    try:
        api = OneDriveAPI(integration)
        token = api.get_access_token()
        
        if token:
            print("✅ Successfully obtained OneDrive access token")
            print(f"   Token preview: {token[:20]}...")
            return True
        else:
            print("❌ Failed to obtain access token")
            return False
    except Exception as e:
        print(f"❌ OneDrive API error: {str(e)}")
        return False

def test_conference_recording_model():
    """Test ConferenceRecording model"""
    print("\n=== Testing ConferenceRecording Model ===")
    
    try:
        # Check if new fields exist
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'conferences_conferencerecording'
                AND column_name LIKE 'onedrive%'
            """)
            columns = cursor.fetchall()
        
        if columns:
            print(f"✅ OneDrive fields added to model: {len(columns)} fields")
            for col in columns:
                print(f"   - {col[0]}")
            return True
        else:
            print("❌ OneDrive fields not found in database")
            return False
    except Exception as e:
        print(f"❌ Database error: {str(e)}")
        return False

def test_conferences():
    """Test conference data"""
    print("\n=== Testing Conferences ===")
    
    teams_conferences = Conference.objects.filter(meeting_platform='teams')
    total_count = teams_conferences.count()
    
    print(f"Total Teams conferences: {total_count}")
    
    if total_count > 0:
        recent = teams_conferences.order_by('-created_at')[:5]
        print(f"\nRecent Teams conferences:")
        for conf in recent:
            print(f"   - {conf.title} (ID: {conf.id})")
            print(f"     Status: {conf.meeting_status} | Sync: {conf.data_sync_status}")
            recording_count = conf.recordings.count()
            onedrive_count = conf.recordings.filter(stored_in_onedrive=True).count()
            print(f"     Recordings: {recording_count} total, {onedrive_count} in OneDrive")
    else:
        print("ℹ️  No Teams conferences found yet")
    
    return True

def test_recordings():
    """Test recording data"""
    print("\n=== Testing Recordings ===")
    
    total_recordings = ConferenceRecording.objects.count()
    onedrive_recordings = ConferenceRecording.objects.filter(stored_in_onedrive=True).count()
    
    print(f"Total recordings: {total_recordings}")
    print(f"OneDrive recordings: {onedrive_recordings}")
    
    if onedrive_recordings > 0:
        recent = ConferenceRecording.objects.filter(stored_in_onedrive=True).order_by('-created_at')[:5]
        print(f"\nRecent OneDrive recordings:")
        for rec in recent:
            print(f"   - {rec.title}")
            print(f"     Conference: {rec.conference.title}")
            print(f"     Size: {rec.file_size / (1024*1024):.2f} MB" if rec.file_size else "     Size: Unknown")
            print(f"     Downloads: {rec.download_count}")
            print(f"     OneDrive ID: {rec.onedrive_item_id[:20]}..." if rec.onedrive_item_id else "     OneDrive ID: Not set")
    else:
        print("ℹ️  No OneDrive recordings found yet")
        print("   Create a Teams meeting and sync after it ends to see recordings here")
    
    return True

def test_sync_status():
    """Test sync status"""
    print("\n=== Testing Sync Status ===")
    
    from conferences.models import ConferenceSyncLog
    
    recent_syncs = ConferenceSyncLog.objects.filter(
        sync_type__in=['recordings', 'full']
    ).order_by('-started_at')[:5]
    
    if recent_syncs.exists():
        print("Recent recording sync operations:")
        for log in recent_syncs:
            status_icon = "✅" if log.status == 'completed' else "❌" if log.status == 'failed' else "⏳"
            print(f"   {status_icon} {log.conference.title}")
            print(f"      Type: {log.sync_type} | Status: {log.status}")
            print(f"      Processed: {log.items_processed} | Failed: {log.items_failed}")
            if log.error_message:
                print(f"      Error: {log.error_message[:100]}...")
    else:
        print("ℹ️  No sync operations found yet")
    
    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("Teams Recording Integration Test")
    print("=" * 60)
    
    tests = [
        ("Teams Integration", test_teams_integration),
        ("OneDrive API", test_onedrive_api),
        ("Database Schema", test_conference_recording_model),
        ("Conferences", test_conferences),
        ("Recordings", test_recordings),
        ("Sync Status", test_sync_status),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test '{name}' failed with exception: {str(e)}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print("\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All tests passed! Teams recording integration is ready.")
        print("\nNext steps:")
        print("1. Create a Teams conference")
        print("2. Hold the meeting (it will be auto-recorded)")
        print("3. Wait 5-10 minutes after meeting ends")
        print("4. Click 'Sync Data' button on conference detail page")
        print("5. Recordings will appear in the Recordings tab")
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        print("   Check the setup guide: TEAMS_RECORDING_SETUP.md")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

