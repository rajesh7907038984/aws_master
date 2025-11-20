# Teams Meeting Chat History Sync Fix

## Issue Description

**Problem**: Chat History shows (0) messages on conference pages (e.g., https://vle.nexsy.io/conferences/46/) for Teams meetings because the chat data was not being synced properly from Microsoft Teams.

**Root Cause**: The `sync_meeting_chat` function in `/teams_integration/utils/sync_services.py` was implemented as a placeholder that only marked the chat as "synced" without actually fetching any chat messages from the Teams API.

## Files Modified

### 1. `/teams_integration/utils/teams_api.py`

**Added Methods:**

#### `get_meeting_transcript(meeting_id, user_email=None)`
Fetches meeting transcript and chat messages from Teams using Microsoft Graph API. This method attempts two approaches:

1. **Method 1: Transcript API** - Uses `/users/{email}/onlineMeetings/{meetingId}/transcripts` endpoint
   - Requires: `OnlineMeetings.Read.All` or `OnlineMeetings.ReadWrite.All` permission
   - Requires: Teams Premium license for transcription feature
   - Returns: VTT format transcript content

2. **Method 2: Chat API** - Uses `/chats/{chatId}/messages` endpoint
   - Requires: `Chat.Read.All` permission
   - Returns: Individual chat messages with sender information

**Parameters:**
- `meeting_id`: Teams online meeting ID
- `user_email`: User's email address for API authentication

**Returns:**
```python
{
    'success': True/False,
    'messages': [
        {
            'id': 'message_id',
            'created': 'ISO_timestamp',
            'sender': 'Display Name',
            'sender_email': 'email@domain.com',
            'message': 'message content',
            'message_type': 'message' or 'systemEventMessage'
        },
        ...
    ],
    'total_messages': count,
    'note': 'Optional note about permissions/license requirements'
}
```

#### `get_online_meeting_id_from_join_url(join_url)`
Helper method to extract the online meeting ID from a Teams meeting join URL.

### 2. `/teams_integration/utils/sync_services.py`

**Modified Method:** `sync_meeting_chat(conference)`

**Changes:**
- Removed placeholder implementation
- Added actual API call to fetch transcript/chat messages
- Implemented message processing and storage logic
- Added user matching by email
- Added duplicate detection using `platform_message_id`
- Stores messages in `ConferenceChat` model
- Handles errors gracefully and logs detailed information

**Processing Logic:**
1. Validates conference has a meeting ID
2. Gets user email for API authentication
3. Calls `get_meeting_transcript()` to fetch messages
4. Processes each message:
   - Extracts sender name, email, message content, timestamp
   - Matches sender to LMS user by email
   - Checks for existing messages using `platform_message_id`
   - Creates new messages or updates existing ones
5. Updates sync status with counts (created, updated, processed)
6. Marks chat as synced in `TeamsMeetingSync` record

## Required API Permissions

To enable chat sync, the Azure AD application needs these Microsoft Graph API permissions:

### Option 1: Transcript API (Recommended for Teams Premium)
- **Permission**: `OnlineMeetings.Read.All` (Application)
- **Admin Consent**: Required
- **License Requirement**: Teams Premium with meeting transcription enabled

### Option 2: Chat API (Alternative)
- **Permission**: `Chat.Read.All` (Application)
- **Admin Consent**: Required
- **License Requirement**: Standard Teams license

### Current Required Permissions (Already Configured)
- `User.Read.All` - Read user profiles
- `Calendars.ReadWrite` - Create and manage meetings
- `OnlineMeetings.ReadWrite.All` - Create and manage online meetings

## Setup Instructions

### 1. Add Required API Permissions in Azure Portal

1. Go to Azure Portal → Azure Active Directory → App registrations
2. Select your LMS application
3. Go to "API permissions"
4. Click "Add a permission"
5. Select "Microsoft Graph"
6. Select "Application permissions"
7. Add one or both:
   - `OnlineMeetings.Read.All` (for transcripts)
   - `Chat.Read.All` (for chat messages)
8. Click "Grant admin consent for [Your Organization]"

### 2. Verify Dependencies

Ensure these Python packages are installed:
```bash
pip install python-dateutil  # For timestamp parsing
```

### 3. Test the Chat Sync

#### Manual Sync via Django Shell:
```python
from conferences.models import Conference
from teams_integration.tasks import sync_meeting_data

# Get a conference with a Teams meeting
conference = Conference.objects.get(id=46)

# Trigger sync
result = sync_meeting_data(conference.id)
print(result)
```

#### Automatic Sync via Scheduled Task:
The chat sync will automatically run when the `sync_teams_data` Celery task executes (configured in `/teams_integration/tasks.py`).

### 4. Verify Chat Messages

Check if messages were synced:
```python
from conferences.models import Conference, ConferenceChat

conference = Conference.objects.get(id=46)
chat_messages = conference.chat_messages.all()
print(f"Total messages: {chat_messages.count()}")

# View messages
for msg in chat_messages[:10]:
    print(f"{msg.sender_name}: {msg.message_text[:50]}")
```

## Limitations and Notes

### 1. API Availability
- **Transcripts**: Only available for meetings with transcription enabled (Teams Premium)
- **Chat**: Only available if meeting has an associated chat thread
- If neither is available, the sync will complete successfully but retrieve 0 messages

### 2. Historical Data
- Can only sync chat data that is still available in Teams
- Microsoft may have retention policies that limit historical data
- Meetings must be completed and recorded for transcripts to be available

### 3. Meeting ID Format
- The `conference.meeting_id` must be the **online meeting ID**, not the calendar event ID
- Online meeting IDs can be extracted from the join URL

### 4. User Matching
- Users are matched by email address
- If a sender's email doesn't match any LMS user, the message is still saved with `sender=None` and `sender_name` populated

### 5. Message Updates
- Messages are identified by `platform_message_id`
- If a message with the same ID already exists, it will be updated
- This prevents duplicate messages on repeated syncs

## Troubleshooting

### Chat History Still Shows (0)

**Check 1: Verify API Permissions**
```python
from account_settings.models import TeamsIntegration

integration = TeamsIntegration.objects.filter(is_active=True).first()
result = integration.api_client.test_connection()
print(result)
```

**Check 2: Check Sync Logs**
```python
from teams_integration.models import TeamsMeetingSync

sync = TeamsMeetingSync.objects.filter(conference_id=46).first()
print(f"Chat synced: {sync.chat_synced}")
print(f"Last sync: {sync.last_chat_sync}")
print(f"Errors: {sync.sync_errors}")
```

**Check 3: View Application Logs**
```bash
tail -f /home/ec2-user/lms/logs/lms.log | grep -i "chat"
```

### Error: "No user email available"
- Ensure the Teams integration has a user assigned with a valid email
- Or configure a `service_account_email` on the TeamsIntegration model

### Error: "403 Forbidden"
- Missing API permissions in Azure AD
- Admin consent not granted
- Verify permissions in Azure Portal

### Error: "404 Not Found"
- Meeting ID may be invalid
- Meeting may not have transcription enabled
- Meeting may not have an associated chat thread

## Testing the Fix

### 1. Create a Test Meeting
```python
from conferences.models import Conference
from datetime import datetime, timedelta
from django.utils import timezone

conference = Conference.objects.create(
    title="Test Chat Sync Meeting",
    meeting_platform='teams',
    start_time=timezone.now(),
    end_time=timezone.now() + timedelta(hours=1),
    created_by=your_user
)
```

### 2. Conduct the Meeting
- Join the meeting in Teams
- Send chat messages during the meeting
- Enable transcription if testing transcript API

### 3. Sync the Chat
```python
from teams_integration.tasks import sync_meeting_data

result = sync_meeting_data(conference.id)
print(f"Success: {result['success']}")
print(f"Messages created: {result['created']}")
```

### 4. Verify on Frontend
Visit: https://vle.nexsy.io/conferences/{conference_id}/
The "Chat History" tab should now show the synced messages with a count > 0.

## Frontend Display

Chat messages are displayed in these templates:
- `/conferences/templates/conferences/conference_detail_instructor.html` - Instructor view
- `/conferences/templates/conferences/detailed_report_comprehensive.html` - Detailed report

The chat count is shown as: **Chat History (X)** where X is the number of messages.

## Maintenance

### Regular Sync Schedule
Configure Celery beat to run periodic syncs:
```python
# In settings.py or celery.py
CELERY_BEAT_SCHEDULE = {
    'sync-teams-meetings-daily': {
        'task': 'teams_integration.tasks.sync_teams_data',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'args': (integration_id, 'meetings', 'from_teams'),
    },
}
```

### Monitor Sync Health
```python
from conferences.models import Conference, ConferenceChat
from teams_integration.models import TeamsMeetingSync

# Check conferences with missing chat data
teams_conferences = Conference.objects.filter(meeting_platform='teams')
for conf in teams_conferences:
    chat_count = conf.chat_messages.count()
    sync = TeamsMeetingSync.objects.filter(conference=conf).first()
    
    if sync and sync.chat_synced and chat_count == 0:
        print(f"Conference {conf.id}: Synced but 0 messages - may need attention")
```

## Summary

This fix implements full Teams meeting chat synchronization by:
1. Adding Microsoft Graph API integration for transcripts and chat messages
2. Implementing proper message fetching, processing, and storage
3. Providing graceful error handling and detailed logging
4. Supporting both transcript API (Teams Premium) and chat API (Standard)

The chat history will now properly sync and display on conference detail pages, resolving the "(0)" count issue.

