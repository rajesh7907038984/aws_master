# Microsoft Teams Conference Bugs Report
## Conference ID: 52 (https://vle.nexsy.io/conferences/52/)

Date: November 23, 2025
Project: LMS - Microsoft Teams Conference Integration

---

## Executive Summary

Analysis of the Microsoft Teams conference integration reveals **5 CRITICAL BUGS** affecting the Sync Data functionality, Total Time calculation, Chat History, and Recordings tabs. These bugs prevent proper data synchronization and display for Teams meetings.

---

## 🔴 BUG #1: Total Time (min) NOT CALCULATED - CRITICAL

### Location
- **File**: `/home/ec2-user/lms/teams_integration/utils/sync_services.py`
- **Function**: `_process_attendee()` (lines 164-199)
- **Also affects**: `teams_api.py` `get_meeting_attendance()` (lines 402-460)

### Problem Description
The Teams attendance sync **NEVER calculates or stores duration_minutes**. The code only sets:
- `attendance_status = 'present'`
- `join_time = timezone.now()` (WRONG - should be actual meeting time)
- **MISSING**: `duration_minutes` (never set)
- **MISSING**: `leave_time` (never set)

### Root Cause
1. The `get_meeting_attendance()` API call in `teams_api.py` only fetches **calendar attendees** (who was invited), NOT actual meeting attendance report with join/leave times
2. The API endpoint used is: `/users/{email}/events/{meeting_id}` which returns:
   - Attendee emails
   - Attendee names  
   - Response status (accepted/declined)
   - **BUT NO ACTUAL ATTENDANCE DATA** (no join times, leave times, duration)

3. Microsoft Graph API requires a **DIFFERENT endpoint** to get actual attendance:
   - Should use: `/communications/callRecords/{id}` (requires CallRecords.Read.All permission)
   - Or: `/users/{userId}/onlineMeetings/{meetingId}/attendanceReports` (requires OnlineMeetingArtifact.Read.All)

### Current Buggy Code
```python
# sync_services.py - Lines 175-189
attendance, created = ConferenceAttendance.objects.get_or_create(
    conference=conference,
    user=user,
    defaults={
        'participant_id': attendee.get('email'),
        'attendance_status': 'present',
        'join_time': timezone.now()  # ❌ WRONG: Uses current time, not actual join time
        # ❌ MISSING: duration_minutes
        # ❌ MISSING: leave_time
    }
)

if not created:
    # Update existing attendance
    attendance.attendance_status = 'present'
    attendance.join_time = timezone.now()  # ❌ WRONG AGAIN
    # ❌ MISSING: duration_minutes still not set
    attendance.save()
```

### Impact
- **Total Time (min)** column shows **0** for all Teams meeting attendees
- Attendance reports are inaccurate
- Rubric evaluations based on attendance time are broken
- Statistics calculations are wrong

### Fix Required
```python
def _process_attendee(self, conference, attendee):
    """Process a single meeting attendee WITH DURATION"""
    try:
        # Find user by email
        user = CustomUser.objects.filter(email=attendee['email']).first()
        
        if not user:
            logger.warning(f"User not found for email: {attendee['email']}")
            return
        
        # ✅ FIX: Extract actual attendance data
        join_time = attendee.get('join_time')  # Need to get from attendance report
        leave_time = attendee.get('leave_time')  # Need to get from attendance report
        duration_seconds = attendee.get('duration', 0)  # Need to get from attendance report
        duration_minutes = duration_seconds // 60 if duration_seconds else 0
        
        # Create or update attendance record
        attendance, created = ConferenceAttendance.objects.get_or_create(
            conference=conference,
            user=user,
            defaults={
                'participant_id': attendee.get('email'),
                'attendance_status': 'present',
                'join_time': join_time,
                'leave_time': leave_time,
                'duration_minutes': duration_minutes  # ✅ NOW SET
            }
        )
        
        if not created:
            # Update existing attendance with actual data
            attendance.attendance_status = 'present'
            if join_time:
                attendance.join_time = join_time
            if leave_time:
                attendance.leave_time = leave_time
            attendance.duration_minutes = max(duration_minutes, attendance.duration_minutes)  # Keep highest
            attendance.save()
        
        self.log_sync_result(
            f"process_attendee_{attendee['email']}", 
            True, 
            f"Processed attendee: {attendee['name']} - Duration: {duration_minutes}min"
        )
        
    except Exception as e:
        logger.error(f"Error processing attendee {attendee.get('email', 'unknown')}: {str(e)}")
        raise
```

