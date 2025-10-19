#!/usr/bin/env python
"""
Check for missing related tables in the database
This script identifies missing ManyToMany and ForeignKey relationships
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.db import connection
from django.apps import apps
from django.db.models import ManyToManyField, ForeignKey

def get_all_tables():
    """Get all tables in the database"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        return [row[0] for row in cursor.fetchall()]

def check_model_tables():
    """Check if all model tables exist"""
    db_tables = get_all_tables()
    missing_tables = []
    missing_relations = []
    
    print("🔍 Checking Django Models vs Database Tables")
    print("=" * 70)
    
    for model in apps.get_models():
        table_name = model._meta.db_table
        
        # Check if model table exists
        if table_name not in db_tables:
            missing_tables.append(table_name)
            print(f"❌ Missing table: {table_name} (Model: {model.__name__})")
        else:
            print(f"✅ Table exists: {table_name}")
        
        # Check ManyToMany fields
        for field in model._meta.get_fields():
            if isinstance(field, ManyToManyField):
                if not field.remote_field.through._meta.auto_created:
                    # Custom through model
                    through_table = field.remote_field.through._meta.db_table
                else:
                    # Auto-generated M2M table
                    through_table = field.m2m_db_table()
                
                if through_table not in db_tables:
                    missing_relations.append({
                        'table': through_table,
                        'model': model.__name__,
                        'field': field.name,
                        'type': 'ManyToMany'
                    })
                    print(f"  ⚠️  Missing M2M table: {through_table} for {model.__name__}.{field.name}")
    
    print("\n" + "=" * 70)
    print("📊 Summary:")
    print(f"  Total tables in database: {len(db_tables)}")
    print(f"  Missing model tables: {len(missing_tables)}")
    print(f"  Missing relation tables: {len(missing_relations)}")
    
    if missing_tables:
        print("\n❌ Missing Model Tables:")
        for table in missing_tables:
            print(f"  - {table}")
    
    if missing_relations:
        print("\n❌ Missing Relation Tables:")
        for rel in missing_relations:
            print(f"  - {rel['table']} (Model: {rel['model']}.{rel['field']} - {rel['type']})")
    
    if not missing_tables and not missing_relations:
        print("\n✅ All model tables and relations exist!")
    
    return missing_tables, missing_relations

def check_orphaned_tables():
    """Check for tables in database that don't have corresponding models"""
    db_tables = get_all_tables()
    model_tables = set()
    
    # Get all model tables including M2M
    for model in apps.get_models():
        model_tables.add(model._meta.db_table)
        
        # Add M2M tables
        for field in model._meta.get_fields():
            if isinstance(field, ManyToManyField):
                if not field.remote_field.through._meta.auto_created:
                    model_tables.add(field.remote_field.through._meta.db_table)
                else:
                    model_tables.add(field.m2m_db_table())
    
    # Exclude Django system tables
    system_tables = {
        'django_migrations', 'django_session', 'django_admin_log',
        'django_content_type', 'auth_permission', 'django_site',
        'lms_cache_table', 'auth_group', 'auth_group_permissions'
    }
    
    orphaned_tables = []
    for table in db_tables:
        if table not in model_tables and table not in system_tables:
            orphaned_tables.append(table)
    
    if orphaned_tables:
        print("\n" + "=" * 70)
        print("🗑️  Orphaned Tables (in database but not in models):")
        for table in orphaned_tables:
            print(f"  - {table}")
    
    return orphaned_tables

def check_foreign_keys():
    """Check for missing foreign key constraints"""
    print("\n" + "=" * 70)
    print("🔗 Checking Foreign Key Constraints")
    print("=" * 70)
    
    with connection.cursor() as cursor:
        # Get all foreign keys in database
        cursor.execute("""
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name;
        """)
        
        fk_constraints = cursor.fetchall()
        print(f"✅ Found {len(fk_constraints)} foreign key constraints in database")
        
        # Check if related tables exist
        db_tables = get_all_tables()
        missing_fk_targets = []
        
        for fk in fk_constraints:
            table_name, column_name, foreign_table, foreign_column = fk
            if foreign_table not in db_tables:
                missing_fk_targets.append({
                    'table': table_name,
                    'column': column_name,
                    'references': foreign_table,
                    'ref_column': foreign_column
                })
                print(f"  ❌ FK target missing: {table_name}.{column_name} -> {foreign_table}.{foreign_column}")
        
        if missing_fk_targets:
            print(f"\n⚠️  Found {len(missing_fk_targets)} foreign keys pointing to missing tables")
        else:
            print("✅ All foreign key targets exist")
    
    return missing_fk_targets

def main():
    print("🔍 Database Relationship Check")
    print("=" * 70)
    print()
    
    # Check model tables
    missing_tables, missing_relations = check_model_tables()
    
    # Check orphaned tables
    orphaned_tables = check_orphaned_tables()
    
    # Check foreign keys
    missing_fk_targets = check_foreign_keys()
    
    print("\n" + "=" * 70)
    print("🎯 Final Summary:")
    print(f"  Missing model tables: {len(missing_tables)}")
    print(f"  Missing relation tables: {len(missing_relations)}")
    print(f"  Orphaned tables: {len(orphaned_tables)}")
    print(f"  Missing FK targets: {len(missing_fk_targets)}")
    
    if missing_tables or missing_relations or missing_fk_targets:
        print("\n⚠️  Database has issues that need attention!")
        print("\n💡 Recommended actions:")
        print("  1. Run: python manage.py makemigrations")
        print("  2. Run: python manage.py migrate")
        print("  3. Review and remove orphaned tables if needed")
        return False
    else:
        print("\n✅ Database structure is healthy!")
        if orphaned_tables:
            print("  Note: Some orphaned tables exist but they won't affect functionality")
        return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

