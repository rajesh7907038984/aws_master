# SSO Conference Join - Quick Reference

## 🚀 Quick Start

For any conference, just replace `{conference_id}` with the actual conference ID:

### Microsoft SSO Join
```
https://vle.nexsy.io/conferences/{conference_id}/join/microsoft/
```

### Google SSO Join
```
https://vle.nexsy.io/conferences/{conference_id}/join/google/
```

## 📋 Examples

### Conference ID 46

**Microsoft SSO:**
```
https://vle.nexsy.io/conferences/46/join/microsoft/
```

**Google SSO:**
```
https://vle.nexsy.io/conferences/46/join/google/
```

### Conference ID 100

**Microsoft SSO:**
```
https://vle.nexsy.io/conferences/100/join/microsoft/
```

**Google SSO:**
```
https://vle.nexsy.io/conferences/100/join/google/
```

## 🔗 URL Structure

```
Base URL: https://vle.nexsy.io
Path: /conferences/{id}/join/{provider}/

Providers:
- microsoft  → Microsoft SSO (Azure AD)
- google     → Google SSO (Gmail/Workspace)
```

## ✨ What Happens

1. **Click link** → Redirect to SSO provider
2. **Sign in** → Microsoft/Google authentication
3. **Auto-create account** (if new user)
4. **Join conference** → Auto-register for meeting
5. **Launch meeting** → Redirect to Zoom/Teams/etc.

## 📧 Email Template Example

```
Subject: Join Our Conference

Hi [Name],

Join our conference with one click:

🔵 Microsoft: https://vle.nexsy.io/conferences/46/join/microsoft/
🔴 Google: https://vle.nexsy.io/conferences/46/join/google/

No login required - just click and join!
```

## 🎯 Calendar Invite

**Meeting Link:** 
```
https://vle.nexsy.io/conferences/46/join/microsoft/
```

**Description:**
```
Click the meeting link above to join with your Microsoft account.
New to the platform? An account will be created automatically.
```

## 💡 Tips

- **Bookmark:** Users can bookmark SSO links for quick access
- **Mobile:** Works perfectly on mobile devices
- **QR Codes:** Generate QR codes for easy scanning
- **Email Campaigns:** Include in automated email campaigns
- **LMS Integration:** Embed in other systems

## 🔒 Security

- ✅ OAuth 2.0 standard authentication
- ✅ Supports Two-Factor Authentication (2FA)
- ✅ Secure session handling
- ✅ CSRF protection
- ✅ Conference access rules enforced

## 🐛 Troubleshooting

**Link not working?**
- Verify conference ID is correct
- Check if conference exists and is active
- Ensure OAuth is configured in admin settings

**User not redirected?**
- Clear browser cache/cookies
- Try incognito/private browsing mode
- Check for JavaScript errors in console

## 📞 Support

For issues or questions, contact your system administrator or refer to the full documentation in `SSO_CONFERENCE_JOIN.md`.

