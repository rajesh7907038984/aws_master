# Teams Meeting Creation Fix - Service Account Setup Guide

## Problem Summary

When creating time slots with Teams meetings, the system was failing with error:
```
API request failed: 404 Not Found for endpoint /users/hi@nexsy.io/calendar/events
The user 'hi@nexsy.io' does not exist in Azure AD or doesn't have a mailbox.
```

**Root Cause:** The system was trying to use the logged-in user's email (hi@nexsy.io) to create Teams meetings, but this email doesn't exist in your Azure AD tenant.

## Solution Implemented

We've added a **Service Account Email** feature to the Teams Integration. This allows you to specify a valid Azure AD email address that will be used for creating Teams meetings when:

1. The logged-in user's email doesn't exist in Azure AD
2. The integration owner has no email configured  
3. You want to centralize Teams meeting creation under a single account

## Changes Made

### 1. Database Schema
- Added `service_account_email` field to `TeamsIntegration` model
- This field stores the service account email address

### 2. Code Updates
- **conferences/views.py**: Updated to use service account email as fallback
- **teams_integration/utils/teams_api.py**: Enhanced email resolution logic
- **account_settings/admin.py**: Added service account field to admin interface

### 3. New Management Command
- **set_service_account**: Command to set and verify service account email

## Setup Instructions

### Step 1: Create or Identify a Service Account in Azure AD

You need an Azure AD user account that will be used for creating Teams meetings. This account must:
- ✅ Exist in your Azure AD tenant
- ✅ Have an Exchange Online license (for mailbox/calendar access)
- ✅ Be enabled and active

**Option A: Use an existing account**
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: Azure Active Directory > Users
3. Find a suitable account (e.g., admin account, shared mailbox)
4. Note the email address / User Principal Name

**Option B: Create a new service account**
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: Azure Active Directory > Users > New user
3. Create user with details:
   - User principal name: `lms-teams-service@yourdomain.com` (or similar)
   - Display name: `LMS Teams Service Account`
   - Password: Set a strong password
4. Assign licenses:
   - Go to: Azure Active Directory > Users > [Your new user] > Licenses
   - Click: + Assign
   - Select: Microsoft 365 license with Exchange Online
5. Wait 5-10 minutes for the mailbox to be provisioned

### Step 2: Verify the Account in Azure AD

Use the management command to verify the account exists and has a mailbox:

```bash
cd /home/ec2-user/lms
python3 manage.py set_service_account --integration-id 1 --email YOUR_SERVICE_ACCOUNT_EMAIL --verify
```

**Example:**
```bash
python3 manage.py set_service_account --integration-id 1 --email lms-teams-service@yourdomain.com --verify
```

**Expected output if successful:**
```
✓ User EXISTS in Azure AD
✓ User has a calendar/mailbox
✅ Service account email set successfully!
```

**If user doesn't exist:**
```
✗ User NOT FOUND in Azure AD
📝 Next steps: [instructions to create user]
```

**If user exists but has no mailbox:**
```
✗ User exists but has NO MAILBOX
⚠️  This user cannot create calendar events.
Solutions:
  1. Assign an Exchange Online license to this user
  2. Use a different user email that has a mailbox
```

### Step 3: Set the Service Account (without verification)

If you're confident the email exists, you can set it without verification:

```bash
python3 manage.py set_service_account --integration-id 1 --email YOUR_SERVICE_ACCOUNT_EMAIL
```

### Step 4: List All Integrations

To see all your Teams integrations and their service accounts:

```bash
python3 manage.py set_service_account --list
```

**Current integrations:**
```
ID    Name                      Owner                Service Account                Active
3     testing                   admin1_test          Not set                        ✓
1     Production                None                 Not set                        ✓
2     Testing 2.1 - 3E Project  support1             Not set                        ✓
```

## Testing the Fix

After setting up the service account:

1. **Log in to the LMS**
2. **Navigate to the conference page**: https://vle.nexsy.io/conferences/46/time-slots/
3. **Create a new time slot** with Teams meeting
4. **Expected result**: Time slot created successfully with Teams meeting link

## Email Resolution Priority

When creating Teams meetings, the system now uses emails in this order:

