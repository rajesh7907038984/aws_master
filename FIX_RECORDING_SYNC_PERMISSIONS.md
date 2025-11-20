# Fix Recording Sync - Missing OneDrive Permission

## Issue
Recordings are created in OneDrive but cannot be synced to LMS due to missing permission.

**Error**: `HTTP 403: Access denied` when accessing OneDrive

## Root Cause
The Azure App Registration is missing the `Files.Read.All` permission needed to access OneDrive recordings.

## Solution

### Step 1: Add Files.Read.All Permission

1. Go to: https://portal.azure.com
2. Navigate to: **Azure Active Directory** > **App registrations**
3. Select your app: **"testing"** (Application ID: ac65128a-1b39-4563-bffe-42a356c173dd)
4. Click: **API permissions** (in left menu)
5. Click: **Add a permission**
6. Select: **Microsoft Graph**
7. Select: **Application permissions**
8. Search for: `Files.Read.All`
9. Check the box next to: **Files.Read.All**
   - Description: "Read files in all site collections"
10. Click: **Add permissions**

### Step 2: Grant Admin Consent

After adding the permission:

1. Click: **Grant admin consent for Nexsy Ltd**
2. Confirm: Click **Yes**
3. Wait for status to show: **Granted for Nexsy Ltd** with green checkmark ✅

### Step 3: Verify Permissions

Your app should now have these permissions:

- ✅ `Calendars.ReadWrite` - Create meetings
- ✅ `OnlineMeetings.ReadWrite.All` - Enable recording (**YOU HAVE THIS**)
- ✅ `OnlineMeetingRecording.Read.All` - Read recordings (**YOU HAVE THIS**)
- ✅ `OnlineMeetingTranscript.Read.All` - Read transcripts (**YOU HAVE THIS**)
- ✅ `Files.Read.All` - Access OneDrive files (**MISSING - ADD THIS**)
- ✅ `Group.Read.All` - Read groups (**YOU HAVE THIS**)
- ✅ `User.Read.All` - Read users (**YOU HAVE THIS**)

### Step 4: Test the Sync Again

After adding the permission, run:

```bash
cd /home/ec2-user/lms
python3 manage.py sync_conference_data --conference-id 46 --force
```

You should see:
```
✓ Found X recordings in OneDrive
✓ Created new recording: Conference 1 - 2025-11-19...
```

### Step 5: Verify in LMS

1. Go to: https://vle.nexsy.io/conferences/46/
2. Click on: **Recordings (0)** tab
3. Should now show: **Recordings (1)** ✅
4. Recording should be available for download

## Why This Permission Is Needed

- **OnlineMeetings.ReadWrite.All**: Creates the meeting and enables recording ✅ (You have this)
- **OnlineMeetingRecording.Read.All**: Allows reading recording metadata ✅ (You have this)
- **Files.Read.All**: Allows accessing the actual recording files in OneDrive ❌ (You need this)

When a Teams meeting is recorded, the video file is stored in OneDrive. To sync and download these recordings, the app needs permission to read files from OneDrive.

## Alternative Solution (If Can't Add Permission)

If you cannot add `Files.Read.All` permission due to organizational policies, you can:

1. Use **delegated permissions** instead of application permissions
2. Or manually provide direct links to recordings
3. Or use Teams admin credentials with proper OneDrive access

## Quick Checklist

- [ ] Add `Files.Read.All` permission in Azure Portal
- [ ] Grant admin consent
- [ ] Verify green checkmark next to permission
- [ ] Run sync command again
- [ ] Check recordings appear in LMS

## Support

If you still see the error after adding the permission:

1. **Wait 5-10 minutes** - Permission changes may take time to propagate
2. **Restart gunicorn** - `sudo systemctl restart gunicorn`
3. **Check Azure logs** - Review sign-in logs in Azure AD
4. **Verify service account** - Ensure the service account email has OneDrive access

## Related Documentation

- [Mandatory Auto-Recording](MANDATORY_AUTO_RECORDING.md)
- [Teams Recording Setup](TEAMS_RECORDING_SETUP.md)
- [Teams Recording Implementation](TEAMS_RECORDING_IMPLEMENTATION_SUMMARY.md)

---

**Status**: Awaiting `Files.Read.All` permission
**Priority**: High - Blocks recording sync functionality
**ETA**: 5 minutes after adding permission

