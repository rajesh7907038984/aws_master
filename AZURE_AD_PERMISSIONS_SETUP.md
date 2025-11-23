# Azure AD Permissions Setup Guide
## Required for Teams Conference Integration

**CRITICAL:** You must complete these steps for the fixes to work!

---

## 🚨 Required Permissions

The following Microsoft Graph API permissions are **REQUIRED** for full functionality:

| Permission | Purpose | Priority |
|------------|---------|----------|
| `OnlineMeetingArtifact.Read.All` | Read attendance reports with duration | 🔴 CRITICAL |
| `Chat.Read.All` | Read chat messages from meetings | 🔴 CRITICAL |
| `Files.Read.All` | Read recordings from OneDrive | 🟡 HIGH |
| `Calendars.ReadWrite` | Create and manage calendar events | 🟢 REQUIRED |
| `OnlineMeetings.ReadWrite` | Create and manage online meetings | 🟢 REQUIRED |
| `CallRecords.Read.All` | Advanced call analytics (optional) | 🟤 OPTIONAL |

---

## 📋 Step-by-Step Setup

### Step 1: Open Azure Portal

1. Go to **https://portal.azure.com**
2. Sign in with your Azure AD admin account
3. Navigate to: **Azure Active Directory** → **App Registrations**

### Step 2: Find Your Teams App

1. In the App Registrations list, find your LMS Teams integration app
   - Look for the app name or Client ID used in your LMS
2. Click on the app name to open its details

### Step 3: Add API Permissions

1. In the left sidebar, click **"API permissions"**
2. Click **"Add a permission"**
3. Select **"Microsoft Graph"**
4. Select **"Application permissions"** (NOT Delegated)

### Step 4: Add Each Required Permission

For each permission in the table above:

1. In the search box, type the permission name (e.g., `OnlineMeetingArtifact.Read.All`)
2. Check the box next to the permission
3. Click **"Add permissions"** at the bottom

Repeat for all required permissions.

### Step 5: Grant Admin Consent ⚠️ CRITICAL

**This is the most important step!** Without admin consent, permissions won't work.

1. After adding all permissions, you'll see them listed with status "Not granted"
2. Click the button **"Grant admin consent for [Your Organization]"**
3. Confirm by clicking **"Yes"** in the popup
4. Wait for the status to change to "✓ Granted for [Your Organization]"

### Step 6: Verify Permissions

After granting consent, your permissions list should look like this:

```
✓ Calendars.ReadWrite                    Granted for [Your Org]
✓ Chat.Read.All                         Granted for [Your Org]
✓ Files.Read.All                        Granted for [Your Org]
✓ OnlineMeetingArtifact.Read.All        Granted for [Your Org]
✓ OnlineMeetings.ReadWrite              Granted for [Your Org]
```

---

## 🧪 Test Permissions in LMS

After granting permissions in Azure AD, test them in your LMS:

### Method 1: Use Django Shell

```bash
cd /home/ec2-user/lms
python manage.py shell
```

```python
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient

# Get active integration
integration = TeamsIntegration.objects.filter(is_active=True).first()

if integration:
    # Initialize API client
    api = TeamsAPIClient(integration)
    
    # Validate permissions
    results = api.validate_permissions()
    
    # Display results
    print("\n" + "="*60)
    print(results['message'])
    print("="*60)
    
    print(f"\n✅ Available Features ({len(results['available_features'])}):")
    for feature in results['available_features']:
        perm_info = results['permissions'][feature]
        print(f"  • {feature}: {perm_info['permission_name']}")
    
    if results['missing_permissions']:
        print(f"\n❌ Missing Permissions ({len(results['missing_permissions'])}):")
        for perm in results['missing_permissions']:
            print(f"  • {perm}")
        print("\n⚠️  Please grant these in Azure AD!")
    else:
        print("\n🎉 All required permissions are granted!")
else:
    print("❌ No Teams integration found")
```

### Method 2: Test Sync on Conference Page

1. Go to any conference: https://vle.nexsy.io/conferences/52/
2. Click the **"Sync Data"** button
3. Check the sync results:
   - If permissions are missing, you'll see specific error messages
   - If permissions are granted, sync should complete successfully

---

## 🔍 Troubleshooting

### Problem: "Grant admin consent" button is greyed out

**Cause:** You don't have admin privileges in Azure AD

**Solution:**
1. Contact your Azure AD Global Administrator
2. Ask them to grant admin consent for your app
3. They can do this in Azure Portal → App Registrations → Your App → API Permissions

