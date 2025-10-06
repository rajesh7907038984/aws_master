#!/usr/bin/env python3
"""
Test authentication decorator
"""
import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.insert(0, '/home/ec2-user/lms')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

@login_required
def test_view(request):
    return HttpResponse("Authenticated!")

def test_decorator():
    factory = RequestFactory()
    request = factory.get('/test/')
    request.user = AnonymousUser()
    
    print("Testing @login_required decorator...")
    print(f"User authenticated: {request.user.is_authenticated}")
    
    response = test_view(request)
    print(f"Response status: {response.status_code}")
    print(f"Response location: {response.get('Location', 'None')}")
    
    if response.status_code == 302 and '/login/' in response.get('Location', ''):
        print("✓ @login_required decorator working correctly")
        return True
    else:
        print("✗ @login_required decorator not working")
        return False

if __name__ == "__main__":
    test_decorator()
