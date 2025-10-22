"""
Database Schema Dump Command
Dumps complete database schema to JSON for version control and migration safety
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import json
import os
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Dump database schema to JSON file for version control'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', 
            type=str, 
            help='Output file path (default: database_schema/schema_TIMESTAMP.json)'
        )
        parser.add_argument(
            '--baseline', 
            action='store_true',
            help='Create baseline schema file'
        )
        parser.add_argument(
            '--include-data', 
            action='store_true',
            help='Include sample data (first 10 rows per table)'
        )
        parser.add_argument(
            '--include-django-tables',
            action='store_true',
            help='Include Django system tables (django_migrations, etc.)'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'sql'],
            default='json',
            help='Output format (default: json)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🗄️  Starting Database Schema Dump...")
        
        # Create schema directory
        schema_dir = Path('database_schema')
        schema_dir.mkdir(exist_ok=True)
        
        # Determine output file
        if options.get('output'):
            output_file = Path(options['output'])
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            if options.get('baseline'):
                output_file = schema_dir / 'baseline_schema.json'
            else:
                output_file = schema_dir / f'schema_{timestamp}.json'
        
        # Dump schema based on format
        if options['format'] == 'json':
            self.dump_json_schema(output_file, options)
        else:
            self.dump_sql_schema(output_file, options)
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Schema dumped to: {output_file}')
        )

    def dump_json_schema(self, output_file, options):
        """Dump schema as structured JSON"""
        self.stdout.write("📊 Extracting database schema...")
        
        schema_data = {
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'database_engine': connection.settings_dict['ENGINE'],
                'database_name': connection.settings_dict['NAME'],
                'django_version': settings.DJANGO_VERSION if hasattr(settings, 'DJANGO_VERSION') else 'Unknown',
                'baseline': options.get('baseline', False)
            },
            'tables': {},
            'indexes': {},
            'constraints': {},
            'functions': {},
            'triggers': {},
            'views': {},
            'sample_data': {} if options.get('include_data') else None
        }
        
        with connection.cursor() as cursor:
            # Get all tables and their structure
            self.stdout.write("📋 Extracting table structures...")
            schema_data['tables'] = self._extract_table_structures(cursor, options)
            
            # Get indexes
            self.stdout.write("📇 Extracting indexes...")
            schema_data['indexes'] = self._extract_indexes(cursor)
            
            # Get constraints
            self.stdout.write("🔗 Extracting constraints...")
            schema_data['constraints'] = self._extract_constraints(cursor)
            
            # Get views
            self.stdout.write("👁️  Extracting views...")
            schema_data['views'] = self._extract_views(cursor)
            
            # Get functions and triggers (PostgreSQL specific)
            if 'postgresql' in connection.settings_dict['ENGINE']:
                self.stdout.write("⚙️  Extracting functions and triggers...")
                schema_data['functions'] = self._extract_functions(cursor)
                schema_data['triggers'] = self._extract_triggers(cursor)
            
            # Get sample data if requested
            if options.get('include_data'):
                self.stdout.write("📊 Extracting sample data...")
                schema_data['sample_data'] = self._extract_sample_data(cursor, options)
        
        # Write to file
        with open(output_file, 'w') as f:
            json.dump(schema_data, f, indent=2, default=str)
        
        self.stdout.write(f"📄 Schema written to: {output_file}")
        self._display_schema_summary(schema_data)

    def dump_sql_schema(self, output_file, options):
        """Dump schema as SQL DDL"""
        self.stdout.write("📊 Extracting SQL schema...")
        
        with connection.cursor() as cursor:
            # Get table creation SQL
            if 'postgresql' in connection.settings_dict['ENGINE']:
                cursor.execute("""
                    SELECT 
                        'CREATE TABLE ' || schemaname || '.' || tablename || ' (' ||
                        string_agg(
                            column_name || ' ' || 
                            CASE 
                                WHEN data_type = 'character varying' THEN 'VARCHAR(' || character_maximum_length || ')'
                                WHEN data_type = 'character' THEN 'CHAR(' || character_maximum_length || ')'
                                WHEN data_type = 'numeric' THEN 'NUMERIC(' || numeric_precision || ',' || numeric_scale || ')'
                                ELSE UPPER(data_type)
                            END ||
                            CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
                            CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END,
                            ', '
                        ) || ');'
                    FROM information_schema.columns c
                    WHERE table_schema = 'public'
                    GROUP BY schemaname, tablename
                    ORDER BY tablename
                """)
                
                with open(output_file, 'w') as f:
                    f.write("-- Database Schema Dump\n")
                    f.write(f"-- Generated: {datetime.now().isoformat()}\n")
                    f.write(f"-- Database: {connection.settings_dict['NAME']}\n\n")
                    
                    for row in cursor.fetchall():
                        f.write(row[0] + '\n\n')

    def _extract_table_structures(self, cursor, options):
        """Extract table structures from database"""
        tables = {}
        
        # Build query based on database engine
        if 'postgresql' in connection.settings_dict['ENGINE']:
            query = """
                SELECT 
                    table_name, column_name, data_type, is_nullable, 
                    column_default, character_maximum_length, numeric_precision, 
                    numeric_scale, ordinal_position
                FROM information_schema.columns 
                WHERE table_schema = 'public'
            """
            
            if not options.get('include_django_tables'):
                query += " AND table_name NOT LIKE 'django_%' AND table_name NOT LIKE 'auth_%'"
            
            query += " ORDER BY table_name, ordinal_position"
            
        elif 'sqlite' in connection.settings_dict['ENGINE']:
            query = """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
            if not options.get('include_django_tables'):
                query += " AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'"
        else:  # MySQL
            query = "SHOW TABLES"
        
        cursor.execute(query)
        
        if 'postgresql' in connection.settings_dict['ENGINE']:
            for row in cursor.fetchall():
                table_name, column_name, data_type, is_nullable, default, max_length, precision, scale, position = row
                
                if table_name not in tables:
                    tables[table_name] = {}
                
                column_info = {
                    'type': data_type,
                    'nullable': is_nullable == 'YES',
                    'default': default,
                    'position': position
                }
                
                if max_length:
                    column_info['max_length'] = max_length
                if precision:
                    column_info['precision'] = precision
                if scale:
                    column_info['scale'] = scale
                
                tables[table_name][column_name] = column_info
        
        return tables

    def _extract_indexes(self, cursor):
        """Extract database indexes"""
        indexes = {}
        
        if 'postgresql' in connection.settings_dict['ENGINE']:
            cursor.execute("""
                SELECT 
                    tablename, indexname, indexdef
                FROM pg_indexes 
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """)
            
            for table_name, index_name, index_def in cursor.fetchall():
                if table_name not in indexes:
                    indexes[table_name] = []
                
                indexes[table_name].append({
                    'name': index_name,
                    'definition': index_def
                })
        
        return indexes

    def _extract_constraints(self, cursor):
        """Extract database constraints"""
        constraints = {}
        
        if 'postgresql' in connection.settings_dict['ENGINE']:
            cursor.execute("""
                SELECT 
                    tc.table_name, tc.constraint_name, tc.constraint_type,
                    kcu.column_name, ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_schema = 'public'
                ORDER BY tc.table_name, tc.constraint_name
            """)
            
            for row in cursor.fetchall():
                table_name, constraint_name, constraint_type, column_name, foreign_table, foreign_column = row
                
                if table_name not in constraints:
                    constraints[table_name] = []
                
                constraint_info = {
                    'name': constraint_name,
                    'type': constraint_type,
                    'column': column_name
                }
                
                if foreign_table:
                    constraint_info['foreign_table'] = foreign_table
                    constraint_info['foreign_column'] = foreign_column
                
                constraints[table_name].append(constraint_info)
        
        return constraints

    def _extract_views(self, cursor):
        """Extract database views"""
        views = {}
        
        if 'postgresql' in connection.settings_dict['ENGINE']:
            cursor.execute("""
                SELECT 
                    table_name, view_definition
                FROM information_schema.views 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            for view_name, definition in cursor.fetchall():
                views[view_name] = {
                    'definition': definition
                }
        
        return views

    def _extract_functions(self, cursor):
        """Extract database functions (PostgreSQL)"""
        functions = {}
        
        cursor.execute("""
            SELECT 
                routine_name, routine_definition, data_type
            FROM information_schema.routines 
            WHERE routine_schema = 'public'
            ORDER BY routine_name
        """)
        
        for func_name, definition, return_type in cursor.fetchall():
            functions[func_name] = {
                'definition': definition,
                'return_type': return_type
            }
        
        return functions

    def _extract_triggers(self, cursor):
        """Extract database triggers (PostgreSQL)"""
        triggers = {}
        
        cursor.execute("""
            SELECT 
                trigger_name, event_manipulation, event_object_table,
                action_statement, action_timing
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public'
            ORDER BY event_object_table, trigger_name
        """)
        
        for trigger_name, event, table_name, statement, timing in cursor.fetchall():
            if table_name not in triggers:
                triggers[table_name] = []
            
            triggers[table_name].append({
                'name': trigger_name,
                'event': event,
                'statement': statement,
                'timing': timing
            })
        
        return triggers

    def _extract_sample_data(self, cursor, options):
        """Extract sample data from tables"""
        sample_data = {}
        
        # Get all tables
        if 'postgresql' in connection.settings_dict['ENGINE']:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """)
        else:
            cursor.execute("SHOW TABLES")
        
        tables = [row[0] for row in cursor.fetchall()]
        
        for table_name in tables[:10]:  # Limit to first 10 tables for performance
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                
                sample_data[table_name] = {
                    'columns': columns,
                    'rows': [dict(zip(columns, row)) for row in rows]
                }
            except Exception as e:
                logger.warning(f"Could not extract sample data from {table_name}: {e}")
        
        return sample_data

    def _display_schema_summary(self, schema_data):
        """Display summary of extracted schema"""
        self.stdout.write("\n📊 Schema Summary:")
        self.stdout.write(f"   • Tables: {len(schema_data['tables'])}")
        self.stdout.write(f"   • Indexes: {sum(len(indexes) for indexes in schema_data['indexes'].values())}")
        self.stdout.write(f"   • Constraints: {sum(len(constraints) for constraints in schema_data['constraints'].values())}")
        self.stdout.write(f"   • Views: {len(schema_data['views'])}")
        
        if schema_data.get('sample_data'):
            self.stdout.write(f"   • Sample Data: {len(schema_data['sample_data'])} tables")
        
        if schema_data.get('functions'):
            self.stdout.write(f"   • Functions: {len(schema_data['functions'])}")
        
        if schema_data.get('triggers'):
            self.stdout.write(f"   • Triggers: {sum(len(triggers) for triggers in schema_data['triggers'].values())}")
