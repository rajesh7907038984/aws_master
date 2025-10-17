#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify logout button functionality
"""
import requests
import time
import sys

def test_logout_button():
    """Test the logout button functionality"""
    base_url = "http://localhost:8000"
    
    print("Testing logout button functionality...")
    
    try:
        # Test 1: Check if server is running
        print("1. Checking if server is running...")
        response = requests.get(base_url + "/", timeout=5)
        if response.status_code == 200:
            print("   ✅ Server is running")
        else:
            print("   ❌ Server returned status " + str(response.status_code))
            return False
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Server is not running. Please start the server first.")
        return False
    except Exception as e:
        print("   ❌ Error connecting to server: " + str(e))
        return False
    
    # Test 2: Check if logout URL exists
    print("2. Checking logout URL...")
    try:
        response = requests.get(base_url + "/logout/", timeout=5)
        if response.status_code == 200:
            print("   ✅ Logout URL is accessible")
        else:
            print("   ❌ Logout URL returned status " + str(response.status_code))
    except Exception as e:
        print("   ❌ Error accessing logout URL: " + str(e))
    
    # Test 3: Check if logout form exists in response
    print("3. Checking for logout form in header...")
    try:
        response = requests.get(base_url + "/", timeout=5)
        if 'id="logout-form"' in response.text:
            print("   ✅ Logout form found in HTML")
        else:
            print("   ❌ Logout form not found in HTML")
            
        if 'id="logout-button"' in response.text:
            print("   ✅ Logout button found in HTML")
        else:
            print("   ❌ Logout button not found in HTML")
            
    except Exception as e:
        print("   ❌ Error checking HTML content: " + str(e))
    
    print("\nLogout button test completed!")
    print("To test manually:")
    print("1. Open browser and go to http://localhost:8000")
    print("2. Login with valid credentials")
    print("3. Click on the profile dropdown in the header")
    print("4. Click the logout button")
    print("5. Verify that logout works properly")
    
    return True

if __name__ == "__main__":
    test_logout_button()
