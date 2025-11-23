#!/usr/bin/env python3
"""
Debug Conference 54 Sync Issue - Permissions ARE granted but data not syncing
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

print("=" * 80)
print("🐛 DEBUGGING CONFERENCE 54 SYNC ISSUE")
print("=" * 80)

from conferences.models import Conference, ConferenceSyncLog
from account_settings.models import TeamsIntegration

try:
    conf = Conference.objects.get(id=54)
    
    print(f"\n✅ Conference 54 Found")
    print(f"   Title: {conf.title}")
    print(f"   Meeting occurred: YES (users attended)")
    print(f"   Meeting link: {conf.meeting_link[:80]}...")
    
    # Extract tenant and meeting IDs
    print(f"\n🔍 Meeting IDs:")
    print(f"   Meeting ID: {conf.meeting_id}")
    print(f"   Online Meeting ID: {conf.online_meeting_id}")
    
    # Check if IDs match the join URL
    join_url = "19:meeting_NDRlZDM5YWItMGZhNi00M2MwLWI2NDMtODdiMjJkZmIwOTJh@thread.v2"
    tenant_id = "ac882ab2-23dc-480d-ae6e-ea51ec15c5ea"
    
    print(f"\n🔗 From Join URL:")
    print(f"   Meeting Thread: {join_url}")
    print(f"   Tenant: {tenant_id}")
    
    print(f"\n🔍 Checking ID Mismatch:")
    if conf.meeting_id != join_url:
        print(f"   ⚠️ MISMATCH FOUND!")
        print(f"   Stored Meeting ID: {conf.meeting_id}")
        print(f"   Actual Meeting ID: {join_url}")
        print(f"   🐛 BUG: Wrong meeting ID stored!")
    
    if conf.online_meeting_id != join_url:
        print(f"   ⚠️ MISMATCH FOUND!")
        print(f"   Stored Online Meeting ID: {conf.online_meeting_id}")
        print(f"   Actual Online Meeting ID: {join_url}")
        print(f"   🐛 BUG: Wrong online meeting ID stored!")
    
    # Check Teams integration
    print(f"\n🔧 Teams Integration:")
    creator = conf.created_by
    
    integration = None
    if hasattr(creator, 'branch') and creator.branch:
        integration = TeamsIntegration.objects.filter(
            branch=creator.branch,
            is_active=True
        ).first()
    
    if integration:
        print(f"   Tenant in Integration: {integration.tenant_id}")
        print(f"   Tenant in Join URL: {tenant_id}")
        
        if integration.tenant_id != tenant_id:
            print(f"   ⚠️ TENANT MISMATCH!")
            print(f"   🐛 BUG: Meeting created in different tenant!")
    
    # Check last sync log details
    print(f"\n📝 Last Sync Attempt:")
    last_log = ConferenceSyncLog.objects.filter(conference=conf).order_by('-started_at').first()
    
    if last_log:
        print(f"   Time: {last_log.started_at}")
        print(f"   Status: {last_log.status}")
        print(f"   Processed: {last_log.items_processed}")
        
        if hasattr(last_log, 'platform_response') and last_log.platform_response:
            print(f"\n   Platform Response Details:")
            import json
            print(json.dumps(last_log.platform_response, indent=4))
        
        if last_log.error_message:
            print(f"\n   Error: {last_log.error_message}")
    
    # Key issues to check
    print(f"\n" + "=" * 80)
    print(f"🐛 POTENTIAL BUGS IDENTIFIED:")
    print("=" * 80)
    
    bugs = []
    
    # Bug 1: Meeting ID format mismatch
    if conf.meeting_id and "meeting_" not in conf.meeting_id:
        bugs.append({
            'id': 1,
            'issue': 'Meeting ID wrong format',
            'current': conf.meeting_id,
            'should_be': 'Should contain "meeting_" in the ID',
            'impact': 'Attendance reports API will fail'
        })
    
    # Bug 2: Online meeting ID might be calendar event ID instead of join URL thread ID
    if conf.online_meeting_id and "@thread.v2" not in conf.online_meeting_id:
        bugs.append({
            'id': 2,
            'issue': 'Online Meeting ID is calendar event ID, not thread ID',
            'current': conf.online_meeting_id,
            'should_be': f'{join_url}',
            'impact': 'Chat and attendance APIs will use wrong ID'
        })
    
    # Bug 3: Check if API is using correct endpoint format
    bugs.append({
        'id': 3,
        'issue': 'API endpoint might be using wrong ID format',
        'current': f'/users/{{email}}/onlineMeetings/{conf.online_meeting_id}/attendanceReports',
        'should_check': 'Thread ID vs Calendar Event ID usage',
        'impact': 'API calls return 404 or no data'
    })
    
    for bug in bugs:
        print(f"\n🐛 BUG #{bug['id']}: {bug['issue']}")
        print(f"   Current: {bug.get('current', 'N/A')}")
        print(f"   Should be: {bug.get('should_be', bug.get('should_check', 'N/A'))}")
        print(f"   Impact: {bug['impact']}")
    
    # THE REAL BUG
    print(f"\n" + "=" * 80)
    print(f"🎯 ROOT CAUSE IDENTIFIED:")
    print("=" * 80)
    
    print(f"""
