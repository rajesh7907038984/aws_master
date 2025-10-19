#!/usr/bin/env python
"""
Fix Missing Database Relations
This script creates missing ManyToMany tables and cleans up orphaned tables
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.db import connection, transaction
from django.apps import apps

def create_missing_m2m_tables():
    """Create missing ManyToMany relationship tables"""
    print("🔧 Creating Missing ManyToMany Tables")
    print("=" * 70)
    
    missing_tables = [
        {
            'name': 'users_customuser_groups',
            'sql': """
                CREATE TABLE IF NOT EXISTS users_customuser_groups (
                    id SERIAL PRIMARY KEY,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    group_id INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
                    UNIQUE(customuser_id, group_id)
                );
                CREATE INDEX IF NOT EXISTS users_customuser_groups_customuser_id_idx ON users_customuser_groups(customuser_id);
                CREATE INDEX IF NOT EXISTS users_customuser_groups_group_id_idx ON users_customuser_groups(group_id);
            """
        },
        {
            'name': 'users_customuser_user_permissions',
            'sql': """
                CREATE TABLE IF NOT EXISTS users_customuser_user_permissions (
                    id SERIAL PRIMARY KEY,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
                    UNIQUE(customuser_id, permission_id)
                );
                CREATE INDEX IF NOT EXISTS users_customuser_user_permissions_customuser_id_idx ON users_customuser_user_permissions(customuser_id);
                CREATE INDEX IF NOT EXISTS users_customuser_user_permissions_permission_id_idx ON users_customuser_user_permissions(permission_id);
            """
        },
        {
            'name': 'courses_discussion_likes',
            'sql': """
                CREATE TABLE IF NOT EXISTS courses_discussion_likes (
                    id SERIAL PRIMARY KEY,
                    discussion_id BIGINT NOT NULL REFERENCES courses_discussion(id) ON DELETE CASCADE,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    UNIQUE(discussion_id, customuser_id)
                );
                CREATE INDEX IF NOT EXISTS courses_discussion_likes_discussion_id_idx ON courses_discussion_likes(discussion_id);
                CREATE INDEX IF NOT EXISTS courses_discussion_likes_customuser_id_idx ON courses_discussion_likes(customuser_id);
            """
        },
        {
            'name': 'courses_comment_likes',
            'sql': """
                CREATE TABLE IF NOT EXISTS courses_comment_likes (
                    id SERIAL PRIMARY KEY,
                    comment_id BIGINT NOT NULL REFERENCES courses_comment(id) ON DELETE CASCADE,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    UNIQUE(comment_id, customuser_id)
                );
                CREATE INDEX IF NOT EXISTS courses_comment_likes_comment_id_idx ON courses_comment_likes(comment_id);
                CREATE INDEX IF NOT EXISTS courses_comment_likes_customuser_id_idx ON courses_comment_likes(customuser_id);
            """
        },
        {
            'name': 'discussions_discussion_likes',
            'sql': """
                CREATE TABLE IF NOT EXISTS discussions_discussion_likes (
                    id SERIAL PRIMARY KEY,
                    discussion_id BIGINT NOT NULL REFERENCES discussions_discussion(id) ON DELETE CASCADE,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    UNIQUE(discussion_id, customuser_id)
                );
                CREATE INDEX IF NOT EXISTS discussions_discussion_likes_discussion_id_idx ON discussions_discussion_likes(discussion_id);
                CREATE INDEX IF NOT EXISTS discussions_discussion_likes_customuser_id_idx ON discussions_discussion_likes(customuser_id);
            """
        },
        {
            'name': 'discussions_comment_likes',
            'sql': """
                CREATE TABLE IF NOT EXISTS discussions_comment_likes (
                    id SERIAL PRIMARY KEY,
                    comment_id BIGINT NOT NULL REFERENCES discussions_comment(id) ON DELETE CASCADE,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    UNIQUE(comment_id, customuser_id)
                );
                CREATE INDEX IF NOT EXISTS discussions_comment_likes_comment_id_idx ON discussions_comment_likes(comment_id);
                CREATE INDEX IF NOT EXISTS discussions_comment_likes_customuser_id_idx ON discussions_comment_likes(customuser_id);
            """
        },
        {
            'name': 'reports_report_shared_with',
            'sql': """
                CREATE TABLE IF NOT EXISTS reports_report_shared_with (
                    id SERIAL PRIMARY KEY,
                    report_id BIGINT NOT NULL REFERENCES reports_report(id) ON DELETE CASCADE,
                    customuser_id BIGINT NOT NULL REFERENCES users_customuser(id) ON DELETE CASCADE,
                    UNIQUE(report_id, customuser_id)
                );
                CREATE INDEX IF NOT EXISTS reports_report_shared_with_report_id_idx ON reports_report_shared_with(report_id);
                CREATE INDEX IF NOT EXISTS reports_report_shared_with_customuser_id_idx ON reports_report_shared_with(customuser_id);
            """
        },
        {
            'name': 'account_settings_menucontrolsettings_visible_to_custom_roles',
            'sql': """
                CREATE TABLE IF NOT EXISTS account_settings_menucontrolsettings_visible_to_custom_roles (
                    id SERIAL PRIMARY KEY,
                    menucontrolsettings_id BIGINT NOT NULL REFERENCES account_settings_menucontrolsettings(id) ON DELETE CASCADE,
                    role_id BIGINT NOT NULL REFERENCES role_management_role(id) ON DELETE CASCADE,
                    UNIQUE(menucontrolsettings_id, role_id)
                );
                CREATE INDEX IF NOT EXISTS account_settings_menucontrolsettings_visible_to_custom_roles_menucontrolsettings_id_idx ON account_settings_menucontrolsettings_visible_to_custom_roles(menucontrolsettings_id);
                CREATE INDEX IF NOT EXISTS account_settings_menucontrolsettings_visible_to_custom_roles_role_id_idx ON account_settings_menucontrolsettings_visible_to_custom_roles(role_id);
            """
        }
    ]
    
    created_count = 0
    with connection.cursor() as cursor:
        for table_info in missing_tables:
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = %s
                    );
                """, [table_info['name']])
                
                table_exists = cursor.fetchone()[0]
                
                if not table_exists:
                    print(f"Creating table: {table_info['name']}")
                    cursor.execute(table_info['sql'])
                    print(f"✅ Created: {table_info['name']}")
                    created_count += 1
                else:
                    print(f"ℹ️  Table already exists: {table_info['name']}")
                    
            except Exception as e:
                print(f"❌ Error creating table {table_info['name']}: {e}")
    
    print(f"\n✅ Created {created_count} missing tables")
    return created_count

