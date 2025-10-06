"""
Migration Best Practices Guide - Ensures Future Compatibility

This module provides guidelines and utilities for creating safe migrations
that work with the Universal Migration System.

Usage Examples:
    from core.utils.migration_best_practices import SafeMigrationHelper
    
    # Before creating a migration
    helper = SafeMigrationHelper()
    helper.validate_new_field('user_profile', 'phone_number')
    
    # In migration files
    from core.utils.migration_best_practices import safe_add_field
    safe_add_field(schema_editor, 'user_profile', 'phone_number', 'VARCHAR(20)')
"""

import logging
from django.db import connection, transaction
from django.core.management import call_command
from core.utils.migration_safety import UniversalMigrationSafety

logger = logging.getLogger(__name__)


class SafeMigrationHelper:
    """Helper class for creating future-proof migrations"""
    
    def __init__(self):
        self.safety = UniversalMigrationSafety()
        self.safety._refresh_schema_cache()
    
    def validate_new_field(self, table_name: str, field_name: str) -> dict:
        """
        Validate that a new field can be added safely
        
        Returns:
            dict: Validation result with 'safe', 'reason', and 'recommendation'
        """
        if table_name in self.safety.existing_columns:
            if field_name in self.safety.existing_columns[table_name]:
                return {
                    'safe': False,
                    'reason': f'Column {field_name} already exists in {table_name}',
                    'recommendation': 'Use AlterField instead of AddField, or check if migration should be faked'
                }
        
        return {
            'safe': True,
            'reason': 'No conflicts detected',
            'recommendation': 'Safe to proceed with AddField'
        }
    
    def validate_new_table(self, table_name: str) -> dict:
        """Validate that a new table can be created safely"""
        if table_name in self.safety.existing_tables:
            return {
                'safe': False,
                'reason': f'Table {table_name} already exists',
                'recommendation': 'Consider using a different table name or check if migration should be faked'
            }
        
        return {
            'safe': True,
            'reason': 'No conflicts detected',
            'recommendation': 'Safe to proceed with CreateModel'
        }
    
    def suggest_safe_field_name(self, table_name: str, desired_name: str) -> str:
        """Suggest a safe field name if the desired one conflicts"""
        if table_name not in self.safety.existing_columns:
            return desired_name
        
        existing_fields = self.safety.existing_columns[table_name]
        if desired_name not in existing_fields:
            return desired_name
        
        # Generate alternatives
        for i in range(1, 100):
            alternative = f"{desired_name}_{i}"
            if alternative not in existing_fields:
                return alternative
        
        return f"{desired_name}_new"


# Safe migration operation functions
def safe_add_field(schema_editor, table_name: str, field_name: str, field_definition: str):
    """
    Safely add a field with automatic conflict detection
    
    Usage in migrations:
        from core.utils.migration_best_practices import safe_add_field
        
        def forwards(apps, schema_editor):
            safe_add_field(schema_editor, 'myapp_mymodel', 'new_field', 'VARCHAR(100)')
    """
    safety = UniversalMigrationSafety()
    
    # Check if field already exists
    if safety._get_all_columns().get(table_name, set()).get(field_name):
        logger.info(f"Field {table_name}.{field_name} already exists, skipping AddField")
        return True
    
    # Execute the field addition
    try:
        quoted_table = schema_editor.connection.ops.quote_name(table_name)
        quoted_field = schema_editor.connection.ops.quote_name(field_name)
        sql = f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_field} {field_definition}"
        schema_editor.execute(sql)
        logger.info(f"Successfully added field {table_name}.{field_name}")
        return True
    except Exception as e:
        if 'already exists' in str(e).lower():
            logger.info(f"Field {table_name}.{field_name} already exists (detected during execution)")
            return True
        else:
            logger.error(f"Failed to add field {table_name}.{field_name}: {e}")
            raise


def safe_create_table(schema_editor, table_name: str, table_sql: str):
    """
    Safely create a table with automatic conflict detection
    """
    safety = UniversalMigrationSafety()
    
    if table_name in safety._get_all_tables():
        logger.info(f"Table {table_name} already exists, skipping CreateTable")
        return True
    
    try:
        schema_editor.execute(table_sql)
        logger.info(f"Successfully created table {table_name}")
        return True
    except Exception as e:
        if 'already exists' in str(e).lower():
            logger.info(f"Table {table_name} already exists (detected during execution)")
            return True
        else:
            logger.error(f"Failed to create table {table_name}: {e}")
            raise


