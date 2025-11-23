#!/usr/bin/env python3
"""
Check Teams Integration Configuration and API Usage
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

print("=" * 80)
print("🔍 TEAMS INTEGRATION CONFIGURATION CHECK")
print("=" * 80)

from account_settings.models import TeamsIntegration
from conferences.models import Conference

# Check Teams Integration Configuration
print("\n[1] Teams Integration Accounts")
print("-" * 80)

integrations = TeamsIntegration.objects.all()
print(f"Total Teams integrations: {integrations.count()}")

for idx, integration in enumerate(integrations, 1):
    print(f"\n📋 Integration #{idx}:")
    print(f"   Is Active: {'✅ Yes' if integration.is_active else '❌ No'}")
    print(f"   Tenant ID: {integration.tenant_id}")
    print(f"   Client ID: {integration.client_id[:20]}...")
    
    # Check associated user
    if integration.user:
        print(f"\n   👤 Associated User:")
        print(f"      Username: {integration.user.username}")
        print(f"      Email: {integration.user.email}")
        print(f"      Full Name: {integration.user.get_full_name()}")
        print(f"      Role: {integration.user.role}")
        
        # Check branch
        if hasattr(integration.user, 'branch') and integration.user.branch:
            print(f"      Branch: {integration.user.branch.name}")
        else:
            print(f"      Branch: None")
    else:
        print(f"   ⚠️  No user associated")
    
    # Check service account
    if hasattr(integration, 'service_account_email'):
        print(f"\n   📧 Service Account Email:")
        print(f"      {integration.service_account_email or 'Not configured'}")
    
    # Check branch
    if hasattr(integration, 'branch') and integration.branch:
        print(f"\n   🏢 Branch Configuration:")
        print(f"      Branch: {integration.branch.name}")
    else:
        print(f"   🏢 Branch: Not set (uses user's branch)")

# Check Conference 52 Configuration
print("\n" + "=" * 80)
print("[2] Conference 52 - API Usage Details")
print("-" * 80)

try:
    conf = Conference.objects.get(id=52)
    print(f"\n📅 Conference: {conf.title}")
    print(f"   Platform: {conf.meeting_platform}")
    print(f"   Meeting ID: {conf.meeting_id}")
    print(f"   Online Meeting ID: {conf.online_meeting_id}")
    
    print(f"\n👤 Conference Creator:")
    print(f"   Username: {conf.created_by.username}")
    print(f"   Email: {conf.created_by.email}")
    print(f"   Full Name: {conf.created_by.get_full_name()}")
    print(f"   Role: {conf.created_by.role}")
    
    if hasattr(conf.created_by, 'branch') and conf.created_by.branch:
        print(f"   Branch: {conf.created_by.branch.name}")
    else:
        print(f"   Branch: None")
    
    # Determine which integration would be used
    print(f"\n🔧 API Configuration Logic:")
    print(f"   The sync will use this priority order:")
    
    # Priority 1: Branch-level integration
    branch_integration = None
    if hasattr(conf.created_by, 'branch') and conf.created_by.branch:
        branch_integration = TeamsIntegration.objects.filter(
            branch=conf.created_by.branch,
            is_active=True
        ).first()
        
        if branch_integration:
            print(f"   ✅ 1. Branch integration found (WILL USE THIS)")
            print(f"      Branch: {conf.created_by.branch.name}")
            if branch_integration.user:
                print(f"      Integration Owner: {branch_integration.user.email}")
        else:
            print(f"   ❌ 1. No branch-level integration")
    
    # Priority 2: User-level integration
    user_integration = TeamsIntegration.objects.filter(
        user=conf.created_by,
        is_active=True
    ).first()
    
    if user_integration:
        if not branch_integration:
            print(f"   ✅ 2. User integration found (WILL USE THIS)")
        else:
            print(f"   ℹ️  2. User integration found (backup)")
        print(f"      User: {conf.created_by.email}")
    else:
        print(f"   ❌ 2. No user-level integration")
    
    # Priority 3: Any active integration
    any_integration = TeamsIntegration.objects.filter(is_active=True).first()
    if any_integration and not branch_integration and not user_integration:
        print(f"   ✅ 3. Fallback to any active integration (WILL USE THIS)")
        if any_integration.user:
            print(f"      Integration Owner: {any_integration.user.email}")
    
    # Show which will actually be used
    used_integration = branch_integration or user_integration or any_integration
    
    if used_integration:
        print(f"\n🎯 ACTUAL API USER:")
        print(f"   Integration Type: {'Branch-level' if branch_integration else 'User-level' if user_integration else 'Fallback'}")
        
        # Determine which email will be used for API calls
        print(f"\n📧 Email Used for API Calls:")
        print(f"   Priority order:")
        
        api_email = None
        
        # Check conference creator email
        if conf.created_by and conf.created_by.email:
            api_email = conf.created_by.email
            print(f"   ✅ 1. Conference creator email: {api_email} (WILL USE THIS)")
        else:
            print(f"   ❌ 1. Conference creator has no email")
        
        # Check integration owner email
        if used_integration.user and used_integration.user.email:
            if not api_email:
                api_email = used_integration.user.email
                print(f"   ✅ 2. Integration owner email: {api_email} (WILL USE THIS)")
            else:
                print(f"   ℹ️  2. Integration owner email: {used_integration.user.email} (backup)")
        else:
            print(f"   ❌ 2. Integration owner has no email")
        
        # Check service account email
        if hasattr(used_integration, 'service_account_email') and used_integration.service_account_email:
            if not api_email:
                api_email = used_integration.service_account_email
                print(f"   ✅ 3. Service account email: {api_email} (WILL USE THIS)")
            else:
                print(f"   ℹ️  3. Service account email: {used_integration.service_account_email} (backup)")
        else:
            print(f"   ❌ 3. No service account email configured")
        
        if api_email:
            print(f"\n🎯 FINAL: API calls will use: {api_email}")
            print(f"\n   This email MUST have:")
            print(f"   • Teams license")
            print(f"   • Access to the meeting calendar")
            print(f"   • Permissions to read attendance/chat/recordings")
        else:
            print(f"\n❌ ERROR: No email available for API calls!")
    else:
        print(f"\n❌ ERROR: No active Teams integration found!")
        
except Conference.DoesNotExist:
    print("❌ Conference 52 not found")

# Check API Endpoints Being Used
print("\n" + "=" * 80)
print("[3] API Endpoints Being Used")
print("-" * 80)

print("""
The fixed code uses these Microsoft Graph API endpoints:

