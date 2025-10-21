"""
Database Optimization Command
Optimizes database performance by creating indexes, analyzing tables, and cleaning up
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Optimize database performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--analyze-only',
            action='store_true',
            help='Only run ANALYZE without creating indexes',
        )
        parser.add_argument(
            '--vacuum-only',
            action='store_true',
            help='Only run VACUUM without other optimizations',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting database optimization...')
        
        try:
            with connection.cursor() as cursor:
                # Get database statistics before optimization
                self.stdout.write('Getting database statistics...')
                self.get_database_stats(cursor)
                
                if not options['analyze_only']:
                    # Create performance indexes
                    self.stdout.write('Creating performance indexes...')
                    self.create_performance_indexes(cursor)
                
                if not options['vacuum_only']:
                    # Analyze tables for better query planning
                    self.stdout.write('Analyzing tables...')
                    self.analyze_tables(cursor)
                
                # Vacuum and reindex for better performance
                self.stdout.write('Running VACUUM and REINDEX...')
                self.vacuum_and_reindex(cursor)
                
                # Get final statistics
                self.stdout.write('Getting final database statistics...')
                self.get_database_stats(cursor)
                
            self.stdout.write(
                self.style.SUCCESS('Database optimization completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Database optimization failed: {e}')
            )
            raise

    def get_database_stats(self, cursor):
        """Get database statistics"""
        try:
            # Get database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
            """)
            db_size = cursor.fetchone()[0]
            self.stdout.write(f'Database size: {db_size}')
            
            # Get table count
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cursor.fetchone()[0]
            self.stdout.write(f'Total tables: {table_count}')
            
            # Get index count
            cursor.execute("""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE schemaname = 'public'
            """)
            index_count = cursor.fetchone()[0]
            self.stdout.write(f'Total indexes: {index_count}')
            
        except Exception as e:
            self.stdout.write(f'Error getting database stats: {e}')

    def create_performance_indexes(self, cursor):
        """Create performance indexes for common queries"""
        indexes = [
            # User-related indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON users_customuser(email)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_username ON users_customuser(username)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_role ON users_customuser(role)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_is_active ON users_customuser(is_active)",
            
            # Course-related indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_courses_title ON courses_course(title)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_courses_status ON courses_course(status)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_courses_created_by ON courses_course(created_by_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_courses_created_at ON courses_course(created_at)",
            
            # Enrollment indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enrollment_user_course ON courses_courseenrollment(user_id, course_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enrollment_status ON courses_courseenrollment(status)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enrollment_enrolled_at ON courses_courseenrollment(enrolled_at)",
            
            # Topic progress indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_topic_progress_user_topic ON courses_topicprogress(user_id, topic_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_topic_progress_status ON courses_topicprogress(status)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_topic_progress_completed_at ON courses_topicprogress(completed_at)",
            
            # Assignment indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assignments_course ON assignments_assignment(course_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assignments_due_date ON assignments_assignment(due_date)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_assignments_status ON assignments_assignment(status)",
            
            # Session indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_expire_date ON django_session(expire_date)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_session_key ON django_session(session_key)",
            
            # Message indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_sender ON lms_messages_message(sender_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_created_at ON lms_messages_message(created_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_is_read ON lms_messages_message(is_read)",
        ]
        
        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
                self.stdout.write(f'Created index: {index_sql.split()[-1]}')
            except Exception as e:
                self.stdout.write(f'Index creation failed (may already exist): {e}')

    def analyze_tables(self, cursor):
        """Analyze tables for better query planning"""
        try:
            # Get all tables
            cursor.execute("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY tablename
            """)
            tables = cursor.fetchall()
            
            for (table_name,) in tables:
                try:
                    cursor.execute(f"ANALYZE {table_name}")
                    self.stdout.write(f'Analyzed table: {table_name}')
                except Exception as e:
                    self.stdout.write(f'Error analyzing {table_name}: {e}')
                    
        except Exception as e:
            self.stdout.write(f'Error in analyze_tables: {e}')

    def vacuum_and_reindex(self, cursor):
        """Run VACUUM and REINDEX for better performance"""
        try:
            # VACUUM ANALYZE for better statistics
            cursor.execute("VACUUM ANALYZE")
            self.stdout.write('VACUUM ANALYZE completed')
            
            # Reindex critical tables
            critical_tables = [
                'users_customuser',
                'courses_course',
                'courses_courseenrollment',
                'courses_topicprogress',
                'assignments_assignment',
                'django_session',
                'lms_messages_message'
            ]
            
            for table in critical_tables:
                try:
                    cursor.execute(f"REINDEX TABLE {table}")
                    self.stdout.write(f'Reindexed table: {table}')
                except Exception as e:
                    self.stdout.write(f'Error reindexing {table}: {e}')
                    
        except Exception as e:
            self.stdout.write(f'Error in vacuum_and_reindex: {e}')