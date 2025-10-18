#!/usr/bin/env python3
"""
Cleanup Orphaned Migration Records
=================================

This script removes migration records from django_migrations table
that don't have corresponding migration files in the filesystem.

Usage: python scripts/cleanup_orphaned_migrations.py
"""

import os
import sys
import django
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings.production')
django.setup()

from django.db import connection
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

class OrphanedMigrationCleaner:
    """Clean up orphaned migration records from database"""
    
    def __init__(self):
        self.orphaned_migrations = []
        
    def find_orphaned_migrations(self):
        """Find migrations that are in database but not in filesystem"""
        print("🔍 Finding orphaned migration records...")
        
        # Get all migration files in filesystem
        migration_files = self.get_migration_files()
        
        # Get all applied migrations from database
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
            applied_migrations = cursor.fetchall()
        
        orphaned = []
        for app, name in applied_migrations:
            migration_key = "{{app}}.{{name}}"
            if migration_key not in migration_files:
                # Skip Django built-in apps
                if not (app.startswith('auth') or 
                       app.startswith('contenttypes') or
                       app.startswith('sessions') or
                       app.startswith('admin') or
                       app.startswith('sites')):
                    orphaned.append((app, name))
        
        self.orphaned_migrations = orphaned
        print(" Found {{len(orphaned)}} orphaned migration records")
        return orphaned
    
    def get_migration_files(self):
        """Get all migration files in the project"""
        migration_files = set()
        
        for root, dirs, files in os.walk('.'):
            if 'migrations' in root and '__pycache__' not in root and 'venv' not in root:
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        # Extract app name from path
                        path_parts = root.split(os.sep)
                        if len(path_parts) >= 2:
                            app_name = path_parts[-2]  # Directory before migrations
                            migration_name = file[:-3]  # Remove .py
                            migration_files.add("{{app_name}}.{{migration_name}}")
        
        return migration_files
    
    def remove_orphaned_migrations(self, dry_run=False):
        """Remove orphaned migration records from database"""
        if not self.orphaned_migrations:
            print(" No orphaned migrations found")
            return
        
        print(" {{'DRY RUN: Would remove' if dry_run else 'Removing'}} {{len(self.orphaned_migrations)}} orphaned migration records...")
        
        with connection.cursor() as cursor:
            for app, name in self.orphaned_migrations:
                if dry_run:
                    print("   Would remove: {{app}}.{{name}}")
                else:
                    try:
                        cursor.execute(
                            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                            [app, name]
                        )
                        print("   Removed: {{app}}.{{name}}")
                    except Exception as e:
                        print("   Error removing {{app}}.{{name}}: {{e}}")
        
        if not dry_run:
            print(" Successfully removed {{len(self.orphaned_migrations)}} orphaned migration records")
    
    def show_orphaned_migrations(self):
        """Show list of orphaned migrations"""
        if not self.orphaned_migrations:
            print(" No orphaned migrations found")
            return
        
        print("\n📋 Orphaned Migration Records:")
        print("=" * 50)
        
        # Group by app
        by_app = {}
        for app, name in self.orphaned_migrations:
            if app not in by_app:
                by_app[app] = []
            by_app[app].append(name)
        
        for app in sorted(by_app.keys()):
            print("\n{{app}}:")
            for name in sorted(by_app[app]):
                print("  - {{name}}")
    
    def run_cleanup(self, dry_run=False):
        """Run the complete cleanup process"""
        print("🧹 Orphaned Migration Cleanup")
        print("=" * 40)
        
        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        
        # Find orphaned migrations
        orphaned = self.find_orphaned_migrations()
        
        if not orphaned:
            print("✅ No orphaned migrations found - database is clean!")
            return
        
        # Show what will be removed
        self.show_orphaned_migrations()
        
        # Remove orphaned migrations
        self.remove_orphaned_migrations(dry_run)
        
        if not dry_run:
            print("\n✅ Orphaned migration cleanup completed!")
            print("💡 You may now run 'python manage.py showmigrations' to verify")
        else:
            print("\n💡 Run without --dry-run to actually remove these records")

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up orphaned migration records')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be removed without making changes')
    parser.add_argument('--show-only', action='store_true',
                       help='Only show orphaned migrations without removing them')
    
    args = parser.parse_args()
    
    try:
        cleaner = OrphanedMigrationCleaner()
        
        if args.show_only:
            cleaner.find_orphaned_migrations()
            cleaner.show_orphaned_migrations()
        else:
            cleaner.run_cleanup(dry_run=args.dry_run)
        
    except Exception as e:
        print("❌ Error during cleanup: {{e}}")
        sys.exit(1)

if __name__ == "__main__":
    main()
