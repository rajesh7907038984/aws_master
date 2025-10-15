#!/usr/bin/env python3
"""
Script to check SCORM package data for debugging S3 NoSuchKey error
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

from scorm.models import ScormPackage, ScormAttempt
from courses.models import Topic

def main():
    print("=== SCORM Package Investigation ===\n")
    
    # Check if topic 179 exists
    try:
        topic = Topic.objects.get(id=179)
        print(f"Topic 179 found: {topic.title}")
        print(f"Topic type: {topic.content_type if hasattr(topic, 'content_type') else 'N/A'}")
        
        # Check if it has a SCORM package
        if hasattr(topic, 'scorm_package'):
            package = topic.scorm_package
            print(f"\nSCORM Package found:")
            print(f"  ID: {package.id}")
            print(f"  Title: {package.title}")
            print(f"  Version: {package.version}")
            print(f"  Identifier: {package.identifier}")
            print(f"  Package file: {package.package_file}")
            print(f"  Extracted path: {package.extracted_path}")
            print(f"  Launch URL: {package.launch_url}")
            print(f"  Created: {package.created_at}")
            print(f"  Updated: {package.updated_at}")
            
            # Show recent attempts for this package
            attempts = ScormAttempt.objects.filter(scorm_package=package).order_by('-last_accessed')[:5]
            print(f"\nRecent attempts ({len(attempts)}):")
            for attempt in attempts:
                print(f"  - User: {attempt.user.username}, Status: {attempt.lesson_status}, Last accessed: {attempt.last_accessed}")
            
        else:
            print("\nNo SCORM package found for this topic")
            
    except Topic.DoesNotExist:
        print("Topic 179 not found in database")
    except Exception as e:
        print(f"Error: {e}")
    
    # Show some general SCORM package info
    print(f"\n=== General SCORM Package Statistics ===")
    total_packages = ScormPackage.objects.count()
    print(f"Total SCORM packages: {total_packages}")
    
    if total_packages > 0:
        print(f"\nRecent packages:")
        recent_packages = ScormPackage.objects.order_by('-created_at')[:5]
        for pkg in recent_packages:
            print(f"  - ID: {pkg.id}, Topic: {pkg.topic_id}, Title: {pkg.title[:50]}, Path: {pkg.extracted_path}")

if __name__ == '__main__':
    main()
