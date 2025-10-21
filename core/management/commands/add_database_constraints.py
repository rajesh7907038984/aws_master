"""
Management command to add missing database constraints for data integrity
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps


class Command(BaseCommand):
    help = 'Add missing database constraints for data integrity'

    def handle(self, *args, **options):
        self.stdout.write('Adding missing database constraints...')
        
        constraints_added = 0
        
        with connection.cursor() as cursor:
            # Add unique constraints for critical fields
            unique_constraints = [
                # User constraints
                ('users_customuser', 'email', 'unique_email'),
                ('users_customuser', 'username', 'unique_username'),
                
                # Course constraints
                ('courses_course', 'title', 'unique_course_title'),
                
                # Assignment constraints
                ('assignments_assignment', 'title', 'unique_assignment_title'),
                
                # Quiz constraints
                ('quiz_quiz', 'title', 'unique_quiz_title'),
                
                # Branch constraints
                ('branches_branch', 'name', 'unique_branch_name'),
            ]
            
            for table, column, constraint_name in unique_constraints:
                try:
                    # Check if constraint already exists
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM pg_constraint 
                        WHERE conname = '{constraint_name}'
                    """)
                    
                    if cursor.fetchone()[0] == 0:
                        # Create unique constraint
                        cursor.execute(f"""
                            ALTER TABLE {table} 
                            ADD CONSTRAINT {constraint_name} 
                            UNIQUE ({column})
                        """)
                        self.stdout.write(f'Added unique constraint: {constraint_name}')
                        constraints_added += 1
                        
                except Exception as e:
                    self.stdout.write(f'Error adding constraint {constraint_name}: {e}')
            
            # Add check constraints for data validation
            check_constraints = [
                # User constraints
                ('users_customuser', 'email ~ \'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$\'', 'check_valid_email'),
                ('users_customuser', 'username ~ \'^[a-zA-Z0-9_]+$\'', 'check_valid_username'),
                
                # Course constraints
                ('courses_course', 'title IS NOT NULL AND LENGTH(title) > 0', 'check_course_title_not_empty'),
                
                # Assignment constraints
                ('assignments_assignment', 'title IS NOT NULL AND LENGTH(title) > 0', 'check_assignment_title_not_empty'),
                
                # Quiz constraints
                ('quiz_quiz', 'title IS NOT NULL AND LENGTH(title) > 0', 'check_quiz_title_not_empty'),
            ]
            
            for table, condition, constraint_name in check_constraints:
                try:
                    # Check if constraint already exists
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM pg_constraint 
                        WHERE conname = '{constraint_name}'
                    """)
                    
                    if cursor.fetchone()[0] == 0:
                        # Create check constraint
                        cursor.execute(f"""
                            ALTER TABLE {table} 
                            ADD CONSTRAINT {constraint_name} 
                            CHECK ({condition})
                        """)
                        self.stdout.write(f'Added check constraint: {constraint_name}')
                        constraints_added += 1
                        
                except Exception as e:
                    self.stdout.write(f'Error adding constraint {constraint_name}: {e}')
            
            # Add foreign key constraints where missing
            foreign_key_constraints = [
                # User foreign keys
                ('users_customuser', 'branch_id', 'branches_branch', 'id'),
                ('users_customuser', 'assigned_instructor_id', 'users_customuser', 'id'),
                
                # Course foreign keys
                ('courses_course', 'instructor_id', 'users_customuser', 'id'),
                ('courses_course', 'branch_id', 'branches_branch', 'id'),
                
                # Assignment foreign keys
                ('assignments_assignment', 'created_by_id', 'users_customuser', 'id'),
                
                # Quiz foreign keys
                ('quiz_quiz', 'created_by_id', 'users_customuser', 'id'),
            ]
            
            for table, column, ref_table, ref_column in foreign_key_constraints:
                try:
                    # Check if foreign key already exists
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM pg_constraint 
                        WHERE conname = 'fk_{table}_{column}'
                    """)
                    
                    if cursor.fetchone()[0] == 0:
                        # Create foreign key constraint
                        cursor.execute(f"""
                            ALTER TABLE {table} 
                            ADD CONSTRAINT fk_{table}_{column} 
                            FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column})
                        """)
                        self.stdout.write(f'Added foreign key constraint: fk_{table}_{column}')
                        constraints_added += 1
                        
                except Exception as e:
                    self.stdout.write(f'Error adding foreign key constraint fk_{table}_{column}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully added {constraints_added} database constraints')
        )
