#!/usr/bin/env python3
"""
Old Code Cleanup Script
Identifies and cleans up old, unused, or problematic code references
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import connection
from django.core.management import call_command
from django.apps import apps
import logging

logger = logging.getLogger(__name__)

class OldCodeCleanup:
    def __init__(self):
        self.issues_found = []
        self.cleanup_actions = []
        
    def analyze_old_code(self):
        """Analyze the codebase for old code patterns"""
        print("🔍 Analyzing codebase for old code patterns...")
        
        # Check for backward compatibility code
        self._check_backward_compatibility()
        
        # Check for unused fields
        self._check_unused_fields()
        
        # Check for orphaned records
        self._check_orphaned_records()
        
        # Check for duplicate data
        self._check_duplicate_data()
        
        return self.issues_found
    
    def _check_backward_compatibility(self):
        """Check for backward compatibility code that can be removed"""
        print("  📋 Checking backward compatibility code...")
        
        # Check SCORM models for old aliases
        scorm_file = project_root / 'scorm' / 'models.py'
        if scorm_file.exists():
            with open(scorm_file, 'r') as f:
                content = f.read()
                if '# Backward compatibility alias' in content and 'SCORMPackage = ELearningPackage' in content:
                    self.issues_found.append({
                        'type': 'backward_compatibility',
                        'file': str(scorm_file),
                        'issue': 'Backward compatibility aliases found',
                        'severity': 'medium',
                        'action': 'Remove backward compatibility aliases'
                    })
    
    def _check_unused_fields(self):
        """Check for unused model fields"""
        print("  📋 Checking for unused fields...")
        
        # Check User model for legacy assessment fields
        try:
            from users.models import CustomUser
            user_fields = [field.name for field in CustomUser._meta.fields]
            
            # Check for potentially unused assessment fields
            legacy_fields = [
                'initial_assessment_english', 'initial_assessment_maths',
                'diagnostic_assessment_english', 'diagnostic_assessment_maths',
                'functional_skills_english', 'functional_skills_maths'
            ]
            
            for field in legacy_fields:
                if field in user_fields:
                    # Check if field is actually used
                    usage_count = CustomUser.objects.filter(**{"{{field}}__isnull": False}).count()
                    if usage_count == 0:
                        self.issues_found.append({
                            'type': 'unused_field',
                            'model': 'CustomUser',
                            'field': field,
                            'issue': "Field {{field}} has no data",
                            'severity': 'low',
                            'action': "Consider removing unused field {{field}}"
                        })
        except Exception as e:
            logger.error("Error checking unused fields: {{e}}")
    
    def _check_orphaned_records(self):
        """Check for orphaned records in the database"""
        print("  📋 Checking for orphaned records...")
        
        try:
            with connection.cursor() as cursor:
                # Check for orphaned course enrollments
                cursor.execute("""
                    SELECT COUNT(*) FROM courses_courseenrollment ce 
                    LEFT JOIN users_customuser u ON ce.user_id = u.id 
                    WHERE u.id IS NULL
                """)
                orphaned_enrollments = cursor.fetchone()[0]
                
                if orphaned_enrollments > 0:
                    self.issues_found.append({
                        'type': 'orphaned_records',
                        'table': 'courses_courseenrollment',
                        'count': orphaned_enrollments,
                        'issue': "{{orphaned_enrollments}} orphaned course enrollments found",
                        'severity': 'high',
                        'action': 'Clean up orphaned course enrollments'
                    })
                
                # Check for orphaned assignment submissions
                cursor.execute("""
                    SELECT COUNT(*) FROM assignments_assignmentsubmission aas 
                    LEFT JOIN users_customuser u ON aas.user_id = u.id 
                    WHERE u.id IS NULL
                """)
                orphaned_submissions = cursor.fetchone()[0]
                
                if orphaned_submissions > 0:
                    self.issues_found.append({
                        'type': 'orphaned_records',
                        'table': 'assignments_assignmentsubmission',
                        'count': orphaned_submissions,
                        'issue': "{{orphaned_submissions}} orphaned assignment submissions found",
                        'severity': 'high',
                        'action': 'Clean up orphaned assignment submissions'
                    })
                
        except Exception as e:
            logger.error("Error checking orphaned records: {{e}}")
    
    def _check_duplicate_data(self):
        """Check for duplicate data"""
        print("  📋 Checking for duplicate data...")
        
        try:
            with connection.cursor() as cursor:
                # Check for duplicate users (same email)
                cursor.execute("""
                    SELECT email, COUNT(*) as count 
                    FROM users_customuser 
                    WHERE email IS NOT NULL AND email != '' 
                    GROUP BY email 
                    HAVING COUNT(*) > 1
                """)
                duplicate_users = cursor.fetchall()
                
                if duplicate_users:
                    self.issues_found.append({
                        'type': 'duplicate_data',
                        'table': 'users_customuser',
                        'count': len(duplicate_users),
                        'issue': "{{len(duplicate_users)}} duplicate email addresses found",
                        'severity': 'medium',
                        'action': 'Consolidate duplicate user accounts'
                    })
                
        except Exception as e:
            logger.error("Error checking duplicate data: {{e}}")
    
    def generate_cleanup_script(self):
        """Generate a cleanup script for identified issues"""
        print("📝 Generating cleanup script...")
        
        script_content = '''#!/usr/bin/env python3
"""
Generated Cleanup Script
Run this script to clean up identified issues
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LMS_Project.settings')
django.setup()

