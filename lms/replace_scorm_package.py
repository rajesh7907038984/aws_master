#!/usr/bin/env python
"""
Script to replace SCORM package for topic 24
Usage: python replace_scorm_package.py <path_to_new_scorm_zip>
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.core.files import File
from courses.models import Topic
from scorm.models import ScormPackage
from scorm.parser import ScormParser

def replace_scorm_package(topic_id, zip_file_path):
    """Replace SCORM package for a topic"""
    
    # Check if file exists
    if not os.path.exists(zip_file_path):
        print(f"❌ Error: File not found: {zip_file_path}")
        return False
    
    # Check if it's a ZIP file
    if not zip_file_path.endswith('.zip'):
        print(f"❌ Error: File must be a ZIP file")
        return False
    
    # Get the topic
    try:
        topic = Topic.objects.get(id=topic_id)
        print(f"✅ Found topic: {topic.title}")
    except Topic.DoesNotExist:
        print(f"❌ Error: Topic {topic_id} not found")
        return False
    
    # Get existing SCORM package
    try:
        scorm_package = topic.scorm_package
        print(f"✅ Found existing SCORM package: {scorm_package.title} (ID: {scorm_package.id})")
    except ScormPackage.DoesNotExist:
        print(f"❌ Error: No SCORM package attached to topic {topic_id}")
        return False
    
    # Parse the new SCORM package
    print(f"\n📦 Parsing new SCORM package...")
    parser = ScormParser(zip_file_path)
    
    if not parser.validate():
        print(f"❌ Error: Invalid SCORM package")
        print(f"   Errors: {parser.errors}")
        return False
    
    manifest_data = parser.parse()
    print(f"✅ SCORM package validated successfully")
    print(f"   Title: {manifest_data.get('title', 'Unknown')}")
    print(f"   Version: {manifest_data.get('version', 'Unknown')}")
    print(f"   Launch URL: {manifest_data.get('launch_url', 'Unknown')}")
    
    # Update the SCORM package
    print(f"\n🔄 Updating SCORM package...")
    
    with open(zip_file_path, 'rb') as f:
        scorm_package.package_file.save(
            os.path.basename(zip_file_path),
            File(f),
            save=False
        )
    
    # Update metadata
    scorm_package.title = manifest_data.get('title', scorm_package.title)
    scorm_package.version = manifest_data.get('version', '1.2')
    scorm_package.identifier = manifest_data.get('identifier', scorm_package.identifier)
    scorm_package.description = manifest_data.get('description', '')
    scorm_package.launch_url = manifest_data.get('launch_url', 'index.html')
    scorm_package.manifest_data = manifest_data
    
    if 'mastery_score' in manifest_data:
        scorm_package.mastery_score = manifest_data['mastery_score']
    
    scorm_package.save()
    
    print(f"✅ SCORM package updated successfully!")
    print(f"\n📊 New Package Details:")
    print(f"   Title: {scorm_package.title}")
    print(f"   Version: {scorm_package.version}")
    print(f"   Launch URL: {scorm_package.launch_url}")
    print(f"   Package File: {scorm_package.package_file.name}")
    print(f"\n🌐 View at: https://staging.nexsy.io/scorm/view/{topic_id}/")
    
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python replace_scorm_package.py <path_to_new_scorm_zip>")
        print("\nExample:")
        print("  python replace_scorm_package.py /path/to/new_scorm_package.zip")
        sys.exit(1)
    
    zip_file = sys.argv[1]
    topic_id = 24  # Topic ID for the SCORM content
    
    success = replace_scorm_package(topic_id, zip_file)
    sys.exit(0 if success else 1)
