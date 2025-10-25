#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Streaming Diagnostic Script
"""
import os
import sys
import django
import urllib.parse

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.core.files.storage import default_storage
from django.conf import settings
import boto3
from botocore.exceptions import ClientError

def test_s3_connection():
    print("Testing S3 Connection...")
    try:
        s3_client = boto3.client('s3')
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        region = settings.AWS_S3_REGION_NAME
        
        print("   Bucket: " + str(bucket_name))
        print("   Region: " + str(region))
        
        response = s3_client.head_bucket(Bucket=bucket_name)
        print("S3 bucket access successful")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '403':
            print("S3 Access Denied - Check IAM permissions")
        elif error_code == '404':
            print("S3 Bucket not found")
        else:
            print("S3 Error: " + str(e))
        return False
    except Exception as e:
        print("S3 Connection Error: " + str(e))
        return False

def test_video_file():
    print("\nTesting Video File...")
    
    video_path = "course_videos/12/20251023_133825_ac3ec5f7_Induction Video 1.mp4"
    print("   Testing path: " + video_path)
    
    try:
        print("   Testing Django storage access...")
        exists = default_storage.exists(video_path)
        print("   File exists (Django): " + str(exists))
        
        print("   Testing URL generation...")
        try:
            file_url = default_storage.url(video_path)
            print("   Generated URL: " + str(file_url))
        except Exception as url_error:
            print("   URL generation error: " + str(url_error))
            return False
        
        print("   Testing direct S3 access...")
        s3_client = boto3.client('s3')
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        media_location = settings.AWS_MEDIA_LOCATION
        
        s3_key = media_location + "/" + video_path
        print("   S3 Key: " + s3_key)
        
        try:
            response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            print("File exists in S3")
            print("   File size: " + str(response['ContentLength']) + " bytes")
            print("   Content type: " + str(response.get('ContentType', 'Unknown')))
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                print("File not found in S3")
            elif error_code == '403':
                print("Access denied to file in S3")
            else:
                print("S3 Error: " + str(e))
            return False
            
    except Exception as e:
        print("Error testing video file: " + str(e))
        return False

def test_url_encoding():
    print("\nTesting URL Encoding...")
    
    encoded_path = "course_videos/12/20251023_133825_ac3ec5f7_Induction%20Video%201.mp4"
    decoded_path = urllib.parse.unquote(encoded_path)
    
    print("   Encoded path: " + encoded_path)
    print("   Decoded path: " + decoded_path)
    
    for path_name, path in [("Encoded", encoded_path), ("Decoded", decoded_path)]:
        try:
            exists = default_storage.exists(path)
            print("   " + path_name + " path exists: " + str(exists))
        except Exception as e:
            print("   " + path_name + " path error: " + str(e))

def main():
    print("=" * 60)
    print("VIDEO STREAMING DIAGNOSTIC")
    print("=" * 60)
    
    s3_ok = test_s3_connection()
    
    if not s3_ok:
        print("\nS3 connection failed. Check your AWS credentials and permissions.")
        return
    
    video_ok = test_video_file()
    test_url_encoding()
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print("S3 Connection: " + ("OK" if s3_ok else "FAILED"))
    print("Video File: " + ("OK" if video_ok else "FAILED"))

if __name__ == "__main__":
    main()
