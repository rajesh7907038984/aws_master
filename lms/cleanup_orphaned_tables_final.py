#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Final Database Cleanup Script
Removes orphaned tables and optimizes database structure
"""

import os
import sys
import django
from django.conf import settings
from django.db import connection, transaction
from django.core.management import execute_from_command_line

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

def cleanup_orphaned_tables():
    """Remove orphaned tables that are no longer needed"""
    
    # List of orphaned tables to remove (from database analysis)
    orphaned_tables = [
        "users_customuser_groups",
        "lms_messages_message_recipients", 
        "reports_report_shared_with",
        "courses_comment_likes",
        "lms_notifications_bulknotification_target_branches",
        "lms_notifications_bulknotification_target_courses",
        "courses_course_prerequisites",
        "lms_notifications_bulknotification_custom_recipients",
        "courses_discussion_likes",
        "lms_notifications_bulknotification_target_groups",
        "account_settings_menucontrolsettings_visible_to_custom_roles",
        "users_customuser_user_permissions",
        "account_settings_ipwhitelistentry"
    ]
    
    print("Starting database cleanup...")
    
    with connection.cursor() as cursor:
        for table in orphaned_tables:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, [table])
                
                table_exists = cursor.fetchone()[0]
                
                if table_exists:
                    print("Dropping orphaned table: {}".format(table))
                    cursor.execute("DROP TABLE IF EXISTS {} CASCADE;".format(table))
                    print("Successfully dropped {}".format(table))
                else:
                    print("Table {} does not exist, skipping".format(table))
                    
            except Exception as e:
                print("Error dropping table {}: {}".format(table, e))
                continue
    
    print("Database cleanup completed!")

def optimize_database_indexes():
    """Optimize database indexes for better performance"""
    
    print("Optimizing database indexes...")
    
    with connection.cursor() as cursor:
        try:
            # Update table statistics
            cursor.execute("ANALYZE;")
            print("Database statistics updated")
            
            # Vacuum to reclaim space
            cursor.execute("VACUUM ANALYZE;")
            print("Database vacuumed and analyzed")
            
        except Exception as e:
            print("Error optimizing database: {}".format(e))

def main():
    """Main cleanup function"""
    print("Starting comprehensive database cleanup...")
    
    try:
        # Clean up orphaned tables
        cleanup_orphaned_tables()
        
        # Optimize database
        optimize_database_indexes()
        
        print("All cleanup operations completed successfully!")
        
    except Exception as e:
        print("Cleanup failed: {}".format(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
