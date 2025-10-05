#!/usr/bin/env python
"""
SCORM Package Diagnostic Tool
Checks SCORM packages for common issues and validates content structure
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, '/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from django.core.files.storage import default_storage
import re


def check_base_tag_in_file(file_path):
    """Check if a file has a hardcoded base tag"""
    try:
        with default_storage.open(file_path, 'rb') as f:
            content = f.read().decode('utf-8', errors='ignore')
            
        base_tag_pattern = re.compile(r'<base\s+[^>]*href\s*=\s*["\']([^"\']*)["\'][^>]*>', re.IGNORECASE)
        match = base_tag_pattern.search(content)
        
        if match:
            return True, match.group(1)
    except Exception as e:
        return None, str(e)
    
    return False, None


def list_directory_contents(directory_path, max_depth=2, current_depth=0):
    """List contents of a directory in S3"""
    if current_depth >= max_depth:
        return []
    
    try:
        dirs, files = default_storage.listdir(directory_path)
        results = []
        
        for filename in files:
            file_path = f"{directory_path}/{filename}" if directory_path else filename
            results.append(('file', file_path))
        
        for dirname in dirs:
            dir_path = f"{directory_path}/{dirname}" if directory_path else dirname
            results.append(('dir', dir_path))
            if current_depth < max_depth - 1:
                results.extend(list_directory_contents(dir_path, max_depth, current_depth + 1))
        
        return results
    except Exception as e:
        return [('error', str(e))]


def diagnose_package(package_id):
    """Diagnose a specific SCORM package"""
    print("=" * 80)
    print(f"SCORM Package Diagnostic Report")
    print("=" * 80)
    print()
    
    try:
        package = ScormPackage.objects.get(id=package_id)
    except ScormPackage.DoesNotExist:
        print(f"❌ Error: SCORM Package with ID {package_id} not found")
        return
    
    print(f"📦 Package Information:")
    print(f"   ID: {package.id}")
    print(f"   Title: {package.title}")
    print(f"   Version: {package.version}")
    print(f"   Launch URL: {package.launch_url}")
    print(f"   Extracted Path: {package.extracted_path}")
    print(f"   Created: {package.created_at}")
    print()
    
    # Check if extracted path exists
    print(f"📁 Storage Check:")
    try:
        exists = default_storage.exists(package.extracted_path)
        if exists:
            print(f"   ✅ Extracted path exists in storage")
        else:
            print(f"   ❌ Extracted path does NOT exist in storage")
            return
    except Exception as e:
        print(f"   ❌ Error checking storage: {e}")
        return
    print()
    
    # Check launch file
    print(f"🚀 Launch File Check:")
    launch_file_path = f"{package.extracted_path}/{package.launch_url}"
    try:
        if default_storage.exists(launch_file_path):
            print(f"   ✅ Launch file exists: {package.launch_url}")
            
            # Check for hardcoded base tag
            has_base, base_href = check_base_tag_in_file(launch_file_path)
            if has_base:
                print(f"   ⚠️  WARNING: Launch file has hardcoded <base> tag!")
                print(f"      Base href: {base_href}")
                print(f"      This will be automatically fixed by the system.")
            elif has_base is False:
                print(f"   ✅ No hardcoded base tag found (good)")
            else:
                print(f"   ⚠️  Could not check for base tag: {base_href}")
        else:
            print(f"   ❌ Launch file NOT found: {package.launch_url}")
    except Exception as e:
        print(f"   ❌ Error checking launch file: {e}")
    print()
    
    # List package contents
    print(f"📂 Package Contents:")
    try:
        contents = list_directory_contents(package.extracted_path, max_depth=3)
        if contents:
            files = [c for c in contents if c[0] == 'file']
            dirs = [c for c in contents if c[0] == 'dir']
            errors = [c for c in contents if c[0] == 'error']
            
            print(f"   Total files: {len(files)}")
            print(f"   Total directories: {len(dirs)}")
            
            if errors:
                print(f"   ⚠️  Errors: {len(errors)}")
                for _, error in errors[:5]:
                    print(f"      - {error}")
            
            # Show first 20 files
            print(f"\n   Sample files (first 20):")
            for file_type, file_path in files[:20]:
                relative_path = file_path.replace(package.extracted_path + '/', '')
                print(f"      - {relative_path}")
            
            if len(files) > 20:
                print(f"      ... and {len(files) - 20} more files")
        else:
            print(f"   ⚠️  No contents found (empty directory or access error)")
    except Exception as e:
        print(f"   ❌ Error listing contents: {e}")
    print()
    
    # Check attempts
    print(f"👥 User Attempts:")
    attempts = ScormAttempt.objects.filter(scorm_package=package)
    if attempts.exists():
        print(f"   Total attempts: {attempts.count()}")
        print(f"\n   Recent attempts:")
        for attempt in attempts[:5]:
            print(f"      - User: {attempt.user.username}")
            print(f"        Attempt #{attempt.attempt_number}")
            print(f"        Status: {attempt.lesson_status}")
            print(f"        Score: {attempt.score_raw or 'N/A'}")
            print(f"        Last accessed: {attempt.last_accessed}")
            print()
    else:
        print(f"   No attempts yet")
    print()
    
    # Check for common issues
    print(f"🔍 Common Issues Check:")
    issues_found = False
    
    # Check for JavaScript files
    js_files = [f for t, f in contents if t == 'file' and f.endswith('.js')]
    if not js_files:
        print(f"   ⚠️  WARNING: No JavaScript files found")
        issues_found = True
    else:
        print(f"   ✅ Found {len(js_files)} JavaScript files")
    
    # Check for HTML files
    html_files = [f for t, f in contents if t == 'file' and (f.endswith('.html') or f.endswith('.htm'))]
    if not html_files:
        print(f"   ⚠️  WARNING: No HTML files found")
        issues_found = True
    else:
        print(f"   ✅ Found {len(html_files)} HTML files")
        
        # Check each HTML file for hardcoded base tags
        print(f"\n   Checking HTML files for hardcoded base tags...")
        html_with_base = []
        for file_path in html_files[:10]:  # Check first 10 HTML files
            has_base, base_href = check_base_tag_in_file(file_path)
            if has_base:
                relative_path = file_path.replace(package.extracted_path + '/', '')
                html_with_base.append((relative_path, base_href))
        
        if html_with_base:
            print(f"   ⚠️  Found {len(html_with_base)} HTML files with hardcoded base tags:")
            for file_path, base_href in html_with_base[:5]:
                print(f"      - {file_path}")
                print(f"        Base href: {base_href}")
            issues_found = True
        else:
            print(f"   ✅ No hardcoded base tags in checked HTML files")
    
    # Check manifest
    manifest_path = f"{package.extracted_path}/imsmanifest.xml"
    if default_storage.exists(manifest_path):
        print(f"   ✅ Manifest file exists")
    else:
        print(f"   ⚠️  WARNING: imsmanifest.xml not found")
        issues_found = True
    
    if not issues_found:
        print(f"\n   ✅ No obvious issues detected")
    
    print()
    print("=" * 80)
    print("Diagnostic Complete")
    print("=" * 80)


def list_all_packages():
    """List all SCORM packages"""
    packages = ScormPackage.objects.all()
    
    if not packages.exists():
        print("No SCORM packages found in the system.")
        return
    
    print("=" * 80)
    print("All SCORM Packages")
    print("=" * 80)
    print()
    
    for package in packages:
        print(f"ID: {package.id}")
        print(f"Title: {package.title}")
        print(f"Version: {package.version}")
        print(f"Topic: {package.topic.name if hasattr(package, 'topic') else 'N/A'}")
        print(f"Topic ID: {package.topic.id if hasattr(package, 'topic') else 'N/A'}")
        print(f"Launch URL: {package.launch_url}")
        print(f"Created: {package.created_at}")
        print("-" * 80)
    
    print()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Diagnose SCORM package issues')
    parser.add_argument('--package-id', type=int, help='SCORM package ID to diagnose')
    parser.add_argument('--list', action='store_true', help='List all SCORM packages')
    
    args = parser.parse_args()
    
    if args.list:
        list_all_packages()
    elif args.package_id:
        diagnose_package(args.package_id)
    else:
        # Default: diagnose all packages
        packages = ScormPackage.objects.all()
        if not packages.exists():
            print("No SCORM packages found.")
        else:
            for package in packages:
                diagnose_package(package.id)
                print("\n")

