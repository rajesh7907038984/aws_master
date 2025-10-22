"""
Universal Migration Safety Framework - Future-Proof Solution

This module provides intelligent, generic migration safety that works with any
database tables, columns, and constraints - both current and future ones.

Author: LMS Development Team
Created: 2025-08-26
Purpose: Prevent ALL migration conflicts permanently (current + future)
"""

import logging
import re
import json
from pathlib import Path
from datetime import datetime
from django.db import connection, transaction
from django.core.management.color import no_style
from django.db.migrations.recorder import MigrationRecorder
from django.apps import apps
from django.conf import settings
from typing import Dict, List, Tuple, Optional, Any, Set
from django.core.management import CommandError

logger = logging.getLogger(__name__)


class UniversalMigrationSafety:
    """
    Universal migration safety that works with any database schema changes
    """
    
    def __init__(self):
        self.connection = connection
        self.cursor = connection.cursor()
        self.existing_tables = None
        self.existing_columns = None
        self.existing_constraints = None
        self.existing_indexes = None
        
    def _refresh_schema_cache(self):
        """Refresh cached database schema information"""
        self.existing_tables = self._get_all_tables()
        self.existing_columns = self._get_all_columns()
        self.existing_constraints = self._get_all_constraints()
        self.existing_indexes = self._get_all_indexes()
    
    def _get_all_tables(self) -> Set[str]:
        """Get all existing table names"""
        try:
            self.cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            return {row[0] for row in self.cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Could not fetch table list: {e}")
            return set()
    
    def _get_all_columns(self) -> Dict[str, Set[str]]:
        """Get all existing columns grouped by table"""
        try:
            self.cursor.execute("""
                SELECT table_name, column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public'
            """)
            columns = {}
            for table_name, column_name in self.cursor.fetchall():
                if table_name not in columns:
                    columns[table_name] = set()
                columns[table_name].add(column_name)
            return columns
        except Exception as e:
            logger.warning(f"Could not fetch column list: {e}")
            return {}
    
    def _get_all_constraints(self) -> Set[str]:
        """Get all existing constraint names"""
        try:
            self.cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_schema = 'public'
            """)
            return {row[0] for row in self.cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Could not fetch constraint list: {e}")
            return set()
    
    def _get_all_indexes(self) -> Set[str]:
        """Get all existing index names"""
        try:
            self.cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE schemaname = 'public'
            """)
            return {row[0] for row in self.cursor.fetchall()}
        except Exception as e:
            logger.warning(f"Could not fetch index list: {e}")
            return set()
    
    def analyze_migration_conflicts(self, migration_content: str) -> List[Dict[str, Any]]:
        """
        Analyze migration content for potential conflicts with existing schema
        
        Args:
            migration_content: The content of a migration file
            
        Returns:
            List of potential conflicts with details
        """
        conflicts = []
        
        # Refresh schema cache
        self._refresh_schema_cache()
        
        # Patterns to detect different migration operations
        patterns = {
            'add_field': r'migrations\.AddField\(\s*model_name=[\'"](\w+)[\'"],\s*name=[\'"](\w+)[\'"]',
            'create_model': r'migrations\.CreateModel\(\s*name=[\'"](\w+)[\'"]',
            'add_constraint': r'migrations\.AddConstraint\([^)]*name=[\'"]([^"\']+)[\'"]',
            'add_index': r'migrations\.AddIndex\([^)]*name=[\'"]([^"\']+)[\'"]',
            'rename_field': r'migrations\.RenameField\(\s*model_name=[\'"](\w+)[\'"],\s*old_name=[\'"](\w+)[\'"],\s*new_name=[\'"](\w+)[\'"]',
            'alter_field': r'migrations\.AlterField\(\s*model_name=[\'"](\w+)[\'"],\s*name=[\'"](\w+)[\'"]',
        }
        
        for operation_type, pattern in patterns.items():
            matches = re.findall(pattern, migration_content, re.MULTILINE | re.DOTALL)
            
            for match in matches:
                conflict = self._check_operation_conflict(operation_type, match)
                if conflict:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _check_operation_conflict(self, operation_type: str, match: tuple) -> Optional[Dict[str, Any]]:
        """Check if a specific operation would cause a conflict"""
        
        if operation_type == 'add_field':
            model_name, field_name = match
            table_name = self._get_table_name_from_model(model_name)
            if table_name in self.existing_columns and field_name in self.existing_columns[table_name]:
                return {
                    'type': 'duplicate_column',
                    'table': table_name,
                    'column': field_name,
                    'operation': 'AddField',
                    'severity': 'high'
                }
        
        elif operation_type == 'create_model':
            model_name = match[0]
            table_name = self._get_table_name_from_model(model_name)
            if table_name in self.existing_tables:
                return {
                    'type': 'duplicate_table',
                    'table': table_name,
                    'operation': 'CreateModel',
                    'severity': 'high'
                }
        
        elif operation_type == 'add_constraint':
            constraint_name = match[0]
            if constraint_name in self.existing_constraints:
                return {
                    'type': 'duplicate_constraint',
                    'constraint': constraint_name,
                    'operation': 'AddConstraint',
                    'severity': 'medium'
                }
        
        elif operation_type == 'add_index':
            index_name = match[0]
            if index_name in self.existing_indexes:
                return {
                    'type': 'duplicate_index',
                    'index': index_name,
                    'operation': 'AddIndex',
                    'severity': 'medium'
                }
        
        elif operation_type == 'rename_field':
            model_name, old_name, new_name = match
            table_name = self._get_table_name_from_model(model_name)
            if table_name in self.existing_columns:
                if old_name not in self.existing_columns[table_name]:
                    return {
                        'type': 'missing_source_column',
                        'table': table_name,
                        'column': old_name,
                        'operation': 'RenameField',
                        'severity': 'high'
                    }
                if new_name in self.existing_columns[table_name]:
                    return {
                        'type': 'target_column_exists',
                        'table': table_name,
                        'column': new_name,
                        'operation': 'RenameField',
                        'severity': 'high'
                    }
        
        return None
    
    def _get_table_name_from_model(self, model_name: str) -> str:
        """Convert Django model name to database table name"""
        # Try to find the actual table name from Django apps
        for app_config in apps.get_app_configs():
            try:
                model = app_config.get_model(model_name)
                return model._meta.db_table
            except:
                continue
        
        # Fallback: generate likely table name
        app_label = "unknown"  # This would need to be passed in or inferred
        return f"{app_label}_{model_name.lower()}"
    
    def safe_execute_sql(self, sql: str, params: Optional[List] = None) -> bool:
        """
        Safely execute SQL with automatic conflict detection and resolution
        """
        try:
            with transaction.atomic():
                self.cursor.execute(sql, params or [])
                return True
        except Exception as e:
            error_msg = str(e).lower()
            
            # Handle common conflict patterns
            if 'already exists' in error_msg:
                logger.info(f"Skipping SQL due to existing object: {sql[:100]}...")
                return True
            elif 'does not exist' in error_msg and 'drop' in sql.lower():
                logger.info(f"Skipping drop of non-existent object: {sql[:100]}...")
                return True
            elif 'column' in error_msg and 'does not exist' in error_msg:
                logger.warning(f"Column operation on non-existent column: {sql[:100]}...")
                return False
            else:
                logger.error(f"SQL execution failed: {e}")
                return False
    
    def generate_safe_migration_sql(self, original_sql: str) -> str:
        """
        Convert regular migration SQL to safe SQL with existence checks
        """
        safe_sql = original_sql
        
        # Add IF NOT EXISTS to CREATE statements
        safe_sql = re.sub(
            r'CREATE TABLE (\w+)',
            r'CREATE TABLE IF NOT EXISTS \1',
            safe_sql,
            flags=re.IGNORECASE
        )
        
        # Add IF NOT EXISTS to ALTER TABLE ADD COLUMN
        safe_sql = re.sub(
            r'ALTER TABLE (\w+) ADD COLUMN (\w+)',
            r'ALTER TABLE \1 ADD COLUMN IF NOT EXISTS \2',
            safe_sql,
            flags=re.IGNORECASE
        )
        
        # Add IF EXISTS to DROP statements
        safe_sql = re.sub(
            r'DROP TABLE (\w+)',
            r'DROP TABLE IF EXISTS \1',
            safe_sql,
            flags=re.IGNORECASE
        )
        
        safe_sql = re.sub(
            r'ALTER TABLE (\w+) DROP COLUMN (\w+)',
            r'ALTER TABLE \1 DROP COLUMN IF EXISTS \2',
            safe_sql,
            flags=re.IGNORECASE
        )
        
        return safe_sql


