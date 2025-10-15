#!/usr/bin/env python3
"""
Script to check if SCORM files exist in S3 bucket
"""
import os
import sys
import django
import boto3

# Add the project directory to the path
sys.path.append('/home/ec2-user/lms')
os.chdir('/home/ec2-user/lms')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage
from core.env_loader import get_env

def main():
    print("=== S3 SCORM File Check ===\n")
    
    # Get SCORM package 119 (topic 179)
    try:
        package = ScormPackage.objects.get(id=119)
        print(f"Checking SCORM Package: {package.title}")
        print(f"Extracted path: {package.extracted_path}")
        print(f"Launch URL: {package.launch_url}")
        
        # Setup S3 client
        bucket_name = get_env('AWS_STORAGE_BUCKET_NAME', 'lms-staging-nexsy-io')
        region = get_env('AWS_S3_REGION_NAME', 'eu-west-2')
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=get_env('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=get_env('AWS_SECRET_ACCESS_KEY'),
            region_name=region
        )
        
        print(f"\nS3 Bucket: {bucket_name}")
        print(f"Region: {region}")
        
        # Check different potential paths
        base_paths = [
            f"media/{package.extracted_path}",  # Current expected path
            package.extracted_path,             # Without media prefix
            f"{package.extracted_path}",        # As stored
        ]
        
        for base_path in base_paths:
            print(f"\nChecking base path: {base_path}")
            
            # Try to list objects with this prefix
            try:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    Prefix=base_path,
                    MaxKeys=10
                )
                
                if 'Contents' in response:
                    print(f"  ✅ Found {len(response['Contents'])} files with prefix '{base_path}'")
                    for obj in response['Contents'][:5]:  # Show first 5 files
                        print(f"     - {obj['Key']}")
                    if len(response['Contents']) > 5:
                        print(f"     ... and {len(response['Contents']) - 5} more files")
                    
                    # Try to access the launch file specifically
                    launch_key = f"{base_path}/{package.launch_url}"
                    try:
                        s3_client.head_object(Bucket=bucket_name, Key=launch_key)
                        print(f"  ✅ Launch file exists: {launch_key}")
                    except Exception as e:
                        print(f"  ❌ Launch file not found: {launch_key} - {e}")
                        
                else:
                    print(f"  ❌ No files found with prefix '{base_path}'")
            except Exception as e:
                print(f"  ❌ Error listing objects: {e}")
        
        # Check what the error message indicates
        error_path = "media/scorm_content/b0919a0c-efdc-461d-b53f-2946efdc7322/scormcontent/falseKCH9GX2MSA8CZ8JQwT1DhIxFeOF0Lx4ATn88Kg7DB3EanFM0+cKg3QnnmC5nF/rPOrKp3Q0L/RavtEFVPsb4rCjO7KI="
        print(f"\nChecking problematic path from error: {error_path}")
        try:
            s3_client.head_object(Bucket=bucket_name, Key=error_path)
            print("  ✅ Error path exists (unexpected)")
        except Exception as e:
            print(f"  ❌ Error path doesn't exist (expected): {e}")
            
        # Check for common SCORM files
        common_files = ['index.html', 'index.htm', 'story.html', 'indexAPI.html']
        for base_path in base_paths[:1]:  # Only check the first valid base path
            print(f"\nChecking common SCORM files in {base_path}:")
            for filename in common_files:
                file_key = f"{base_path}/{filename}"
                try:
                    s3_client.head_object(Bucket=bucket_name, Key=file_key)
                    print(f"  ✅ {filename} exists")
                except Exception as e:
                    print(f"  ❌ {filename} not found")
    
    except ScormPackage.DoesNotExist:
        print("SCORM Package 119 not found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