### API Changes Required
```python
def get_meeting_attendance_report(self, online_meeting_id, user_email=None):
    """
    Get ACTUAL meeting attendance data with join/leave times and duration
    
    Args:
        online_meeting_id: Teams online meeting ID (not calendar event ID)
        user_email: Meeting organizer's email
        
    Returns:
        dict: Actual attendance data with durations
    """
    try:
        if not user_email and self.integration.user and self.integration.user.email:
            user_email = self.integration.user.email
        
        if not user_email:
            raise TeamsAPIError("User email required for attendance reports")
        
        # ✅ CORRECT API: Get attendance reports
        endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}/attendanceReports'
        response = self._make_request('GET', endpoint)
        
        reports = response.get('value', [])
        
        if not reports:
            logger.warning("No attendance reports available for this meeting")
            return {
                'success': True,
                'attendees': [],
                'note': 'No attendance report available yet. Reports are generated after meeting ends.'
            }
        
        # Get the latest attendance report
        latest_report = reports[0]
        report_id = latest_report.get('id')
        
        # Get detailed attendance records
        attendance_endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}/attendanceReports/{report_id}/attendanceRecords'
        attendance_response = self._make_request('GET', attendance_endpoint)
        
        attendance_records = attendance_response.get('value', [])
        
        # Process attendance records
        attendance_data = []
        for record in attendance_records:
            # Parse join and leave times
            join_time = None
            leave_time = None
            duration_seconds = 0
            
            if record.get('attendanceIntervals'):
                # Calculate total duration from all intervals
                for interval in record['attendanceIntervals']:
                    join_dt = datetime.fromisoformat(interval['joinDateTime'].replace('Z', '+00:00'))
                    leave_dt = datetime.fromisoformat(interval['leaveDateTime'].replace('Z', '+00:00'))
                    
                    if not join_time or join_dt < join_time:
                        join_time = join_dt
                    if not leave_time or leave_dt > leave_time:
                        leave_time = leave_dt
                    
                    interval_duration = (leave_dt - join_dt).total_seconds()
                    duration_seconds += interval_duration
            
            attendance_data.append({
                'email': record.get('emailAddress'),
                'name': record.get('identity', {}).get('displayName'),
                'join_time': join_time,
                'leave_time': leave_time,
                'duration': int(duration_seconds),
                'role': record.get('role'),
                'total_attendance_seconds': record.get('totalAttendanceInSeconds', 0)
            })
        
        return {
            'success': True,
            'attendees': attendance_data,
            'total_attendees': len(attendance_data),
            'report_id': report_id
        }
        
    except TeamsAPIError as e:
        return {
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        logger.error(f"Error getting meeting attendance report: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
```

---

## 🔴 BUG #2: Chat History (0) - NO DATA SYNCING

### Location
- **File**: `/home/ec2-user/lms/teams_integration/utils/sync_services.py`
- **Function**: `sync_meeting_chat()` (lines 359-578)

### Problem Description
Chat messages are **NOT being retrieved** from Teams meetings. The tab shows "Chat History (0)" even after sync.

### Root Cause
The API call `get_meeting_transcript()` tries to fetch chat/transcript data but:

1. **Requires premium Teams license** for transcription (not all tenants have this)
2. **Requires additional API permissions**:
   - `OnlineMeetings.Read.All` (for transcripts)
   - `Chat.Read.All` (for chat messages)
   
