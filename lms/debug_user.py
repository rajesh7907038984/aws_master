#!/usr/bin/env python3
"""
Debug what user is being set in requests
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

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from users.views import learner_dashboard

def debug_user_state():
    factory = RequestFactory()
    request = factory.get('/dashboard/learner/')
    request.user = AnonymousUser()
    
    print("Testing user state in learner_dashboard...")
    print(f"Initial user: {request.user}")
    print(f"User authenticated: {request.user.is_authenticated}")
    print(f"User type: {type(request.user)}")
    
    # Check if there's a session
    from django.contrib.sessions.middleware import SessionMiddleware
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    
    print(f"Session key: {request.session.session_key}")
    print(f"Session data: {dict(request.session)}")
    
    # Try to call the view
    try:
        response = learner_dashboard(request)
        print(f"Response status: {response.status_code}")
        print(f"Response type: {type(response)}")
        
        if hasattr(response, 'content'):
            content = response.content.decode('utf-8')
            print(f"Content length: {len(content)}")
            if 'learner' in content.lower():
                print("✓ Dashboard content found")
            else:
                print("✗ No dashboard content found")
    except Exception as e:
        print(f"Error calling view: {e}")

if __name__ == "__main__":
    debug_user_state()
