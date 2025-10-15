#!/usr/bin/env python3
"""
Script to list SCORM package files in S3
"""
import os
import sys
import django

# Add the project directory to the path
sys.path.append('/home/ec2-user/lms')
os.chdir('/home/ec2-user/lms')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.s3_direct import scorm_s3
from scorm.models import ScormPackage

def main():
    print("=== SCORM Package Files ===\n")
    
    try:
        pkg = ScormPackage.objects.get(id=119)
        print(f"SCORM Package: {pkg.title}")
        print(f"Launch URL: {pkg.launch_url}")
        print(f"Extracted Path: {pkg.extracted_path}")
        
        files = scorm_s3.list_package_files(pkg)
        print(f'\nPackage contains {len(files)} files:')
        
        # Show all files for analysis
        for i, f in enumerate(files):
            print(f'  {i+1:3d}. {f}')
            
        # Look for files that might be what the SCORM content is trying to access
        print(f'\n=== Analysis ===')
        print(f"Looking for files matching common SCORM patterns:")
        
        patterns = ['scormcontent', 'false', 'index', 'story', 'main']
        for pattern in patterns:
            matching_files = [f for f in files if pattern.lower() in f.lower()]
            if matching_files:
                print(f"  Files containing '{pattern}': {len(matching_files)}")
                for mf in matching_files[:5]:  # Show first 5 matches
                    print(f"    - {mf}")
            else:
                print(f"  No files containing '{pattern}'")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
