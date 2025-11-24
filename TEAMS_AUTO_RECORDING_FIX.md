# Microsoft Teams Automatic Recording - Fix Documentation

## Problem
Teams meetings were not automatically starting recording. Users had to manually click "Start recording" in the meeting interface.

## Root Causes Identified

### 1. **Bug: Wrong Meeting ID Format** ✅ FIXED
- **Issue**: Code was using thread ID (`19:meeting_XXX@thread.v2`) instead of GUID for recording API calls
- **Impact**: Recording enablement API calls were failing silently
- **Fix**: Now correctly uses GUID from calendar event for API calls, while preserving thread ID for attendance/chat sync

### 2. **Recording Not Set During Creation** ✅ FIXED
- **Issue**: Recording was only attempted via PATCH after meeting creation
- **Impact**: Less reliable, could fail if PATCH call fails
- **Fix**: Now sets `recordAutomatically: True` during meeting creation AND via PATCH as backup

### 3. **Missing Verification** ✅ FIXED
- **Issue**: No verification that recording was actually enabled
- **Impact**: Could report success even if recording wasn't enabled
- **Fix**: Added verification checks and better error reporting

## Changes Made

### File: `teams_integration/utils/teams_api.py`

1. **Enhanced `create_meeting()` method**:
   - Sets `recordAutomatically: True` AND `allowRecording: True` during meeting creation
   - Uses correct GUID format for API calls (not thread ID)
   - Verifies recording was set during creation
   - Falls back to PATCH method if creation didn't set it
   - Better error handling and logging

2. **Enhanced `enable_meeting_recording()` method**:
   - Validates ID format (rejects thread IDs)
   - Sets both `recordAutomatically` and `allowRecording` properties
   - Verifies response confirms recording is enabled
   - Better error messages for common issues

3. **New `verify_recording_enabled()` method**:
   - Allows checking if recording is actually enabled for a meeting
   - Useful for troubleshooting

## Important Notes

### Tenant-Level Configuration May Be Required

Even with these fixes, automatic recording might not work if:

1. **Tenant Policies Block Recording**:
   - Check Teams Admin Center → Meetings → Meeting Policies
   - Ensure "Allow cloud recording" is enabled
   - Ensure "Allow transcription" is enabled (if needed)

2. **User Permissions**:
   - Users need permission to record meetings
   - Check user's meeting policy assignments

3. **Teams Premium Required** (for some features):
   - Meeting templates with locked recording settings require Teams Premium
   - Automatic recording via API should work with standard Teams licenses

4. **API Permissions**:
   - Ensure Azure AD app has `OnlineMeetings.ReadWrite.All` permission
   - Admin consent must be granted

### How to Verify Recording is Enabled

1. **Check via API** (after meeting creation):
   ```python
   teams_client = TeamsAPIClient(integration)
   result = teams_client.verify_recording_enabled(online_meeting_id, user_email)
   print(result['recording_enabled'])  # Should be True
   ```

2. **Check in Teams UI**:
   - When meeting starts, recording should begin automatically
   - Look for recording indicator in meeting controls
   - Check meeting details - should show "Recording automatically"

3. **Check via Management Command**:
   ```bash
   python manage.py fix_teams_recording --conference-id 55 --enable-recording
   ```

## Testing

### For Existing Meetings:
```bash
# Check status
python manage.py fix_teams_recording --conference-id 55 --dry-run

# Fix and enable recording
python manage.py fix_teams_recording --conference-id 55 --enable-recording
```

### For New Meetings:
- All new Teams meetings created through the LMS will automatically have recording enabled
- Check the `recording_status` field in the API response
- Verify in Teams UI when meeting starts

## Troubleshooting

### If Recording Still Doesn't Start Automatically:

1. **Check Tenant Policies**:
   - Teams Admin Center → Meetings → Meeting Policies
   - Verify "Allow cloud recording" is enabled
   - Check if any policies restrict recording

2. **Check API Permissions**:
   - Azure AD → App registrations → Your app → API permissions
   - Verify `OnlineMeetings.ReadWrite.All` is granted with admin consent

3. **Check Meeting Response**:
   - Look at API response when creating meeting
   - Check if `onlineMeeting.recordAutomatically` is `true` in response

4. **Check Logs**:
   - Look for "✓ Auto-recording enabled successfully" messages
   - Check for any error messages about recording

5. **Verify User Has Recording Permission**:
   - User organizing meeting must have permission to record
   - Check user's assigned meeting policy

## Expected Behavior

After these fixes:
- ✅ New Teams meetings will have `recordAutomatically: True` set during creation
- ✅ Recording will be verified via PATCH if not set during creation
- ✅ Correct meeting ID format (GUID) is used for API calls
- ✅ Better error messages if recording fails to enable
- ✅ Verification method available to check recording status

## Next Steps

1. Test with a new meeting to verify recording starts automatically
2. If recording still doesn't start automatically, check tenant-level policies
3. Consider using Teams Premium meeting templates for additional control
4. Monitor logs for any recording-related errors

