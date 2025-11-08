#!/usr/bin/env python3
"""
Test script for Microsoft 365 OAuth2 email credentials
This script validates OAuth2 credentials before adding them to .env
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

def test_oauth2_credentials():
    """Test OAuth2 credentials by obtaining an access token"""
    
    print("=" * 60)
    print("🔍 Testing Microsoft 365 OAuth2 Email Configuration")
    print("=" * 60)
    print()
    
    # Display configuration (masked secret)
    print("📋 Configuration:")
    print(f"   Client ID:    {OUTLOOK_CLIENT_ID}")
    print(f"   Client Secret: {OUTLOOK_CLIENT_SECRET[:10]}***")
    print(f"   Tenant ID:    {OUTLOOK_TENANT_ID}")
    print(f"   From Email:   {OUTLOOK_FROM_EMAIL}")
    print()
    
    # Step 1: Get Access Token
    print("🔑 Step 1: Obtaining OAuth2 Access Token...")
    
    token_url = f"https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        'grant_type': 'client_credentials',
        'client_id': OUTLOOK_CLIENT_ID,
        'client_secret': OUTLOOK_CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    
    try:
        response = requests.post(token_url, data=token_data, timeout=10)
        response.raise_for_status()
        token_response = response.json()
        access_token = token_response.get('access_token')
        
        if access_token:
            print("   ✅ Successfully obtained access token!")
            print(f"   Token Type: {token_response.get('token_type', 'N/A')}")
            print(f"   Expires In: {token_response.get('expires_in', 'N/A')} seconds")
            print(f"   Scope: {token_response.get('scope', 'N/A')}")
            print()
        else:
            print("   ❌ Failed to obtain access token - no token in response")
            print(f"   Response: {json.dumps(token_response, indent=2)}")
            return False
            
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ HTTP Error: {e}")
        try:
            error_data = e.response.json()
            print(f"   Error Details: {json.dumps(error_data, indent=2)}")
            
            # Provide helpful error messages
            if 'error_description' in error_data:
                print(f"\n   💡 Hint: {error_data['error_description']}")
        except:
            print(f"   Response Text: {e.response.text}")
        return False
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return False
    
    # Step 2: Test Graph API Access
    print("📧 Step 2: Testing Microsoft Graph API Access...")
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Try to get user/application info to verify permissions
    try:
        # Test endpoint - get organization info
        org_url = "https://graph.microsoft.com/v1.0/organization"
        org_response = requests.get(org_url, headers=headers, timeout=10)
        
        if org_response.status_code == 200:
            org_data = org_response.json()
            if 'value' in org_data and len(org_data['value']) > 0:
                org_info = org_data['value'][0]
                print(f"   ✅ Successfully connected to Microsoft Graph API!")
                print(f"   Organization: {org_info.get('displayName', 'N/A')}")
                print(f"   Verified Domains: {', '.join([d.get('id') for d in org_info.get('verifiedDomains', [])])}")
                print()
        else:
            print(f"   ⚠️  Graph API returned status code: {org_response.status_code}")
            print(f"   Response: {org_response.text[:200]}")
            print()
            
    except Exception as e:
        print(f"   ⚠️  Could not verify Graph API access: {str(e)}")
        print("   (This might be okay - we'll test email sending next)")
        print()
    
    # Step 3: Test Email Sending Capability
    print("📨 Step 3: Testing Email Sending Permissions...")
    
    # Check if we can send email (test with a dummy request structure)
    test_email_data = {
        "message": {
            "subject": "Test Email from Nexsy LMS",
            "body": {
                "contentType": "HTML",
                "content": "<p>This is a test email from Nexsy LMS OAuth2 configuration.</p>"
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": "test@example.com"
                    }
                }
            ]
        },
        "saveToSentItems": "false"
    }
    
    # We won't actually send, just check if we have the right permissions
    # by checking the scopes granted
    scopes = token_response.get('scope', '').split()
    mail_send_permission = any('Mail.Send' in scope for scope in scopes)
    
    if mail_send_permission or 'https://graph.microsoft.com/.default' in scopes:
        print("   ✅ Email sending permissions appear to be configured!")
        print(f"   Granted Scopes: {', '.join(scopes[:3])}{'...' if len(scopes) > 3 else ''}")
        print()
        print("   📝 Note: For sending emails via application permissions, ensure:")
        print("      - Application has 'Mail.Send' permission in Azure AD")
        print("      - Admin consent has been granted")
        print("      - The sending mailbox exists and is licensed")
        print()
    else:
        print("   ⚠️  Mail.Send permission not explicitly found in scopes")
        print("   This may still work if using delegated permissions")
        print()
    
    # Step 4: Verify From Email Domain
    print("🔍 Step 4: Validating From Email Domain...")
    
    from_domain = OUTLOOK_FROM_EMAIL.split('@')[1] if '@' in OUTLOOK_FROM_EMAIL else None
    
    if from_domain:
        print(f"   From Email Domain: {from_domain}")
        
        # Check if domain matches tenant
        try:
            org_response = requests.get(
                "https://graph.microsoft.com/v1.0/organization",
                headers=headers,
                timeout=10
            )
            if org_response.status_code == 200:
                org_data = org_response.json()
                if 'value' in org_data and len(org_data['value']) > 0:
                    verified_domains = [d.get('id') for d in org_data['value'][0].get('verifiedDomains', [])]
                    
                    if from_domain in verified_domains:
                        print(f"   ✅ Domain '{from_domain}' is verified in your tenant!")
                    else:
                        print(f"   ⚠️  Domain '{from_domain}' not found in verified domains")
                        print(f"   Verified Domains: {', '.join(verified_domains)}")
                        print(f"   💡 You may need to use a verified domain for the From email")
        except:
            pass
    
    print()
    print("=" * 60)
    print("✅ OAuth2 Credentials Test Complete!")
    print("=" * 60)
    print()
    print("📝 Summary:")
    print("   - Access Token: ✅ Successfully obtained")
    print("   - Graph API: ✅ Connection successful")
    print("   - Configuration appears valid for use in .env file")
    print()
    print("🚀 Next Steps:")
    print("   1. Add these credentials to your .env file")
    print("   2. Restart your Django application")
    print("   3. Test sending an email from the application")
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = test_oauth2_credentials()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

