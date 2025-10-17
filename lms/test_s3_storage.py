#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for S3 storage configuration
"""
import os
import sys
import django

# Add the project root to the Python path
sys.path.insert(0, '/home/ec2-user/lms')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

def test_s3_storage():
    """Test the S3 storage configuration"""
    print("🧪 Testing S3 Storage Configuration")
    print("=" * 50)
    
    # Test 1: Check S3 configuration
    print(f"☁️ AWS Bucket: {getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'Not set')}")
    print(f"☁️ AWS Region: {getattr(settings, 'AWS_S3_REGION_NAME', 'Not set')}")
    print(f"☁️ MEDIA_URL: {getattr(settings, 'MEDIA_URL', 'Not set')}")
    print(f"☁️ DEFAULT_FILE_STORAGE: {getattr(settings, 'DEFAULT_FILE_STORAGE', 'Not set')}")
    
    # Test 2: Check if S3 credentials are available
    aws_access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
    aws_secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
    
    if aws_access_key and aws_secret_key:
        print("✅ AWS credentials are configured")
    else:
        print("❌ AWS credentials are missing")
        print("   Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file")
        return False
    
    # Test 3: Test S3 storage functionality
    try:
        # Create a test file
        test_filename = 'test_s3_upload.txt'
        test_content = ContentFile(b'This is a test file for S3 storage')
        
        # Save file to S3
        saved_name = default_storage.save(test_filename, test_content)
        print(f"✅ File saved to S3: {saved_name}")
        
        # Check if file exists
        if default_storage.exists(saved_name):
            print(f"✅ File exists in S3")
            
            # Get file URL
            file_url = default_storage.url(saved_name)
            print(f"🌐 File URL: {file_url}")
            
            # Get file size
            file_size = default_storage.size(saved_name)
            print(f"📏 File size: {file_size} bytes")
            
            # Clean up test file
            default_storage.delete(saved_name)
            print(f"🗑️ Test file deleted from S3")
            
        else:
            print(f"❌ File not found in S3")
            return False
            
    except Exception as e:
        print(f"❌ Error testing S3 storage: {e}")
        return False
    
    print("\n✅ S3 storage configuration test completed successfully!")
    return True

def test_scorm_s3_storage():
    """Test the SCORM S3 storage specifically"""
    print("\n🧪 Testing SCORM S3 Storage")
    print("=" * 50)
    
    try:
        from scorm.storage import SCORMS3Storage
        
        # Create SCORM S3 storage instance
        scorm_storage = SCORMS3Storage()
        print(f"✅ SCORM S3 storage created successfully")
        print(f"☁️ SCORM storage location: {scorm_storage.location}")
        print(f"☁️ SCORM storage bucket: {scorm_storage.bucket_name}")
        
        # Test SCORM storage functionality
        test_filename = 'scorm_test.txt'
        test_content = ContentFile(b'This is a test SCORM file for S3 storage')
        
        # Save file using SCORM storage
        saved_name = scorm_storage.save(test_filename, test_content)
        print(f"✅ SCORM file saved to S3: {saved_name}")
        
        # Check if file exists
        if scorm_storage.exists(saved_name):
            print(f"✅ SCORM file exists in S3")
            
            # Get file URL
            file_url = scorm_storage.url(saved_name)
            print(f"🌐 SCORM file URL: {file_url}")
            
            # Clean up test file
            scorm_storage.delete(saved_name)
            print(f"🗑️ SCORM test file deleted from S3")
            
        else:
            print(f"❌ SCORM file not found in S3")
            return False
            
    except Exception as e:
        print(f"❌ Error testing SCORM S3 storage: {e}")
        return False
    
    print("\n✅ SCORM S3 storage test completed successfully!")
    return True

if __name__ == "__main__":
    print("🚀 Starting S3 Storage Tests")
    print("=" * 60)
    
    # Test general S3 storage
    s3_success = test_s3_storage()
    
    # Test SCORM S3 storage
    scorm_success = test_scorm_s3_storage()
    
    if s3_success and scorm_success:
        print("\n🎉 All S3 storage tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some S3 storage tests failed!")
        sys.exit(1)