### Problem: Permissions show as "Not granted" after clicking button

**Cause:** Admin consent wasn't properly applied

**Solution:**
1. Wait 5-10 minutes (Azure AD can be slow)
2. Refresh the page
3. If still not granted, try again or contact Azure support

### Problem: Sync still fails with "403 Forbidden" error

**Possible Causes:**
1. Admin consent not granted (even though UI shows "Granted")
2. Token cache needs refresh
3. App doesn't have the right permissions

**Solution:**
```python
# In Django shell - Force token refresh
from account_settings.models import TeamsIntegration
from teams_integration.utils.teams_api import TeamsAPIClient

integration = TeamsIntegration.objects.filter(is_active=True).first()
api = TeamsAPIClient(integration)

# Force new token
token = api.get_access_token(force_refresh=True)
print(f"New token obtained: {token[:20]}...")

# Test connection
result = api.test_connection()
print(result)
```

### Problem: Some features work but others don't

**Cause:** Only some permissions were granted

**Solution:**
1. Check which permissions are granted in Azure AD
2. Make sure ALL required permissions show "✓ Granted"
3. Run validation command to see which features are available

---

## 📱 Admin Consent URL (Alternative Method)

If you can't access Azure Portal, you can grant consent via URL:

```
https://login.microsoftonline.com/{TENANT_ID}/adminconsent?client_id={CLIENT_ID}
```

Replace:
- `{TENANT_ID}` with your Azure AD tenant ID
- `{CLIENT_ID}` with your app's client ID

Send this URL to your Azure AD admin to grant consent.

---

## 🔒 Security Notes

### Why Application Permissions?

We use **Application permissions** (not Delegated) because:
- The LMS needs to access data when users are offline
- The app acts on behalf of the organization, not individual users
- Service accounts don't have delegated permissions

### Who Can Grant Admin Consent?

Only these Azure AD roles can grant admin consent:
- Global Administrator
- Privileged Role Administrator
- Cloud Application Administrator
- Application Administrator

### Permission Scope

These permissions apply to:
- **Entire organization** - The app can access data for all users
- **Read-only** (mostly) - Most permissions only READ data, not modify
- **Audit logged** - All access is logged in Azure AD audit logs

---

## 📊 Permission Validation Results

After setup, you should see these results:

```python
# Expected validation output:
{
    'all_granted': True,
    'message': '✅ All required permissions are granted',
    'available_features': [
        'calendar',
        'attendance', 
        'chat',
        'recordings',
        'meetings'
    ],
    'missing_permissions': [],
    'unavailable_features': []
}
```

---

## 🎯 Quick Checklist

Use this checklist to ensure everything is set up correctly:

- [ ] Opened Azure Portal (https://portal.azure.com)
- [ ] Found app in App Registrations
- [ ] Clicked "API permissions"
- [ ] Added all 5+ required permissions
- [ ] Selected "Application permissions" (not Delegated)
- [ ] Clicked "Grant admin consent for [Org]"
- [ ] Confirmed all permissions show "✓ Granted"
- [ ] Waited 5 minutes for propagation
- [ ] Ran validation command in Django shell
- [ ] Tested sync on a conference
- [ ] Verified attendance duration appears
- [ ] Verified chat messages sync
- [ ] Verified recording duration shows

---

## 📞 Need Help?

**Azure AD Issues:**
- Contact your IT department or Azure AD administrator
- Check Azure AD documentation: https://docs.microsoft.com/azure/active-directory/

**LMS Integration Issues:**
- Check Django logs: `/home/ec2-user/lms/logs/`
- Run validation command to see what's working
- Review error messages in sync logs

**Microsoft Graph API Issues:**
- Test APIs in Graph Explorer: https://developer.microsoft.com/graph/graph-explorer
- Review Graph API docs: https://learn.microsoft.com/graph/

---

## ✅ Success Criteria

You'll know the setup is successful when:

1. **Validation command shows**: "✅ All required permissions are granted"
2. **Sync Data button works** without permission errors
3. **Total Time (min) displays** actual meeting duration (not 0)
4. **Chat History shows** messages from meetings (not 0)
5. **Recordings show** correct duration (not 0)

---

**Setup Time:** ~15 minutes  
**Difficulty:** Easy (with admin access)  
**Impact:** HIGH - Enables all conference features  
**Priority:** 🔴 CRITICAL

