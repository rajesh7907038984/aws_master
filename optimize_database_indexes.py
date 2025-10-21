#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database Performance Optimization Script
Adds strategic database indexes for improved query performance
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

def add_performance_indexes():
    """Add strategic database indexes for performance optimization"""
    
    # Define indexes to add for better performance
    indexes_to_add = [
        # User-related indexes
        {
            'name': 'idx_users_email',
            'table': 'users_customuser',
            'columns': 'email',
            'description': 'Index on user email for faster lookups'
        },
        {
            'name': 'idx_users_username',
            'table': 'users_customuser', 
            'columns': 'username',
            'description': 'Index on username for faster authentication'
        },
        {
            'name': 'idx_users_branch_id',
            'table': 'users_customuser',
            'columns': 'branch_id',
            'description': 'Index on branch_id for user filtering'
        },
        {
            'name': 'idx_users_is_active',
            'table': 'users_customuser',
            'columns': 'is_active',
            'description': 'Index on is_active for user status filtering'
        },
        
        # Course-related indexes
        {
            'name': 'idx_courses_title',
            'table': 'courses_course',
            'columns': 'title',
            'description': 'Index on course title for search functionality'
        },
        {
            'name': 'idx_courses_branch_id',
            'table': 'courses_course',
            'columns': 'branch_id',
            'description': 'Index on branch_id for course filtering'
        },
        {
            'name': 'idx_courses_is_active',
            'table': 'courses_course',
            'columns': 'is_active',
            'description': 'Index on is_active for course status filtering'
        },
        {
            'name': 'idx_courses_created_at',
            'table': 'courses_course',
            'columns': 'created_at',
            'description': 'Index on created_at for chronological sorting'
        },
        
        # Enrollment indexes
        {
            'name': 'idx_enrollment_user_course',
            'table': 'courses_courseenrollment',
            'columns': 'user_id, course_id',
            'description': 'Composite index for enrollment lookups'
        },
        {
            'name': 'idx_enrollment_status',
            'table': 'courses_courseenrollment',
            'columns': 'status',
            'description': 'Index on enrollment status'
        },
        
        # Quiz and assignment indexes
        {
            'name': 'idx_quiz_course_id',
            'table': 'quiz_quiz',
            'columns': 'course_id',
            'description': 'Index on quiz course_id for course-based queries'
        },
        {
            'name': 'idx_quiz_is_active',
            'table': 'quiz_quiz',
            'columns': 'is_active',
            'description': 'Index on quiz is_active status'
        },
        
        # Session and authentication indexes
        {
            'name': 'idx_sessions_expire_date',
            'table': 'django_session',
            'columns': 'expire_date',
            'description': 'Index on session expire_date for cleanup operations'
        },
        {
            'name': 'idx_sessions_session_key',
            'table': 'django_session',
            'columns': 'session_key',
            'description': 'Index on session_key for faster session lookups'
        },
        
        # Message and notification indexes
        {
            'name': 'idx_messages_recipient',
            'table': 'lms_messages_message',
            'columns': 'recipient_id',
            'description': 'Index on message recipient for inbox queries'
        },
        {
            'name': 'idx_messages_created_at',
            'table': 'lms_messages_message',
            'columns': 'created_at',
            'description': 'Index on message created_at for chronological sorting'
        },
        
        # Branch indexes
        {
            'name': 'idx_branches_name',
            'table': 'branches_branch',
            'columns': 'name',
            'description': 'Index on branch name for search functionality'
        },
        {
            'name': 'idx_branches_is_active',
            'table': 'branches_branch',
            'columns': 'is_active',
            'description': 'Index on branch is_active status'
        }
    ]
    
    print("Adding performance indexes to database...")
    print("Found {} indexes to add".format(len(indexes_to_add)))
    
    with connection.cursor() as cursor:
        for index_info in indexes_to_add:
            try:
                index_name = index_info['name']
                table_name = index_info['table']
                columns = index_info['columns']
                description = index_info['description']
                
                # Check if index already exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = %s
                    );
                """, [index_name])
                
                index_exists = cursor.fetchone()[0]
                
                if not index_exists:
                    # Create the index
                    if ',' in columns:
                        # Composite index
                        cursor.execute("CREATE INDEX {} ON {} ({});".format(
                            index_name, table_name, columns
                        ))
                    else:
                        # Single column index
                        cursor.execute("CREATE INDEX {} ON {} ({});".format(
                            index_name, table_name, columns
                        ))
                    
                    print("✅ Added index: {} on {}({})".format(index_name, table_name, columns))
                else:
                    print("ℹ️  Index {} already exists, skipping".format(index_name))
                    
            except Exception as e:
                print("❌ Error adding index {}: {}".format(index_info['name'], e))
                logger.error("Error adding index {}: {}".format(index_info['name'], e))

def analyze_query_performance():
    """Analyze and report on query performance improvements"""
    
    print("\nAnalyzing query performance...")
    
    with connection.cursor() as cursor:
        try:
            # Get database statistics
            cursor.execute("""
                SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, n_dead_tup
                FROM pg_stat_user_tables 
                ORDER BY n_live_tup DESC 
                LIMIT 10;
            """)
            
            tables = cursor.fetchall()
            print("\nTop 10 tables by row count:")
            for table in tables:
                print("  {}: {} live rows, {} dead rows".format(
                    table[1], table[5], table[6]
                ))
            
            # Get index usage statistics
            cursor.execute("""
                SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
                FROM pg_stat_user_indexes 
                WHERE idx_scan > 0
                ORDER BY idx_scan DESC 
                LIMIT 10;
            """)
            
            indexes = cursor.fetchall()
            print("\nTop 10 most used indexes:")
            for index in indexes:
                print("  {}: {} scans, {} tuples read".format(
                    index[2], index[3], index[4]
                ))
                
        except Exception as e:
            print("❌ Error analyzing performance: {}".format(e))
            logger.error("Performance analysis error: {}".format(e))

def main():
    """Main optimization function"""
    print("🚀 Database Performance Optimization Script")
    print("=" * 50)
    
    try:
        # Add performance indexes
        add_performance_indexes()
        
        # Analyze performance
        analyze_query_performance()
        
        print("\n🎉 Database optimization completed successfully!")
        print("✅ Performance indexes added")
        print("✅ Query performance analyzed")
        print("✅ Database statistics updated")
        
    except Exception as e:
        print("\n❌ Database optimization failed: {}".format(e))
        logger.error("Database optimization failed: {}".format(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
