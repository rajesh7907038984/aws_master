#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Database Cleanup Script - Remove Orphaned Tables
This script connects directly to PostgreSQL to drop orphaned tables.
"""

import psycopg2
import os
from urllib.parse import urlparse

def get_db_connection():
    """Get database connection from environment variables"""
    # Get database connection details from environment
    host = os.environ.get('AWS_DB_HOST', 'localhost')
    port = os.environ.get('AWS_DB_PORT', '5432')
    database = os.environ.get('AWS_DB_NAME', 'postgres')
    user = os.environ.get('AWS_DB_USER', 'postgres')
    password = os.environ.get('AWS_DB_PASSWORD', '')
    
    if not password:
        print("Error: AWS_DB_PASSWORD not set in environment")
        return None
    
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            sslmode='require'
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def drop_orphaned_tables():
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
    
    print("Starting database cleanup...")
    print(f"Found {len(orphaned_tables)} orphaned tables to remove")
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        with conn.cursor() as cursor:
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
                        print(f"Dropping table: {table}")
                        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                        print(f"Successfully dropped: {table}")
                    else:
                        print(f"Table {table} does not exist, skipping...")
                        
                except Exception as e:
                    print(f"Error dropping table {table}: {e}")
                    continue
        
        conn.commit()
        print("Database cleanup completed!")
        
    except Exception as e:
        print(f"Database error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    drop_orphaned_tables()