class DynamicMigrationResolver:
    """
    Dynamically resolves migration conflicts based on error patterns
    """
    
    def __init__(self):
        self.safety = UniversalMigrationSafety()
    
    def resolve_migration_error(self, error_message: str, app_name: str = None) -> bool:
        """
        Dynamically resolve migration errors based on error patterns
        
        Args:
            error_message: The error message from failed migration
            app_name: Optional app name where error occurred
            
        Returns:
            True if error was resolved, False otherwise
        """
        error_lower = error_message.lower()
        
        # Pattern 1: Duplicate column
        if 'already exists' in error_lower and 'column' in error_lower:
            return self._resolve_duplicate_column_error(error_message, app_name)
        
        # Pattern 2: Duplicate table
        elif 'already exists' in error_lower and ('table' in error_lower or 'relation' in error_lower):
            return self._resolve_duplicate_table_error(error_message, app_name)
        
        # Pattern 3: Missing column for rename
        elif 'does not exist' in error_lower and 'column' in error_lower:
            return self._resolve_missing_column_error(error_message, app_name)
        
        # Pattern 4: Constraint conflicts
        elif 'constraint' in error_lower and 'already exists' in error_lower:
            return self._resolve_constraint_conflict(error_message, app_name)
        
        # Pattern 5: Index conflicts  
        elif 'index' in error_lower and 'already exists' in error_lower:
            return self._resolve_index_conflict(error_message, app_name)
        
        return False
    
    def _resolve_duplicate_column_error(self, error_message: str, app_name: str) -> bool:
        """Resolve duplicate column errors by faking the migration"""
        logger.info(f"Resolving duplicate column error for {app_name}")
        
        if app_name:
            try:
                # Get the latest unapplied migration for this app
                from django.core.management import call_command
                import subprocess
                import sys
                
                result = subprocess.run([
                    sys.executable, 'manage.py', 'showmigrations', app_name, '--plan'
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    # Find unapplied migrations (marked with [ ])
                    unapplied = []
                    for line in result.stdout.split('\n'):
                        if '[ ]' in line and app_name in line:
                            migration = line.split('.')[-1].strip()
                            unapplied.append(migration)
                    
                    if unapplied:
                        # DISABLED: Fake the first unapplied migration (dangerous)
                        # migration_name = unapplied[0]
                        # call_command('migrate', app_name, migration_name, fake=True)
                        # logger.info(f"Faked migration {app_name}.{migration_name}")
                        logger.warning(f"Migration issue detected but fake migrations disabled for safety. Use safe_migration_manager.py instead.")
                        return False
            except Exception as e:
                logger.error(f"Could not fake migration: {e}")
        
        return False
    
    def _resolve_duplicate_table_error(self, error_message: str, app_name: str) -> bool:
        """Resolve duplicate table errors"""
        return self._resolve_duplicate_column_error(error_message, app_name)
    
    def _resolve_missing_column_error(self, error_message: str, app_name: str) -> bool:
        """Resolve missing column errors for rename operations"""
        logger.info(f"Resolving missing column error for {app_name}")
        # For rename operations where source column doesn't exist, 
        # we can fake the migration since the end state is what matters
        return self._resolve_duplicate_column_error(error_message, app_name)
    
    def _resolve_constraint_conflict(self, error_message: str, app_name: str) -> bool:
        """Resolve constraint conflicts"""
        return self._resolve_duplicate_column_error(error_message, app_name)
    
    def _resolve_index_conflict(self, error_message: str, app_name: str) -> bool:
        """Resolve index conflicts"""
        return self._resolve_duplicate_column_error(error_message, app_name)


# Utility functions for easy use
def safe_migrate(app_name: str = None, migration_name: str = None) -> bool:
    """
    Safely run migrations with automatic conflict resolution
    """
    from django.core.management import call_command
    import subprocess
    import sys
    
    resolver = DynamicMigrationResolver()
    
    try:
        if app_name and migration_name:
            call_command('migrate', app_name, migration_name)
        elif app_name:
            call_command('migrate', app_name)
        else:
            call_command('migrate')
        return True
    except Exception as e:
        logger.warning(f"Migration failed: {e}")
        
        # Try to resolve the error
        if resolver.resolve_migration_error(str(e), app_name):
            # Retry migration after resolution
            try:
                if app_name and migration_name:
                    call_command('migrate', app_name, migration_name)
                elif app_name:
                    call_command('migrate', app_name)
                else:
                    call_command('migrate')
                return True
            except Exception as retry_error:
                logger.error(f"Migration failed again after resolution: {retry_error}")
                return False
        
        return False

    def check_schema_consistency(self, baseline_schema_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if current database schema matches expected baseline schema
        """
        logger.info("🔍 Checking schema consistency...")
        
        # Load baseline schema if provided
        if baseline_schema_path:
            baseline_schema = self._load_baseline_schema(baseline_schema_path)
        else:
            # Try to find default baseline schema
            default_baseline = Path('database_schema/baseline_schema.json')
            if default_baseline.exists():
                baseline_schema = self._load_baseline_schema(str(default_baseline))
            else:
                logger.warning("No baseline schema found - skipping schema consistency check")
                return {'consistent': True, 'message': 'No baseline schema available'}
        
        # Get current schema
        current_schema = self._dump_current_schema()
        
        # Compare schemas
        differences = self._compare_schemas(baseline_schema, current_schema)
        
        if differences['has_differences']:
            logger.warning(f"Schema inconsistencies detected: {differences['summary']['total_differences']} differences")
            return {
                'consistent': False,
                'differences': differences,
                'message': f"Schema has {differences['summary']['total_differences']} differences from baseline"
            }
        else:
            logger.info("✅ Schema is consistent with baseline")
            return {
                'consistent': True,
                'message': 'Schema matches baseline'
            }

    def _load_baseline_schema(self, schema_path: str) -> Dict[str, Any]:
        """Load baseline schema from file"""
        try:
            with open(schema_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load baseline schema from {schema_path}: {e}")
            return {}

    def _dump_current_schema(self) -> Dict[str, Any]:
        """Dump current database schema"""
        from core.management.commands.dump_schema import Command as DumpSchemaCommand
        
        # Create temporary schema dump
        temp_file = Path('temp_current_schema.json')
        
        try:
            # Use the dump_schema command to get current schema
            dump_command = DumpSchemaCommand()
            dump_command.handle(
                output=str(temp_file),
                include_django_tables=False
            )
            
            # Load the dumped schema
            with open(temp_file, 'r') as f:
                current_schema = json.load(f)
            
            return current_schema
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()

    def _compare_schemas(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two schemas and return differences"""
        from core.management.commands.compare_schema import Command as CompareSchemaCommand
        
        # Use the compare_schema command logic
        compare_command = CompareSchemaCommand()
        return compare_command._compare_schemas(baseline, current, {})

    def validate_schema_before_migration(self, migration_file_path: str, baseline_schema_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate schema consistency before applying a migration
        """
        logger.info(f"🔍 Validating schema before migration: {migration_file_path}")
        
        # Check current schema consistency
        schema_check = self.check_schema_consistency(baseline_schema_path)
        
        if not schema_check['consistent']:
            logger.warning("Schema inconsistencies detected before migration")
            return {
                'valid': False,
                'reason': 'schema_inconsistent',
                'message': 'Database schema is not consistent with baseline',
                'details': schema_check
            }
        
        # Check migration safety
        migration_conflicts = self.analyze_migration_conflicts_from_file(migration_file_path)
        
        if migration_conflicts:
            logger.warning(f"Migration conflicts detected: {len(migration_conflicts)} issues")
            return {
                'valid': False,
                'reason': 'migration_conflicts',
                'message': f'Migration has {len(migration_conflicts)} potential conflicts',
                'details': migration_conflicts
            }
        
        logger.info("✅ Schema validation passed")
        return {
            'valid': True,
            'message': 'Schema and migration validation passed'
        }

    def analyze_migration_conflicts_from_file(self, migration_file_path: str) -> List[Dict[str, Any]]:
        """Analyze migration file for conflicts"""
        try:
            with open(migration_file_path, 'r') as f:
                content = f.read()
            return self.analyze_migration_conflicts(content)
        except Exception as e:
            logger.error(f"Could not analyze migration file {migration_file_path}: {e}")
            return []

    def create_schema_snapshot(self, output_path: str = None) -> str:
        """
        Create a schema snapshot for version control
        """
        from core.management.commands.dump_schema import Command as DumpSchemaCommand
        
        if not output_path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'database_schema/schema_snapshot_{timestamp}.json'
        
        # Create schema directory
        schema_dir = Path('database_schema')
        schema_dir.mkdir(exist_ok=True)
        
        # Use dump_schema command
        dump_command = DumpSchemaCommand()
        dump_command.handle(
            output=output_path,
            include_django_tables=False
        )
        
        logger.info(f"Schema snapshot created: {output_path}")
        return output_path


def check_migration_safety(migration_file_path: str) -> List[Dict[str, Any]]:
    """
    Check a migration file for potential conflicts before applying
    """
    safety = UniversalMigrationSafety()
    
    try:
        with open(migration_file_path, 'r') as f:
            content = f.read()
        return safety.analyze_migration_conflicts(content)
    except Exception as e:
        logger.error(f"Could not analyze migration file {migration_file_path}: {e}")
        return []