from django.db import connection, transaction
from django.core.management import call_command

def cleanup_orphaned_records():
    """Clean up orphaned records"""
    print("🧹 Cleaning up orphaned records...")
    
    with connection.cursor() as cursor:
        # Clean up orphaned course enrollments
        cursor.execute("""
            DELETE FROM courses_courseenrollment 
            WHERE user_id NOT IN (SELECT id FROM users_customuser)
        """)
        deleted_enrollments = cursor.rowcount
        print("  ✅ Deleted {{deleted_enrollments}} orphaned course enrollments")
        
        # Clean up orphaned assignment submissions
        cursor.execute("""
            DELETE FROM assignments_assignmentsubmission 
            WHERE user_id NOT IN (SELECT id FROM users_customuser)
        """)
        deleted_submissions = cursor.rowcount
        print("  ✅ Deleted {{deleted_submissions}} orphaned assignment submissions")

def cleanup_duplicate_data():
    """Clean up duplicate data"""
    print("🧹 Cleaning up duplicate data...")
    
    with connection.cursor() as cursor:
        # Find and handle duplicate users
        cursor.execute("""
            SELECT email, MIN(id) as keep_id, COUNT(*) as count
            FROM users_customuser 
            WHERE email IS NOT NULL AND email != ''
            GROUP BY email 
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        
        for email, keep_id, count in duplicates:
            print("  📧 Found {{count}} duplicates for {{email}}, keeping ID {{keep_id}}")
            # Note: Actual cleanup would require more complex logic
            # to handle related records

if __name__ == "__main__":
    print("🚀 Starting database cleanup...")
    
    try:
        with transaction.atomic():
            cleanup_orphaned_records()
            cleanup_duplicate_data()
        print("✅ Cleanup completed successfully!")
    except Exception as e:
        print("❌ Cleanup failed: {{e}}")
        sys.exit(1)
'''
        
        cleanup_script_path = project_root / 'scripts' / 'execute_cleanup.py'
        with open(cleanup_script_path, 'w') as f:
            f.write(script_content)
        
        # Make the script executable
        os.chmod(cleanup_script_path, 0o755)
        
        print("✅ Cleanup script generated: {{cleanup_script_path}}")
        return cleanup_script_path
    
    def print_report(self):
        """Print a detailed report of findings"""
        print("\n" + "="*60)
        print("📊 OLD CODE ANALYSIS REPORT")
        print("="*60)
        
        if not self.issues_found:
            print("✅ No old code issues found!")
            return
        
        # Group issues by type
        issues_by_type = {}
        for issue in self.issues_found:
            issue_type = issue['type']
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        for issue_type, issues in issues_by_type.items():
            print("\n🔍 {{issue_type.upper().replace('_', ' ')}} ISSUES ({{len(issues)}} found)")
            print("-" * 40)
            
            for issue in issues:
                severity_icon = {
                    'high': '🔴',
                    'medium': '🟡', 
                    'low': '🟢'
                }.get(issue.get('severity', 'low'), '⚪')
                
                print("{{severity_icon}} {{issue.get('issue', 'Unknown issue')}}")
                if 'action' in issue:
                    print("   💡 Action: {{issue['action']}}")
                if 'file' in issue:
                    print("   📁 File: {{issue['file']}}")
                if 'count' in issue:
                    print("   📊 Count: {{issue['count']}}")
                print()

def main():
    """Main function"""
    print("🚀 Starting Old Code Analysis...")
    
    cleanup = OldCodeCleanup()
    
    # Analyze old code
    issues = cleanup.analyze_old_code()
    
    # Print report
    cleanup.print_report()
    
    # Generate cleanup script if issues found
    if issues:
        cleanup.generate_cleanup_script()
        print("\n💡 Next steps:")
        print("1. Review the generated cleanup script")
        print("2. Test the cleanup in a development environment")
        print("3. Backup your database before running cleanup")
        print("4. Run: python scripts/execute_cleanup.py")
    else:
        print("\n🎉 No cleanup needed - your codebase is clean!")

if __name__ == "__main__":
    main()
