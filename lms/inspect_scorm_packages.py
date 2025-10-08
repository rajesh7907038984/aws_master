#!/usr/bin/env python
"""
Deep inspection of SCORM packages to understand their structure
"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from courses.models import Topic

def inspect_all_scorm_packages():
    print("="*100)
    print("DEEP SCORM PACKAGE INSPECTION")
    print("="*100)
    
    packages = ScormPackage.objects.all().order_by('-created_at')
    
    print(f"\nTotal SCORM Packages: {packages.count()}")
    print("="*100)
    
    for i, pkg in enumerate(packages, 1):
        print(f"\n{'='*100}")
        print(f"PACKAGE #{i}: {pkg.title}")
        print(f"{'='*100}")
        print(f"ID: {pkg.id}")
        print(f"Topic: {pkg.topic.title} (ID: {pkg.topic.id})")
        print(f"Version: {pkg.version}")
        print(f"Launch URL: {pkg.launch_url}")
        print(f"Extracted Path: {pkg.extracted_path}")
        print(f"Created: {pkg.created_at}")
        
        # Check manifest data
        if pkg.manifest_data:
            print(f"\nManifest Data Keys: {list(pkg.manifest_data.keys())}")
            
            if 'identifier' in pkg.manifest_data:
                print(f"Package Identifier: {pkg.manifest_data['identifier']}")
            
            if 'raw_manifest' in pkg.manifest_data:
                raw_manifest = pkg.manifest_data['raw_manifest']
                print(f"\nRaw Manifest Preview (first 500 chars):")
                print("-"*80)
                print(raw_manifest[:500] if isinstance(raw_manifest, str) else str(raw_manifest)[:500])
                print("-"*80)
                
                # Try to detect content type
                if isinstance(raw_manifest, str):
                    content_types = []
                    if 'quiz' in raw_manifest.lower():
                        content_types.append('Quiz')
                    if 'slide' in raw_manifest.lower():
                        content_types.append('Slides')
                    if 'page' in raw_manifest.lower():
                        content_types.append('Pages')
                    if 'assessment' in raw_manifest.lower():
                        content_types.append('Assessment')
                    if 'lesson' in raw_manifest.lower():
                        content_types.append('Lessons')
                    if 'activity' in raw_manifest.lower():
                        content_types.append('Activities')
                    
                    if content_types:
                        print(f"\nDetected Content Types: {', '.join(content_types)}")
        else:
            print(f"\n⚠️  No manifest data stored")
        
        # Check recent attempts
        recent_attempts = ScormAttempt.objects.filter(
            scorm_package=pkg
        ).order_by('-last_accessed')[:3]
        
        if recent_attempts:
            print(f"\nRecent Attempts (last 3):")
            for j, attempt in enumerate(recent_attempts, 1):
                print(f"\n  {j}. User: {attempt.user.username}")
                print(f"     Status: {attempt.lesson_status}")
                print(f"     Entry: {attempt.entry}")
                print(f"     Has Location: {'Yes' if attempt.lesson_location else 'No'}")
                print(f"     Has Suspend Data: {'Yes (%d chars)' % len(attempt.suspend_data) if attempt.suspend_data else 'No'}")
                print(f"     Last Accessed: {attempt.last_accessed}")
                
                # Check what's in suspend data to understand structure
                if attempt.suspend_data:
                    suspend_preview = attempt.suspend_data[:200]
                    print(f"     Suspend Data Preview: {suspend_preview}...")
        else:
            print(f"\n⚠️  No attempts found for this package")
    
    print("\n" + "="*100)
    print("SCORM CONTENT STRUCTURE ANALYSIS")
    print("="*100)
    
    # Analyze launch URLs to understand structure
    launch_patterns = {}
    for pkg in packages:
        launch_url = pkg.launch_url
        if launch_url:
            # Extract directory structure
            parts = launch_url.split('/')
            if len(parts) > 1:
                directory = parts[0]
                file = parts[-1]
                pattern = f"{directory}/.../{ file}"
            else:
                pattern = launch_url
            
            if pattern not in launch_patterns:
                launch_patterns[pattern] = []
            launch_patterns[pattern].append(pkg.title)
    
    print("\nLaunch URL Patterns:")
    for pattern, titles in launch_patterns.items():
        print(f"\n  Pattern: {pattern}")
        print(f"  Used by: {', '.join(titles)}")
    
    print("\n" + "="*100)
    print("RECOMMENDATIONS FOR RESUME FIX")
    print("="*100)
    
    print("""
    Based on the inspection, here's what to verify:
    
    1. LAUNCH FILE STRUCTURE:
       - Check if different packages use different launch files
       - Verify each launch file properly implements SCORM API
       - Ensure all launch files handle bookmark/resume data
    
    2. CONTENT TYPE VARIATIONS:
       - Quiz-based SCORM: May store question states differently
       - Slide-based SCORM: May use lesson_location for slide position
       - Page-based SCORM: May have different navigation tracking
       - Assessment-based: May have more complex state management
    
    3. SCORM API IMPLEMENTATION:
       - Each SCORM authoring tool (Articulate, Captivate, etc.) may
         implement the SCORM API slightly differently
       - Some may use cmi.core.lesson_location for slides
       - Others may rely more heavily on cmi.suspend_data
    
    4. FRONTEND CACHING FIX:
       - The fix applied disables caching for ALL bookmark-related elements
       - This should work for ALL types of SCORM content
       - However, need to verify in browser that fix is active
    
    5. TESTING REQUIRED:
       - Test with each different content type (quiz, slide, page)
       - Verify resume works for all variations
       - Check browser console for "NO CACHE" messages
    """)

if __name__ == '__main__':
    inspect_all_scorm_packages()

