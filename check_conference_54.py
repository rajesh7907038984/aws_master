#!/usr/bin/env python3
"""
Check Conference 54 Sync Status
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

print("=" * 80)
print("🔍 CONFERENCE 54 - SYNC STATUS CHECK")
print("=" * 80)

from conferences.models import Conference, ConferenceAttendance, ConferenceChat, ConferenceRecording, ConferenceSyncLog
from account_settings.models import TeamsIntegration

try:
    conf = Conference.objects.get(id=54)
    
    print(f"\n📅 Conference: {conf.title}")
    print(f"   Platform: {conf.meeting_platform}")
    print(f"   Status: {conf.get_meeting_status_display()}")
    print(f"   Sync Status: {conf.data_sync_status}")
    print(f"   Last Sync: {conf.last_sync_at or 'Never'}")
    
    print(f"\n🔗 Meeting Details:")
    print(f"   Meeting ID: {conf.meeting_id or 'Not set'}")
    print(f"   Online Meeting ID: {conf.online_meeting_id or 'Not set'}")
    if conf.meeting_link:
        print(f"   Meeting Link: {conf.meeting_link[:60]}...")
    
    # Check creator
    creator = conf.created_by
    print(f"\n👤 Created By:")
    print(f"   Username: {creator.username}")
    print(f"   Email: {creator.email}")
    print(f"   Role: {creator.role}")
    if hasattr(creator, 'branch') and creator.branch:
        print(f"   Branch: {creator.branch.name}")
    
    # Find which Teams integration is used
    print(f"\n🔧 Teams Integration Used:")
    
    used_integration = None
    
    # Check branch integration
    if hasattr(creator, 'branch') and creator.branch:
        branch_int = TeamsIntegration.objects.filter(
            branch=creator.branch,
            is_active=True
        ).first()
        
        if branch_int:
            used_integration = branch_int
            print(f"   ✅ Branch Integration Found")
            print(f"      Branch: {creator.branch.name}")
            if branch_int.user:
                print(f"      Configured by: {branch_int.user.username} ({branch_int.user.email})")
                print(f"      Admin role: {branch_int.user.role}")
            print(f"      Tenant ID: {branch_int.tenant_id[:30]}...")
            
            # Configuration URL
            print(f"\n   📋 Admin configured at:")
            print(f"      https://vle.nexsy.io/account/?tab=integrations&integration=teams")
    
    if not used_integration:
        print(f"   ⚠️  No branch integration found, checking fallbacks...")
    
    # Check API user
    print(f"\n📧 API User for Sync:")
    api_user = None
    if creator.email:
        api_user = creator.email
        print(f"   Conference creator: {api_user} ✅ (WILL USE THIS)")
    elif used_integration and used_integration.user and used_integration.user.email:
        api_user = used_integration.user.email
        print(f"   Integration owner: {api_user}")
    else:
        print(f"   ❌ No email available for API calls!")
    
    # Check current data
    print(f"\n" + "=" * 80)
    print(f"📊 CURRENT DATA STATUS")
    print("=" * 80)
    
    # Attendance
    attendances = ConferenceAttendance.objects.filter(conference=conf)
    att_with_duration = attendances.filter(duration_minutes__gt=0)
    print(f"\n👥 Attendance:")
    print(f"   Total records: {attendances.count()}")
    print(f"   With duration > 0: {att_with_duration.count()}")
    
    if attendances.exists():
        print(f"\n   Details:")
        for att in attendances[:5]:
            print(f"   • {att.user.email}: {att.duration_minutes or 0} min (Status: {att.attendance_status})")
    else:
        print(f"   ℹ️  No attendance records")
    
    # Chat
    chats = ConferenceChat.objects.filter(conference=conf)
    print(f"\n💬 Chat History:")
    print(f"   Total messages: {chats.count()}")
    
    if chats.exists():
        print(f"\n   Sample messages:")
        for msg in chats[:3]:
            print(f"   • {msg.sender_name}: {msg.message_text[:50]}...")
    else:
        print(f"   ℹ️  No chat messages (Chat History (0))")
    
    # Recordings
    recordings = ConferenceRecording.objects.filter(conference=conf)
    rec_with_duration = recordings.filter(duration_minutes__gt=0)
    print(f"\n📹 Recordings:")
    print(f"   Total: {recordings.count()}")
    print(f"   With duration > 0: {rec_with_duration.count()}")
    
    if recordings.exists():
        print(f"\n   Details:")
        for rec in recordings:
            print(f"   • {rec.title}: {rec.duration_minutes or 0} min, Status: {rec.status}")
    else:
        print(f"   ℹ️  No recordings (Recordings (0))")
    
    # Sync logs
    print(f"\n📝 Recent Sync Logs:")
    logs = ConferenceSyncLog.objects.filter(conference=conf).order_by('-started_at')[:3]
    
    if logs.exists():
        for log in logs:
            status_icon = "✅" if log.status == 'completed' else "❌" if log.status == 'failed' else "⚠️"
            print(f"\n   {status_icon} {log.started_at}")
            print(f"      Type: {log.sync_type}")
            print(f"      Status: {log.status}")
            print(f"      Processed: {log.items_processed}, Failed: {log.items_failed}")
            if log.error_message:
                print(f"      Error: {log.error_message[:100]}...")
            
            # Check platform_response for details
            if hasattr(log, 'platform_response') and log.platform_response:
                print(f"      Platform Response:")
                for key, value in log.platform_response.items():
                    if isinstance(value, dict):
                        print(f"         {key}: {value}")
    else:
        print(f"   ℹ️  No sync logs yet")
    
    # Analysis
    print(f"\n" + "=" * 80)
    print(f"🔍 SYNC ANALYSIS")
    print("=" * 80)
    
    if chats.count() == 0 and recordings.count() == 0:
        print(f"\n⚠️  Chat History (0) and Recordings (0) - WHY?")
        print(f"\nPossible reasons:")
        
        # Check if meeting occurred
        if conf.meeting_status == 'scheduled':
            print(f"\n1️⃣ Meeting Status: {conf.meeting_status}")
            print(f"   ℹ️  Meeting may not have occurred yet")
        
        # Check if sync happened
        if logs.exists():
            last_log = logs.first()
            if last_log.items_processed == 0:
                print(f"\n2️⃣ Last Sync: Processed 0 items")
                print(f"   Possible reasons:")
                print(f"   • Meeting hasn't occurred with participants")
                print(f"   • Chat wasn't used during meeting")
                print(f"   • Recording wasn't enabled")
                print(f"   • Azure AD permissions not granted")
        else:
            print(f"\n2️⃣ No sync attempted yet")
            print(f"   ℹ️  Click 'Sync Data' button to sync")
        
        # Check meeting IDs
        if not conf.online_meeting_id:
            print(f"\n3️⃣ Online Meeting ID: Not set")
            print(f"   ⚠️  Required for attendance reports and chat")
        
        # Check API permissions
        if used_integration:
            print(f"\n4️⃣ Azure AD Permissions:")
            print(f"   Required for admin's Azure AD app:")
            print(f"   • OnlineMeetingArtifact.Read.All (for attendance)")
            print(f"   • Chat.Read.All (for chat messages)")
            print(f"   • Files.Read.All (for recordings)")
            print(f"\n   ⚠️  Check if these are granted at:")
            print(f"   https://portal.azure.com")
            print(f"   → Tenant: {used_integration.tenant_id[:30]}...")
            print(f"   → App: {used_integration.client_id[:30]}...")
    else:
        print(f"\n✅ Data found!")
        if chats.count() > 0:
            print(f"   • Chat messages synced successfully")
        if recordings.count() > 0:
            print(f"   • Recordings synced successfully")
    
    # Recommendations
    print(f"\n" + "=" * 80)
    print(f"🎯 WHAT TO DO")
    print("=" * 80)
    
    print(f"\n1️⃣ IF MEETING HASN'T OCCURRED:")
    print(f"   • Join the meeting with 2-3 users")
    print(f"   • Send chat messages")
    print(f"   • Enable/start recording")
    print(f"   • Stay for 10+ minutes")
    print(f"   • End meeting")
    print(f"   • Wait 10 minutes")
    print(f"   • Then click 'Sync Data'")
    
    print(f"\n2️⃣ IF MEETING OCCURRED BUT NO DATA:")
    print(f"   • Check Azure AD permissions")
    print(f"   • Admin ({used_integration.user.username if used_integration and used_integration.user else 'N/A'}) must grant:")
    print(f"     - OnlineMeetingArtifact.Read.All")
    print(f"     - Chat.Read.All")
    print(f"     - Files.Read.All")
    print(f"   • Go to: https://portal.azure.com")
    print(f"   • Then click 'Sync Data' again")
    
    print(f"\n3️⃣ VERIFY EMAIL ACCESS:")
    print(f"   • API user: {api_user}")
    print(f"   • This account must have access to the meeting")
    print(f"   • Check if {api_user} can see meeting in Teams")
    
except Conference.DoesNotExist:
    print(f"\n❌ Conference 54 not found")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print(f"\n" + "=" * 80)

