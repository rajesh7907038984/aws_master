"""
Automatic Database Migration Management System
Handles all database changes automatically with safety checks
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection, transaction
from django.conf import settings
from django.apps import apps
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Automatically detect and apply database migrations with safety checks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what migrations would be applied without actually applying them',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force apply migrations even if there are warnings',
        )
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Create database backup before applying migrations',
        )
        parser.add_argument(
            '--app',
            type=str,
            help='Only process migrations for specific app',
        )
        parser.add_argument(
            '--list-pending',
            action='store_true',
            help='List all pending migrations',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 Auto Migration System Starting...'))
        
        # List pending migrations if requested
        if options['list_pending']:
            self.list_pending_migrations(options.get('app'))
            return

        # Create backup if requested
        if options['backup']:
            self.create_database_backup()

        # Detect and apply migrations
        pending_migrations = self.detect_pending_migrations(options.get('app'))
        
        if not pending_migrations:
            self.stdout.write(self.style.SUCCESS('✅ No pending migrations found'))
            return

        self.stdout.write(f'📋 Found {len(pending_migrations)} pending migrations')
        
        # Show migrations that would be applied
        for app_label, migration_name in pending_migrations:
            self.stdout.write(f'  📦 {app_label}: {migration_name}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('🔍 Dry run mode - no migrations applied'))
            return

        # Apply migrations with safety checks
        self.apply_migrations_safely(pending_migrations, options['force'])

    def detect_pending_migrations(self, specific_app=None):
        """Detect all pending migrations"""
        pending = []
        
        try:
            # Get migration executor
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            
            # Get migration plan
            if specific_app:
                targets = [(specific_app, None)]
            else:
                targets = [(app_config.label, None) for app_config in apps.get_app_configs()]
            
            plan = executor.migration_plan(targets)
            
            for migration, backwards in plan:
                if not backwards:  # Only forward migrations
                    pending.append((migration.app_label, migration.name))
                    
        except Exception as e:
            logger.error(f"Error detecting migrations: {e}")
            raise CommandError(f"Failed to detect migrations: {e}")
            
        return pending

    def list_pending_migrations(self, specific_app=None):
        """List all pending migrations with details"""
        self.stdout.write('📋 Pending Migrations:')
        
        pending = self.detect_pending_migrations(specific_app)
        
        if not pending:
            self.stdout.write(self.style.SUCCESS('✅ No pending migrations'))
            return
            
        for app_label, migration_name in pending:
            # Try to get migration details
            migration_path = self.get_migration_file_path(app_label, migration_name)
            if migration_path and migration_path.exists():
                self.stdout.write(f'  📦 {app_label}.{migration_name}')
                self.stdout.write(f'     📄 File: {migration_path}')
                
                # Try to extract operations from migration file
                try:
                    operations = self.extract_migration_operations(migration_path)
                    if operations:
                        self.stdout.write(f'     🔧 Operations: {", ".join(operations)}')
                except:
                    pass
            else:
                self.stdout.write(f'  📦 {app_label}.{migration_name} (file not found)')

    def get_migration_file_path(self, app_label, migration_name):
        """Get the file path for a migration"""
        try:
            app_config = apps.get_app_config(app_label)
            migrations_dir = Path(app_config.path) / 'migrations'
            migration_file = migrations_dir / f'{migration_name}.py'
            return migration_file
        except:
            return None

    def extract_migration_operations(self, migration_path):
        """Extract operations from migration file"""
        operations = []
        try:
            with open(migration_path, 'r') as f:
                content = f.read()
                if 'CreateModel' in content:
                    operations.append('CreateModel')
                if 'AddField' in content:
                    operations.append('AddField')
                if 'RemoveField' in content:
                    operations.append('RemoveField')
                if 'AlterField' in content:
                    operations.append('AlterField')
                if 'DeleteModel' in content:
                    operations.append('DeleteModel')
                if 'RunPython' in content:
                    operations.append('RunPython')
                if 'RunSQL' in content:
                    operations.append('RunSQL')
        except:
            pass
        return operations

    def create_database_backup(self):
        """Create database backup before applying migrations"""
        self.stdout.write('📦 Creating database backup...')
        
        try:
            backup_dir = Path(settings.BASE_DIR) / 'database_backups'
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = backup_dir / f'pre_migration_backup_{timestamp}.json'
            
            # Use Django's dumpdata command
            with open(backup_file, 'w') as f:
                call_command('dumpdata', '--natural-foreign', '--natural-primary', 
                           stdout=f, verbosity=0)
            
            self.stdout.write(self.style.SUCCESS(f'✅ Backup created: {backup_file}'))
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Backup failed: {e}')
            )
            raise CommandError('Backup failed - stopping migration process')

    def apply_migrations_safely(self, pending_migrations, force=False):
        """Apply migrations with safety checks"""
        self.stdout.write('🔧 Applying migrations with safety checks...')
        
        # Group migrations by app
        apps_to_migrate = {}
        for app_label, migration_name in pending_migrations:
            if app_label not in apps_to_migrate:
                apps_to_migrate[app_label] = []
            apps_to_migrate[app_label].append(migration_name)
        
        # Apply migrations app by app
        total_applied = 0
        for app_label, migrations in apps_to_migrate.items():
            self.stdout.write(f'📦 Processing app: {app_label}')
            
            # Check for dangerous operations if not forced
            if not force and self.has_dangerous_operations(app_label, migrations):
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️ App {app_label} has potentially dangerous operations. '
                        f'Use --force to proceed.'
                    )
                )
                continue
            
            try:
                # Apply migrations for this app
                self.stdout.write(f'🔧 Migrating {app_label}...')
                call_command('migrate', app_label, verbosity=1, interactive=False)
                total_applied += len(migrations)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ {app_label} migrations applied successfully')
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Migration failed for {app_label}: {e}')
                )
                
                # Try to continue with other apps
                if force:
                    self.stdout.write('⚠️ Continuing with other apps due to --force flag')
                    continue
                else:
                    raise CommandError(f'Migration failed for {app_label}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'🎉 Applied {total_applied} migrations successfully!')
        )
        
        # Run post-migration checks
        self.run_post_migration_checks()

    def has_dangerous_operations(self, app_label, migrations):
        """Check if migrations contain potentially dangerous operations"""
        dangerous_operations = [
            'DeleteModel',
            'RemoveField',
            'RunSQL'
        ]
        
        for migration_name in migrations:
            migration_path = self.get_migration_file_path(app_label, migration_name)
            if migration_path and migration_path.exists():
                try:
                    with open(migration_path, 'r') as f:
                        content = f.read()
                        for op in dangerous_operations:
                            if op in content:
                                return True
                except:
                    pass
        
        return False

    def run_post_migration_checks(self):
        """Run post-migration health checks"""
        self.stdout.write('🏥 Running post-migration health checks...')
        
        try:
            # Check database connectivity
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result[0] == 1:
                    self.stdout.write(self.style.SUCCESS('✅ Database connectivity OK'))
                else:
                    self.stdout.write(self.style.ERROR('❌ Database connectivity issue'))
            
            # Run Django checks
            try:
                call_command('check', verbosity=0)
                self.stdout.write(self.style.SUCCESS('✅ Django system checks passed'))
            except:
                self.stdout.write(self.style.WARNING('⚠️ Some Django system checks failed'))
            
            # Check for additional pending migrations
            remaining = self.detect_pending_migrations()
            if remaining:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ {len(remaining)} migrations still pending')
                )
            else:
                self.stdout.write(self.style.SUCCESS('✅ All migrations applied'))
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Post-migration check failed: {e}')
            )

    def get_migration_summary(self):
        """Get summary of migration status"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'pending_migrations': len(self.detect_pending_migrations()),
            'apps_with_migrations': [],
            'database_status': 'unknown'
        }
        
        try:
            # Test database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                summary['database_status'] = 'connected'
        except:
            summary['database_status'] = 'error'
        
        # Get apps with pending migrations
        pending = self.detect_pending_migrations()
        apps_with_pending = set(app_label for app_label, _ in pending)
        summary['apps_with_migrations'] = list(apps_with_pending)
        
        return summary