3. **Missing chat thread ID**: The code tries to get `chatInfo.threadId` from the meeting but this may not exist if:
   - Meeting hasn't occurred yet
   - Chat wasn't used during meeting
   - API permissions are insufficient

4. **Wrong API endpoint sequence**: Code tries transcripts first, then falls back to chat, but both can fail

### Current Flow Issues
```python
# Line 460: Tries to get transcript (requires premium)
transcript_result = self.api.get_meeting_transcript(
    online_meeting_id,
    user_email=user_email
)

# If transcript fails (which it usually does without premium), 
# falls back to chat messages, but this also requires permissions
# that may not be granted
```

### Error Messages Seen
```
"No transcript or chat data available. This may require additional API permissions (OnlineMeetings.Read.All, Chat.Read.All) or Teams Premium license for transcription."
```

### Fix Required

**Option 1: Use Meeting Chat API (Recommended)**
```python
def get_meeting_chat_messages(self, online_meeting_id, user_email=None):
    """
    Get chat messages from Teams meeting (works without premium)
    
    Requires: Chat.Read.All or Chat.ReadWrite.All permission
    """
    try:
        if not user_email and self.integration.user and self.integration.user.email:
            user_email = self.integration.user.email
        
        # Step 1: Get online meeting details to find chat thread
        meeting_endpoint = f'/users/{user_email}/onlineMeetings/{online_meeting_id}'
        meeting_details = self._make_request('GET', meeting_endpoint)
        
        # Step 2: Extract chat thread ID
        chat_info = meeting_details.get('chatInfo', {})
        thread_id = chat_info.get('threadId')
        
        if not thread_id:
            logger.info("No chat thread found for this meeting")
            return {
                'success': True,
                'messages': [],
                'note': 'No chat thread available. Chat may not have been used during this meeting.'
            }
        
        # Step 3: Get chat messages
        chat_endpoint = f'/chats/{thread_id}/messages'
        params = {
            '$top': 50,  # Limit messages
            '$orderby': 'createdDateTime desc'
        }
        
        response = self._make_request('GET', chat_endpoint, params=params)
        
        messages = response.get('value', [])
        
        # Process messages
        chat_data = []
        for msg in messages:
            # Skip system messages
            if msg.get('messageType') != 'message':
                continue
            
            chat_data.append({
                'id': msg.get('id'),
                'created': msg.get('createdDateTime'),
                'sender': msg.get('from', {}).get('user', {}).get('displayName', 'Unknown'),
                'sender_email': msg.get('from', {}).get('user', {}).get('userPrincipalName'),
                'message': msg.get('body', {}).get('content', ''),
                'message_type': msg.get('messageType'),
            })
        
        return {
            'success': True,
            'messages': chat_data,
            'total_messages': len(chat_data),
            'thread_id': thread_id
        }
        
    except Exception as e:
        logger.error(f"Error getting meeting chat: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
```

**Option 2: Check and Report Missing Permissions**
```python
def check_teams_permissions(self):
    """
    Check which Teams API permissions are available
    """
    required_permissions = {
        'chat': 'Chat.Read.All',
        'attendance': 'OnlineMeetingArtifact.Read.All',
        'transcripts': 'OnlineMeetings.Read.All',
        'calendar': 'Calendars.ReadWrite',
    }
    
    available_permissions = {}
    
    for feature, permission in required_permissions.items():
        try:
            # Try a test API call for each permission
            if feature == 'chat':
                # Test chat access
                test_endpoint = '/chats'
                self._make_request('GET', test_endpoint, params={'$top': 1})
                available_permissions[feature] = True
            # ... test other permissions
            
        except Exception as e:
            available_permissions[feature] = False
            logger.warning(f"Permission {permission} not available: {str(e)}")
    
    return available_permissions
```

---

## 🔴 BUG #3: Recordings (0) - DURATION NOT CALCULATED

### Location
- **File**: `/home/ec2-user/lms/teams_integration/utils/sync_services.py`
- **Function**: `sync_meeting_recordings()` (lines 201-357)

