# Microsoft Teams Auto-Recording and OneDrive Storage Setup Guide

## Overview

This guide explains how to set up automatic recording for Microsoft Teams meetings in your LMS, with recordings automatically stored in OneDrive and made available for download to users.

## Features

- ✅ **Automatic Recording**: Teams meetings are automatically recorded to the cloud
- ✅ **OneDrive Storage**: Recordings are stored in the configured admin's OneDrive
- ✅ **Automatic Sync**: Recordings are automatically synced to the LMS after meetings
- ✅ **Download Access**: Users can download recordings directly from the conference page
- ✅ **View Online**: Users can view recordings in OneDrive without downloading
- ✅ **Download Tracking**: System tracks how many times each recording is downloaded

## Prerequisites

### 1. Microsoft Teams Integration

You must have Microsoft Teams integration configured with the following permissions:

**Required Microsoft Graph API Permissions:**
- `Calendars.ReadWrite` - Create and manage meetings
- `OnlineMeetings.ReadWrite.All` - Enable recording settings
- `Files.Read.All` - Access OneDrive recordings
- `User.Read.All` - Access user OneDrive folders

### 2. OneDrive Configuration

The admin account whose credentials are used for Teams integration must have:
- An active Microsoft 365 license with OneDrive access
- Sufficient OneDrive storage space for recordings
- Teams recording feature enabled in Microsoft 365 admin center

### 3. Teams Recording Policy

Ensure that cloud recording is enabled in your Microsoft Teams admin center:
1. Go to Microsoft Teams admin center
2. Navigate to **Meetings** > **Meeting policies**
3. Enable **Cloud recording**
4. Enable **Recording automatically expires** (optional, for compliance)

## Setup Instructions

### Step 1: Configure Teams Integration

1. Log in as an admin user
2. Navigate to **Account Settings** > **Integrations**
3. Click on **Microsoft Teams**
4. Enter your credentials:
   - **Tenant ID**: Your Azure AD tenant ID
   - **Client ID**: Azure app registration client ID
   - **Client Secret**: Azure app registration client secret
   - **Service Account Email**: Email of the admin account for OneDrive storage

   > **Important**: The service account email is where all meeting recordings will be stored. Use a dedicated admin account with sufficient storage.

5. Click **Save** and verify the connection

### Step 2: Grant Required Permissions in Azure

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select your LMS app registration
4. Go to **API permissions**
5. Add the following Microsoft Graph **Application permissions**:
   - `Calendars.ReadWrite`
   - `OnlineMeetings.ReadWrite.All`
   - `Files.Read.All`
   - `User.Read.All`
6. Click **Grant admin consent** for your organization

### Step 3: Create a Conference with Auto-Recording

1. Navigate to **Conferences** > **New Conference**
2. Fill in conference details:
   - Title
   - Description
   - Date and time
   - Select **Microsoft Teams** as the platform
3. The system will automatically:
   - Create the Teams meeting
   - Enable auto-recording
   - Store recordings in the configured admin's OneDrive

### Step 4: Sync Recordings After Meeting

After your meeting ends:

1. Wait 5-10 minutes for Teams to process the recording
2. Navigate to the conference detail page
3. Click the **Sync Data** button
4. The system will:
   - Search for recordings in OneDrive
   - Download metadata
   - Make recordings available for download

Alternatively, you can enable automatic sync:
```bash
# Run sync for all conferences
python manage.py sync_conference_data --all

# Run sync for specific conference
python manage.py sync_conference_data --conference-id <ID>
```

## Using Conference Recordings

### For Instructors/Admins

1. Navigate to the conference detail page
2. Click on the **Recordings** tab
3. You'll see:
   - Recording title and duration
   - File size
   - Storage location (OneDrive badge)
   - Download button
   - View online button
   - Download count

**Actions Available:**
- **Download**: Download the recording file to your computer
- **View Online**: Open the recording in OneDrive/SharePoint
- **Sync Data**: Refresh recordings list from OneDrive

### For Learners

1. Navigate to the conference detail page
2. Click on the **Recordings** tab
3. Click **Download** to get the recording file
4. Click **View Online** to watch in browser (if available)

## Troubleshooting

### Recordings Not Showing Up

**Problem**: Recordings don't appear after syncing

**Solutions**:
1. **Wait longer**: Teams may take up to 15-20 minutes to process recordings
2. **Check OneDrive**: Verify recordings are in the admin's OneDrive Recordings folder
3. **Verify permissions**: Ensure the app has `Files.Read.All` permission
4. **Check integration**: Verify Teams integration is active and service account email is correct
5. **Manual sync**: Click the "Sync Data" button again

### Download Fails

**Problem**: Users can't download recordings

**Solutions**:
1. **Check file size**: Large files may timeout - use "View Online" instead
2. **Verify access**: Ensure the conference is published and user has access
3. **Check OneDrive link**: Verify the OneDrive download URL is still valid
4. **Re-sync**: Click "Sync Data" to refresh download URLs

### Recording Not Auto-Starting

**Problem**: Meetings aren't being recorded automatically

