#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic script for Microsoft OAuth configuration
Run this to check if Microsoft OAuth is properly configured
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.urls import reverse
from django.test import RequestFactory
from account_settings.models import GlobalAdminSettings

def diagnose_microsoft_oauth():
    """Diagnose Microsoft OAuth configuration issues"""
    
    print("=" * 80)
    print("Microsoft OAuth Configuration Diagnostic")
    print("=" * 80)
    print()
    
    # Check 1: Database Configuration
    print("1. Checking database configuration...")
    try:
        settings = GlobalAdminSettings.get_settings()
        
        print(f"   ✓ GlobalAdminSettings found")
        print(f"   - Microsoft OAuth Enabled: {settings.microsoft_oauth_enabled}")
        print(f"   - Microsoft Client ID: {'✓ SET' if settings.microsoft_client_id else '✗ NOT SET'}")
        print(f"   - Microsoft Client Secret: {'✓ SET' if settings.microsoft_client_secret else '✗ NOT SET'}")
        print(f"   - Microsoft Tenant ID: {settings.microsoft_tenant_id or 'common (default)'}")
        
        if not settings.microsoft_client_id or not settings.microsoft_client_secret:
            print()
            print("   ⚠️  WARNING: Microsoft OAuth credentials are not configured!")
            print("   The button may appear but won't work without credentials.")
            print("   Configure them at: Admin Settings > Microsoft OAuth")
            print()
    except Exception as e:
        print(f"   ✗ Error checking database: {e}")
        return
    
    print()
    
    # Check 2: URL Configuration
    print("2. Checking URL configuration...")
    try:
        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'vle.nexsy.io'
        request.META['SERVER_PORT'] = '443'
        request.META['wsgi.url_scheme'] = 'https'
        
        # Build absolute URI for callback
        callback_path = reverse('users:microsoft_callback')
        redirect_uri = f"https://vle.nexsy.io{callback_path}"
        
        print(f"   ✓ Callback URL path: {callback_path}")
        print(f"   ✓ Full redirect URI: {redirect_uri}")
        print()
        print("   ⚠️  IMPORTANT: This redirect URI must be registered in Azure AD!")
        print("      Go to: Azure Portal > App Registrations > Your App > Authentication")
        print("      Add this exact URL as a redirect URI:")
        print(f"      {redirect_uri}")
        print()
    except Exception as e:
        print(f"   ✗ Error building redirect URI: {e}")
    
    print()
    
    # Check 3: Common Issues
    print("3. Common Microsoft OAuth Issues:")
    print()
    print("   Issue A: Redirect URI Mismatch")
    print("   ────────────────────────────────")
    print("   - The redirect URI in your Azure AD app MUST exactly match:")
    print(f"     {redirect_uri}")
    print("   - It must include the protocol (https://)")
    print("   - It must match the domain exactly")
    print("   - No trailing slash")
    print()
    
    print("   Issue B: Application Permissions")
    print("   ─────────────────────────────────")
    print("   - Required Microsoft Graph API permissions:")
    print("     • openid (enabled)")
    print("     • email (enabled)")
    print("     • profile (enabled)")
    print("     • User.Read (enabled)")
    print()
    
    print("   Issue C: Supported Account Types")
    print("   ─────────────────────────────────")
    print("   - Check your app's supported account types in Azure AD")
    print("   - For multi-tenant: Use tenant_id = 'common'")
    print("   - For single tenant: Use your specific tenant ID")
    print(f"   - Currently configured: {settings.microsoft_tenant_id or 'common'}")
    print()
    
    print("   Issue D: Client Secret Expiration")
    print("   ──────────────────────────────────")
    print("   - Client secrets expire in Azure AD (typically 6-24 months)")
    print("   - Check if your client secret has expired")
    print("   - Generate a new secret if needed and update in Admin Settings")
    print()
    
    # Check 4: Template Tag
    print("4. Checking template tag...")
    from account_settings.templatetags.account_settings_tags import is_microsoft_oauth_enabled
    is_enabled = is_microsoft_oauth_enabled()
    
    if is_enabled:
        print(f"   ✓ Template tag returns: {is_enabled}")
        print("   Microsoft OAuth button should be visible")
    else:
        print(f"   ✗ Template tag returns: {is_enabled}")
        print("   Microsoft OAuth button will NOT be visible")
        print("   Reason: Client ID or Client Secret is missing")
    
    print()
    print("=" * 80)
    print()
    
    # Provide actionable recommendations
    print("RECOMMENDATIONS:")
    print("=" * 80)
    
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        print()
        print("🔴 CRITICAL: Configure Microsoft OAuth credentials")
        print("   1. Go to Azure Portal (portal.azure.com)")
        print("   2. Navigate to 'App registrations'")
        print("   3. Create or select your app")
        print("   4. Copy the 'Application (client) ID'")
        print("   5. Create a new 'Client secret' under 'Certificates & secrets'")
        print("   6. Add these to: Admin Settings > Microsoft OAuth Configuration")
        print()
    else:
        print()
        print("🟡 IMPORTANT: Verify Azure AD configuration")
        print(f"   1. Add redirect URI: {redirect_uri}")
        print("   2. Ensure API permissions are granted")
        print("   3. Check if client secret has expired")
        print("   4. Test the OAuth flow")
        print()
    
    print("=" * 80)
    print()

if __name__ == '__main__':
    diagnose_microsoft_oauth()