### Problem Description
Recordings are synced from OneDrive but **duration_minutes is always 0**. The code explicitly sets:
```python
duration_minutes = 0  # Line 292 - HARDCODED TO ZERO
```

### Root Cause
Line 292 hardcodes duration to 0:
```python
# Extract duration from file name if possible (format: Meeting-YYYYMMDD-HHMMSS.mp4)
duration_minutes = 0  # ❌ HARDCODED - NO CALCULATION ATTEMPTED
```

The comment suggests duration should be extracted from filename, but **NO CODE ACTUALLY DOES THIS**.

### Current Buggy Code
```python
for recording_data in recordings:
    try:
        recording_id = recording_data.get('id')
        
        # Extract duration from file name if possible (format: Meeting-YYYYMMDD-HHMMSS.mp4)
        duration_minutes = 0  # ❌ BUG: Hardcoded to 0
        
        # Create or update recording
        recording, created = ConferenceRecording.objects.update_or_create(
            conference=conference,
            recording_id=f"onedrive_{recording_id}",
            defaults={
                'title': recording_data.get('name', 'Meeting Recording'),
                'recording_type': 'cloud',
                'file_url': recording_data.get('webUrl'),
                'file_size': recording_data.get('size', 0),
                'duration_minutes': duration_minutes,  # ❌ ALWAYS 0
                # ...
            }
        )
```

### Fix Required

**Option 1: Extract from OneDrive Video Metadata**
```python
def get_video_duration_from_onedrive(self, drive_id, item_id):
    """
    Get video duration from OneDrive file metadata
    """
    try:
        endpoint = f'/drives/{drive_id}/items/{item_id}'
        params = {
            '$select': 'id,name,size,video'
        }
        
        response = self._make_request('GET', endpoint, params=params)
        
        video_metadata = response.get('video', {})
        duration_ms = video_metadata.get('duration', 0)
        duration_minutes = duration_ms // 60000  # Convert milliseconds to minutes
        
        return duration_minutes
        
    except Exception as e:
        logger.warning(f"Could not get video duration: {str(e)}")
        return 0
```

**Option 2: Parse from Stream Recording Metadata**
```python
def sync_meeting_recordings(self, conference):
    # ... existing code ...
    
    for recording_data in recordings:
        try:
            recording_id = recording_data.get('id')
            drive_id = recordings_result.get('drive_id')
            
            # ✅ FIX: Get actual video duration from metadata
            duration_minutes = 0
            
            # Try to get duration from OneDrive video metadata
            if drive_id and recording_id:
                try:
                    from teams_integration.utils.onedrive_api import OneDriveAPI
                    onedrive_api = OneDriveAPI(self.config)
                    
                    # Get video metadata
                    video_info = onedrive_api.get_video_metadata(drive_id, recording_id)
                    if video_info.get('success'):
                        duration_minutes = video_info.get('duration_minutes', 0)
                        logger.info(f"Retrieved video duration: {duration_minutes} minutes")
                except Exception as e:
                    logger.warning(f"Could not get video duration: {str(e)}")
            
            # Fallback: Try to parse from filename if available
            if duration_minutes == 0:
                filename = recording_data.get('name', '')
                # Parse filename patterns like "Meeting Recording 2024-11-23 14-30-15.mp4"
                # or extract from file metadata if available
                pass
            
            # Create or update recording WITH DURATION
            recording, created = ConferenceRecording.objects.update_or_create(
                conference=conference,
                recording_id=f"onedrive_{recording_id}",
                defaults={
                    'title': recording_data.get('name', 'Meeting Recording'),
                    'recording_type': 'cloud',
                    'file_url': recording_data.get('webUrl'),
                    'file_size': recording_data.get('size', 0),
                    'duration_minutes': duration_minutes,  # ✅ NOW HAS ACTUAL DURATION
                    # ... rest of fields
                }
            )
```

---

## 🔴 BUG #4: Sync Data Function - INCOMPLETE ERROR HANDLING

