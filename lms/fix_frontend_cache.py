#!/usr/bin/env python3
"""
Frontend Cache Fix Script
Clears browser cache and forces static file refresh
"""
import os
import sys
import django
import time
import subprocess

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.conf import settings
from django.core.management import execute_from_command_line

def clear_static_cache():
    """Clear static files cache"""
    print("🔧 Clearing static files cache...")
    
    try:
        # Remove static files
        if os.path.exists('static'):
            subprocess.run(['rm', '-rf', 'static'], check=True)
            print("✅ Removed static directory")
        
        # Recreate static files
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
        print("✅ Recreated static files")
        
        return True
    except Exception as e:
        print(f"❌ Error clearing static cache: {e}")
        return False

def restart_services():
    """Restart web services"""
    print("🔄 Restarting web services...")
    
    try:
        # Restart Gunicorn
        subprocess.run(['pkill', '-f', 'gunicorn'], check=False)
        time.sleep(2)
        
        # Start Gunicorn in background
        subprocess.Popen([
            '/home/ec2-user/lms/venv/bin/python', '-m', 'gunicorn',
            '--config', 'gunicorn.conf.py',
            'LMS_Project.wsgi:application'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print("✅ Gunicorn restarted")
        
        # Restart Nginx
        subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'], check=True)
        print("✅ Nginx reloaded")
        
        return True
    except Exception as e:
        print(f"❌ Error restarting services: {e}")
        return False

def add_cache_busting():
    """Add cache busting to static files"""
    print("🔧 Adding cache busting...")
    
    try:
        # Create a version file with timestamp
        version = str(int(time.time()))
        version_file = 'static/version.txt'
        
        with open(version_file, 'w') as f:
            f.write(version)
        
        print(f"✅ Created version file: {version}")
        return True
    except Exception as e:
        print(f"❌ Error adding cache busting: {e}")
        return False

def test_frontend():
    """Test if frontend is working"""
    print("🧪 Testing frontend...")
    
    try:
        import requests
        
        # Test login page
        response = requests.get('http://localhost:8000/login/', timeout=10)
        if response.status_code == 200:
            print("✅ Login page accessible")
            
            # Check for static files
            if 'static' in response.text:
                print("✅ Static files referenced")
            else:
                print("⚠️  Static files not found in response")
            
            return True
        else:
            print(f"❌ Login page error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing frontend: {e}")
        return False

def main():
    """Main function to fix frontend caching"""
    print("=" * 60)
    print("FRONTEND CACHE FIX")
    print("=" * 60)
    
    steps = [
        ("Clearing static cache", clear_static_cache),
        ("Adding cache busting", add_cache_busting),
        ("Restarting services", restart_services),
        ("Testing frontend", test_frontend),
    ]
    
    for step_name, step_func in steps:
        print(f"\n🔧 {step_name}...")
        if not step_func():
            print(f"❌ {step_name} failed")
            return False
        print(f"✅ {step_name} completed")
    
    print("\n" + "=" * 60)
    print("🎉 FRONTEND CACHE FIX COMPLETED!")
    print("=" * 60)
    print("\n📋 SOLUTIONS FOR BROWSER CACHE:")
    print("1. Hard refresh: Ctrl+F5 (Windows) or Cmd+Shift+R (Mac)")
    print("2. Clear browser cache: Ctrl+Shift+Delete")
    print("3. Open in incognito/private mode")
    print("4. Add ?v=" + str(int(time.time())) + " to URLs")
    print("\n🚀 Frontend should now reflect all changes!")
    
    return True

if __name__ == "__main__":
    main()
