"""
Database Schema Comparison Command
Compares current database schema with baseline or other schema files
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import json
import os
from datetime import datetime
from pathlib import Path
import logging
from typing import Dict, List, Any, Set

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Compare current database schema with baseline or other schema files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--baseline', 
            type=str, 
            required=True,
            help='Baseline schema file path'
        )
        parser.add_argument(
            '--current',
            type=str,
            help='Current schema file path (if not provided, will dump current schema)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for comparison results'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'text', 'html'],
            default='text',
            help='Output format (default: text)'
        )
        parser.add_argument(
            '--include-django-tables',
            action='store_true',
            help='Include Django system tables in comparison'
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Strict mode - fail on any differences'
        )
        parser.add_argument(
            '--ignore-indexes',
            action='store_true',
            help='Ignore index differences'
        )
        parser.add_argument(
            '--ignore-constraints',
            action='store_true',
            help='Ignore constraint differences'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔍 Starting Schema Comparison...")
        
        # Load baseline schema
        baseline_file = Path(options['baseline'])
        if not baseline_file.exists():
            self.stdout.write(
                self.style.ERROR(f'❌ Baseline schema file not found: {baseline_file}')
            )
            return
        
        self.stdout.write(f"📄 Loading baseline schema from: {baseline_file}")
        baseline_schema = self._load_schema_file(baseline_file)
        
        # Get current schema
        if options.get('current'):
            current_file = Path(options['current'])
            if not current_file.exists():
                self.stdout.write(
                    self.style.ERROR(f'❌ Current schema file not found: {current_file}')
                )
                return
            self.stdout.write(f"📄 Loading current schema from: {current_file}")
            current_schema = self._load_schema_file(current_file)
        else:
            self.stdout.write("📊 Dumping current database schema...")
            current_schema = self._dump_current_schema(options)
        
        # Compare schemas
        self.stdout.write("🔍 Comparing schemas...")
        comparison_result = self._compare_schemas(
            baseline_schema, 
            current_schema, 
            options
        )
        
        # Display results
        self._display_comparison_results(comparison_result, options)
        
        # Save results if requested
        if options.get('output'):
            self._save_comparison_results(comparison_result, options)
        
        # Exit with error if strict mode and differences found
        if options.get('strict') and comparison_result['has_differences']:
            self.stdout.write(
                self.style.ERROR("❌ Schema differences found in strict mode")
            )
            exit(1)

    def _load_schema_file(self, file_path: Path) -> Dict[str, Any]:
        """Load schema from JSON file"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error loading schema file: {e}')
            )
            return {}

    def _dump_current_schema(self, options) -> Dict[str, Any]:
        """Dump current database schema"""
        from .dump_schema import Command as DumpSchemaCommand
        
        # Create temporary schema dump
        temp_file = Path('temp_current_schema.json')
        
        # Use the dump_schema command to get current schema
        dump_command = DumpSchemaCommand()
        dump_command.handle(
            output=str(temp_file),
            include_django_tables=options.get('include_django_tables', False),
            format='json'
        )
        
        # Load the dumped schema
        current_schema = self._load_schema_file(temp_file)
        
        # Clean up temp file
        if temp_file.exists():
            temp_file.unlink()
        
        return current_schema

    def _compare_schemas(self, baseline: Dict[str, Any], current: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two schemas and return differences"""
        comparison = {
            'baseline_file': str(options['baseline']),
            'current_file': options.get('current', 'current_database'),
            'compared_at': datetime.now().isoformat(),
            'has_differences': False,
            'differences': {
                'tables': {
                    'added': [],
                    'removed': [],
                    'modified': []
                },
                'columns': {
                    'added': [],
                    'removed': [],
                    'modified': []
                },
                'indexes': {
                    'added': [],
                    'removed': [],
                    'modified': []
                },
                'constraints': {
                    'added': [],
                    'removed': [],
                    'modified': []
                }
            },
            'summary': {
                'total_tables_baseline': 0,
                'total_tables_current': 0,
                'total_differences': 0
            }
        }
        
        # Compare tables
        baseline_tables = set(baseline.get('tables', {}).keys())
        current_tables = set(current.get('tables', {}).keys())
        
        comparison['summary']['total_tables_baseline'] = len(baseline_tables)
        comparison['summary']['total_tables_current'] = len(current_tables)
        
        # Find table differences
        added_tables = current_tables - baseline_tables
        removed_tables = baseline_tables - current_tables
        common_tables = baseline_tables & current_tables
        
        comparison['differences']['tables']['added'] = list(added_tables)
        comparison['differences']['tables']['removed'] = list(removed_tables)
        
        # Compare common tables
        for table_name in common_tables:
            table_differences = self._compare_table_structures(
                baseline['tables'][table_name],
                current['tables'][table_name],
                table_name,
                options
            )
            
            if table_differences:
                comparison['differences']['tables']['modified'].append({
                    'table': table_name,
                    'changes': table_differences
                })
        
        # Compare indexes if not ignored
        if not options.get('ignore_indexes'):
            self._compare_indexes(baseline, current, comparison)
        
        # Compare constraints if not ignored
        if not options.get('ignore_constraints'):
            self._compare_constraints(baseline, current, comparison)
        
        # Calculate total differences
        total_diffs = (
            len(comparison['differences']['tables']['added']) +
            len(comparison['differences']['tables']['removed']) +
            len(comparison['differences']['tables']['modified']) +
            len(comparison['differences']['columns']['added']) +
            len(comparison['differences']['columns']['removed']) +
            len(comparison['differences']['columns']['modified']) +
            len(comparison['differences']['indexes']['added']) +
            len(comparison['differences']['indexes']['removed']) +
            len(comparison['differences']['indexes']['modified']) +
            len(comparison['differences']['constraints']['added']) +
            len(comparison['differences']['constraints']['removed']) +
            len(comparison['differences']['constraints']['modified'])
        )
        
        comparison['summary']['total_differences'] = total_diffs
        comparison['has_differences'] = total_diffs > 0
        
        return comparison

    def _compare_table_structures(self, baseline_table: Dict[str, Any], current_table: Dict[str, Any], table_name: str, options: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compare table structures and return differences"""
        differences = []
        
        baseline_columns = set(baseline_table.keys())
        current_columns = set(current_table.keys())
        
        # Find column differences
        added_columns = current_columns - baseline_columns
        removed_columns = baseline_columns - current_columns
        common_columns = baseline_columns & current_columns
        
        # Add column differences to global comparison
        for col in added_columns:
            comparison['differences']['columns']['added'].append({
                'table': table_name,
                'column': col,
                'type': current_table[col].get('type', 'unknown')
            })
        
        for col in removed_columns:
            comparison['differences']['columns']['removed'].append({
                'table': table_name,
                'column': col,
                'type': baseline_table[col].get('type', 'unknown')
            })
        
        # Compare common columns
        for column_name in common_columns:
            baseline_col = baseline_table[column_name]
            current_col = current_table[column_name]
            
            col_differences = []
            
            # Compare column properties
            for prop in ['type', 'nullable', 'default', 'max_length', 'precision', 'scale']:
                if baseline_col.get(prop) != current_col.get(prop):
                    col_differences.append({
                        'property': prop,
                        'baseline': baseline_col.get(prop),
                        'current': current_col.get(prop)
                    })
            
            if col_differences:
                differences.append({
                    'column': column_name,
                    'changes': col_differences
                })
                
                comparison['differences']['columns']['modified'].append({
                    'table': table_name,
                    'column': column_name,
                    'changes': col_differences
                })
        
        return differences

    def _compare_indexes(self, baseline: Dict[str, Any], current: Dict[str, Any], comparison: Dict[str, Any]):
        """Compare indexes between schemas"""
        baseline_indexes = baseline.get('indexes', {})
        current_indexes = current.get('indexes', {})
        
        # Get all index names
        baseline_index_names = set()
        current_index_names = set()
        
        for table_indexes in baseline_indexes.values():
            for idx in table_indexes:
                baseline_index_names.add(idx['name'])
        
        for table_indexes in current_indexes.values():
            for idx in table_indexes:
                current_index_names.add(idx['name'])
        
        # Find differences
        added_indexes = current_index_names - baseline_index_names
        removed_indexes = baseline_index_names - current_index_names
        
        comparison['differences']['indexes']['added'] = list(added_indexes)
        comparison['differences']['indexes']['removed'] = list(removed_indexes)

    def _compare_constraints(self, baseline: Dict[str, Any], current: Dict[str, Any], comparison: Dict[str, Any]):
        """Compare constraints between schemas"""
        baseline_constraints = baseline.get('constraints', {})
        current_constraints = current.get('constraints', {})
        
        # Get all constraint names
        baseline_constraint_names = set()
        current_constraint_names = set()
        
        for table_constraints in baseline_constraints.values():
            for constraint in table_constraints:
                baseline_constraint_names.add(constraint['name'])
        
        for table_constraints in current_constraints.values():
            for constraint in table_constraints:
                current_constraint_names.add(constraint['name'])
        
        # Find differences
        added_constraints = current_constraint_names - baseline_constraint_names
        removed_constraints = baseline_constraint_names - current_constraint_names
        
        comparison['differences']['constraints']['added'] = list(added_constraints)
        comparison['differences']['constraints']['removed'] = list(removed_constraints)

    def _display_comparison_results(self, comparison: Dict[str, Any], options: Dict[str, Any]):
        """Display comparison results in the specified format"""
        if options['format'] == 'text':
            self._display_text_results(comparison)
        elif options['format'] == 'json':
            self._display_json_results(comparison)
        elif options['format'] == 'html':
            self._display_html_results(comparison)

    def _display_text_results(self, comparison: Dict[str, Any]):
        """Display results in text format"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("📊 SCHEMA COMPARISON RESULTS")
        self.stdout.write("="*60)
        
        if not comparison['has_differences']:
            self.stdout.write(self.style.SUCCESS("✅ No schema differences found!"))
            return
        
        self.stdout.write(f"📈 Summary:")
        self.stdout.write(f"   • Baseline Tables: {comparison['summary']['total_tables_baseline']}")
        self.stdout.write(f"   • Current Tables: {comparison['summary']['total_tables_current']}")
        self.stdout.write(f"   • Total Differences: {comparison['summary']['total_differences']}")
        
        # Display table differences
        if comparison['differences']['tables']['added']:
            self.stdout.write(f"\n🆕 Added Tables ({len(comparison['differences']['tables']['added'])}):")
            for table in comparison['differences']['tables']['added']:
                self.stdout.write(f"   • {table}")
        
        if comparison['differences']['tables']['removed']:
            self.stdout.write(f"\n🗑️  Removed Tables ({len(comparison['differences']['tables']['removed'])}):")
            for table in comparison['differences']['tables']['removed']:
                self.stdout.write(f"   • {table}")
        
        if comparison['differences']['tables']['modified']:
            self.stdout.write(f"\n🔄 Modified Tables ({len(comparison['differences']['tables']['modified'])}):")
            for table_change in comparison['differences']['tables']['modified']:
                self.stdout.write(f"   • {table_change['table']}: {len(table_change['changes'])} changes")
        
        # Display column differences
        if comparison['differences']['columns']['added']:
            self.stdout.write(f"\n🆕 Added Columns ({len(comparison['differences']['columns']['added'])}):")
            for col in comparison['differences']['columns']['added']:
                self.stdout.write(f"   • {col['table']}.{col['column']} ({col['type']})")
        
        if comparison['differences']['columns']['removed']:
            self.stdout.write(f"\n🗑️  Removed Columns ({len(comparison['differences']['columns']['removed'])}):")
            for col in comparison['differences']['columns']['removed']:
                self.stdout.write(f"   • {col['table']}.{col['column']} ({col['type']})")
        
        if comparison['differences']['columns']['modified']:
            self.stdout.write(f"\n🔄 Modified Columns ({len(comparison['differences']['columns']['modified'])}):")
            for col in comparison['differences']['columns']['modified']:
                self.stdout.write(f"   • {col['table']}.{col['column']}: {len(col['changes'])} changes")
                for change in col['changes']:
                    self.stdout.write(f"     - {change['property']}: {change['baseline']} → {change['current']}")

    def _display_json_results(self, comparison: Dict[str, Any]):
        """Display results in JSON format"""
        import json
        self.stdout.write(json.dumps(comparison, indent=2, default=str))

    def _display_html_results(self, comparison: Dict[str, Any]):
        """Display results in HTML format"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Schema Comparison Results</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .summary {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
                .added {{ color: green; }}
                .removed {{ color: red; }}
                .modified {{ color: orange; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>Schema Comparison Results</h1>
            <div class="summary">
                <h2>Summary</h2>
                <p>Total Differences: {comparison['summary']['total_differences']}</p>
                <p>Baseline Tables: {comparison['summary']['total_tables_baseline']}</p>
                <p>Current Tables: {comparison['summary']['total_tables_current']}</p>
            </div>
        </body>
        </html>
        """
        self.stdout.write(html)

    def _save_comparison_results(self, comparison: Dict[str, Any], options: Dict[str, Any]):
        """Save comparison results to file"""
        output_file = Path(options['output'])
        
        if options['format'] == 'json':
            with open(output_file, 'w') as f:
                json.dump(comparison, f, indent=2, default=str)
        else:
            with open(output_file, 'w') as f:
                f.write(str(comparison))
        
        self.stdout.write(f"📄 Comparison results saved to: {output_file}")