**Solutions**:
1. **Check Teams policy**: Verify cloud recording is enabled in Teams admin center
2. **Verify permissions**: Ensure `OnlineMeetings.ReadWrite.All` permission is granted
3. **Check license**: Verify the organizer has a proper Microsoft 365 license
4. **Manual start**: Participants can manually start recording during the meeting

### OneDrive Storage Full

**Problem**: Recordings fail due to storage limits

**Solutions**:
1. **Increase storage**: Upgrade the admin account's OneDrive storage
2. **Archive old recordings**: Move old recordings to SharePoint or external storage
3. **Enable auto-expiration**: Configure Teams to auto-delete recordings after X days
4. **Use different account**: Configure a different service account with more storage

## Storage Locations

Recordings are stored in the following structure in OneDrive:

```
OneDrive/
└── Recordings/
    ├── Meeting_Title_20241120_143000.mp4
    ├── Meeting_Title_20241120_143000_transcript.vtt
    └── Meeting_Title_20241120_143000_chat.txt
```

## Database Schema

The system stores recording metadata in the `ConferenceRecording` model:

```python
- recording_id: Unique identifier
- title: Recording name
- file_size: Size in bytes
- duration_minutes: Recording length
- onedrive_item_id: OneDrive file ID
- onedrive_drive_id: OneDrive drive ID
- onedrive_web_url: View online URL
- onedrive_download_url: Direct download URL
- stored_in_onedrive: Boolean flag
- download_count: Number of downloads
- last_downloaded_at: Last download timestamp
```

## Security Considerations

1. **Access Control**: Only users with conference access can download recordings
2. **Token Authentication**: OneDrive downloads use OAuth tokens, not public URLs
3. **Download Tracking**: All downloads are logged with user and timestamp
4. **Temporary URLs**: OneDrive download URLs expire after 1 hour
5. **Permission Checks**: System verifies user permissions before allowing downloads

## Automated Maintenance

### Scheduled Sync

Set up automated sync using cron:

```bash
# Add to crontab to run every hour
0 * * * * cd /home/ec2-user/lms && /home/ec2-user/venv/bin/python manage.py sync_conference_data --all --status ended
```

### Clean Old Recordings

```bash
# Archive recordings older than 90 days
python manage.py cleanup_old_recordings --days 90 --archive
```

## API Integration

You can also trigger recording sync via API:

```python
POST /conferences/<conference_id>/sync/
Headers:
    X-CSRFToken: <token>
    Content-Type: application/json

Response:
{
    "success": true,
    "items_processed": 3,
    "details": {
        "recordings": {
            "created": 1,
            "updated": 0,
            "success": true
        },
        "attendance": {...},
        "chat": {...},
        "files": {...}
    }
}
```

## Best Practices

1. **Use Dedicated Account**: Use a dedicated admin account for OneDrive storage, not a personal account
2. **Regular Sync**: Set up automated sync to run hourly for ended meetings
3. **Monitor Storage**: Set up alerts for OneDrive storage approaching limits
4. **Archive Old Recordings**: Implement a retention policy for recordings
5. **Test First**: Test with a small meeting before deploying to production
6. **Notify Users**: Inform participants that meetings will be recorded
7. **Backup Important Recordings**: Download and backup critical recordings externally

## Support and Maintenance

### Logs

Check logs for recording sync issues:
```bash
# View recent sync logs
tail -f /home/ec2-user/lms/logs/lms.log | grep -i "recording\|onedrive"

# Check specific conference sync
python manage.py sync_conference_data --conference-id <ID> --verbose
```

### Health Check

Monitor recording sync health:
```bash
# Check sync status for all conferences
python manage.py monitor_conference_sync --report

# Check specific conference
python manage.py monitor_conference_sync --conference-id <ID>
```

## Frequently Asked Questions

**Q: Can learners record meetings?**
A: Recording is controlled by Teams policies. By default, only organizers and instructors can start recordings.

**Q: How long are recordings stored?**
A: Recordings are stored indefinitely unless you configure auto-expiration in Teams admin center.

**Q: Can I use a different storage location?**
A: Currently, recordings must be stored in OneDrive. You can manually move them to SharePoint after sync.

**Q: What video format are recordings in?**
A: Teams recordings are typically in MP4 format with H.264 video codec.

**Q: Can I download recordings from the LMS mobile app?**
A: Yes, if your mobile app implements the recording download API endpoint.

**Q: Are transcripts available?**
A: If Teams auto-transcription is enabled, transcripts will be synced alongside recordings.

## Migration Notes

If migrating from an existing system:

1. **Apply migrations**: 
   ```bash
   python manage.py migrate conferences
   ```

2. **Sync existing conferences**:
   ```bash
   python manage.py sync_conference_data --all --force
   ```

3. **Verify recordings**:
   ```bash
   python manage.py shell
   >>> from conferences.models import ConferenceRecording
   >>> ConferenceRecording.objects.filter(stored_in_onedrive=True).count()
   ```

## Version History

- **v1.0** (2024-11-20): Initial release with OneDrive recording support
  - Auto-recording for Teams meetings
  - OneDrive storage integration
  - Download and view online functionality
  - Recording sync service

## Contact

For issues or questions:
- Check logs: `/home/ec2-user/lms/logs/lms.log`
- Contact your system administrator
- Review Microsoft Teams admin center settings

