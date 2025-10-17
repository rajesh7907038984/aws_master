#!/usr/bin/env python3
"""
SCORM API Test Script
Tests the enhanced SCORM API implementation
"""

import os
import sys
import django
import requests
from bs4 import BeautifulSoup

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

def test_scorm_api_discovery():
    """Test SCORM API discovery mechanism"""
    print("🔍 Testing SCORM API Discovery...")
    
    # Test SCORM launch page
    try:
        response = requests.get("https://staging.nexsy.io/scorm/launch/276/", timeout=10)
        if response.status_code == 200:
            print("✅ SCORM launch page accessible")
            
            # Check for API injection
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts = soup.find_all('script')
            
            api_found = False
            for script in scripts:
                if script.string and 'SCORM API' in script.string:
                    api_found = True
                    print("✅ SCORM API script found in launch page")
                    break
            
            if not api_found:
                print("⚠️  SCORM API script not found in launch page")
                
        else:
            print(f"❌ SCORM launch page returned status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing SCORM launch: {e}")

def test_scorm_content_api():
    """Test SCORM content API injection"""
    print("\n🔍 Testing SCORM Content API...")
    
    try:
        # Test SCORM content endpoint
        response = requests.get("https://staging.nexsy.io/scorm/content/276/index.html", timeout=10)
        if response.status_code == 200:
            print("✅ SCORM content accessible")
            
            # Check for API injection in content
            if 'SCORM API' in response.text:
                print("✅ SCORM API injected into content")
            else:
                print("⚠️  SCORM API not found in content")
                
        else:
            print(f"❌ SCORM content returned status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing SCORM content: {e}")

def test_scorm_api_endpoint():
    """Test SCORM API endpoint"""
    print("\n🔍 Testing SCORM API Endpoint...")
    
    try:
        # Test SCORM API endpoint
        response = requests.get("https://staging.nexsy.io/scorm/api/276/", timeout=10)
        if response.status_code == 200:
            print("✅ SCORM API endpoint accessible")
        else:
            print(f"❌ SCORM API endpoint returned status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing SCORM API endpoint: {e}")

def main():
    """Run all SCORM tests"""
    print("🚀 SCORM API Test Suite")
    print("=" * 50)
    
    test_scorm_api_discovery()
    test_scorm_content_api()
    test_scorm_api_endpoint()
    
    print("\n" + "=" * 50)
    print("✅ SCORM API testing completed")

if __name__ == "__main__":
    main()
