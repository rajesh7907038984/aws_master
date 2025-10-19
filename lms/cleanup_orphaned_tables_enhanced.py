#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Enhanced Database Cleanup Script - Remove Orphaned Tables and Indexes
This script removes all orphaned tables and indexes identified in the database analysis.
"""

import os
import sys
import django
from django.db import connection, transaction
import logging

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

logger = logging.getLogger(__name__)

def cleanup_orphaned_tables():
    """Drop all orphaned tables identified in database analysis"""
    
    # NOTE: BulkNotification tables are NOT orphaned - they are required by the model!
    orphaned_tables = [
        "users_customuser_groups",
        "lms_messages_message_recipients", 
        "reports_report_shared_with",
        "courses_comment_likes",
        "courses_course_prerequisites",
        "courses_discussion_likes",
        "account_settings_menucontrolsettings_visible_to_custom_roles",
        "users_customuser_user_permissions",
        "account_settings_ipwhitelistentry"
    ]
    
    print("Starting enhanced database cleanup...")
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
                    # Drop table with CASCADE to handle dependencies
                    cursor.execute("DROP TABLE IF EXISTS {} CASCADE;".format(table))
                    print("✅ Dropped orphaned table: {}".format(table))
                else:
                    print("ℹ️  Table {} does not exist, skipping".format(table))
                    
            except Exception as e:
                print("❌ Error dropping table {}: {}".format(table, e))
                logger.error("Error dropping table {}: {}".format(table, e))

def cleanup_orphaned_indexes():
    """Drop orphaned indexes identified in database analysis"""
    
    orphaned_indexes = [
        "branches_branch_name_key",
        "branches_branch_name_2cf4114b_like",
        "lms_messages_message_recipients_message_id_customuser_id_key",
        "users_customuser_username_key",
        "users_customuser_username_80452fdf_like",
        "users_customuser_assigned_instructor_id_f1763aa6",
        "users_customuser_branch_id_982dd111",
        "courses_course_prerequis_from_course_id_to_course_91caca13_uniq"
    ]
    
    print("\nCleaning up {} orphaned indexes...".format(len(orphaned_indexes)))
    
    with connection.cursor() as cursor:
        for index in orphaned_indexes:
            try:
                # Check if index exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = %s
                    );
                """, [index])
                
                index_exists = cursor.fetchone()[0]
                
                if index_exists:
                    cursor.execute("DROP INDEX IF EXISTS {};".format(index))
                    print("✅ Dropped orphaned index: {}".format(index))
                else:
                    print("ℹ️  Index {} does not exist, skipping".format(index))
                    
            except Exception as e:
                print("❌ Error dropping index {}: {}".format(index, e))
                logger.error("Error dropping index {}: {}".format(index, e))

def optimize_database():
    """Run database optimization commands"""
    
    print("\nRunning database optimization...")
    
    with connection.cursor() as cursor:
        try:
            # Update database statistics
            cursor.execute("ANALYZE;")
            print("✅ Updated database statistics")
            
            # Vacuum to reclaim space
            cursor.execute("VACUUM ANALYZE;")
            print("✅ Completed VACUUM ANALYZE")
            
            # Reindex to optimize indexes
            cursor.execute("REINDEX DATABASE postgres;")
            print("✅ Completed database reindexing")
            
        except Exception as e:
            print("❌ Error during database optimization: {}".format(e))
            logger.error("Database optimization error: {}".format(e))

def main():
    """Main cleanup function"""
    print("🧹 Enhanced Database Cleanup Script")
    print("=" * 50)
    
    try:
        # Clean up orphaned tables
        cleanup_orphaned_tables()
        
        # Clean up orphaned indexes
        cleanup_orphaned_indexes()
        
        # Optimize database
        optimize_database()
        
        print("\n🎉 Database cleanup completed successfully!")
        print("✅ Orphaned tables removed")
        print("✅ Orphaned indexes removed") 
        print("✅ Database optimized")
        
    except Exception as e:
        print("\n❌ Database cleanup failed: {}".format(e))
        logger.error("Database cleanup failed: {}".format(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
