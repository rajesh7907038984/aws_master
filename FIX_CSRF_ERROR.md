# CSRF Error Fix Guide

## Current Issue
You're getting: "Forbidden (403) - CSRF verification failed. Request aborted."

## Common Causes and Solutions

### Solution 1: Add Missing Domain to CSRF_TRUSTED_ORIGINS (Most Common)

If you're accessing the site via a URL that's not in CSRF_TRUSTED_ORIGINS, you need to add it.

#### Check your .env file and ensure these are set:

```bash
# Your primary domain
PRIMARY_DOMAIN=vle.nexsy.io

# If using load balancer
ALB_DOMAIN=vle.nexsy.io

# Add any additional domains (comma-separated)
ADDITIONAL_CSRF_ORIGINS=https://www.vle.nexsy.io,http://vle.nexsy.io
```

### Solution 2: Add HTTP variant if accessing via HTTP

If you're accessing the site via HTTP (not HTTPS), add HTTP variant:

Edit your `.env` file:
```bash
ADDITIONAL_CSRF_ORIGINS=http://vle.nexsy.io,http://www.vle.nexsy.io
```

### Solution 3: Temporarily Disable CSRF for Testing (NOT for production)

To test if CSRF is the issue, you can temporarily disable it:

Edit `/home/ec2-user/lms/LMS_Project/settings/base.py`:

Find line 222:
```python
'django.middleware.csrf.CsrfViewMiddleware',  # RE-ENABLED FOR PROPER CSRF PROTECTION
```

Comment it out:
```python
# 'django.middleware.csrf.CsrfViewMiddleware',  # TEMPORARILY DISABLED FOR TESTING
```

**IMPORTANT:** Only do this for testing! Re-enable it immediately after.

### Solution 4: Clear Browser Cookies

Sometimes old cookies cause CSRF errors:
1. Clear your browser cookies for the site
2. Clear browser cache
3. Try accessing the site again in an incognito/private window

### Solution 5: Restart the Django Server

After making changes to settings:
```bash
sudo systemctl restart lms-production
# OR if using gunicorn
sudo systemctl restart gunicorn
# OR if running manually
pkill -f gunicorn
cd /home/ec2-user/lms
gunicorn LMS_Project.wsgi:application --bind 0.0.0.0:8000
```

### Solution 6: Check if Form Has CSRF Token

If you have a custom form, ensure it includes:
```html
<form method="post">
    {% csrf_token %}
    <!-- form fields -->
</form>
```

### Solution 7: For AJAX Requests

If making AJAX requests, ensure CSRF token is included:
```javascript
fetch('/your-endpoint/', {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'Content-Type': 'application/json',
    },
    body: JSON.stringify(data)
});

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
```

## Quick Fix (Recommended)

1. **Edit your .env file** and add:
```bash
ADDITIONAL_CSRF_ORIGINS=https://vle.nexsy.io,http://vle.nexsy.io,https://www.vle.nexsy.io,http://www.vle.nexsy.io
```

2. **Restart your Django application**:
```bash
sudo systemctl restart lms-production
```

3. **Clear browser cookies** and try again

## How to Check Current Settings

Run this command to see current CSRF settings:
```bash
cd /home/ec2-user/lms
grep -E "CSRF_TRUSTED_ORIGINS|PRIMARY_DOMAIN|ALB_DOMAIN" .env
```

## Still Having Issues?

Enable DEBUG mode temporarily to see more details:

Edit `/home/ec2-user/lms/LMS_Project/settings/production.py`:

Change line 375:
```python
DEBUG = True  # Temporarily enable for debugging
```

Then check the detailed error page in your browser.

**IMPORTANT:** Set DEBUG back to False after debugging!

## Need More Help?

Please provide:
1. The exact URL you're accessing (e.g., http://vle.nexsy.io or https://vle.nexsy.io)
2. Whether you're submitting a form or making an AJAX request
3. The browser console errors (F12 > Console tab)