### Location
- **File**: `/home/ec2-user/lms/conferences/views.py`
- **Function**: `sync_teams_meeting_data()` (lines 2757-2897)

### Problem Description
The sync function returns "success" even when critical operations fail, making debugging impossible.

### Current Issues
```python
# Lines 2852: Marks as successful if at least ONE operation succeeds
results['success'] = at_least_one_success or results['items_processed'] == 0

# Lines 2867-2868: Treats "no data" as success
elif not at_least_one_success and results['items_processed'] == 0:
    results['warning'] = "No data available to sync..."
```

### Problems
1. If attendance fails but recordings succeed → returns `success: True` (misleading)
2. If all operations fail due to permissions → returns `success: True` with warning (should be error)
3. No clear indication of **WHICH** operations failed and **WHY**
4. UI shows "Sync successful" even when 75% of data failed to sync

### Fix Required
```python
def sync_teams_meeting_data(conference):
    """Sync meeting data from Microsoft Teams with CLEAR error reporting"""
    try:
        # ... existing code ...
        
        # Sync recordings (OneDrive)
        logger.info("📹 Syncing recordings from OneDrive...")
        recording_results = meeting_sync.sync_meeting_recordings(conference)
        results['items_processed'] += recording_results.get('processed', 0)
        results['details']['recordings'] = {
            'created': recording_results.get('created', 0),
            'updated': recording_results.get('updated', 0),
            'success': recording_results.get('success', False),
            'error': recording_results.get('error') if not recording_results.get('success') else None
        }
        
        # Sync attendance WITH DURATION
        logger.info("👥 Syncing attendance with duration...")
        attendance_results = meeting_sync.sync_meeting_attendance(conference)
        results['items_processed'] += attendance_results.get('processed', 0)
        results['details']['attendance'] = {
            'processed': attendance_results.get('processed', 0),
            'success': attendance_results.get('success', False),
            'error': attendance_results.get('error') if not attendance_results.get('success') else None
        }
        
        # Sync chat
        logger.info("💬 Syncing chat messages...")
        chat_results = meeting_sync.sync_meeting_chat(conference)
        results['items_processed'] += chat_results.get('processed', 0)
        results['details']['chat'] = {
            'processed': chat_results.get('processed', 0),
            'success': chat_results.get('success', False),
            'error': chat_results.get('error') if not chat_results.get('success') else None
        }
        
        # Sync files
        logger.info("📎 Syncing shared files...")
        file_results = meeting_sync.sync_meeting_files(conference)
        results['items_processed'] += file_results.get('processed', 0)
        results['details']['files'] = {
            'processed': file_results.get('processed', 0),
            'success': file_results.get('success', False),
            'error': file_results.get('error') if not file_results.get('success') else None
        }
        
        # ✅ FIX: More strict success criteria
        successful_count = sum([
            1 for op in ['recordings', 'attendance', 'chat', 'files']
            if results['details'][op]['success']
        ])
        
        # Consider sync successful only if:
        # 1. At least 2 operations succeeded (50%)
        # 2. OR all operations had no data (meeting hasn't occurred)
        no_data = all([
            results['details'][op]['processed'] == 0
            for op in ['recordings', 'attendance', 'chat', 'files']
        ])
        
        results['success'] = successful_count >= 2 or no_data
        results['success_rate'] = f"{successful_count}/4 operations succeeded"
        
        # Build DETAILED error messages
        if successful_count < 4:
            failed_ops = [
                op for op in ['recordings', 'attendance', 'chat', 'files']
                if not results['details'][op]['success']
            ]
            
            error_details = []
            for op in failed_ops:
                error_msg = results['details'][op].get('error', 'Unknown error')
                error_details.append(f"{op}: {error_msg}")
            
            results['failed_operations'] = failed_ops
            results['error_details'] = error_details
            results['warning'] = f"Partial sync: {', '.join(failed_ops)} failed. {'; '.join(error_details)}"
        
        # Log with clear success/failure indication
        if successful_count == 4:
            logger.info(f"✅ ALL Teams data synced successfully for conference {conference.id}")
        elif successful_count >= 2:
            logger.warning(f"⚠️ PARTIAL Teams data sync for conference {conference.id}: {successful_count}/4 operations succeeded")
            logger.warning(f"   Failed operations: {', '.join(results.get('failed_operations', []))}")
        else:
            logger.error(f"❌ Teams data sync MOSTLY FAILED for conference {conference.id}: Only {successful_count}/4 operations succeeded")
            for detail in results.get('error_details', []):
                logger.error(f"   {detail}")
        
        return results
```

