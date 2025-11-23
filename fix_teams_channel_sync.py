#!/usr/bin/env python3
"""
Fix Teams Channel Meeting Sync Issue
This script provides solutions for syncing Teams channel meetings
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.base')

# Initialize Django
django.setup()

from account_settings.models import TeamsIntegration
from conferences.models import Conference
from django.contrib.auth import get_user_model

User = get_user_model()

def create_regular_meeting_test():
    """Create a test conference with regular Teams meeting"""
    from datetime import datetime, timedelta
    
    print("=" * 60)
    print("CREATING TEST CONFERENCE WITH REGULAR TEAMS MEETING")
    print("=" * 60)
    
    # Get the support user
    support_user = User.objects.get(username='support')
    
    # Create new conference
    conference = Conference.objects.create(
        title='Regular Teams Meeting Test - Chat Sync',
        description='Testing regular Teams meeting (not channel) for proper sync',
        created_by=support_user,
        course_id=101,  # Conferences course
        meeting_platform='teams',
        date=datetime.now().date(),
        start_time=datetime.now().time(),
        end_time=(datetime.now() + timedelta(hours=1)).time(),
        timezone='UTC',
        use_time_slots=False
    )
    
    print(f"✅ Created conference: {conference.title}")
    print(f"   ID: {conference.id}")
    print(f"   URL: https://vle.nexsy.io/conferences/{conference.id}")
    print()
    print("INSTRUCTIONS FOR REGULAR MEETING:")
    print("-" * 40)
    print("1. Go to the conference page")
    print("2. Click 'Create Teams Meeting'")
    print("3. When creating, DO NOT select any channel")
    print("4. Just add attendees directly")
    print("5. Join the meeting, send chat messages")
    print("6. End meeting and click 'Sync Data'")
    print()
    print("This will create a regular meeting that syncs properly!")
    
    return conference

def check_channel_permissions():
    """Check if we can add Channel.Read.All permission"""
    print("=" * 60)
    print("CHECKING AZURE AD APP PERMISSIONS")
    print("=" * 60)
    
    integration = TeamsIntegration.objects.filter(is_active=True).first()
    if integration:
        print(f"Active integration: {integration.name}")
        print(f"Service account: {integration.service_account_email}")
        print()
        print("Required permissions for channel meetings:")
        print("  - Channel.Read.All")
        print("  - ChannelMessage.Read.All")
        print("  - Files.Read.All")
        print()
        print("TO ADD THESE PERMISSIONS:")
        print("-" * 40)
        print("1. Go to Azure Portal (portal.azure.com)")
        print("2. Navigate to: Azure Active Directory > App registrations")
        print(f"3. Find app with Client ID: {integration.client_id}")
        print("4. Click 'API permissions' > 'Add a permission'")
        print("5. Select 'Microsoft Graph' > 'Application permissions'")
        print("6. Add:")
        print("   - Channel > Channel.Read.All")
        print("   - ChannelMessage > ChannelMessage.Read.All")
        print("7. Click 'Grant admin consent'")
        print()
        print("After adding permissions, channel meeting sync will work!")
    else:
        print("No active Teams integration found")

def add_service_account_to_channel():
    """Instructions for adding service account to Teams channel"""
    print("=" * 60)
    print("ADDING SERVICE ACCOUNT TO TEAMS CHANNEL")
    print("=" * 60)
    
    integration = TeamsIntegration.objects.filter(is_active=True).first()
    if integration and integration.service_account_email:
        email = integration.service_account_email
        print(f"Service account to add: {email}")
        print()
        print("STEPS TO ADD TO CHANNEL:")
        print("-" * 40)
        print("1. Open Microsoft Teams")
        print("2. Go to the team/channel where meetings are created")
        print("3. Click the 3 dots (...) next to channel name")
        print("4. Select 'Manage channel'")
        print("5. Go to 'Members' tab")
        print(f"6. Click 'Add members' and add: {email}")
        print("7. Set role as 'Member' (or 'Owner' for full access)")
        print()
        print("Once added, the service account can access channel meetings!")
    else:
        print("No service account configured")

def diagnose_current_meetings():
    """Check all current meetings and their types"""
    print("=" * 60)
    print("DIAGNOSING CURRENT MEETINGS")
    print("=" * 60)
    
    conferences = Conference.objects.filter(
        meeting_platform='teams'
    ).exclude(meeting_id__isnull=True).order_by('-id')[:5]
    
    for conf in conferences:
        print(f"\nConference {conf.id}: {conf.title}")
        print(f"  Meeting ID: {conf.meeting_id}")
        
        if conf.meeting_id and 'meeting_' in conf.meeting_id:
            print("  Type: ❌ CHANNEL MEETING (requires special permissions)")
            print("  Fix: Add service account to channel OR use regular meetings")
        else:
            print("  Type: ✅ REGULAR MEETING (should sync properly)")
        
        # Check sync status
        from conferences.models import ConferenceAttendance, ConferenceChat
        attendance = ConferenceAttendance.objects.filter(conference=conf).count()
        chat = ConferenceChat.objects.filter(conference=conf).count()
        print(f"  Synced data: {attendance} attendance, {chat} chat messages")

def main():
    """Main menu for fixing Teams sync issues"""
    print("\n" + "=" * 60)
    print("TEAMS SYNC FIX UTILITY")
    print("=" * 60)
    print("\nSelect an option:")
    print("1. Create test conference with REGULAR meeting (recommended)")
    print("2. Check Azure AD permission requirements")
    print("3. Get instructions to add service account to channel")
    print("4. Diagnose current meetings")
    print("5. Run all diagnostics")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == '1':
        create_regular_meeting_test()
    elif choice == '2':
        check_channel_permissions()
    elif choice == '3':
        add_service_account_to_channel()
    elif choice == '4':
        diagnose_current_meetings()
    elif choice == '5':
        diagnose_current_meetings()
        print()
        check_channel_permissions()
        print()
        add_service_account_to_channel()
        print()
        create_regular_meeting_test()
    else:
        print("Invalid choice")

if __name__ == '__main__':
    main()