1. **Logged-in user's email** (if set and exists in Azure AD)
2. **Integration owner's email** (if set and exists in Azure AD)  
3. **Service account email** (configured via this setup) ⭐ NEW
4. **Error** (if none of the above are available)

## Admin Interface

You can also configure the service account email via the Django admin:

1. Go to: https://vle.nexsy.io/admin/
2. Navigate to: Account Settings > Teams Integrations
3. Click on your integration (e.g., "Production")
4. Find the "Service Account" section
5. Enter the service account email
6. Save

## Troubleshooting

### Error: "User not found in Azure AD"

**Cause:** The email you provided doesn't exist in Azure AD

**Solutions:**
1. Double-check the email spelling
2. Verify in Azure Portal: Azure AD > Users
3. Create the user if it doesn't exist (see Step 1)
4. Check you're using the correct Azure AD tenant

### Error: "User exists but has no mailbox"

**Cause:** The user exists but doesn't have an Exchange Online license

**Solutions:**
1. Go to Azure Portal > Azure AD > Users > [Your user] > Licenses
2. Assign a Microsoft 365 license that includes Exchange Online
3. Wait 5-10 minutes for mailbox provisioning
4. Try again

### Error: "API request failed: 401 Unauthorized"

**Cause:** The Teams integration credentials are invalid or expired

**Solutions:**
1. Check the integration credentials in admin
2. Verify client ID, client secret, and tenant ID are correct
3. Ensure the Azure AD app has the required permissions:
   - `Calendars.ReadWrite` (Application permission)
   - `User.Read.All` (Application permission)
4. Ensure admin consent has been granted

### Error: "API request failed: 403 Forbidden"

**Cause:** The Azure AD app doesn't have the required permissions

**Solutions:**
1. Go to Azure Portal > Azure AD > App registrations > [Your app]
2. Navigate to: API permissions
3. Ensure these permissions are present:
   - Microsoft Graph > Application permissions > `Calendars.ReadWrite`
   - Microsoft Graph > Application permissions > `User.Read.All`
4. Click: "Grant admin consent for [Your tenant]"
5. Wait a few minutes and try again

## Alternative Solutions

If you cannot set up a service account, here are alternatives:

### Option 1: Update Your User Email

Update your LMS user account email to a valid Azure AD email:

```bash
python3 manage.py shell
>>> from users.models import CustomUser
>>> user = CustomUser.objects.get(username='hi')
>>> user.email = 'valid_email@yourdomain.com'  # Replace with valid Azure AD email
>>> user.save()
>>> exit()
```

### Option 2: Set Integration Owner

Assign a user with a valid Azure AD email as the integration owner:

```bash
python3 manage.py shell
>>> from account_settings.models import TeamsIntegration
>>> from users.models import CustomUser
>>> integration = TeamsIntegration.objects.get(id=1)
>>> owner = CustomUser.objects.get(username='USERNAME_WITH_VALID_EMAIL')
>>> integration.user = owner
>>> integration.save()
>>> exit()
```

## Monitoring and Logs

After setup, monitor the logs for any issues:

```bash
tail -f /home/ec2-user/lms/logs/lms.log | grep -i teams
```

Or check the server log:

```bash
tail -f /home/ec2-user/lms/server.log | grep -i teams
```

## Support

If you continue to experience issues:

1. Check the error message in the browser
2. Review the server logs: `/home/ec2-user/lms/logs/`
3. Verify Azure AD configuration in Azure Portal
4. Test with the check_azure_user command:
   ```bash
   python3 manage.py check_azure_user --email YOUR_EMAIL --integration-id 1
   ```

## Summary

✅ **What we fixed:**
- Added service account email support to Teams integration
- Enhanced email resolution logic with fallback chain
- Created management commands for easy setup and verification
- Updated admin interface for configuration

✅ **What you need to do:**
1. Create or identify a service account in Azure AD
2. Verify it has Exchange Online license
3. Set it using: `python3 manage.py set_service_account --integration-id 1 --email YOUR_EMAIL --verify`
4. Test by creating a time slot with Teams meeting

---

**Created:** November 20, 2025  
**Last Updated:** November 20, 2025

