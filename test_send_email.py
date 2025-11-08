#!/usr/bin/env python3
"""
Test sending an actual email using Microsoft Graph API
This validates that Mail.Send permission is properly configured
"""

import requests
import json
import sys

# Test credentials - Load from environment variables
import os

OUTLOOK_CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID", "your-client-id-here")
OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET", "your-client-secret-here")
OUTLOOK_TENANT_ID = os.getenv("OUTLOOK_TENANT_ID", "your-tenant-id-here")
OUTLOOK_FROM_EMAIL = os.getenv("OUTLOOK_FROM_EMAIL", "noreply@nexsy.io")

def get_access_token():
    """Get OAuth2 access token"""
    token_url = f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': OUTLOOK_CLIENT_ID,
        'client_secret': OUTLOOK_CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    response = requests.post(token_url, data=token_data, timeout=10)
    response.raise_for_status()
    return response.json().get('access_token')


def send_test_email(recipient_email):
    """Send a test email via Microsoft Graph API"""
    
    print("=" * 60)
    print("📧 Testing Email Send via Microsoft Graph API")
    print("=" * 60)
    print()
    
    # Get access token
    print("🔑 Getting access token...")
    try:
        access_token = get_access_token()
        print("   ✅ Access token obtained")
        print()
    except Exception as e:
        print(f"   ❌ Failed to get access token: {str(e)}")
        return False
    
    # Prepare email
    print(f"📨 Preparing test email...")
    print(f"   From: {OUTLOOK_FROM_EMAIL}")
    print(f"   To: {recipient_email}")
    print(f"   Subject: Test Email from Nexsy LMS - OAuth2 Configuration")
    print()
    
    email_data = {
        "message": {
            "subject": "Test Email from Nexsy LMS - OAuth2 Configuration",
            "body": {
                "contentType": "HTML",
                "content": """
                <html>
                <body>
                    <h2>✅ Success! OAuth2 Email Configuration is Working</h2>
                    <p>This is a test email from your Nexsy LMS system.</p>
                    <p><strong>Configuration Details:</strong></p>
                    <ul>
                        <li>From Email: {from_email}</li>
                        <li>Authentication: Microsoft 365 OAuth2</li>
                        <li>Date: {date}</li>
                    </ul>
                    <p>Your email system is now properly configured and ready to send notifications.</p>
                    <hr>
                    <p><small>Nexsy Learning Management System</small></p>
                </body>
                </html>
                """.format(
                    from_email=OUTLOOK_FROM_EMAIL,
                    date=__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
                )
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient_email
                    }
                }
            ],
            "from": {
                "emailAddress": {
                    "address": OUTLOOK_FROM_EMAIL
                }
            }
        },
        "saveToSentItems": False
    }
    
    # Send email using Microsoft Graph API
    print("🚀 Attempting to send email...")
    
    # Use the send mail endpoint with the sender's mailbox
    send_url = f"https://graph.microsoft.com/v1.0/users/{OUTLOOK_FROM_EMAIL}/sendMail"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(send_url, headers=headers, json=email_data, timeout=15)
        
        if response.status_code == 202:
            print("   ✅ Email sent successfully!")
            print(f"   Status Code: {response.status_code} (Accepted)")
            print()
            print("=" * 60)
            print("✅ SUCCESS! Email configuration is fully functional!")
            print("=" * 60)
            print()
            print("📝 Next Steps:")
            print("   1. Check the recipient inbox for the test email")
            print("   2. Add credentials to your .env file")
            print("   3. Restart your Django application")
            print()
            return True
            
        else:
            print(f"   ⚠️  Unexpected response code: {response.status_code}")
            print(f"   Response: {response.text}")
            
            if response.status_code == 400:
                print()
                print("💡 Troubleshooting:")
                print("   - Verify the sender mailbox exists in Microsoft 365")
                print("   - Check that the mailbox is licensed")
                print("   - Ensure the mailbox can send emails")
                
            return False
            
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ HTTP Error: {e}")
        
        try:
            error_data = e.response.json()
            print(f"   Error Details: {json.dumps(error_data, indent=2)}")
            
            error_code = error_data.get('error', {}).get('code', '')
            error_message = error_data.get('error', {}).get('message', '')
            
            print()
            print("💡 Troubleshooting:")
            
            if 'Mail.Send' in error_message or 'Insufficient privileges' in error_message:
                print("   ❌ Missing Mail.Send Permission!")
                print()
                print("   To fix this:")
                print("   1. Go to Azure Portal (portal.azure.com)")
                print("   2. Navigate to: Azure Active Directory > App Registrations")
                print(f"   3. Find your app (Client ID: {OUTLOOK_CLIENT_ID})")
                print("   4. Go to 'API Permissions'")
                print("   5. Add 'Mail.Send' (Application permission)")
                print("   6. Grant Admin Consent")
                print()
                
            elif 'MailboxNotEnabledForRESTAPI' in error_code or 'MailboxNotFound' in error_code:
                print(f"   ❌ Mailbox issue for {OUTLOOK_FROM_EMAIL}")
                print()
                print("   Possible causes:")
                print("   1. Mailbox doesn't exist in Microsoft 365")
                print("   2. Mailbox is not licensed")
                print("   3. Mailbox is not enabled for this operation")
                print()
                print("   To fix:")
                print("   - Create the mailbox in Microsoft 365 Admin Center")
                print("   - Assign an appropriate license (Exchange Online)")
                print("   - Wait a few minutes for provisioning")
                print()
                
        except:
            print(f"   Response: {e.response.text if hasattr(e.response, 'text') else 'No details'}")
        
        return False
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 test_send_email.py <recipient_email>")
        print()
        print("Example: python3 test_send_email.py admin@nexsy.io")
        print()
        sys.exit(1)
    
    recipient = sys.argv[1]
    
    try:
        success = send_test_email(recipient)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