---

## 🔴 BUG #5: Missing API Permissions - ROOT CAUSE

### Location
- **All Teams API calls**

### Problem Description
The Microsoft Graph API permissions required for full functionality are **NOT GRANTED** or **NOT DOCUMENTED**.

### Required Permissions NOT Configured

| Feature | Required Permission | Status | Impact |
|---------|-------------------|--------|---------|
| Attendance Reports | `OnlineMeetingArtifact.Read.All` | ❌ Missing | Can't get duration/times |
| Chat Messages | `Chat.Read.All` | ❌ Missing | Chat History (0) |
| Call Records | `CallRecords.Read.All` | ❌ Missing | Can't get detailed attendance |
| Meeting Recordings | `Files.Read.All` | ✅ Likely works | OneDrive access |
| Calendar Events | `Calendars.ReadWrite` | ✅ Works | Can create meetings |

### Fix Required

**1. Update Azure AD App Permissions**
```
Go to Azure Portal → App Registrations → Your App → API Permissions

Add these Application Permissions:
1. Microsoft Graph → OnlineMeetingArtifact.Read.All
2. Microsoft Graph → Chat.Read.All  
3. Microsoft Graph → CallRecords.Read.All
4. Microsoft Graph → OnlineMeetings.Read.All

Then click "Grant admin consent for {your org}"
```

**2. Add Permission Checker**
```python
def validate_teams_permissions(integration):
    """
    Validate that all required permissions are granted
    """
    required_permissions = {
        'attendance': 'OnlineMeetingArtifact.Read.All',
        'chat': 'Chat.Read.All',
        'recordings': 'Files.Read.All',
        'calendar': 'Calendars.ReadWrite',
        'meetings': 'OnlineMeetings.Read.All',
    }
    
    missing_permissions = []
    
    from teams_integration.utils.teams_api import TeamsAPIClient
    api = TeamsAPIClient(integration)
    
    for feature, permission in required_permissions.items():
        if not api.test_permission(permission):
            missing_permissions.append(f"{feature} ({permission})")
    
    if missing_permissions:
        return {
            'valid': False,
            'missing_permissions': missing_permissions,
            'message': f"Missing permissions: {', '.join(missing_permissions)}. Please grant in Azure AD."
        }
    
    return {
        'valid': True,
        'message': 'All required permissions are granted'
    }
```

---

## 📊 Summary of Bugs

| Bug | Severity | Component | Impact | Status |
|-----|----------|-----------|--------|--------|
| #1 | 🔴 CRITICAL | Attendance Duration | Total Time always 0 | NOT FIXED |
| #2 | 🔴 CRITICAL | Chat Sync | Chat History (0) | NOT FIXED |
| #3 | 🔴 CRITICAL | Recording Duration | Duration always 0 | NOT FIXED |
| #4 | 🟡 HIGH | Sync Error Handling | Misleading success messages | NOT FIXED |
| #5 | 🔴 CRITICAL | API Permissions | All data sync failures | NOT CONFIGURED |

---

## 🛠️ Recommended Fix Priority

### Phase 1: API Permissions (MUST FIX FIRST)
1. Grant `OnlineMeetingArtifact.Read.All` permission in Azure AD
2. Grant `Chat.Read.All` permission in Azure AD
3. Grant `CallRecords.Read.All` permission in Azure AD
4. Test permissions with `test_connection()` API

