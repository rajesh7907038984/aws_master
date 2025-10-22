#!/usr/bin/env python3
"""
Simple SCORM Content Serving Fix
Replaces complex JavaScript injection with simple version
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.views import scorm_content
from django.test import RequestFactory
from scorm.models import ScormPackage
from django.contrib.auth import get_user_model

User = get_user_model()

def test_simple_content_serving():
    """Test content serving with simplified approach"""
    print("🔧 Testing Simple Content Serving...")
    
    try:
        package = ScormPackage.objects.first()
        factory = RequestFactory()
        request = factory.get('/scorm/content/')
        request.user = User.objects.first()
        
        # Test with a simple path
        response = scorm_content(request, topic_id=package.topic.id, path='index.html')
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ Content serving working")
            return True
        else:
            print(f"   ❌ Content serving failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_simple_content_serving()
