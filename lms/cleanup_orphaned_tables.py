#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database Cleanup Script - Remove Orphaned Tables
This script removes all orphaned tables identified in the database analysis.
"""

import os
import sys
import django
from django.db import connection, transaction

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

def drop_orphaned_tables():
    """Drop all orphaned tables identified in database analysis"""
    
    orphaned_tables = [
        "users_customuser_groups",
        "lms_messages_message_recipients", 
        "reports_report_shared_with",
        "courses_comment_likes",
        "lms_notifications_bulknotification_target_branches",
        "courses_course_prerequisites",
        "lms_notifications_bulknotification_custom_recipients",
        "courses_discussion_likes",
        "lms_notifications_bulknotification_target_groups",
        "account_settings_menucontrolsettings_visible_to_custom_roles",
        "users_customuser_user_permissions",
        "account_settings_ipwhitelistentry"
    ]
    
    print("Starting database cleanup...")
    print("Found {} orphaned tables to remove".format(len(orphaned_tables)))
    
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
                    print("Dropping table: {}".format(table))
                    cursor.execute("DROP TABLE IF EXISTS {} CASCADE;".format(table))
                    print("Successfully dropped: {}".format(table))
                else:
                    print("Table {} does not exist, skipping...".format(table))
                    
            except Exception as e:
                print("Error dropping table {}: {}".format(table, e))
                continue
    
    print("Database cleanup completed!")
    print("Run 'python manage.py migrate' to ensure database is in sync")

if __name__ == "__main__":
    drop_orphaned_tables()
