#!/usr/bin/env python3
"""
Generated Cleanup Script
Run this script to clean up identified issues
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import connection, transaction
from django.core.management import call_command

def cleanup_orphaned_records():
    """Clean up orphaned records"""
    print("🧹 Cleaning up orphaned records...")
    
    with connection.cursor() as cursor:
        # Clean up orphaned course enrollments
        cursor.execute("""
            DELETE FROM courses_courseenrollment 
            WHERE user_id NOT IN (SELECT id FROM users_customuser)
        """)
        deleted_enrollments = cursor.rowcount
        print(f"  ✅ Deleted {deleted_enrollments} orphaned course enrollments")
        
        # Clean up orphaned assignment submissions
        cursor.execute("""
            DELETE FROM assignments_assignmentsubmission 
            WHERE user_id NOT IN (SELECT id FROM users_customuser)
        """)
        deleted_submissions = cursor.rowcount
        print(f"  ✅ Deleted {deleted_submissions} orphaned assignment submissions")

def cleanup_duplicate_data():
    """Clean up duplicate data"""
    print("🧹 Cleaning up duplicate data...")
    
    with connection.cursor() as cursor:
        # Find and handle duplicate users
        cursor.execute("""
            SELECT email, MIN(id) as keep_id, COUNT(*) as count
            FROM users_customuser 
            WHERE email IS NOT NULL AND email != ''
            GROUP BY email 
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        
        for email, keep_id, count in duplicates:
            print(f"  📧 Found {count} duplicates for {email}, keeping ID {keep_id}")
            # Note: Actual cleanup would require more complex logic
            # to handle related records

if __name__ == "__main__":
    print("🚀 Starting database cleanup...")
    
    try:
        with transaction.atomic():
            cleanup_orphaned_records()
            cleanup_duplicate_data()
        print("✅ Cleanup completed successfully!")
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        sys.exit(1)
