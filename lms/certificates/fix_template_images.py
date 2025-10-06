#!/usr/bin/env python
"""
Script to fix certificate templates with missing S3 images
This addresses the S3 HeadObject 403 permission issue
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from certificates.models import CertificateTemplate
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def fix_template_image(template_id, image_path=None):
    """Fix a template with missing S3 image"""
    try:
        template = CertificateTemplate.objects.get(id=template_id)
        print(f"Found template: {template.name}")
        
        # Check if image exists in S3
        if template.image:
            try:
                exists = default_storage.exists(template.image.name)
                print(f"Image exists in S3: {exists}")
                if exists:
                    print(" Image already exists, no fix needed")
                    return True
            except Exception as e:
                print(f"  Cannot check if image exists (expected with HeadObject permission issue): {str(e)}")
        
        # If we have a local image path, upload it
        if image_path and os.path.exists(image_path):
            print(f"Uploading image from: {image_path}")
            
            with open(image_path, 'rb') as f:
                image_content = f.read()
            
            # Generate S3 path
            filename = os.path.basename(image_path)
            file_path = f"certificate_templates/{timezone.now().strftime('%Y/%m/%d')}/{filename}"
            
            # Save directly to S3
            saved_path = default_storage.save(file_path, ContentFile(image_content))
            
            # Update template - bypass model save to avoid HeadObject
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE certificates_certificatetemplate SET image = %s WHERE id = %s",
                    [saved_path, template.id]
                )
            
            # Refresh from database
            template.refresh_from_db()
            
            print(f" Successfully uploaded image: {saved_path}")
            print(f" Image URL: {template.get_image_url()}")
            return True
            
        else:
            # Create a simple placeholder image if no image provided
            print("Creating placeholder image...")
            
            # Create a simple text-based placeholder
            placeholder_content = """<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f0f0f0" stroke="#ccc" stroke-width="2"/>
  <text x="50%" y="50%" font-family="Arial" font-size="24" text-anchor="middle" fill="#666">
    Certificate Template Background
  </text>
  <text x="50%" y="60%" font-family="Arial" font-size="16" text-anchor="middle" fill="#999">
    Please upload your own background image
  </text>
</svg>"""
            
            # Save placeholder
            file_path = f"certificate_templates/{timezone.now().strftime('%Y/%m/%d')}/placeholder_{template.id}.svg"
            saved_path = default_storage.save(file_path, ContentFile(placeholder_content.encode('utf-8')))
            
            # Update template - bypass model save to avoid HeadObject  
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE certificates_certificatetemplate SET image = %s WHERE id = %s",
                    [saved_path, template.id]
                )
            
            # Refresh from database
            template.refresh_from_db()
            
            print(f" Created placeholder image: {saved_path}")
            print(f" Image URL: {template.get_image_url()}")
            return True
            
    except Exception as e:
        print(f" Error fixing template: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Certificate Template Image Fix Tool ===")
    print()
    
    # Find templates with potential missing images
    templates = CertificateTemplate.objects.filter(image__isnull=False)
    print(f"Found {templates.count()} templates with images:")
    
    for template in templates:
        print(f"- ID {template.id}: {template.name}")
        print(f"  Image: {template.image.name}")
        
        # Try to check if exists (will likely fail with HeadObject error)
        try:
            exists = default_storage.exists(template.image.name)
            status = " EXISTS" if exists else " MISSING"
        except Exception:
            status = "  UNKNOWN (HeadObject permission issue)"
        
        print(f"  Status: {status}")
        print()
    
    # Fix the wdfw template specifically
    print("Fixing 'wdfw' template...")
    wdfw_template = CertificateTemplate.objects.filter(name='wdfw').first()
    if wdfw_template:
        success = fix_template_image(wdfw_template.id)
        if success:
            print(f" Fixed template '{wdfw_template.name}'")
        else:
            print(f" Failed to fix template '{wdfw_template.name}'")
    else:
        print(" 'wdfw' template not found")
