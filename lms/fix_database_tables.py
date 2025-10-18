#!/usr/bin/env python
"""
Database Table Fix Script for LMS
This script ensures all required database tables exist and fixes common database issues.
"""

import os
import sys
import django
from django.conf import settings
from django.db import connection, transaction
from django.core.management import execute_from_command_line

def setup_django():
    """Setup Django environment"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
    django.setup()

def check_table_exists(table_name):
    """Check if a table exists in the database"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, [table_name])
        return cursor.fetchone()[0]

def create_missing_tables():
    """Create missing database tables"""
    missing_tables = []
    
    # Check for courses_course_prerequisites table
    if not check_table_exists('courses_course_prerequisites'):
        missing_tables.append('courses_course_prerequisites')
        print("❌ courses_course_prerequisites table missing")
    else:
        print("✅ courses_course_prerequisites table exists")
    
    # Check for other critical tables
    critical_tables = [
        'courses_course',
        'courses_topic',
        'users_customuser',
        'assignments_assignment',
        'quiz_quiz',
        'scorm_elearningpackage'
    ]
    
    for table in critical_tables:
        if not check_table_exists(table):
            missing_tables.append(table)
            print(f"❌ {table} table missing")
        else:
            print(f"✅ {table} table exists")
    
    return missing_tables

def fix_prerequisites_table():
    """Fix the prerequisites table specifically"""
    try:
        with connection.cursor() as cursor:
            # Create the prerequisites table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS courses_course_prerequisites (
                    id SERIAL PRIMARY KEY,
                    from_course_id INTEGER NOT NULL REFERENCES courses_course(id) ON DELETE CASCADE,
                    to_course_id INTEGER NOT NULL REFERENCES courses_course(id) ON DELETE CASCADE,
                    UNIQUE(from_course_id, to_course_id)
                );
            """)
            print("✅ courses_course_prerequisites table created/fixed")
    except Exception as e:
        print(f"❌ Error creating prerequisites table: {e}")

def run_migrations():
    """Run Django migrations to ensure all tables are created"""
    try:
        print("🔄 Running Django migrations...")
        execute_from_command_line(['manage.py', 'migrate', '--noinput'])
        print("✅ Migrations completed successfully")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")

def check_database_connection():
    """Check database connection"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def main():
    """Main function to fix database issues"""
    print("🔧 LMS Database Fix Script")
    print("=" * 50)
    
    # Setup Django
    setup_django()
    
    # Check database connection
    if not check_database_connection():
        print("❌ Cannot proceed without database connection")
        return False
    
    # Check for missing tables
    missing_tables = create_missing_tables()
    
    if missing_tables:
        print(f"\n🔧 Found {len(missing_tables)} missing tables")
        
        # Fix prerequisites table specifically
        if 'courses_course_prerequisites' in missing_tables:
            fix_prerequisites_table()
        
        # Run migrations for other tables
        run_migrations()
        
        # Verify fixes
        print("\n🔍 Verifying fixes...")
        missing_tables_after = create_missing_tables()
        
        if missing_tables_after:
            print(f"❌ Still missing {len(missing_tables_after)} tables: {missing_tables_after}")
            return False
        else:
            print("✅ All tables now exist")
            return True
    else:
        print("✅ All required tables exist")
        return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
