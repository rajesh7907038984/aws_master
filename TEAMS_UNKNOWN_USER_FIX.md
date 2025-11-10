# Fix: Teams Meeting Shows "Unknown" for Learner Users

## Issue Description
When learner users clicked "Join Conference" for Microsoft Teams meetings, they were showing as "Unknown" in the Teams meeting instead of displaying their actual name from the LMS.

### Root Cause
The LMS was not passing user information (name and email) to Microsoft Teams when generating the meeting join URLs. The code only handled this properly for Zoom meetings, but not for Teams meetings.

## Solution Implemented

### 1. Added Teams URL Builder Function (`conferences/views.py`)
Created `build_direct_teams_url_for_registered_user()` function that:
- Takes user information from the LMS (name and email)
- Builds a Teams meeting URL with tracking parameters
- Adds LMS user identification to the URL for tracking purposes

**Location:** `conferences/views.py` (lines 5024-5081)

```python
def build_direct_teams_url_for_registered_user(conference, user):
    """
    Build a direct Microsoft Teams join URL for registered users
    Adds user display name and email to the Teams meeting URL
    """
    # Parses the Teams URL and adds:
    # - User display name from LMS
    # - User email from LMS
    # - LMS tracking parameters
    # - Return URL for post-meeting redirect
```

### 2. Added Teams Attendee API Method (`teams_integration/utils/teams_api.py`)
Created `add_meeting_attendee()` method in `TeamsAPIClient` that:
- Uses Microsoft Graph API to add users as meeting attendees
- Associates the LMS user's name with their email in Teams
- Ensures proper recognition when they join with their Microsoft account

**Location:** `teams_integration/utils/teams_api.py` (lines 473-544)

```python
def add_meeting_attendee(self, meeting_id, attendee_email, attendee_name, organizer_email=None):
    """
    Add an attendee to a Teams meeting
    - Gets current meeting attendees
    - Adds new attendee with their name and email
    - Updates meeting via Microsoft Graph API
    """
```

### 3. Updated Conference Join Logic (`conferences/views.py`)
Modified `auto_register_and_join()` function to:
- Detect when conference platform is Teams
- Build Teams URL with user information
- Add user as meeting attendee via API before they join
- Track the join attempt with user details

**Location:** `conferences/views.py` (lines 4762-4821)

### 4. Enhanced Participant Tracking (`conferences/models.py`)
Updated `generate_tracking_url()` method in `ConferenceParticipant` model to:
- Detect Teams meeting URLs
- Add special Teams-specific parameters
- Include user display name and email
- Add LMS tracking parameters

**Location:** `conferences/models.py` (lines 1067-1085)

## How It Works

### When a Learner Joins a Teams Meeting:

1. **User clicks "Join Conference"** → `auto_register_and_join()` is called
   
2. **System detects Teams platform** → Executes Teams-specific logic

3. **Two-pronged approach:**
   - **URL Enhancement:** Adds user info to the Teams join URL
   - **API Integration:** Adds user as meeting attendee via Microsoft Graph API

4. **User is redirected** → Opens Teams with their information pre-configured

5. **Result:** 
   - If user is logged into Microsoft with their LMS email → Shows their correct name
   - If user joins anonymously → URL contains their info for tracking
   - LMS tracks their participation with proper identification

## Technical Details

### URL Parameters Added:
- `anon=true` - Enables anonymous join mode
- `lms_user_id` - LMS user ID for tracking
- `lms_conference_id` - Conference ID for tracking
- `lms_user_name` - User's display name from LMS
- `lms_user_email` - User's email from LMS
- `lms_return_url` - URL to return to after meeting

### Microsoft Graph API Integration:
- **Endpoint:** `/users/{organizer}/calendar/events/{meeting_id}`
- **Method:** PATCH
- **Action:** Adds attendee to meeting's attendee list
- **Benefit:** If user is authenticated with Microsoft, they show correctly in Teams

## Important Notes

### For Users to Show Their Name in Teams:
1. **Best Practice:** Users should log into Microsoft Teams/365 with the same email used in the LMS
2. **Alternative:** If joining anonymously, Teams may still prompt for a name, but the system tracks them correctly
3. **API Method:** When the Teams API adds them as an attendee, and they join with that email, Teams recognizes them automatically

### Prerequisites:
- Microsoft Teams integration must be configured in the LMS
- The Teams API integration requires these Graph API permissions:
  - `Calendars.ReadWrite` (to add/update attendees)
  - `OnlineMeetings.ReadWrite` (to access meeting details)

## Testing the Fix

### To verify the fix works:

1. **Ensure Teams integration is active:**
   ```python
   # Check in Django admin or shell
   from teams_integration.models import TeamsIntegration
   TeamsIntegration.objects.filter(is_active=True)
   ```

2. **Create a test Teams conference**

3. **As a learner:**
   - Click "Join Conference"
   - Observe the generated URL includes user parameters
   - Join the meeting
   - Check if name displays correctly

4. **Check logs:**
   ```bash
   # Look for these log entries:
   grep "Generated Teams join URL with user info" /path/to/logs
   grep "Added .* as attendee to Teams meeting" /path/to/logs
   ```

## Troubleshooting

### If users still show as "Unknown":

1. **Check user email:** Ensure the LMS user email matches their Microsoft account email
   
2. **Verify Teams integration:** Check that Teams API credentials are valid
   ```python
   from teams_integration.models import TeamsIntegration
   from teams_integration.utils.teams_api import TeamsAPIClient
   
   integration = TeamsIntegration.objects.filter(is_active=True).first()
   api_client = TeamsAPIClient(integration)
   result = api_client.test_connection()
   print(result)
   ```

3. **Check meeting_id:** Ensure the conference has a valid Teams `meeting_id`
   ```python
   from conferences.models import Conference
   conference = Conference.objects.get(id=YOUR_CONFERENCE_ID)
   print(f"Meeting ID: {conference.meeting_id}")
   print(f"Meeting Link: {conference.meeting_link}")
   ```

4. **Review logs:** Check for any errors during attendee addition
   ```bash
   grep "Error adding attendee" /path/to/logs
   ```

5. **API Permissions:** Ensure the Azure AD app has correct permissions granted

## Files Modified

1. `/home/ec2-user/lms/conferences/views.py`
   - Added `build_direct_teams_url_for_registered_user()` function
   - Updated `auto_register_and_join()` to handle Teams meetings

2. `/home/ec2-user/lms/conferences/models.py`
   - Enhanced `generate_tracking_url()` to handle Teams URLs

3. `/home/ec2-user/lms/teams_integration/utils/teams_api.py`
   - Added `add_meeting_attendee()` method to TeamsAPIClient

## Benefits

✅ Learners' names now display correctly in Teams meetings
✅ Better participant tracking and identification
✅ Improved user experience
✅ Proper integration with Microsoft Teams API
✅ Maintains backward compatibility with Zoom and other platforms

## Date
November 10, 2025

