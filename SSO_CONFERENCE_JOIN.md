# SSO Conference Join - Passthrough Authentication

## Overview

This feature allows users to join conferences directly using Microsoft or Google SSO authentication without going through the standard login flow first. This provides a seamless "one-click" join experience for conference participants.

## How It Works

### User Flow

1. **User clicks SSO conference join link** (Microsoft or Google)
2. **System stores conference intent** in session
3. **User is redirected to SSO provider** (Microsoft/Google)
4. **After successful authentication:**
   - New users are automatically created
   - Existing users are logged in
   - Both are redirected to the conference join page
5. **Auto-registration and join** happens automatically
6. **User is redirected to the meeting platform** (Zoom/Teams/etc.)

### URLs

For conference ID `46`:

#### Microsoft SSO Join
```
https://vle.nexsy.io/conferences/46/join/microsoft/
```

#### Google SSO Join
```
https://vle.nexsy.io/conferences/46/join/google/
```

#### Standard Join (requires login)
```
https://vle.nexsy.io/conferences/46/join/
```

## Technical Implementation

### New URL Patterns

**File:** `conferences/urls.py`

```python
path('<int:conference_id>/join/microsoft/', views.join_conference_microsoft_sso, name='join_conference_microsoft_sso'),
path('<int:conference_id>/join/google/', views.join_conference_google_sso, name='join_conference_google_sso'),
```

### New Views

**File:** `conferences/views.py`

#### `join_conference_microsoft_sso(request, conference_id)`
- Validates conference exists
- Stores conference join intent in session
- Redirects to Microsoft OAuth login with `next` parameter

#### `join_conference_google_sso(request, conference_id)`
- Validates conference exists
- Stores conference join intent in session
- Redirects to Google OAuth login with `next` parameter

### Modified OAuth Views

**File:** `users/views.py`

#### Modified Functions:
1. **`microsoft_login(request)`**
   - Now accepts `next` URL parameter
   - Stores in session for post-authentication redirect

2. **`microsoft_callback(request)`**
   - Checks for `oauth_next_url` in session
   - Redirects to conference join page after authentication
   - Handles both existing users and new user creation
   - Works with 2FA enabled accounts

3. **`google_login(request)`**
   - Now accepts `next` URL parameter
   - Stores in session for post-authentication redirect

4. **`google_callback(request)`**
   - Checks for `oauth_next_url` in session
   - Redirects to conference join page after authentication
   - Handles both existing users and new user creation
   - Works with 2FA enabled accounts

## Session Data Flow

```python
# Step 1: SSO join view stores conference intent
request.session['conference_join_after_auth'] = conference_id
request.session['conference_join_method'] = 'microsoft_sso'  # or 'google_sso'

# Step 2: OAuth login stores next URL
request.session['oauth_next_url'] = '/conferences/46/join/'

# Step 3: OAuth callback retrieves and redirects
next_url = request.session.pop('oauth_next_url', None)
if next_url:
    return redirect(next_url)
```

## 2FA Support

The implementation fully supports Two-Factor Authentication (2FA):

1. **If user has 2FA enabled:**
   - OTP is sent to user's email
   - `oauth_next_url` is transferred to `otp_next_url` in session
   - After successful OTP verification, user is redirected to conference

2. **If user doesn't have 2FA:**
   - User is logged in immediately
   - Redirected directly to conference join page

## Use Cases

### 1. Direct Conference Links
Send participants a direct SSO link:
```
Email: "Click here to join the conference: 
https://vle.nexsy.io/conferences/46/join/microsoft/"
```

### 2. Calendar Invites
Include SSO links in calendar invitations for one-click join

### 3. External Integrations
Use SSO links in third-party systems that integrate with your LMS

### 4. QR Codes
Generate QR codes with SSO links for easy mobile access

## Benefits

1. **Reduced Friction:** Users don't need to navigate to login page first
2. **Single Click Join:** From link to meeting in minimal steps
3. **Automatic Account Creation:** New users are created automatically
4. **Secure:** Uses standard OAuth 2.0 flows
5. **Organization SSO:** Leverages Microsoft/Google organizational accounts
6. **Mobile Friendly:** Works seamlessly on mobile devices

## Security Considerations

1. **OAuth 2.0 Standard:** Uses industry-standard authentication
2. **Session Security:** Conference intent stored in secure session
3. **CSRF Protection:** All forms use CSRF tokens
4. **Access Control:** Conference access rules still apply after authentication
5. **2FA Compatible:** Works with two-factor authentication

## Example Usage

### HTML Link
```html
<a href="https://vle.nexsy.io/conferences/46/join/microsoft/">
    Join Conference with Microsoft
</a>
```

### JavaScript Redirect
```javascript
window.location.href = 'https://vle.nexsy.io/conferences/46/join/google/';
```

### Email Template
```
Subject: Conference Invitation

Hi there!

You're invited to join our conference. Choose your preferred sign-in method:

• Microsoft SSO: https://vle.nexsy.io/conferences/46/join/microsoft/
• Google SSO: https://vle.nexsy.io/conferences/46/join/google/

See you there!
```

## Testing

### Manual Testing Steps

1. **Test Microsoft SSO Join:**
   ```
   1. Ensure you're logged out
   2. Visit: https://vle.nexsy.io/conferences/46/join/microsoft/
   3. Sign in with Microsoft account
   4. Verify automatic redirect to conference join
   5. Verify successful meeting entry
   ```

2. **Test Google SSO Join:**
   ```
   1. Ensure you're logged out
   2. Visit: https://vle.nexsy.io/conferences/46/join/google/
   3. Sign in with Google account
   4. Verify automatic redirect to conference join
   5. Verify successful meeting entry
   ```

3. **Test with 2FA Enabled:**
   ```
   1. Enable 2FA for OAuth in user settings
   2. Follow SSO join flow
   3. Enter OTP code
   4. Verify redirect to conference after 2FA
   ```

4. **Test New User Creation:**
   ```
   1. Use a new Google/Microsoft account
   2. Follow SSO join flow
   3. Verify new account is created
   4. Verify conference join succeeds
   ```

## Troubleshooting

### Issue: Redirect loops
**Solution:** Clear session data and try again

### Issue: Conference not found
**Solution:** Verify conference ID exists and is not deleted

### Issue: OAuth not configured
**Solution:** Configure Microsoft/Google OAuth in admin settings

### Issue: 2FA code not received
**Solution:** Check email spam folder, verify email settings

## API Reference

### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| conference_id | integer | Yes | The ID of the conference to join |

### Session Keys

| Key | Type | Description |
|-----|------|-------------|
| `oauth_next_url` | string | URL to redirect after OAuth authentication |
| `conference_join_after_auth` | integer | Conference ID to join after authentication |
| `conference_join_method` | string | SSO method used ('microsoft_sso' or 'google_sso') |
| `otp_next_url` | string | URL to redirect after 2FA verification |

## Changelog

### Version 1.0 (November 20, 2025)
- Initial implementation
- Microsoft SSO conference join
- Google SSO conference join
- 2FA support
- New user auto-creation
- Session-based redirect handling

## Future Enhancements

1. **Token-based authentication:** Generate secure tokens for direct access
2. **Guest SSO:** Allow guest users to join with SSO
3. **SAML support:** Add enterprise SAML SSO support
4. **Analytics:** Track SSO join success rates
5. **Customization:** Allow custom branding for SSO pages

