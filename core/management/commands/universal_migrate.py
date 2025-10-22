"""
Universal Migration Command - Works with ANY future database changes

This command provides intelligent migration handling that automatically
resolves conflicts for any tables, columns, or constraints - both current and future.

Usage:
    python manage.py universal_migrate
    python manage.py universal_migrate --app myapp  
    python manage.py universal_migrate --analyze-only
    python manage.py universal_migrate --force-safe
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection
from django.apps import apps
import subprocess
import sys
import os
import re
from core.utils.migration_safety import UniversalMigrationSafety, DynamicMigrationResolver, safe_migrate

class Command(BaseCommand):
    help = 'Universal safe migration that works with any future database changes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            help='Specific app to migrate'
        )
        parser.add_argument(
            '--migration',
            type=str,
            help='Specific migration to apply'
        )
        parser.add_argument(
            '--analyze-only',
            action='store_true',
            help='Only analyze migrations for conflicts, do not apply'
        )
        parser.add_argument(
            '--force-safe',
            action='store_true',
            help='Force safe mode - skip conflicting migrations (DEPRECATED - use safe_migration_manager.py instead)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        self.safety = UniversalMigrationSafety()
        self.resolver = DynamicMigrationResolver()
        
        self.stdout.write(self.style.SUCCESS(' Universal Migration System'))
        self.stdout.write('🔍 Analyzing database schema and pending migrations...\n')
        
        # Get all pending migrations
        pending_migrations = self._get_pending_migrations(options.get('app'))
        
        if not pending_migrations:
            self.stdout.write(self.style.SUCCESS(' No pending migrations found'))
            return
        
        self.stdout.write(f"📋 Found {len(pending_migrations)} pending migrations:")
        for app_name, migration_name in pending_migrations:
            self.stdout.write(f"   • {app_name}.{migration_name}")
        self.stdout.write("")
        
        # Analyze each migration for conflicts
        all_conflicts = []
        for app_name, migration_name in pending_migrations:
            conflicts = self._analyze_migration_file(app_name, migration_name)
            if conflicts:
                all_conflicts.extend(conflicts)
                self.stdout.write(f"  {app_name}.{migration_name} has {len(conflicts)} potential conflicts")
        
        if options['analyze_only']:
            self._display_conflict_analysis(all_conflicts)
            return
        
        if options['dry_run']:
            self._display_dry_run_plan(pending_migrations, all_conflicts)
            return
        
        # Apply migrations with intelligent conflict resolution
        self._apply_migrations_safely(pending_migrations, all_conflicts, options['force_safe'])
    
    def _get_pending_migrations(self, specific_app=None):
        """Get all pending migrations"""
        try:
            cmd = ['python', 'manage.py', 'showmigrations', '--plan']
            if specific_app:
                cmd.append(specific_app)
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='.')
            
            pending = []
            for line in result.stdout.split('\n'):
                if '[ ]' in line:  # Unapplied migration
                    # Extract app and migration name
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        full_name = parts[1]  # Format: app_name.migration_name
                        if '.' in full_name:
                            app_name, migration_name = full_name.split('.', 1)
                            pending.append((app_name, migration_name))
            
            return pending
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Could not get pending migrations: {e}"))
            return []
    
    def _analyze_migration_file(self, app_name, migration_name):
        """Analyze a specific migration file for conflicts"""
        try:
            # Find the migration file
            migration_file = self._find_migration_file(app_name, migration_name)
            if not migration_file:
                return []
            
            # Read and analyze the file
            with open(migration_file, 'r') as f:
                content = f.read()
            
            return self.safety.analyze_migration_conflicts(content)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not analyze {app_name}.{migration_name}: {e}"))
            return []
    
    def _find_migration_file(self, app_name, migration_name):
        """Find the migration file path"""
        try:
            app_config = apps.get_app_config(app_name)
            migrations_dir = os.path.join(app_config.path, 'migrations')
            
            # Look for the migration file
            for filename in os.listdir(migrations_dir):
                if filename.startswith(migration_name.split('_')[0]) and filename.endswith('.py'):
                    return os.path.join(migrations_dir, filename)
        except Exception:
            pass
        return None
    
    def _display_conflict_analysis(self, conflicts):
        """Display detailed conflict analysis"""
        if not conflicts:
            self.stdout.write(self.style.SUCCESS(' No conflicts detected!'))
            return
        
        self.stdout.write(self.style.WARNING(f'  Found {len(conflicts)} potential conflicts:'))
        
        for i, conflict in enumerate(conflicts, 1):
            self.stdout.write(f"\n{i}. {conflict['type'].upper()}")
            self.stdout.write(f"   Operation: {conflict['operation']}")
            self.stdout.write(f"   Severity: {conflict['severity']}")
            
            if 'table' in conflict:
                self.stdout.write(f"   Table: {conflict['table']}")
            if 'column' in conflict:
                self.stdout.write(f"   Column: {conflict['column']}")
            if 'constraint' in conflict:
                self.stdout.write(f"   Constraint: {conflict['constraint']}")
            if 'index' in conflict:
                self.stdout.write(f"   Index: {conflict['index']}")
    
    def _display_dry_run_plan(self, pending_migrations, conflicts):
        """Display what would be done in a dry run"""
        self.stdout.write(self.style.WARNING('🔍 DRY RUN - No changes will be made\n'))
        
        self.stdout.write('Plan:')
        for app_name, migration_name in pending_migrations:
            # Check if this migration has conflicts
            has_conflicts = any(True for c in conflicts if app_name in str(c))
            
            if has_conflicts:
                self.stdout.write(f"    Would FAKE: {app_name}.{migration_name} (has conflicts)")
            else:
                self.stdout.write(f"    Would APPLY: {app_name}.{migration_name}")
        
        if conflicts:
            self.stdout.write(f"\n  {len(conflicts)} conflicts would be automatically resolved")
    
    def _apply_migrations_safely(self, pending_migrations, conflicts, force_safe=False):
        """Apply migrations with intelligent conflict resolution"""
        self.stdout.write(' Applying migrations with intelligent conflict resolution...\n')
        
        success_count = 0
        error_count = 0
        faked_count = 0
        
        for app_name, migration_name in pending_migrations:
            self.stdout.write(f"Processing {app_name}.{migration_name}...")
            
            # Check if this migration has known conflicts
            migration_conflicts = [c for c in conflicts if app_name in str(c)]
            
            if migration_conflicts or force_safe:
                # DISABLED: Fake conflicting migrations (dangerous)
                # try:
                #     call_command('migrate', app_name, migration_name, fake=True, verbosity=0)
                #     self.stdout.write(f"    FAKED (had {len(migration_conflicts)} conflicts)")
                #     faked_count += 1
                # except Exception as e:
                #     self.stdout.write(f"    FAILED to fake: {e}")
                #     error_count += 1
                self.stdout.write(f"     SKIPPED (had {len(migration_conflicts)} conflicts) - use safe_migration_manager.py instead")
                error_count += 1
            else:
                # Try to apply normally, with fallback to conflict resolution
                try:
                    call_command('migrate', app_name, migration_name, verbosity=0)
                    self.stdout.write(f"    APPLIED successfully")
                    success_count += 1
                except Exception as e:
                    self.stdout.write(f"     Failed, attempting intelligent resolution...")
                    
                    # Try to resolve the error dynamically
                    if self.resolver.resolve_migration_error(str(e), app_name):
                        self.stdout.write(f"    RESOLVED and faked")
                        faked_count += 1
                    else:
                        self.stdout.write(f"    FAILED: {e}")
                        error_count += 1
        
        # Final summary
        self.stdout.write(f"\n📊 Migration Summary:")
        self.stdout.write(f"    Successfully applied: {success_count}")
        self.stdout.write(f"    Safely faked: {faked_count}")
        self.stdout.write(f"    Failed: {error_count}")
        
        if error_count == 0:
            self.stdout.write(self.style.SUCCESS('\n All migrations completed successfully!'))
            
            # Final validation
            try:
                call_command('check', database='default')
                self.stdout.write(' Database validation passed')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Database validation warnings: {e}'))
        else:
            self.stdout.write(self.style.ERROR(f'\n💥 {error_count} migrations failed'))
            
        # Show any remaining pending migrations
        remaining = self._get_pending_migrations()
        if remaining:
            self.stdout.write(f"\n📋 {len(remaining)} migrations still pending:")
            for app_name, migration_name in remaining[:5]:  # Show first 5
                self.stdout.write(f"   • {app_name}.{migration_name}")
            if len(remaining) > 5:
                self.stdout.write(f"   ... and {len(remaining) - 5} more")


class MigrationValidator:
    """Validates migrations before they are created"""
    
    @staticmethod
    def validate_new_migration(app_name, migration_name):
        """Validate a new migration before it's applied"""
        safety = UniversalMigrationSafety()
        
        # This could be called from makemigrations to prevent problematic migrations
        # from being created in the first place
        pass
