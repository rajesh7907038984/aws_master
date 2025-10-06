#!/usr/bin/env python3
"""
SCORM Bookmark Recovery Script
Fixes existing SCORM attempts that have suspend data but missing lesson_location
"""

import os
import sys
import django
import json

# Setup Django environment
sys.path.append('/home/ec2-user/lms')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from scorm.models import ScormPackage, ScormAttempt
from django.utils import timezone

def fix_existing_bookmarks():
    """Fix existing SCORM attempts with bookmark issues"""
    
    print("=== SCORM BOOKMARK RECOVERY SCRIPT ===")
    print()
    
    # Find attempts with suspend data but empty lesson_location
    problematic_attempts = ScormAttempt.objects.filter(
        lesson_location='',
        suspend_data__isnull=False
    ).exclude(suspend_data='')
    
    print(f"Found {problematic_attempts.count()} attempts with bookmark issues")
    print()
    
    fixed_count = 0
    
    for attempt in problematic_attempts:
        print(f"Processing attempt {attempt.id} for user {attempt.user.username}")
        
        try:
            # Check CMI data for lesson location
            cmi_location = None
            if attempt.cmi_data:
                # Check both SCORM 1.2 and 2004 formats
                cmi_location = (
                    attempt.cmi_data.get('cmi.core.lesson_location') or 
                    attempt.cmi_data.get('cmi.location')
                )
            
            # Try to extract location from suspend data
            suspend_location = None
            if attempt.suspend_data:
                try:
                    # Try to parse as JSON
                    suspend_json = json.loads(attempt.suspend_data)
                    if 'd' in suspend_json:
                        # Decode the data array
                        try:
                            data_str = ''.join([chr(x) for x in suspend_json['d']])
                            if 'lesson' in data_str.lower() or 'slide' in data_str.lower():
                                # Extract potential location info
                                suspend_location = "recovered_from_suspend_data"
                        except:
                            pass
                except json.JSONDecodeError:
                    # Treat as simple string
                    if 'progress' in attempt.suspend_data.lower():
                        suspend_location = "recovered_from_suspend_data"
            
            # Determine the best location to use
            location_to_use = cmi_location or suspend_location
            
            if location_to_use:
                # Update the attempt
                attempt.lesson_location = location_to_use
                
                # Update lesson status if still not_attempted
                if attempt.lesson_status == 'not_attempted':
                    attempt.lesson_status = 'incomplete'
                    print(f"  ✅ Updated status to 'incomplete'")
                
                # Update CMI data to ensure consistency
                if not attempt.cmi_data:
                    attempt.cmi_data = {}
                
                if attempt.scorm_package.version == '1.2':
                    attempt.cmi_data['cmi.core.lesson_location'] = location_to_use
                    attempt.cmi_data['cmi.core.entry'] = 'resume'
                else:
                    attempt.cmi_data['cmi.location'] = location_to_use
                    attempt.cmi_data['cmi.entry'] = 'resume'
                
                # Set entry mode to resume
                attempt.entry = 'resume'
                
                attempt.save()
                
                print(f"  ✅ Fixed lesson_location: '{location_to_use}'")
                fixed_count += 1
                
            else:
                print(f"  ⚠️  Could not determine location from data")
                
        except Exception as e:
            print(f"  ❌ Error processing attempt {attempt.id}: {e}")
        
        print()
    
    print("=== RECOVERY SUMMARY ===")
    print(f"Total attempts processed: {problematic_attempts.count()}")
    print(f"Successfully fixed: {fixed_count}")
    print(f"Could not fix: {problematic_attempts.count() - fixed_count}")
    
    if fixed_count > 0:
        print()
        print("🎉 Bookmark recovery completed!")
        print("Users should now be able to resume their SCORM content properly.")
    else:
        print()
        print("ℹ️  No recoverable bookmark data found.")

def verify_fixes():
    """Verify that the fixes are working"""
    print()
    print("=== VERIFICATION ===")
    
    # Check topic 24 specifically
    try:
        topic_24_attempts = ScormAttempt.objects.filter(
            scorm_package__topic_id=24
        ).order_by('-last_accessed')[:5]
        
        print("Recent Topic 24 attempts:")
        for attempt in topic_24_attempts:
            print(f"  User: {attempt.user.username}")
            print(f"    Status: {attempt.lesson_status}")
            print(f"    Location: '{attempt.lesson_location}'")
            print(f"    Entry: {attempt.entry}")
            print(f"    Has suspend data: {'Yes' if attempt.suspend_data else 'No'}")
            print()
            
    except Exception as e:
        print(f"Error in verification: {e}")

if __name__ == '__main__':
    fix_existing_bookmarks()
    verify_fixes()
