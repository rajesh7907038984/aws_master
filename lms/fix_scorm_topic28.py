#!/usr/bin/env python
"""
Script to extract and link the Cybersecurity Session 3 SCORM package to Topic 28
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

import zipfile
from io import BytesIO
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from courses.models import Topic
from scorm.models import ScormPackage
from scorm.parser import ScormParser
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_scorm_topic28():
    """
    Extract the Cybersecurity Session 3 SCORM package and link it to Topic 28
    """
    print("\n" + "="*80)
    print("SCORM Package Fix Script for Topic 28")
    print("="*80 + "\n")
    
    # Step 1: Get Topic 28
    try:
        topic = Topic.objects.get(id=28)
        print(f"✅ Found Topic 28: {topic.title}")
    except Topic.DoesNotExist:
        print("❌ Topic 28 does not exist!")
        return False
    
    # Step 2: Check if topic already has a SCORM package
    try:
        existing_pkg = topic.scorm_package
        print(f"⚠️  Topic already has a SCORM package: {existing_pkg.title}")
        response = input("Do you want to replace it? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Aborted.")
            return False
        # Delete existing package
        existing_pkg.delete()
        print("✅ Deleted existing SCORM package")
    except ScormPackage.DoesNotExist:
        print("✅ Topic has no SCORM package - ready to add one")
    
    # Step 3: Download the SCORM ZIP from S3
    # Note: default_storage already includes AWS_MEDIA_LOCATION prefix, so we don't need 'media/' prefix
    s3_key = 'scorm_content/None_Cybersecurity-Session_3_SCORM1.2.zip'
    print(f"\n📥 Downloading SCORM package from S3...")
    print(f"   S3 Key: {s3_key}")
    
    try:
        # Read the file from S3
        with default_storage.open(s3_key, 'rb') as f:
            zip_content = f.read()
        
        print(f"✅ Downloaded {len(zip_content)} bytes from S3")
        
        # Create a Django file object from the content
        from django.core.files.uploadedfile import InMemoryUploadedFile
        zip_file = InMemoryUploadedFile(
            file=BytesIO(zip_content),
            field_name='package_file',
            name='Cybersecurity-Session_3_SCORM1.2.zip',
            content_type='application/zip',
            size=len(zip_content),
            charset=None
        )
        
    except Exception as e:
        print(f"❌ Error downloading from S3: {str(e)}")
        return False
    
    # Step 4: Parse and extract the SCORM package
    print(f"\n🔍 Parsing SCORM package...")
    
    try:
        parser = ScormParser(zip_file)
        # Skip validation for Tin Can packages that may not have standard structure
        package_info = parser.parse(skip_validation=True)
        
        print(f"✅ SCORM package parsed successfully!")
        print(f"   Version: {package_info['version']}")
        print(f"   Title: {package_info['title']}")
        print(f"   Launch URL: {package_info['launch_url']}")
        print(f"   Extracted Path: {package_info['extracted_path']}")
        print(f"   Files extracted: {len(package_info.get('extracted_files', []))}")
        
        # CRITICAL FIX: If launch_url is None or empty, try to find a launch file
        if not package_info['launch_url']:
            print(f"\n⚠️  Launch URL not found in manifest, searching for common entry points...")
            
            # Common entry points for SCORM/Tin Can packages
            common_entry_points = ['story.html', 'index.html', 'launch.html', 'start.html', 'main.html']
            
            for entry_point in common_entry_points:
                if entry_point in package_info.get('extracted_files', []):
                    package_info['launch_url'] = entry_point
                    print(f"✅ Found launch file: {entry_point}")
                    break
            
            if not package_info['launch_url']:
                # If still not found, use the first HTML file
                html_files = [f for f in package_info.get('extracted_files', []) if f.lower().endswith(('.html', '.htm'))]
                if html_files:
                    package_info['launch_url'] = html_files[0]
                    print(f"✅ Using first HTML file as launch URL: {html_files[0]}")
                else:
                    raise ValueError("No HTML files found in package - cannot determine launch URL")
        
    except Exception as e:
        print(f"❌ Error parsing SCORM package: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 5: Save the SCORM package file
    print(f"\n💾 Saving SCORM package file...")
    
    try:
        # Reset file pointer
        zip_file.seek(0)
        
        # Save package file to S3
        package_file_path = f"scorm_packages/{package_info['extracted_path']}/package.zip"
        saved_path = default_storage.save(package_file_path, zip_file)
        
        print(f"✅ Saved package file to: {saved_path}")
        
    except Exception as e:
        print(f"❌ Error saving package file: {str(e)}")
        return False
    
    # Step 6: Create ScormPackage database entry
    print(f"\n📝 Creating SCORM package database entry...")
    
    try:
        scorm_package = ScormPackage.objects.create(
            topic=topic,
            version=package_info['version'],
            identifier=package_info['identifier'],
            title="Cybersecurity - Session 3" if not package_info['title'] or package_info['title'] == 'Legacy SCORM Package' else package_info['title'],
            description=package_info['description'],
            package_file=saved_path,
            extracted_path=package_info['extracted_path'],
            launch_url=package_info['launch_url'],
            manifest_data=package_info['manifest_data'],
            mastery_score=package_info.get('mastery_score')
        )
        
        print(f"✅ Created SCORM package: {scorm_package.title}")
        print(f"   ID: {scorm_package.id}")
        print(f"   Version: {scorm_package.version}")
        print(f"   Launch URL: {scorm_package.launch_url}")
        
    except Exception as e:
        print(f"❌ Error creating SCORM package: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 7: Verify the setup
    print(f"\n🔍 Verifying setup...")
    
    try:
        # Refresh topic from database
        topic.refresh_from_db()
        
        # Check if SCORM package is accessible
        pkg = topic.scorm_package
        print(f"✅ Topic 28 now has SCORM package: {pkg.title}")
        print(f"   Package ID: {pkg.id}")
        print(f"   Version: {pkg.version}")
        print(f"   Launch URL: {pkg.launch_url}")
        print(f"   Extracted Path: {pkg.extracted_path}")
        
        # Generate URLs
        from scorm.s3_direct import scorm_s3
        launch_url = scorm_s3.generate_launch_url(pkg)
        print(f"\n🔗 SCORM Content URLs:")
        print(f"   View URL: https://staging.nexsy.io/courses/topic/{topic.id}/view/")
        print(f"   Launch URL: {launch_url}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying setup: {str(e)}")
        return False

if __name__ == '__main__':
    try:
        success = fix_scorm_topic28()
        
        if success:
            print("\n" + "="*80)
            print("✅ SUCCESS! SCORM package successfully linked to Topic 28")
            print("="*80 + "\n")
            print("You can now access the SCORM content at:")
            print("https://staging.nexsy.io/courses/topic/28/view/")
            print()
        else:
            print("\n" + "="*80)
            print("❌ FAILED! Please check the errors above")
            print("="*80 + "\n")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
