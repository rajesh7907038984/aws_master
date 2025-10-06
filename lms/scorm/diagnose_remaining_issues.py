#!/usr/bin/env python3
"""
SCORM Remaining Issues Diagnostic
Identifies and provides solutions for remaining SCORM issues
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from scorm.s3_direct import scorm_s3
from django.core.files.storage import default_storage
import boto3

def check_s3_content():
    """Check if SCORM content exists in S3"""
    print("🔍 Checking S3 Content...")
    
    try:
        package = ScormPackage.objects.first()
        if not package:
            print("❌ No SCORM packages found")
            return False
        
        print(f"✅ Package: {package.title}")
        print(f"   Extracted Path: {package.extracted_path}")
        print(f"   Launch URL: {package.launch_url}")
        
        # Check if extracted path exists
        if default_storage.exists(package.extracted_path):
            print(f"✅ Extracted path exists in storage")
        else:
            print(f"❌ Extracted path does NOT exist in storage")
            return False
        
        # Check launch file
        launch_file_path = f"{package.extracted_path}/{package.launch_url}"
        if default_storage.exists(launch_file_path):
            print(f"✅ Launch file exists: {package.launch_url}")
        else:
            print(f"❌ Launch file does NOT exist: {package.launch_url}")
            
            # Try to find the actual launch file
            print("🔍 Searching for alternative launch files...")
            try:
                dirs, files = default_storage.listdir(package.extracted_path)
                html_files = [f for f in files if f.endswith(('.html', '.htm'))]
                print(f"   Found HTML files: {html_files}")
                
                if html_files:
                    # Update the launch URL
                    package.launch_url = html_files[0]
                    package.save()
                    print(f"✅ Updated launch URL to: {html_files[0]}")
                else:
                    print("❌ No HTML files found in package")
                    return False
            except Exception as e:
                print(f"❌ Error listing directory: {e}")
                return False
        
        # Test S3 direct access
        s3 = scorm_s3
        if s3.verify_file_exists(package, package.launch_url):
            print(f"✅ S3 verification successful for {package.launch_url}")
        else:
            print(f"❌ S3 verification failed for {package.launch_url}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking S3 content: {e}")
        return False

def check_scorm_attempts():
    """Check SCORM attempts and their status"""
    print("\n🔍 Checking SCORM Attempts...")
    
    try:
        attempts = ScormAttempt.objects.all()
        if not attempts.exists():
            print("❌ No SCORM attempts found")
            return False
        
        print(f"✅ Found {attempts.count()} attempts")
        
        for attempt in attempts:
            print(f"\n   Attempt {attempt.id}:")
            print(f"     User: {attempt.user.username}")
            print(f"     Status: {attempt.lesson_status}")
            print(f"     Location: {attempt.lesson_location}")
            print(f"     Entry: {attempt.entry}")
            print(f"     CMI Data Keys: {len(attempt.cmi_data) if attempt.cmi_data else 0}")
            
            # Check for initialization issues
            if attempt.cmi_data and '_initialized' in attempt.cmi_data:
                print(f"     Initialized: {attempt.cmi_data['_initialized']}")
            else:
                print(f"     Initialized: False (missing _initialized flag)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking attempts: {e}")
        return False

def check_api_initialization():
    """Check API initialization issues"""
    print("\n🔍 Checking API Initialization...")
    
    try:
        attempt = ScormAttempt.objects.first()
        if not attempt:
            print("❌ No attempts found")
            return False
        
        # Check if attempt is already initialized
        if attempt.cmi_data and attempt.cmi_data.get('_initialized'):
            print("⚠️  Attempt is already initialized - this causes error 101")
            print("   Solution: Clear the _initialized flag or create a new attempt")
            
            # Clear the initialization flag
            if '_initialized' in attempt.cmi_data:
                del attempt.cmi_data['_initialized']
                attempt.save()
                print("✅ Cleared _initialized flag")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking API initialization: {e}")
        return False

def provide_solutions():
    """Provide solutions for remaining issues"""
    print("\n" + "="*60)
    print("SOLUTIONS FOR REMAINING ISSUES")
    print("="*60)
    
    print("\n1. S3 File Not Found Issue:")
    print("   - Check if SCORM package was properly extracted")
    print("   - Verify S3 permissions and bucket configuration")
    print("   - Run: python manage.py shell -c \"from scorm.models import ScormPackage; p=ScormPackage.objects.first(); print('Path:', p.extracted_path)\"")
    
    print("\n2. API Initialization Error (101):")
    print("   - This happens when API is called multiple times")
    print("   - Solution: Clear _initialized flag in CMI data")
    print("   - Or create a new attempt for testing")
    
    print("\n3. Content Serving Issues:")
    print("   - Check if launch URL is correct")
    print("   - Verify S3 file exists")
    print("   - Test with direct S3 URL")
    
    print("\n4. Performance Issues:")
    print("   - Progress tracking interval reduced to 3 seconds")
    print("   - Added proper cleanup for DOM observers")
    print("   - Added database locking to prevent race conditions")
    
    print("\n5. Security Issues:")
    print("   - Added path traversal protection")
    print("   - Added proper authentication checks")
    print("   - Added input validation")

def run_diagnosis():
    """Run complete diagnosis"""
    print("="*60)
    print("SCORM REMAINING ISSUES DIAGNOSIS")
    print("="*60)
    
    checks = [
        check_s3_content,
        check_scorm_attempts,
        check_api_initialization
    ]
    
    passed = 0
    for check in checks:
        if check():
            passed += 1
    
    print(f"\n✅ {passed}/{len(checks)} checks passed")
    
    provide_solutions()
    
    return passed == len(checks)

if __name__ == "__main__":
    run_diagnosis()