### Phase 2: Attendance Duration Fix
1. Update `get_meeting_attendance()` to use attendance reports API
2. Update `_process_attendee()` to store duration, join_time, leave_time
3. Update `sync_meeting_attendance()` to call new API
4. Test with real Teams meeting

### Phase 3: Chat Messages Fix
1. Implement `get_meeting_chat_messages()` using Chat API
2. Update `sync_meeting_chat()` to use new method
3. Handle missing chat thread gracefully
4. Test with meeting that has chat messages

### Phase 4: Recording Duration Fix
1. Implement `get_video_duration_from_onedrive()`
2. Update `sync_meeting_recordings()` to fetch video metadata
3. Parse duration from OneDrive video properties
4. Test with real recording

### Phase 5: Error Handling Improvements
1. Update `sync_teams_meeting_data()` with stricter success criteria
2. Add detailed error reporting
3. Update UI to show partial sync status
4. Add permission validation checks

---

## 🧪 Testing Checklist

After fixes are implemented, test:

- [ ] Create a Teams meeting via LMS
- [ ] Join the meeting with 2-3 test users
- [ ] Stay in meeting for different durations (5min, 10min, 15min)
- [ ] Send chat messages during meeting
- [ ] Record the meeting
- [ ] End the meeting
- [ ] Wait 30 minutes (for Teams to generate reports)
- [ ] Click "Sync Data" button
- [ ] Verify Total Time shows correct minutes for each attendee
- [ ] Verify Chat History shows messages
- [ ] Verify Recordings shows correct duration
- [ ] Check detailed sync log for errors

---

## 📝 Additional Notes

### Why Teams is Different from Zoom

Zoom provides:
- ✅ Detailed participant reports immediately after meeting
- ✅ Join/leave times for each participant
- ✅ Duration calculated automatically
- ✅ Chat logs included in reports
- ✅ Recording metadata with duration

Teams provides:
- ❌ Attendance reports generated AFTER meeting (delay)
- ❌ Requires premium license for some features
- ❌ Multiple API calls needed to get complete data
- ❌ Chat requires separate API with different permissions
- ❌ Recordings stored in OneDrive/Stream (different APIs)

### Meeting Organizer Requirements

For Teams sync to work properly:
1. Meeting must be created by user with valid Teams license
2. Meeting must have online meeting ID (not just calendar event)
3. Attendance tracking must be enabled in Teams meeting settings
4. Recording must be enabled and stored in OneDrive
5. Chat must be enabled during meeting

### Debugging Commands

```bash
# Check conference details
python manage.py shell
from conferences.models import Conference
conf = Conference.objects.get(id=52)
print(f"Meeting ID: {conf.meeting_id}")
print(f"Online Meeting ID: {conf.online_meeting_id}")
print(f"Meeting Link: {conf.meeting_link}")
print(f"Sync Status: {conf.data_sync_status}")

# Check attendance records
from conferences.models import ConferenceAttendance
attendances = ConferenceAttendance.objects.filter(conference_id=52)
for att in attendances:
    print(f"{att.user.email}: {att.duration_minutes} minutes")

# Check chat messages
from conferences.models import ConferenceChat
chats = ConferenceChat.objects.filter(conference_id=52)
print(f"Total chat messages: {chats.count()}")

# Check recordings
from conferences.models import ConferenceRecording
recordings = ConferenceRecording.objects.filter(conference_id=52)
for rec in recordings:
    print(f"{rec.title}: {rec.duration_minutes} minutes")
```

---

## Contact & Support

For implementation assistance:
- Check Azure AD App Registration permissions
- Review Microsoft Graph API documentation: https://learn.microsoft.com/en-us/graph/api/resources/onlinemeeting
- Test API calls using Graph Explorer: https://developer.microsoft.com/en-us/graph/graph-explorer

---

**Report Generated**: November 23, 2025
**Reviewed By**: AI Code Analyzer
**Status**: Awaiting fixes and testing

