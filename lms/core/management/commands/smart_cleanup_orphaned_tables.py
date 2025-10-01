from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
import json
import os


class Command(BaseCommand):
    help = 'Intelligently clean up truly orphaned database tables (checks for model references)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion of orphaned tables',
        )

    def handle(self, *args, **options):
        self.stdout.write('🧹 Starting intelligent orphaned table cleanup...')
        
        # Get all database tables
        cursor = connection.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema='public' AND table_type='BASE TABLE'
        """)
        all_db_tables = {row[0] for row in cursor.fetchall()}
        
        # Get all Django model tables
        django_tables = set()
        model_m2m_tables = set()
        
        for model in apps.get_models():
            # Add main model table
            django_tables.add(model._meta.db_table)
            
            # Add many-to-many intermediate tables
            for field in model._meta.get_fields():
                if field.many_to_many and hasattr(field, 'remote_field'):
                    if hasattr(field.remote_field, 'through'):
                        m2m_table = field.remote_field.through._meta.db_table
                        model_m2m_tables.add(m2m_table)
                        django_tables.add(m2m_table)
        
        # Find truly orphaned tables (in database but not referenced by any model)
        orphaned_tables = all_db_tables - django_tables
        
        # Remove Django system tables from orphaned list
        system_tables = {
            'django_migrations', 'django_content_type', 'django_session',
            'django_admin_log', 'auth_group', 'auth_permission', 
            'auth_group_permissions', 'django_site'
        }
        orphaned_tables = orphaned_tables - system_tables
        
        if not orphaned_tables:
            self.stdout.write(
                self.style.SUCCESS('🎉 No truly orphaned tables found!')
            )
            return
        
        # Check if orphaned tables are empty
        safe_to_drop = []
        has_data = []
        
        for table_name in orphaned_tables:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                row_count = cursor.fetchone()[0]
                
                if row_count == 0:
                    safe_to_drop.append(table_name)
                    self.stdout.write(f'✅ {table_name}: Empty orphaned table, safe to drop')
                else:
                    has_data.append(table_name)
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ {table_name}: Contains {row_count} rows, needs review')
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error checking {table_name}: {e}')
                )
        
        # Show analysis results
        self.stdout.write('\n📊 Analysis Results:')
        self.stdout.write(f'  📋 Total database tables: {len(all_db_tables)}')
        self.stdout.write(f'  🏷️ Django model tables: {len(django_tables)}')
        self.stdout.write(f'  🔗 Many-to-many tables: {len(model_m2m_tables)}')
        self.stdout.write(f'  🏝️ Truly orphaned tables: {len(orphaned_tables)}')
        self.stdout.write(f'  ✅ Safe to drop (empty): {len(safe_to_drop)}')
        self.stdout.write(f'  ⚠️ Has data (needs review): {len(has_data)}')
        
        if safe_to_drop:
            self.stdout.write(f'\n📋 Safe to drop (empty orphaned tables):')
            for table in safe_to_drop:
                self.stdout.write(f'  - {table}')
        
        if has_data:
            self.stdout.write(f'\n⚠️ Tables with data (manual review needed):')
            for table in has_data:
                self.stdout.write(f'  - {table}')
        
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING('\n🔍 DRY RUN: No changes made. Use --confirm to actually drop tables.')
            )
            return
        
        if not safe_to_drop:
            self.stdout.write(
                self.style.SUCCESS('\n🎉 No safe tables to drop!')
            )
            return
        
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING('\n⚠️ Use --confirm flag to proceed with deletion')
            )
            return
        
        # Drop only the safe tables
        dropped_count = 0
        for table_name in safe_to_drop:
            try:
                cursor.execute(f'DROP TABLE "{table_name}" CASCADE')
                self.stdout.write(f'🗑️ Dropped table: {table_name}')
                dropped_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to drop {table_name}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n🎉 Successfully dropped {dropped_count} truly orphaned tables!')
        )
        
        if has_data:
            self.stdout.write(
                self.style.WARNING(f'\n💡 {len(has_data)} tables with data were preserved for manual review.')
            )
