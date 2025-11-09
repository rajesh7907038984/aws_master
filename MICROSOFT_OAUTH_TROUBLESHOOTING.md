# Microsoft OAuth "Continue with Microsoft" Not Working - Troubleshooting Guide

## Diagnostic Results

✅ **Database Configuration**: Microsoft OAuth credentials ARE configured  
✅ **Template Tag**: Returns `True` - button should be visible  
✅ **URL Routing**: Properly configured  
✅ **Redirect URI**: `https://vle.nexsy.io/users/auth/microsoft/callback/`

---

## Most Likely Causes

### 1. **Azure AD Redirect URI Not Registered** (Most Common)

**Problem**: The redirect URI must be **exactly registered** in Azure AD App Registration.

**Solution**:
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select your application
4. Go to **Authentication** section
5. Under **Web** platform, add this **exact** redirect URI:
   ```
   https://vle.nexsy.io/users/auth/microsoft/callback/
   ```
6. Click **Save**

**Important Notes**:
- URL must include `https://`
- URL must match **exactly** (no trailing slash mismatch)
- Case-sensitive domain matching
- Protocol (https) is required

---

### 2. **Client Secret Expired**

**Problem**: Azure AD client secrets expire (typically 6-24 months).

**Solution**:
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select your application
4. Go to **Certificates & secrets** > **Client secrets**
5. Check the **Expires** column
6. If expired, create a new secret:
   - Click **+ New client secret**
   - Add a description
   - Set expiration period
   - Click **Add**
   - **COPY THE VALUE IMMEDIATELY** (you won't see it again)
7. Update in LMS:
   - Go to Admin Settings > Microsoft OAuth Configuration
   - Paste the new client secret
   - Save

---

### 3. **Missing API Permissions**

**Problem**: Required Microsoft Graph API permissions not granted.

**Solution**:
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select your application
4. Go to **API permissions**
5. Ensure these Microsoft Graph **Delegated permissions** are added:
   - `openid`
   - `email`
   - `profile`
   - `User.Read`
6. If missing, add them:
   - Click **+ Add a permission**
   - Select **Microsoft Graph**
   - Select **Delegated permissions**
   - Search and add the permissions above
   - Click **Add permissions**
7. **Grant admin consent** (if required):
   - Click **✓ Grant admin consent for [Your Organization]**
   - Click **Yes** to confirm

---

### 4. **Supported Account Types Mismatch**

**Problem**: Tenant configuration doesn't match account type settings.

**Current Configuration**: Tenant ID = `common` (multi-tenant)

**Solution**:

**Option A - Multi-Tenant (Current)**:
- In Azure AD, ensure **Supported account types** is set to:
  - "Accounts in any organizational directory (Any Azure AD directory - Multitenant)"
  - OR "Accounts in any organizational directory and personal Microsoft accounts"
- Keep LMS tenant_id as `common`

**Option B - Single Tenant**:
- In Azure AD, set **Supported account types** to:
  - "Accounts in this organizational directory only"
- In LMS Admin Settings, set Microsoft Tenant ID to your specific tenant ID (GUID)

---

### 5. **Browser Console Errors**

**How to Check**:
1. Open the registration page: https://vle.nexsy.io/users/register/
2. Press **F12** to open Developer Tools
3. Go to **Console** tab
4. Click **"Continue with Microsoft"**
5. Check for any JavaScript errors

**Common Issues**:
- CORS errors → Check Azure AD redirect URI
- Network errors → Check if Azure AD endpoints are accessible
- 404 errors → Check URL routing in Django

---

### 6. **Application ID URI**

**Problem**: Application ID URI may be required for certain Azure AD configurations.

**Solution**:
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Select your application
4. Go to **Expose an API**
5. If **Application ID URI** is not set, click **Set**
6. Accept the default URI or customize it
7. Click **Save**

---

## Testing the OAuth Flow

### Step 1: Test the Login Initiation

Click the "Continue with Microsoft" button. You should be redirected to Microsoft's login page:

```
https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=...
```

**If this fails**:
- Check browser console for errors
- Check if the button href is correct (inspect element)
- Check if JavaScript is blocking navigation

### Step 2: Test the Callback

After logging in with Microsoft, you should be redirected back to:

```
https://vle.nexsy.io/users/auth/microsoft/callback/?code=...&state=...
```

**If this fails with an error**:
- `AADSTS50011`: Redirect URI mismatch → Fix in Azure AD
- `AADSTS7000215`: Invalid client secret → Regenerate secret
- `AADSTS65001`: User doesn't consent → Grant admin consent
- `AADSTS50105`: User not assigned → Add user to app or change assignment requirement

---

## Quick Diagnosis Script

Run this to check configuration:

```bash
cd /home/ec2-user/lms
python3 diagnose_microsoft_oauth.py
```

---

## Viewing Error Logs

Check Django logs for detailed error messages:

```bash
# If using systemd
sudo journalctl -u lms-production -f | grep -i "microsoft\|oauth"

# Check application logs
tail -f /home/ec2-user/lmslogs/application.log | grep -i "microsoft\|oauth"
```

---

## Common Azure AD Error Codes

| Error Code | Meaning | Solution |
|------------|---------|----------|
| AADSTS50011 | Redirect URI mismatch | Add correct redirect URI in Azure AD |
| AADSTS7000215 | Invalid client secret | Generate new client secret |
| AADSTS65001 | User/Admin consent required | Grant admin consent for API permissions |
| AADSTS50105 | User not assigned to app | Assign users or change assignment requirement |
| AADSTS700016 | Application not found | Check Application ID (Client ID) |
| AADSTS90002 | Tenant doesn't exist | Check Tenant ID configuration |

---

## Configuration Checklist

Use this checklist to verify your setup:

### Azure AD Configuration
- [ ] App registration created
- [ ] Client ID copied to LMS Admin Settings
- [ ] Client secret generated and copied to LMS Admin Settings
- [ ] Client secret not expired
- [ ] Redirect URI added: `https://vle.nexsy.io/users/auth/microsoft/callback/`
- [ ] API permissions added: openid, email, profile, User.Read
- [ ] Admin consent granted (if required)
- [ ] Supported account types configured correctly

### LMS Configuration
- [ ] Microsoft Client ID set in Admin Settings
- [ ] Microsoft Client Secret set in Admin Settings
- [ ] Microsoft Tenant ID set (or left empty for 'common')
- [ ] OAuth button visible on registration page
- [ ] No JavaScript errors in browser console

---

## Still Having Issues?

### Enable Detailed Logging

Add this to your Django settings to see detailed OAuth errors:

```python
LOGGING = {
    'loggers': {
        'users.views': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
    },
}
```

### Manual Test

Try accessing these URLs directly:

1. Login initiation:
   ```
   https://vle.nexsy.io/users/auth/microsoft/
   ```

2. Check the redirect URL it generates (should start with login.microsoftonline.com)

---

## Contact Information

If you've followed all steps and still experiencing issues:

1. **Check Django error messages** on the registration page after clicking the button
2. **Capture the exact error** from Azure AD (if redirected to Microsoft)
3. **Check browser network tab** (F12 > Network) for failed requests
4. **Review Django logs** for backend errors

---

## Quick Fix Commands

```bash
# Check if button is visible (should return True)
cd /home/ec2-user/lms
python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()
from account_settings.templatetags.account_settings_tags import is_microsoft_oauth_enabled
print('Microsoft OAuth Enabled:', is_microsoft_oauth_enabled())
"

# Check redirect URI
python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()
from django.urls import reverse
from django.test import RequestFactory
factory = RequestFactory()
request = factory.get('/')
request.META['HTTP_HOST'] = 'vle.nexsy.io'
callback_path = reverse('users:microsoft_callback')
print('Redirect URI:', f'https://vle.nexsy.io{callback_path}')
"

# Restart application to apply any config changes
sudo systemctl restart lms-production
```

---

**Last Updated**: 2025-11-09