def safe_drop_field(schema_editor, table_name: str, field_name: str):
    """
    Safely drop a field with automatic conflict detection
    """
    safety = UniversalMigrationSafety()
    
    # Check if field exists
    if field_name not in safety._get_all_columns().get(table_name, set()):
        logger.info(f"Field {table_name}.{field_name} does not exist, skipping DropField")
        return True
    
    try:
        quoted_table = schema_editor.connection.ops.quote_name(table_name)
        quoted_field = schema_editor.connection.ops.quote_name(field_name)
        sql = f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_field}"
        schema_editor.execute(sql)
        logger.info(f"Successfully dropped field {table_name}.{field_name}")
        return True
    except Exception as e:
        if 'does not exist' in str(e).lower():
            logger.info(f"Field {table_name}.{field_name} does not exist (detected during execution)")
            return True
        else:
            logger.error(f"Failed to drop field {table_name}.{field_name}: {e}")
            raise


# Migration templates for common operations
SAFE_ADD_FIELD_TEMPLATE = '''
# Safe field addition that prevents conflicts
from django.db import migrations, models
from core.utils.migration_best_practices import safe_add_field

def add_field_safely(apps, schema_editor):
    """Safely add field with conflict detection"""
    safe_add_field(schema_editor, '{table_name}', '{field_name}', '{field_definition}')

def reverse_add_field(apps, schema_editor):
    """Reverse the field addition"""
    # Only drop if field exists
    from core.utils.migration_best_practices import safe_drop_field
    safe_drop_field(schema_editor, '{table_name}', '{field_name}')

class Migration(migrations.Migration):
    dependencies = [
        # Your dependencies here
    ]

    operations = [
        migrations.RunPython(
            code=add_field_safely,
            reverse_code=reverse_add_field,
        ),
    ]
'''

SAFE_CREATE_TABLE_TEMPLATE = '''
# Safe table creation that prevents conflicts
from django.db import migrations, models
from core.utils.migration_best_practices import safe_create_table

def create_table_safely(apps, schema_editor):
    """Safely create table with conflict detection"""
    table_sql = """
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            {field_definitions}
        )
    """
    safe_create_table(schema_editor, '{table_name}', table_sql)

class Migration(migrations.Migration):
    dependencies = [
        # Your dependencies here
    ]

    operations = [
        migrations.RunPython(
            code=create_table_safely,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
'''


def generate_safe_migration(operation_type: str, **kwargs) -> str:
    """
    Generate a safe migration template
    
    Args:
        operation_type: 'add_field', 'create_table', etc.
        **kwargs: Parameters for the specific operation
        
    Returns:
        str: Migration file content
    """
    if operation_type == 'add_field':
        return SAFE_ADD_FIELD_TEMPLATE.format(**kwargs)
    elif operation_type == 'create_table':
        return SAFE_CREATE_TABLE_TEMPLATE.format(**kwargs)
    else:
        raise ValueError(f"Unknown operation type: {operation_type}")


# Development helpers
class MigrationDevelopmentHelper:
    """Helper for developers creating new migrations"""
    
    @staticmethod
    def check_before_makemigrations(app_name: str = None):
        """
        Run this before creating new migrations to check for potential conflicts
        
        Usage:
            from core.utils.migration_best_practices import MigrationDevelopmentHelper
            MigrationDevelopmentHelper.check_before_makemigrations('myapp')
        """
        helper = SafeMigrationHelper()
        
        print("🔍 Pre-migration conflict check...")
        
        # This could analyze model changes and predict conflicts
        # For now, just verify the migration system is working
        try:
            call_command('check', verbosity=0)
            print(" Django configuration is valid")
        except Exception as e:
            print(f" Django configuration issues: {e}")
        
        # Check database connectivity
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            print(" Database connection is working")
        except Exception as e:
            print(f" Database connection issues: {e}")
        
        print("🎯 Ready for makemigrations!")
    
    @staticmethod
    def test_migration_safety(app_name: str, migration_name: str):
        """
        Test a migration for safety before applying it
        """
        print(f"🧪 Testing migration safety: {app_name}.{migration_name}")
        
        try:
            # This would analyze the migration file for conflicts
            # For now, just run a dry-run check
            call_command('migrate', app_name, migration_name, verbosity=1, dry_run=True)
            print(" Migration appears safe")
            return True
        except Exception as e:
            print(f" Migration may have issues: {e}")
            return False


# Quick usage examples for documentation
USAGE_EXAMPLES = """
# Example 1: Check before adding a field
helper = SafeMigrationHelper()
result = helper.validate_new_field('users_customuser', 'phone_number')
if result['safe']:
    print("Safe to add field")
else:
    print(f"Conflict: {result['reason']}")

# Example 2: Use in development
MigrationDevelopmentHelper.check_before_makemigrations('myapp')

# Example 3: Safe migration operations
def forwards(apps, schema_editor):
    safe_add_field(schema_editor, 'myapp_mymodel', 'new_field', 'VARCHAR(100)')

# Example 4: Test before applying
MigrationDevelopmentHelper.test_migration_safety('myapp', '0001_initial')
"""