📊 Attendance (with duration):
   GET /users/{email}/onlineMeetings/{id}/attendanceReports
   GET /users/{email}/onlineMeetings/{id}/attendanceReports/{reportId}/attendanceRecords
   ✅ NEW - Gets actual join/leave times and duration

💬 Chat Messages:
   GET /users/{email}/onlineMeetings/{id}  (to get chat thread ID)
   GET /chats/{threadId}/messages
   ✅ NEW - Gets actual chat messages

📹 Recordings:
   OneDrive Search API + Video metadata
   GET /drives/{driveId}/items/{itemId}?$select=video
   ✅ NEW - Gets actual video duration

📅 Calendar Events:
   GET /users/{email}/events/{eventId}
   ✅ EXISTING - Gets meeting details
""")

# Summary
print("=" * 80)
print("📋 CONFIGURATION SUMMARY")
print("=" * 80)

active_int = TeamsIntegration.objects.filter(is_active=True).first()
if active_int:
    print(f"✅ Active Teams Integration: YES")
    if active_int.user:
        print(f"   Owner: {active_int.user.email} ({active_int.user.role})")
    if hasattr(active_int, 'branch') and active_int.branch:
        print(f"   Branch: {active_int.branch.name}")
    
    # Check if it's properly configured for API calls
    has_email = False
    if active_int.user and active_int.user.email:
        has_email = True
    elif hasattr(active_int, 'service_account_email') and active_int.service_account_email:
        has_email = True
    
    if has_email:
        print(f"✅ Email for API calls: Configured")
    else:
        print(f"❌ Email for API calls: NOT configured")
        print(f"   ⚠️  Configure user email or service_account_email!")
else:
    print(f"❌ Active Teams Integration: NO")

print("\n" + "=" * 80)
print("🎯 RECOMMENDATION")
print("=" * 80)

print("""
For proper Teams sync, ensure:

1. ✅ Teams Integration is active with valid credentials
2. ✅ Integration owner OR service account has email configured
3. ✅ The email account has:
   • Valid Microsoft 365 license
   • Teams license
   • Access to meeting calendars
   • Can view meeting data (attendance, chat, recordings)
4. ✅ Azure AD permissions granted:
   • OnlineMeetingArtifact.Read.All
   • Chat.Read.All
   • Files.Read.All

Current configuration will use the email address shown above for all API calls.
""")

print("=" * 80)

