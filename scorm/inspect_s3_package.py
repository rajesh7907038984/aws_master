#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
S3 SCORM Package Inspector
Checks the actual files uploaded to S3 for topic ID 117
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from scorm.models import ScormPackage
from courses.models import Topic
import boto3
from core.env_loader import get_env


def inspect_s3_package(topic_id):
    """Inspect the actual S3 package structure"""
    print("=" * 100)
    print(f"S3 Package Inspector - Topic ID: {topic_id}")
    print("=" * 100)
    print()
    
    try:
        topic = Topic.objects.get(id=topic_id)
        scorm_package = topic.scorm_package
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return
    
    print(f"Package Info:")
    print(f"   ID: {scorm_package.id}")
    print(f"   Title: {scorm_package.title}")
    print(f"   Version: {scorm_package.version}")
    print(f"   Launch URL: {scorm_package.launch_url}")
    print(f"   Extracted Path: {scorm_package.extracted_path}")
    print()
    
    # S3 Configuration
    bucket_name = get_env('AWS_STORAGE_BUCKET_NAME')
    media_location = get_env('AWS_MEDIA_LOCATION', 'media')
    base_path = f"{media_location}/{scorm_package.extracted_path}/"
    
    print(f"S3 Configuration:")
    print(f"   Bucket: {bucket_name}")
    print(f"   Base Path: {base_path}")
    print()
    
    # Initialize S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=get_env('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=get_env('AWS_SECRET_ACCESS_KEY'),
        region_name=get_env('AWS_S3_REGION_NAME', 'eu-west-2')
    )
    
    # List all files
    print(f"S3 File Listing:")
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=base_path)
        
        all_files = []
        font_files = []
        video_files = []
        html_files = []
        js_files = []
        css_files = []
        icon_files = []
        
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                relative_path = key.replace(base_path, '')
                if not relative_path:  # Skip directory itself
                    continue
                
                file_info = {
                    'path': relative_path,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'full_key': key
                }
                all_files.append(file_info)
                
                # Categorize files
                lower_path = relative_path.lower()
                
                # Font files (CRITICAL for video player icons)
                if any(lower_path.endswith(ext) for ext in ['.woff', '.woff2', '.ttf', '.eot', '.otf']):
                    font_files.append(file_info)
                
                # Video files
                if any(lower_path.endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.avi', '.mov']):
                    video_files.append(file_info)
                
                # HTML files
                if lower_path.endswith(('.html', '.htm')):
                    html_files.append(file_info)
                
                # JavaScript files
                if lower_path.endswith('.js'):
                    js_files.append(file_info)
                
                # CSS files
                if lower_path.endswith('.css'):
                    css_files.append(file_info)
                
                # Icon-related files
                if 'icon' in lower_path or 'font' in lower_path or 'player' in lower_path:
                    icon_files.append(file_info)
        
        print(f"File Statistics:")
        print(f"   Total Files: {len(all_files)}")
        print(f"   Font Files: {len(font_files)}")
        print(f"   Video Files: {len(video_files)}")
        print(f"   HTML Files: {len(html_files)}")
        print(f"   JavaScript Files: {len(js_files)}")
        print(f"   CSS Files: {len(css_files)}")
        print(f"   Icon/Player Files: {len(icon_files)}")
        print()
        
        # Show font files (MOST IMPORTANT)
        if font_files:
            print(f"Font Files Found (Video Player Icons):")
            for f in font_files:
                print(f"   FOUND: {f['path']} ({f['size']} bytes)")
                print(f"     S3 URL: https://{bucket_name}.s3.{get_env('AWS_S3_REGION_NAME')}.amazonaws.com/{f['full_key']}")
                print(f"     Django URL: https://staging.nexsy.io/scorm/content/{topic_id}/{f['path']}")
                print()
        else:
            print(f"CRITICAL: No font files found!")
            print(f"   This explains why video player icons don't display.")
            print()
        
        # Show HTML structure
        print(f"HTML Files:")
        for f in html_files:
            marker = "CURRENT" if f['path'] == scorm_package.launch_url else "  "
            print(f"   {marker}: {f['path']} ({f['size']} bytes)")
        print()
        
        # Show icon/player files
        if icon_files:
            print(f"Icon/Player Related Files:")
            for f in icon_files[:20]:
                print(f"   - {f['path']} ({f['size']} bytes)")
            if len(icon_files) > 20:
                print(f"   ... and {len(icon_files) - 20} more")
            print()
        
        # Check for specific player files
        print(f"Player File Detection:")
        player_files = {
            'index_lms.html': False,
            'indexAPI.html': False,
            'index_API.html': False,
            'story.html': False,
            'index.html': False,
        }
        
        for file_info in html_files:
            path = file_info['path'].lower()
            for player_file in player_files.keys():
                if path.endswith(player_file.lower()):
                    player_files[player_file] = file_info['path']
        
        for player_file, found_path in player_files.items():
            if found_path:
                marker = "CURRENT" if found_path == scorm_package.launch_url else "FOUND"
                status = "(CURRENT LAUNCH FILE)" if found_path == scorm_package.launch_url else ""
                print(f"   {marker}: {player_file} - {found_path} {status}")
            else:
                print(f"   NOT FOUND: {player_file}")
        print()
        
        # Show sample files structure
        print(f"Sample File Structure (first 30 files):")
        for i, f in enumerate(all_files[:30]):
            print(f"   {i+1:2d}. {f['path']} ({f['size']} bytes)")
        if len(all_files) > 30:
            print(f"   ... and {len(all_files) - 30} more files")
        print()
        
        # Test font accessibility
        if font_files:
            print(f"Font Accessibility Test:")
            test_font = font_files[0]
            print(f"   Testing: {test_font['path']}")
            print(f"   Direct S3 URL: https://{bucket_name}.s3.{get_env('AWS_S3_REGION_NAME')}.amazonaws.com/{test_font['full_key']}")
            print(f"   Django Proxy URL: https://staging.nexsy.io/scorm/content/{topic_id}/{test_font['path']}")
            if test_font['path'].endswith('.woff2'):
                print(f"   Expected MIME Type: font/woff2")
            elif test_font['path'].endswith('.woff'):
                print(f"   Expected MIME Type: font/woff")
            else:
                print(f"   Expected MIME Type: font/ttf")
            print()
        
    except Exception as e:
        print(f"ERROR listing S3 files: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("=" * 100)
    print("S3 Package Inspection Complete")
    print("=" * 100)


if __name__ == '__main__':
    inspect_s3_package(117)