The issue is likely one of these:

1️⃣ MEETING ID FORMAT ISSUE:
   • Meeting was attended via join URL with thread ID
   • But stored meeting_id might be calendar event ID (GUID format)
   • API endpoint needs thread ID in format: 19:meeting_XXX@thread.v2
   • Currently using: {conf.meeting_id or 'Not set'}
   
2️⃣ CALENDAR EVENT vs ONLINE MEETING:
   • Teams has TWO types of IDs:
     a) Calendar Event ID (GUID like: b3081eb2-c906-4e94...)
     b) Thread/Join ID (19:meeting_XXX@thread.v2)
   
   • For Attendance Reports: Need thread ID
   • For Chat Messages: Need thread ID
   • Currently stored: {conf.online_meeting_id}

3️⃣ API ENDPOINT MISMATCH:
   • Code might be calling:
     GET /users/{{email}}/onlineMeetings/{{calendar-event-id}}/attendanceReports
   • Should be calling:
     GET /users/{{email}}/onlineMeetings/{{thread-id}}/attendanceReports
   
   • Or using different API:
     GET /communications/callRecords (requires different permission)

4️⃣ MEETING NOT IN ORGANIZER'S CALENDAR:
   • API user: {creator.email}
   • This user must be the organizer of the meeting
   • If meeting was created by different account, API calls fail

RECOMMENDATION:
Check the sync logs and API calls to see which ID format is being used.
The thread ID from join URL should be: {join_url}
""")
    
    # Check what the code will actually use
    print(f"\n" + "=" * 80)
    print(f"🔍 WHAT THE CODE WILL TRY TO USE:")
    print("=" * 80)
    
    print(f"\n1. For Attendance Reports API:")
    print(f"   online_meeting_id = {conf.online_meeting_id}")
    print(f"   API call: /users/{creator.email}/onlineMeetings/{conf.online_meeting_id}/attendanceReports")
    
    if "@thread.v2" in conf.online_meeting_id:
        print(f"   ✅ Format looks correct (thread ID)")
    else:
        print(f"   ❌ Format wrong (should be thread ID like 19:meeting_XXX@thread.v2)")
        print(f"   🐛 THIS IS THE BUG!")
    
    print(f"\n2. For Chat Messages API:")
    print(f"   Will try to get chat thread from online meeting")
    print(f"   GET /users/{creator.email}/onlineMeetings/{conf.online_meeting_id}")
    
    print(f"\n3. For Recordings:")
    print(f"   Searches OneDrive of user: {creator.email}")
    print(f"   Meeting title: {conf.title}")

except Conference.DoesNotExist:
    print(f"❌ Conference 54 not found")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print(f"\n" + "=" * 80)
print(f"🎯 NEXT STEPS:")
print("=" * 80)
print(f"""
1. Check server logs during last sync:
   tail -f /home/ec2-user/lmslogs/*.log

2. Look for API errors like:
   • "404 Not Found" - Wrong meeting ID
   • "403 Forbidden" - Still permission issue
   • "No attendance reports available" - Meeting not ended or wait longer

3. Verify the meeting organizer:
   • Who created the meeting in Teams?
   • Is it {creator.email}?
   • API can only access meetings owned by this user

4. Test API call manually to see exact error
""")

print(f"=" * 80)

