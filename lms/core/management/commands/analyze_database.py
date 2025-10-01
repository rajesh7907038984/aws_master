"""
Comprehensive Database Analysis - Find Old/Unused Tables and Columns
This command analyzes your LMS database to identify:
1. Tables that don't correspond to any Django models
2. Columns in tables that don't correspond to model fields
3. Old migration artifacts
4. Orphaned indexes and constraints
5. Comparison with baseline schema
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.contrib.auth import get_user_model
import json
import os
from pathlib import Path

class Command(BaseCommand):
    help = 'Analyze database for old, non-usable tables and columns'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export-json',
            action='store_true',
            help='Export findings to JSON file',
        )
        parser.add_argument(
            '--include-django-tables',
            action='store_true',
            help='Include Django system tables in analysis',
        )
        parser.add_argument(
            '--check-baseline',
            action='store_true',
            help='Compare against baseline schema',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be analyzed without making changes',
        )

    def handle(self, *args, **options):
        self.export_json = options.get('export_json', False)
        self.include_django = options.get('include_django_tables', False)
        self.check_baseline = options.get('check_baseline', False)
        self.dry_run = options.get('dry_run', False)
        
        self.stdout.write("🔍 Comprehensive Database Analysis Starting...")
        self.stdout.write("=" * 60)
        
        # Initialize analysis results
        self.analysis_results = {
            'orphaned_tables': [],
            'orphaned_columns': [],
            'missing_model_tables': [],
            'unknown_indexes': [],
            'baseline_differences': [],
            'migration_artifacts': [],
            'recommendations': []
        }
        
        # Perform analysis steps
        self.analyze_database_tables()
        self.analyze_table_columns()
        self.analyze_indexes()
        self.check_migration_artifacts()
        
        if self.check_baseline:
            self.compare_with_baseline()
        
        # Generate recommendations
        self.generate_recommendations()
        
        # Display results
        self.display_results()
        
        # Export if requested
        if self.export_json:
            self.export_to_json()

    def get_all_django_models(self):
        """Get all Django models and their table information"""
        models_info = {}
        
        for app in apps.get_app_configs():
            if not self.include_django and app.label in ['admin', 'auth', 'contenttypes', 'sessions']:
                continue
                
            for model in app.get_models():
                table_name = model._meta.db_table
                models_info[table_name] = {
                    'app': app.label,
                    'model': model.__name__,
                    'fields': {field.name: {
                        'column': field.column,
                        'type': field.__class__.__name__,
                        'null': field.null,
                        'related_model': field.related_model.__name__ if hasattr(field, 'related_model') and field.related_model else None
                    } for field in model._meta.fields},
                    'many_to_many': {field.name: {
                        'through': field.remote_field.through._meta.db_table if hasattr(field.remote_field, 'through') and hasattr(field.remote_field.through, '_meta') else None,
                        'related_model': field.related_model.__name__
                    } for field in model._meta.many_to_many}
                }
        
        return models_info

    def get_database_tables(self):
        """Get all tables from the database"""
        with connection.cursor() as cursor:
            if 'sqlite' in connection.settings_dict['ENGINE']:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in cursor.fetchall()]
            elif 'postgresql' in connection.settings_dict['ENGINE']:
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public'
                """)
                tables = [row[0] for row in cursor.fetchall()]
            else:  # MySQL
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
        
        return tables

    def get_table_columns(self, table_name):
        """Get columns for a specific table"""
        with connection.cursor() as cursor:
            if 'sqlite' in connection.settings_dict['ENGINE']:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = {row[1]: {
                    'type': row[2],
                    'nullable': not row[3],
                    'default': row[4],
                    'primary_key': bool(row[5])
                } for row in cursor.fetchall()}
            elif 'postgresql' in connection.settings_dict['ENGINE']:
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                """, [table_name])
                columns = {row[0]: {
                    'type': row[1],
                    'nullable': row[2] == 'YES',
                    'default': row[3],
                    'primary_key': False  # Would need additional query
                } for row in cursor.fetchall()}
            else:  # MySQL
                cursor.execute(f"DESCRIBE {table_name}")
                columns = {row[0]: {
                    'type': row[1],
                    'nullable': row[2] == 'YES',
                    'default': row[4],
                    'primary_key': row[3] == 'PRI'
                } for row in cursor.fetchall()}
        
        return columns

    def analyze_database_tables(self):
        """Find tables that don't correspond to Django models"""
        self.stdout.write("\n📊 Analyzing Database Tables...")
        
        # Get Django models and database tables
        django_models = self.get_all_django_models()
        database_tables = self.get_database_tables()
        
        # Expected Django system tables
        django_system_tables = {
            'django_migrations', 'django_content_type', 'django_session',
            'auth_permission', 'auth_group', 'auth_group_permissions',
            'auth_user_groups', 'auth_user_user_permissions', 'django_admin_log',
            'django_site'
        }
        
        model_tables = set(django_models.keys())
        db_tables = set(database_tables)
        
        # Find orphaned tables (in DB but not in models)
        orphaned = db_tables - model_tables
        if not self.include_django:
            orphaned = orphaned - django_system_tables
        
        # Find missing tables (in models but not in DB)
        missing = model_tables - db_tables
        
        self.analysis_results['orphaned_tables'] = list(orphaned)
        self.analysis_results['missing_model_tables'] = list(missing)
        
        self.stdout.write(f"✅ Found {len(db_tables)} database tables")
        self.stdout.write(f"✅ Found {len(model_tables)} Django model tables")
        self.stdout.write(f"⚠️  Found {len(orphaned)} orphaned tables")
        self.stdout.write(f"❌ Found {len(missing)} missing model tables")
        
        if orphaned:
            self.stdout.write("\n🗑️  Orphaned Tables (exist in DB but not in models):")
            for table in sorted(orphaned):
                row_count = self.get_table_row_count(table)
                self.stdout.write(f"   • {table} ({row_count} rows)")
        
        if missing:
            self.stdout.write("\n⚠️  Missing Tables (defined in models but not in DB):")
            for table in sorted(missing):
                self.stdout.write(f"   • {table}")

    def analyze_table_columns(self):
        """Find columns that don't correspond to model fields"""
        self.stdout.write("\n📋 Analyzing Table Columns...")
        
        django_models = self.get_all_django_models()
        orphaned_columns = []
        
        for table_name, model_info in django_models.items():
            try:
                db_columns = self.get_table_columns(table_name)
                model_columns = set()
                
                # Add field columns
                for field_name, field_info in model_info['fields'].items():
                    model_columns.add(field_info['column'])
                
                # Add M2M through table columns (if this is a through table)
                for m2m_field in model_info['many_to_many'].values():
                    if m2m_field['through'] and m2m_field['through'] == table_name:
                        model_columns.update(['id', 'from_' + table_name.split('_')[0] + '_id', 
                                            'to_' + m2m_field['related_model'].lower() + '_id'])
                
                # Find orphaned columns
                db_column_names = set(db_columns.keys())
                orphaned = db_column_names - model_columns
                
                # Remove common Django columns that might not be in model fields
                orphaned.discard('id')  # Primary key
                
                if orphaned:
                    for col in orphaned:
                        orphaned_columns.append({
                            'table': table_name,
                            'column': col,
                            'type': db_columns[col]['type'],
                            'nullable': db_columns[col]['nullable']
                        })
                        
            except Exception as e:
                self.stdout.write(f"⚠️  Error analyzing {table_name}: {e}")
        
        self.analysis_results['orphaned_columns'] = orphaned_columns
        
        if orphaned_columns:
            self.stdout.write(f"\n🗑️  Found {len(orphaned_columns)} orphaned columns:")
            for col_info in orphaned_columns:
                self.stdout.write(f"   • {col_info['table']}.{col_info['column']} ({col_info['type']})")

    def analyze_indexes(self):
        """Find potentially orphaned indexes"""
        self.stdout.write("\n📇 Analyzing Database Indexes...")
        
        unknown_indexes = []
        
        with connection.cursor() as cursor:
            try:
                if 'postgresql' in connection.settings_dict['ENGINE']:
                    cursor.execute("""
                        SELECT indexname, tablename 
                        FROM pg_indexes 
                        WHERE schemaname = 'public'
                        AND indexname NOT LIKE '%_pkey'
                        AND indexname NOT LIKE 'auth_%'
                        AND indexname NOT LIKE 'django_%'
                    """)
                    indexes = cursor.fetchall()
                elif 'sqlite' in connection.settings_dict['ENGINE']:
                    cursor.execute("""
                        SELECT name, tbl_name 
                        FROM sqlite_master 
                        WHERE type = 'index' 
                        AND name NOT LIKE 'sqlite_%'
                        AND name NOT LIKE 'auth_%'
                        AND name NOT LIKE 'django_%'
                    """)
                    indexes = cursor.fetchall()
                
                for index_name, table_name in indexes:
                    unknown_indexes.append({
                        'index': index_name,
                        'table': table_name
                    })
                    
            except Exception as e:
                self.stdout.write(f"⚠️  Error analyzing indexes: {e}")
        
        self.analysis_results['unknown_indexes'] = unknown_indexes
        self.stdout.write(f"📇 Found {len(unknown_indexes)} custom indexes")

    def check_migration_artifacts(self):
        """Check for potential migration artifacts"""
        self.stdout.write("\n🔄 Checking Migration Artifacts...")
        
        artifacts = []
        
        # Check for backup tables (common pattern: table_name_old, table_name_backup)
        database_tables = self.get_database_tables()
        
        for table in database_tables:
            if (table.endswith('_old') or table.endswith('_backup') or 
                table.endswith('_temp') or table.startswith('backup_')):
                row_count = self.get_table_row_count(table)
                artifacts.append({
                    'table': table,
                    'type': 'backup_table',
                    'rows': row_count
                })
        
        self.analysis_results['migration_artifacts'] = artifacts
        
        if artifacts:
            self.stdout.write(f"🗑️  Found {len(artifacts)} potential migration artifacts:")
            for artifact in artifacts:
                self.stdout.write(f"   • {artifact['table']} ({artifact['rows']} rows)")

    def compare_with_baseline(self):
        """Compare current schema with baseline"""
        self.stdout.write("\n📊 Comparing with Baseline Schema...")
        
        baseline_path = Path(__file__).parent.parent.parent.parent / 'schema_baselines' / 'baseline_schema.json'
        
        if not baseline_path.exists():
            self.stdout.write("⚠️  Baseline schema file not found")
            return
        
        try:
            with open(baseline_path, 'r') as f:
                baseline = json.load(f)
            
            # Compare tables
            baseline_tables = set(baseline.get('tables', {}).keys())
            current_tables = set(self.get_database_tables())
            
            extra_tables = current_tables - baseline_tables
            missing_tables = baseline_tables - current_tables
            
            differences = []
            
            if extra_tables:
                differences.extend([{'type': 'extra_table', 'name': table} for table in extra_tables])
            
            if missing_tables:
                differences.extend([{'type': 'missing_table', 'name': table} for table in missing_tables])
            
            self.analysis_results['baseline_differences'] = differences
            
            if differences:
                self.stdout.write(f"📊 Found {len(differences)} differences from baseline:")
                for diff in differences:
                    self.stdout.write(f"   • {diff['type']}: {diff['name']}")
            else:
                self.stdout.write("✅ Database matches baseline schema")
                
        except Exception as e:
            self.stdout.write(f"❌ Error comparing with baseline: {e}")

    def get_table_row_count(self, table_name):
        """Get row count for a table"""
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}")
                return cursor.fetchone()[0]
        except:
            return "Unknown"

    def generate_recommendations(self):
        """Generate cleanup recommendations"""
        recommendations = []
        
        # Orphaned tables recommendations
        if self.analysis_results['orphaned_tables']:
            for table in self.analysis_results['orphaned_tables']:
                row_count = self.get_table_row_count(table)
                if row_count == 0 or row_count == "Unknown":
                    recommendations.append({
                        'priority': 'HIGH',
                        'action': f"DROP TABLE {table}",
                        'reason': f"Empty orphaned table with no corresponding model",
                        'risk': 'LOW'
                    })
                else:
                    recommendations.append({
                        'priority': 'MEDIUM',
                        'action': f"BACKUP and consider dropping {table}",
                        'reason': f"Orphaned table with {row_count} rows",
                        'risk': 'MEDIUM'
                    })
        
        # Orphaned columns recommendations
        if self.analysis_results['orphaned_columns']:
            for col in self.analysis_results['orphaned_columns']:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'action': f"Consider dropping column {col['table']}.{col['column']}",
                    'reason': "Column doesn't exist in model definition",
                    'risk': 'MEDIUM'
                })
        
        # Migration artifacts
        if self.analysis_results['migration_artifacts']:
            for artifact in self.analysis_results['migration_artifacts']:
                recommendations.append({
                    'priority': 'HIGH',
                    'action': f"DROP TABLE {artifact['table']}",
                    'reason': "Migration artifact table",
                    'risk': 'LOW'
                })
        
        self.analysis_results['recommendations'] = recommendations

    def display_results(self):
        """Display comprehensive analysis results"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("📋 COMPREHENSIVE DATABASE ANALYSIS RESULTS")
        self.stdout.write("="*60)
        
        total_issues = (len(self.analysis_results['orphaned_tables']) + 
                       len(self.analysis_results['orphaned_columns']) + 
                       len(self.analysis_results['migration_artifacts']))
        
        if total_issues == 0:
            self.stdout.write(self.style.SUCCESS("✅ No database cleanup issues found!"))
            return
        
        self.stdout.write(f"⚠️  Found {total_issues} potential cleanup items")
        
        # Summary
        self.stdout.write(f"\n📊 Summary:")
        self.stdout.write(f"   • Orphaned Tables: {len(self.analysis_results['orphaned_tables'])}")
        self.stdout.write(f"   • Orphaned Columns: {len(self.analysis_results['orphaned_columns'])}")
        self.stdout.write(f"   • Migration Artifacts: {len(self.analysis_results['migration_artifacts'])}")
        self.stdout.write(f"   • Missing Model Tables: {len(self.analysis_results['missing_model_tables'])}")
        
        # Recommendations
        if self.analysis_results['recommendations']:
            self.stdout.write(f"\n🎯 Recommended Actions:")
            high_priority = [r for r in self.analysis_results['recommendations'] if r['priority'] == 'HIGH']
            medium_priority = [r for r in self.analysis_results['recommendations'] if r['priority'] == 'MEDIUM']
            
            if high_priority:
                self.stdout.write(f"\n🔴 HIGH PRIORITY ({len(high_priority)} items):")
                for rec in high_priority:
                    self.stdout.write(f"   • {rec['action']}")
                    self.stdout.write(f"     Reason: {rec['reason']} (Risk: {rec['risk']})")
            
            if medium_priority:
                self.stdout.write(f"\n🟡 MEDIUM PRIORITY ({len(medium_priority)} items):")
                for rec in medium_priority:
                    self.stdout.write(f"   • {rec['action']}")
                    self.stdout.write(f"     Reason: {rec['reason']} (Risk: {rec['risk']})")

    def export_to_json(self):
        """Export analysis results to JSON"""
        output_file = 'database_analysis_results.json'
        
        try:
            with open(output_file, 'w') as f:
                json.dump(self.analysis_results, f, indent=2, default=str)
            
            self.stdout.write(f"\n📄 Analysis results exported to {output_file}")
        except Exception as e:
            self.stdout.write(f"❌ Error exporting results: {e}")
