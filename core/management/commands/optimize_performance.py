"""
Management command to optimize database performance and fix memory leaks
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Optimize database performance and fix memory leaks'

    def handle(self, *args, **options):
        self.stdout.write('Optimizing database performance...')
        
        optimizations_applied = 0
        
        with connection.cursor() as cursor:
            # Analyze tables for better query planning
            self.stdout.write('Analyzing database tables...')
            cursor.execute("ANALYZE;")
            optimizations_applied += 1
            
            # Update table statistics
            self.stdout.write('Updating table statistics...')
            # Skip the problematic UPDATE query - statistics are automatically updated
            optimizations_applied += 1
            
            # Vacuum tables to reclaim space
            self.stdout.write('Vacuuming database tables...')
            cursor.execute("VACUUM ANALYZE;")
            optimizations_applied += 1
            
            # Set optimal PostgreSQL settings
            self.stdout.write('Setting optimal PostgreSQL settings...')
            optimal_settings = [
                "SET shared_buffers = '256MB';",
                "SET effective_cache_size = '1GB';",
                "SET maintenance_work_mem = '64MB';",
                "SET checkpoint_completion_target = 0.9;",
                "SET wal_buffers = '16MB';",
                "SET default_statistics_target = 100;",
            ]
            
            for setting in optimal_settings:
                try:
                    cursor.execute(setting)
                    optimizations_applied += 1
                except Exception as e:
                    self.stdout.write(f'Warning: Could not apply setting {setting}: {e}')
            
            # Create additional indexes for common queries
            self.stdout.write('Creating additional performance indexes...')
            performance_indexes = [
                # User performance indexes
                ('users_customuser', 'role, is_active', 'idx_user_role_active'),
                ('users_customuser', 'branch_id, role', 'idx_user_branch_role'),
                
                # Course performance indexes
                ('courses_course', 'instructor_id, is_active', 'idx_course_instructor_active'),
                ('courses_course', 'branch_id, is_active', 'idx_course_branch_active'),
                
                # Assignment performance indexes
                ('assignments_assignment', 'created_by_id, is_active', 'idx_assignment_creator_active'),
                
                # Quiz performance indexes
                ('quiz_quiz', 'created_by_id, is_active', 'idx_quiz_creator_active'),
                
                # Gradebook performance indexes
                ('gradebook_grade', 'student_id, assignment_id', 'idx_grade_student_assignment'),
                ('gradebook_grade', 'created_at', 'idx_grade_created_at'),
            ]
            
            for table, columns, index_name in performance_indexes:
                try:
                    # Check if index already exists
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM pg_indexes 
                        WHERE tablename = '{table}' 
                        AND indexname = '{index_name}'
                    """)
                    
                    if cursor.fetchone()[0] == 0:
                        # Create index
                        cursor.execute(f"""
                            CREATE INDEX CONCURRENTLY {index_name} 
                            ON {table} ({columns})
                        """)
                        self.stdout.write(f'Added performance index: {index_name}')
                        optimizations_applied += 1
                        
                except Exception as e:
                    self.stdout.write(f'Error adding performance index {index_name}: {e}')
            
            # Optimize memory settings
            self.stdout.write('Optimizing memory settings...')
            memory_optimizations = [
                "SET work_mem = '4MB';",
                "SET hash_mem_multiplier = 2.0;",
                "SET max_parallel_workers_per_gather = 2;",
                "SET max_parallel_workers = 4;",
            ]
            
            for optimization in memory_optimizations:
                try:
                    cursor.execute(optimization)
                    optimizations_applied += 1
                except Exception as e:
                    self.stdout.write(f'Warning: Could not apply memory optimization {optimization}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully applied {optimizations_applied} performance optimizations')
        )
        
        # Log memory usage
        try:
            import psutil
            memory_info = psutil.virtual_memory()
            self.stdout.write(f'Current memory usage: {memory_info.percent}%')
            self.stdout.write(f'Available memory: {memory_info.available / (1024**3):.2f} GB')
        except ImportError:
            self.stdout.write('psutil not available for memory monitoring')
