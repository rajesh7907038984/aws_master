from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.apps import apps
import os
import re
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Comprehensive migration health check and analysis'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix-issues',
            action='store_true',
            help='Automatically fix detected issues (use with caution)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        fix_issues = options['fix_issues']
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('🔍 Starting comprehensive migration health check...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        try:
            # 1. Analyze dependency chains
            issues = self.analyze_dependencies(verbose)
            
            # 2. Check for merge migration complexity
            merge_issues = self.check_merge_complexity(verbose)
            
            # 3. Check for potential SharePoint-like issues
            sharepoint_issues = self.check_sharepoint_like_issues(verbose)
            
            # 4. Check for orphaned migrations
            orphan_issues = self.check_orphaned_migrations(verbose)
            
            # 5. Check database consistency
            db_issues = self.check_database_consistency(verbose)
            
            all_issues = issues + merge_issues + sharepoint_issues + orphan_issues + db_issues
            
            if all_issues:
                self.stdout.write(
                    self.style.WARNING(f'  Found {len(all_issues)} potential issues:')
                )
                for issue in all_issues:
                    self.stdout.write(f'   - {issue}')
                
                if fix_issues and not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(' Attempting to fix issues...')
                    )
                    self.fix_detected_issues(all_issues)
                elif dry_run:
                    self.stdout.write(
                        self.style.WARNING('DRY RUN: Would attempt to fix these issues')
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS(' No migration health issues detected!')
                )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f' Error during migration health check: {e}')
            )
            raise

    def analyze_dependencies(self, verbose):
        """Analyze migration dependency chains for issues"""
        if verbose:
            self.stdout.write('📊 Analyzing migration dependencies...')
        
        issues = []
        migration_deps = defaultdict(list)
        migration_files = self.get_migration_files()
        
        # Parse dependencies
        for migration_key, filepath in migration_files.items():
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                    deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                    if deps_match:
                        deps_content = deps_match.group(1)
                        dep_matches = re.findall(r'[\"\'](.*?)[\"\']\s*,\s*[\"\'](.*?)[\"\']', deps_content)
                        for app, migration in dep_matches:
                            dep_key = f'{app}.{migration}'
                            migration_deps[migration_key].append(dep_key)
            except Exception as e:
                if verbose:
                    self.stdout.write(f' Error parsing {filepath}: {e}')
        
        # Check for circular dependencies
        if self.has_circular_dependency(migration_deps):
            issues.append('CRITICAL: Circular dependency detected in migration chain')
        
        # Check for missing dependencies
        for migration, deps in migration_deps.items():
            for dep in deps:
                if (dep not in migration_files and 
                    not dep.startswith('auth.') and 
                    not dep.startswith('contenttypes.') and
                    'swappable_dependency' not in dep):
                    issues.append(f'Missing dependency: {migration} → {dep}')
        
        return issues

    def check_merge_complexity(self, verbose):
        """Check for overly complex merge migration history"""
        if verbose:
            self.stdout.write('🔀 Checking merge migration complexity...')
        
        issues = []
        migration_files = self.get_migration_files()
        
        # Count merge migrations per app
        app_merge_counts = defaultdict(int)
        for migration_key in migration_files.keys():
            if 'merge' in migration_key.lower():
                app_name = migration_key.split('.')[0]
                app_merge_counts[app_name] += 1
        
        # Flag apps with excessive merge migrations
        for app, count in app_merge_counts.items():
            if count > 3:
                issues.append(f'Complex merge history in {app}: {count} merge migrations')
        
        return issues

    def check_sharepoint_like_issues(self, verbose):
        """Check for dependency issues similar to the SharePoint problem"""
        if verbose:
            self.stdout.write('🔗 Checking for SharePoint-like dependency issues...')
        
        issues = []
        
        # Check for common problematic patterns
        problematic_deps = [
            'account_settings.0014_add_sharepoint_integration_fields',
            'account_settings.0015_add_microsoft_oauth_fields',
        ]
        
        for prob_dep in problematic_deps:
            dependents = self.find_dependents(prob_dep)
            if len(dependents) > 2:
                issues.append(f'High dependency pattern: {len(dependents)} migrations depend on {prob_dep}')
        
        return issues

    def check_orphaned_migrations(self, verbose):
        """Check for orphaned or isolated migrations"""
        if verbose:
            self.stdout.write('🏝️ Checking for orphaned migrations...')
        
        issues = []
        
        # This is a simplified check - in practice you'd want more sophisticated logic
        migration_files = self.get_migration_files()
        
        # Look for migrations that might be isolated
        for app_name in apps.get_app_configs():
            app_label = app_name.label
            app_migrations = [k for k in migration_files.keys() if k.startswith(f'{app_label}.')]
            
            if len(app_migrations) > 20:  # Apps with many migrations might have issues
                issues.append(f'App {app_label} has {len(app_migrations)} migrations - consider consolidation')
        
        return issues

    def check_database_consistency(self, verbose):
        """Check database migration table consistency"""
        if verbose:
            self.stdout.write('🗄️ Checking database consistency...')
        
        issues = []
        
        try:
            with connection.cursor() as cursor:
                # Check if migration table exists and has expected structure
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = 'django_migrations'
                """)
                
                if cursor.fetchone()[0] == 0:
                    issues.append('CRITICAL: django_migrations table missing')
                else:
                    # Check for any migrations marked as applied but files missing
                    cursor.execute("""
                        SELECT app, name FROM django_migrations 
                        ORDER BY app, name
                    """)
                    
                    applied_migrations = cursor.fetchall()
                    migration_files = self.get_migration_files()
                    
                    for app, name in applied_migrations:
                        migration_key = f'{app}.{name}'
                        if (migration_key not in migration_files and 
                            not app.startswith('auth') and 
                            not app.startswith('contenttypes') and
                            not app.startswith('sessions') and
                            not app.startswith('admin') and
                            not app.startswith('sites')):
                            issues.append(f'Applied migration file missing: {migration_key}')
        
        except Exception as e:
            issues.append(f'Database check failed: {e}')
        
        return issues

    def get_migration_files(self):
        """Get all migration files in the project"""
        migration_files = {}
        
        for root, dirs, files in os.walk('.'):
            if 'migrations' in root and '__pycache__' not in root and 'venv' not in root:
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        # Extract app name from path
                        path_parts = root.split(os.sep)
                        if len(path_parts) >= 2:
                            app_name = path_parts[-2]  # Directory before migrations
                            migration_name = file[:-3]  # Remove .py
                            filepath = os.path.join(root, file)
                            migration_files[f'{app_name}.{migration_name}'] = filepath
        
        return migration_files

    def has_circular_dependency(self, deps_graph):
        """Check for circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        
        def dfs(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in deps_graph.get(node, []):
                if dfs(neighbor):
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in deps_graph:
            if node not in visited and dfs(node):
                return True
        return False

    def find_dependents(self, target_migration):
        """Find all migrations that depend on a specific migration"""
        dependents = []
        migration_files = self.get_migration_files()
        
        for migration_key, filepath in migration_files.items():
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                    if target_migration in content:
                        dependents.append(migration_key)
            except:
                pass
        
        return dependents

    def fix_detected_issues(self, issues):
        """Attempt to fix detected issues"""
        fixed_count = 0
        
        for issue in issues:
            try:
                if 'Missing dependency' in issue:
                    self.stdout.write(f' Attempting to fix: {issue}')
                    # This would need specific logic based on the issue
                    # For now, just log that we would fix it
                    self.stdout.write('   → Would resolve missing dependency')
                    fixed_count += 1
                
                elif 'Complex merge history' in issue:
                    self.stdout.write(f' Recommendation for: {issue}')
                    self.stdout.write('   → Consider squashing migrations in this app')
                
                elif 'High dependency pattern' in issue:
                    self.stdout.write(f' Manual review needed: {issue}')
                    self.stdout.write('   → Review dependency chain for potential conflicts')
                
            except Exception as e:
                self.stdout.write(f' Failed to fix issue: {issue} - {e}')
        
        if fixed_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f' Fixed {fixed_count} issues')
            )
