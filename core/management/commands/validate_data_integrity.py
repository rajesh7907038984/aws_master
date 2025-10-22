"""
Database Data Integrity Validation Command
Validates and cleans up data integrity issues across the LMS
"""

import logging
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.apps import apps

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Validate and fix data integrity issues across the LMS database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--fix-orphans',
            action='store_true',
            help='Remove orphaned records that reference non-existent foreign keys',
        )
        parser.add_argument(
            '--fix-scores',
            action='store_true',
            help='Fix score values that exceed field limits',
        )
        parser.add_argument(
            '--fix-enrollments',
            action='store_true',
            help='Fix duplicate enrollments and inconsistent enrollment data',
        )
        parser.add_argument(
            '--fix-all',
            action='store_true',
            help='Fix all detected issues',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verbose = options['verbose']
        self.fix_all = options['fix_all']
        
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🔍 Starting LMS Data Integrity Validation...')
        )
        
        issues_found = 0
        issues_fixed = 0
        
        # Check orphaned records
        if options['fix_orphans'] or self.fix_all:
            orphan_issues, orphan_fixes = self.check_orphaned_records()
            issues_found += orphan_issues
            issues_fixed += orphan_fixes
        
        # Check score field overflows
        if options['fix_scores'] or self.fix_all:
            score_issues, score_fixes = self.check_score_overflows()
            issues_found += score_issues
            issues_fixed += score_fixes
        
        # Check enrollment duplicates
        if options['fix_enrollments'] or self.fix_all:
            enrollment_issues, enrollment_fixes = self.check_enrollment_issues()
            issues_found += enrollment_issues
            issues_fixed += enrollment_fixes
        
        # Check general data consistency
        consistency_issues = self.check_data_consistency()
        issues_found += consistency_issues
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(f'Data Integrity Validation Complete')
        )
        self.stdout.write(f'📊 Issues found: {issues_found}')
        if not self.dry_run:
            self.stdout.write(f' Issues fixed: {issues_fixed}')
        else:
            self.stdout.write(f' Issues that would be fixed: {issues_fixed}')
        
        if issues_found > 0 and self.dry_run:
            self.stdout.write(
                self.style.WARNING('\n💡 Run with --fix-all to apply fixes')
            )

    def check_orphaned_records(self):
        """Check for orphaned records with missing foreign key references"""
        self.stdout.write('\n🔎 Checking for orphaned records...')
        
        issues_found = 0
        issues_fixed = 0
        
        # Define critical foreign key relationships to check
        relationships = [
            {
                'table': 'gradebook_grade',
                'fk_field': 'student_id',
                'ref_table': 'users_customuser',
                'ref_field': 'id',
                'description': 'Grades with non-existent students'
            },
            {
                'table': 'courses_courseenrollment',
                'fk_field': 'user_id',
                'ref_table': 'users_customuser',
                'ref_field': 'id',
                'description': 'Enrollments with non-existent users'
            },
            {
                'table': 'courses_courseenrollment',
                'fk_field': 'course_id',
                'ref_table': 'courses_course',
                'ref_field': 'id',
                'description': 'Enrollments with non-existent courses'
            },
            {
                'table': 'quiz_quizattempt',
                'fk_field': 'user_id',
                'ref_table': 'users_customuser',
                'ref_field': 'id',
                'description': 'Quiz attempts with non-existent users'
            },
            {
                'table': 'assignments_assignmentsubmission',
                'fk_field': 'user_id',
                'ref_table': 'users_customuser',
                'ref_field': 'id',
                'description': 'Assignment submissions with non-existent users'
            },
        ]
        
        with connection.cursor() as cursor:
            for rel in relationships:
                try:
                    # Check if tables exist
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, [rel['table']])
                    
                    if not cursor.fetchone()[0]:
                        continue
                    
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, [rel['ref_table']])
                    
                    if not cursor.fetchone()[0]:
                        continue
                    
                    # Count orphaned records
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {rel['table']} t
                        LEFT JOIN {rel['ref_table']} r ON t.{rel['fk_field']} = r.{rel['ref_field']}
                        WHERE t.{rel['fk_field']} IS NOT NULL AND r.{rel['ref_field']} IS NULL
                    """)
                    
                    orphan_count = cursor.fetchone()[0]
                    
                    if orphan_count > 0:
                        issues_found += orphan_count
                        self.stdout.write(
                            self.style.WARNING(
                                f'    {rel["description"]}: {orphan_count} orphaned records'
                            )
                        )
                        
                        if not self.dry_run:
                            # Delete orphaned records
                            cursor.execute(f"""
                                DELETE FROM {rel['table']} 
                                WHERE {rel['fk_field']} NOT IN (
                                    SELECT {rel['ref_field']} FROM {rel['ref_table']}
                                ) AND {rel['fk_field']} IS NOT NULL
                            """)
                            
                            issues_fixed += orphan_count
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'     Cleaned up {orphan_count} orphaned records'
                                )
                            )
                    elif self.verbose:
                        self.stdout.write(
                            self.style.SUCCESS(f'   {rel["description"]}: No issues')
                        )
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'   Error checking {rel["table"]}: {e}')
                    )
        
        return issues_found, issues_fixed

    def check_score_overflows(self):
        """Check for score values that exceed field limits"""
        self.stdout.write('\n🔢 Checking for score field overflows...')
        
        issues_found = 0
        issues_fixed = 0
        
        # Score fields to check (assuming decimal(5,2) = max 999.99)
        score_fields = [
            {
                'table': 'gradebook_grade',
                'field': 'score',
                'max_value': 999.99,
                'description': 'Gradebook scores'
            },
            {
                'table': 'courses_topicprogress',
                'field': 'last_score',
                'max_value': 999.99,
                'description': 'Topic progress last scores'
            },
            {
                'table': 'courses_topicprogress',
                'field': 'best_score',
                'max_value': 999.99,
                'description': 'Topic progress best scores'
            },
            {
                'table': 'quiz_quizattempt',
                'field': 'score',
                'max_value': 999.99,
                'description': 'Quiz attempt scores'
            },
        ]
        
        with connection.cursor() as cursor:
            for score_field in score_fields:
                try:
                    # Check if table exists
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, [score_field['table']])
                    
                    if not cursor.fetchone()[0]:
                        continue
                    
                    # Count values exceeding the limit
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {score_field['table']}
                        WHERE {score_field['field']} > %s
                    """, [score_field['max_value']])
                    
                    overflow_count = cursor.fetchone()[0]
                    
                    if overflow_count > 0:
                        issues_found += overflow_count
                        self.stdout.write(
                            self.style.WARNING(
                                f'    {score_field["description"]}: {overflow_count} values exceed {score_field["max_value"]}'
                            )
                        )
                        
                        if not self.dry_run:
                            # Cap values at the maximum
                            cursor.execute(f"""
                                UPDATE {score_field['table']}
                                SET {score_field['field']} = %s
                                WHERE {score_field['field']} > %s
                            """, [score_field['max_value'], score_field['max_value']])
                            
                            issues_fixed += overflow_count
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'     Capped {overflow_count} values to {score_field["max_value"]}'
                                )
                            )
                    elif self.verbose:
                        self.stdout.write(
                            self.style.SUCCESS(f'   {score_field["description"]}: No overflows')
                        )
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'   Error checking {score_field["table"]}.{score_field["field"]}: {e}')
                    )
        
        return issues_found, issues_fixed

    def check_enrollment_issues(self):
        """Check for enrollment data issues"""
        self.stdout.write('\n👥 Checking enrollment data integrity...')
        
        issues_found = 0
        issues_fixed = 0
        
        with connection.cursor() as cursor:
            try:
                # Check for duplicate enrollments
                cursor.execute("""
                    SELECT user_id, course_id, COUNT(*) as count
                    FROM courses_courseenrollment
                    GROUP BY user_id, course_id
                    HAVING COUNT(*) > 1
                """)
                
                duplicates = cursor.fetchall()
                
                if duplicates:
                    duplicate_count = len(duplicates)
                    issues_found += duplicate_count
                    self.stdout.write(
                        self.style.WARNING(
                            f'    Duplicate enrollments: {duplicate_count} user-course pairs have multiple enrollments'
                        )
                    )
                    
                    if not self.dry_run:
                        # Keep the oldest enrollment for each user-course pair
                        for user_id, course_id, count in duplicates:
                            cursor.execute("""
                                DELETE FROM courses_courseenrollment
                                WHERE user_id = %s AND course_id = %s
                                AND id NOT IN (
                                    SELECT id FROM (
                                        SELECT MIN(id) as id
                                        FROM courses_courseenrollment
                                        WHERE user_id = %s AND course_id = %s
                                    ) as subquery
                                )
                            """, [user_id, course_id, user_id, course_id])
                        
                        issues_fixed += duplicate_count
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'     Removed {duplicate_count} duplicate enrollments'
                            )
                        )
                elif self.verbose:
                    self.stdout.write(
                        self.style.SUCCESS('   No duplicate enrollments found')
                    )
                
                # Check for enrollments with completion dates but not marked as completed
                cursor.execute("""
                    SELECT COUNT(*) FROM courses_courseenrollment
                    WHERE completion_date IS NOT NULL AND completed = false
                """)
                
                inconsistent_completions = cursor.fetchone()[0]
                
                if inconsistent_completions > 0:
                    issues_found += inconsistent_completions
                    self.stdout.write(
                        self.style.WARNING(
                            f'    Inconsistent completion status: {inconsistent_completions} enrollments have completion dates but not marked as completed'
                        )
                    )
                    
                    if not self.dry_run:
                        cursor.execute("""
                            UPDATE courses_courseenrollment
                            SET completed = true
                            WHERE completion_date IS NOT NULL AND completed = false
                        """)
                        
                        issues_fixed += inconsistent_completions
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'     Fixed {inconsistent_completions} completion status inconsistencies'
                            )
                        )
                elif self.verbose:
                    self.stdout.write(
                        self.style.SUCCESS('   No completion status inconsistencies found')
                    )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'   Error checking enrollments: {e}')
                )
        
        return issues_found, issues_fixed

    def check_data_consistency(self):
        """Check for general data consistency issues"""
        self.stdout.write('\n🔍 Checking general data consistency...')
        
        issues_found = 0
        
        try:
            # Check for users without required fields
            User = get_user_model()
            users_without_email = User.objects.filter(email__isnull=True).count()
            users_without_username = User.objects.filter(username__isnull=True).count()
            
            if users_without_email > 0:
                issues_found += users_without_email
                self.stdout.write(
                    self.style.WARNING(f'    Users without email: {users_without_email}')
                )
            
            if users_without_username > 0:
                issues_found += users_without_username
                self.stdout.write(
                    self.style.WARNING(f'    Users without username: {users_without_username}')
                )
            
            # Check for courses without required fields
            Course = apps.get_model('courses', 'Course')
            courses_without_title = Course.objects.filter(title__isnull=True).count()
            
            if courses_without_title > 0:
                issues_found += courses_without_title
                self.stdout.write(
                    self.style.WARNING(f'    Courses without title: {courses_without_title}')
                )
            
            if issues_found == 0 and self.verbose:
                self.stdout.write(
                    self.style.SUCCESS('   No general consistency issues found')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'   Error checking data consistency: {e}')
            )
        
        return issues_found