def backup_orphaned_tables():
    """Backup orphaned tables before removal"""
    print("\n🔧 Backing Up Orphaned Tables")
    print("=" * 70)
    
    orphaned_tables = [
        'assignments_assignment_courses',
        'assignments_assignment_topics',
        'branches_branch_groups',
        'courses_course_enrollments',
        'courses_course_instructors',
        'groups_branchgroup_users',
        'lms_notifications_notification_read_by',
        'lms_notifications_notification_recipients',
        'users_user_branches'
    ]
    
    backed_up = []
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
                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    row_count = cursor.fetchone()[0]
                    
                    if row_count > 0:
                        backup_table = f"{table}_backup_{os.getpid()}"
                        print(f"Backing up: {table} ({row_count} rows) -> {backup_table}")
                        cursor.execute(f"CREATE TABLE {backup_table} AS SELECT * FROM {table};")
                        backed_up.append((table, backup_table, row_count))
                        print(f"✅ Backed up: {table}")
                    else:
                        print(f"ℹ️  Table {table} is empty, no backup needed")
                else:
                    print(f"ℹ️  Table {table} does not exist")
                    
            except Exception as e:
                print(f"❌ Error backing up table {table}: {e}")
    
    print(f"\n✅ Backed up {len(backed_up)} tables with data")
    return backed_up

def remove_orphaned_tables():
    """Remove orphaned tables from database"""
    print("\n🔧 Removing Orphaned Tables")
    print("=" * 70)
    
    orphaned_tables = [
        'assignments_assignment_courses',
        'assignments_assignment_topics',
        'branches_branch_groups',
        'courses_course_enrollments',
        'courses_course_instructors',
        'groups_branchgroup_users',
        'lms_notifications_notification_read_by',
        'lms_notifications_notification_recipients',
        'users_user_branches'
    ]
    
    removed_count = 0
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
                    print(f"Removing table: {table}")
                    cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    print(f"✅ Removed: {table}")
                    removed_count += 1
                else:
                    print(f"ℹ️  Table {table} does not exist")
                    
            except Exception as e:
                print(f"❌ Error removing table {table}: {e}")
    
    print(f"\n✅ Removed {removed_count} orphaned tables")
    return removed_count

def verify_fixes():
    """Verify that all fixes were applied successfully"""
    print("\n🔍 Verifying Database Fixes")
    print("=" * 70)
    
    # Check if all expected M2M tables exist
    expected_tables = [
        'users_customuser_groups',
        'users_customuser_user_permissions',
        'courses_discussion_likes',
        'courses_comment_likes',
        'discussions_discussion_likes',
        'discussions_comment_likes',
        'reports_report_shared_with',
        'account_settings_menucontrolsettings_visible_to_custom_roles'
    ]
    
    all_exist = True
    with connection.cursor() as cursor:
        for table in expected_tables:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """, [table])
            
            exists = cursor.fetchone()[0]
            if exists:
                print(f"✅ {table} exists")
            else:
                print(f"❌ {table} missing")
                all_exist = False
    
    return all_exist

def main():
    print("🔧 Database Relations Fix Script")
    print("=" * 70)
    print()
    
    try:
        # Step 1: Create missing M2M tables
        created = create_missing_m2m_tables()
        
        # Step 2: Backup orphaned tables (in case they have important data)
        backed_up = backup_orphaned_tables()
        
        # Step 3: Remove orphaned tables
        removed = remove_orphaned_tables()
        
        # Step 4: Verify fixes
        all_good = verify_fixes()
        
        print("\n" + "=" * 70)
        print("🎯 Summary:")
        print(f"  ✅ Created {created} missing relation tables")
        print(f"  ✅ Backed up {len(backed_up)} tables with data")
        print(f"  ✅ Removed {removed} orphaned tables")
        
        if all_good:
            print("\n✅ Database structure fixed successfully!")
            print("\n💡 Next steps:")
            print("  1. Run: python manage.py migrate")
            print("  2. Test all ManyToMany relationships")
            print("  3. Verify no functionality is broken")
            return True
        else:
            print("\n⚠️  Some issues remain - please review the output above")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during database fix: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

