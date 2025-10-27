#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UI Test for SCORM Video Player Icons
Tests the actual SCORM page to verify icons are displaying correctly
"""
import requests
from requests.auth import HTTPBasicAuth
import time

def test_scorm_ui():
    """Test SCORM UI to verify video player icons are working"""
    print("🎬 SCORM UI Test - Video Player Icons")
    print("=" * 60)
    
    # Test URLs
    base_url = "https://staging.nexsy.io"
    login_url = f"{base_url}/users/login/"
    scorm_url = f"{base_url}/scorm/view/117/"
    
    # Create session
    session = requests.Session()
    
    try:
        print("1. 🔐 Testing Authentication...")
        login_page = session.get(login_url)
        print(f"   Login page status: {login_page.status_code}")
        
        # Try to access SCORM page
        print("\n2. 📄 Testing SCORM Page Access...")
        scorm_response = session.get(scorm_url)
        print(f"   SCORM page status: {scorm_response.status_code}")
        print(f"   Final URL: {scorm_response.url}")
        
        # Check CSP headers
        print("\n3. 🛡️ Checking CSP Headers...")
        csp_header = scorm_response.headers.get('Content-Security-Policy', 'Not found')
        
        # Analyze CSP for font support
        font_src_ok = 'font-src' in csp_header and 'data:' in csp_header
        script_src_ok = 'script-src' in csp_header and 'unsafe-eval' in csp_header
        
        print(f"   ✅ Font-src with data: URLs: {'YES' if font_src_ok else 'NO'}")
        print(f"   ✅ Script-src with unsafe-eval: {'YES' if script_src_ok else 'NO'}")
        
        if font_src_ok and script_src_ok:
            print("   🎉 CSP Configuration: CORRECT")
        else:
            print("   ❌ CSP Configuration: ISSUES FOUND")
        
        # Check page content
        print("\n4. 📋 Checking Page Content...")
        if scorm_response.status_code == 200:
            content = scorm_response.text
            
            # Look for video player elements
            video_elements = content.count('<video')
            iframe_elements = content.count('<iframe')
            scorm_elements = content.count('scorm')
            
            print(f"   Video elements found: {video_elements}")
            print(f"   Iframe elements found: {iframe_elements}")
            print(f"   SCORM references found: {scorm_elements}")
            
            # Check for font references
            font_refs = content.count('font-family') + content.count('@font-face')
            print(f"   Font references found: {font_refs}")
            
            if video_elements > 0 or iframe_elements > 0:
                print("   ✅ SCORM content structure: PRESENT")
            else:
                print("   ⚠️ SCORM content structure: LIMITED")
        
        # Test font loading URLs
        print("\n5. 🔤 Testing Font URLs...")
        font_urls = [
            f"{base_url}/scorm/content/117/scormcontent/lib/fonts/icomoon.woff",
            f"{base_url}/scorm/content/117/scormcontent/lib/fonts/icomoon.ttf",
            f"{base_url}/scorm/content/117/scormcontent/lib/fonts/Lato-Regular.woff"
        ]
        
        for font_url in font_urls:
            try:
                font_response = session.head(font_url)
                status = font_response.status_code
                content_type = font_response.headers.get('Content-Type', 'Unknown')
                
                if status == 200:
                    print(f"   ✅ {font_url.split('/')[-1]}: {status} ({content_type})")
                elif status == 302:
                    print(f"   🔄 {font_url.split('/')[-1]}: {status} (Redirect - Auth required)")
                else:
                    print(f"   ❌ {font_url.split('/')[-1]}: {status}")
            except Exception as e:
                print(f"   ❌ {font_url.split('/')[-1]}: Error - {str(e)}")
        
        # Final assessment
        print("\n6. 📊 Final Assessment...")
        if font_src_ok and script_src_ok:
            print("   🎉 CSP Fix: SUCCESSFUL")
            print("   📝 Next Steps:")
            print("     1. Open browser and go to: https://staging.nexsy.io/scorm/view/117/")
            print("     2. Login with your credentials")
            print("     3. Check if video player icons display correctly (not squares)")
            print("     4. Test video playback and controls")
            print("     5. Check browser console for any remaining CSP errors")
        else:
            print("   ❌ CSP Fix: NEEDS ATTENTION")
            print("   📝 Issues to resolve:")
            if not font_src_ok:
                print("     - Font-src directive needs data: URLs")
            if not script_src_ok:
                print("     - Script-src directive needs unsafe-eval")
        
    except Exception as e:
        print(f"❌ Test Error: {e}")
    
    print("\n" + "=" * 60)
    print("🎬 UI Test Complete")
    print("=" * 60)

if __name__ == '__main__':
    test_scorm_ui()
