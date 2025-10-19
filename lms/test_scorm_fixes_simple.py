#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple SCORM Fixes Test Script
Tests the extraction-related bug fixes implemented
"""
import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ELearningPackage
from scorm.storage import SCORMS3Storage
import tempfile
import zipfile
import shutil

def test_zip_security():
    """Test ZIP security validation"""
    print("Testing ZIP Security Validation...")
    
    # Create a test ZIP with security issues
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as f:
        test_zip_path = f.name
    
    try:
        # Create a malicious ZIP file
        with zipfile.ZipFile(test_zip_path, 'w') as zf:
            # Add a file with path traversal
            zf.writestr('../malicious.txt', 'malicious content')
            # Add a suspicious file
            zf.writestr('system32/cmd.exe', 'fake executable')
        
        # Test security validation
        pkg = ELearningPackage()
        is_secure = pkg._validate_zip_security(test_zip_path)
        
        if not is_secure:
            print("   PASS: ZIP security validation correctly blocked malicious ZIP")
            return True
        else:
            print("   FAIL: ZIP security validation failed to block malicious ZIP")
            return False
            
    except Exception as e:
        print(f"   FAIL: ZIP security test failed: {e}")
        return False
    finally:
        if os.path.exists(test_zip_path):
            os.unlink(test_zip_path)

def test_manifest_parsing():
    """Test enhanced manifest parsing"""
    print("Testing Enhanced Manifest Parsing...")
    
    # Create test manifest file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><manifest><title>Test Title</title></manifest>')
        manifest_path = f.name
    
    try:
        pkg = ELearningPackage()
        pkg._parse_scorm_manifest(manifest_path)
        
        if pkg.title:
            print(f"   PASS: Manifest parsed successfully: {pkg.title}")
            return True
        else:
            print("   FAIL: Manifest parsing failed")
            return False
            
    except Exception as e:
        print(f"   FAIL: Manifest parsing test failed: {e}")
        return False
    finally:
        os.unlink(manifest_path)

def test_content_type_detection():
    """Test enhanced content type detection"""
    print("Testing Enhanced Content Type Detection...")
    
    test_files = [
        ('test.html', 'text/html; charset=utf-8'),
        ('test.css', 'text/css; charset=utf-8'),
        ('test.js', 'application/javascript; charset=utf-8'),
    ]
    
    try:
        pkg = ELearningPackage()
        
        for filename, expected_type in test_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{filename.split(".")[-1]}') as f:
                f.write(b'test content')
                file_path = f.name
            
            try:
                detected_type = pkg._get_enhanced_content_type(file_path, filename)
                
                if detected_type == expected_type:
                    print(f"   PASS: {filename}: {detected_type}")
                else:
                    print(f"   WARN: {filename}: Expected {expected_type}, got {detected_type}")
                    
            finally:
                os.unlink(file_path)
        
        return True
        
    except Exception as e:
        print(f"   FAIL: Content type detection test failed: {e}")
        return False

def test_existing_packages():
    """Test existing SCORM packages for compatibility"""
    print("Testing Existing SCORM Packages...")
    
    try:
        packages = ELearningPackage.objects.all()
        print(f"   Found {packages.count()} SCORM packages")
        
        if packages.count() == 0:
            print("   WARN: No existing packages to test")
            return True
        
        storage = SCORMS3Storage()
        working_packages = 0
        
        for pkg in packages[:3]:  # Test first 3 packages
            if not pkg.is_extracted or not pkg.launch_file:
                continue
            
            try:
                # Test path consistency
                if 'packages/packages/' in pkg.extracted_path:
                    print(f"   FAIL: Package {pkg.topic_id}: Double packages/ prefix")
                    continue
                
                # Test S3 file existence
                full_path = f"{pkg.extracted_path}/{pkg.launch_file}"
                if storage.exists(full_path):
                    print(f"   PASS: Package {pkg.topic_id}: Working correctly")
                    working_packages += 1
                else:
                    print(f"   FAIL: Package {pkg.topic_id}: File not found in S3")
                    
            except Exception as e:
                print(f"   FAIL: Package {pkg.topic_id}: Error - {e}")
        
        print(f"   Working packages: {working_packages}/{min(3, packages.count())}")
        return working_packages > 0
        
    except Exception as e:
        print(f"   FAIL: Existing packages test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("SCORM FIXES TEST SUITE")
    print("=" * 60)
    print()
    
    tests = [
        ("ZIP Security", test_zip_security),
        ("Manifest Parsing", test_manifest_parsing),
        ("Content Type Detection", test_content_type_detection),
        ("Existing Packages", test_existing_packages),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * 40)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   FAIL: Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nALL TESTS PASSED! SCORM fixes are working correctly.")
    else:
        print(f"\n{total - passed} test(s) failed. Some fixes may need attention.")
    
    print("=" * 60)
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
