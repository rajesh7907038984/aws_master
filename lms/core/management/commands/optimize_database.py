"""
Database optimization command
Adds indexes and optimizes database performance
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Optimize database performance by adding indexes'

    def handle(self, *args, **options):
        self.stdout.write('Starting database optimization...')
        
        with connection.cursor() as cursor:
            # Add indexes for frequently queried fields
            indexes = [
                # User model indexes
                "CREATE INDEX IF NOT EXISTS idx_users_email ON users_customuser(email);",
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users_customuser(username);",
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users_customuser(role);",
                "CREATE INDEX IF NOT EXISTS idx_users_branch ON users_customuser(branch_id);",
                "CREATE INDEX IF NOT EXISTS idx_users_is_active ON users_customuser(is_active);",
                "CREATE INDEX IF NOT EXISTS idx_users_date_joined ON users_customuser(date_joined);",
                
                # Course model indexes
                "CREATE INDEX IF NOT EXISTS idx_courses_title ON courses_course(title);",
                "CREATE INDEX IF NOT EXISTS idx_courses_creator ON courses_course(creator_id);",
                "CREATE INDEX IF NOT EXISTS idx_courses_branch ON courses_course(branch_id);",
                "CREATE INDEX IF NOT EXISTS idx_courses_is_active ON courses_course(is_active);",
                "CREATE INDEX IF NOT EXISTS idx_courses_created_at ON courses_course(created_at);",
                
                # Topic model indexes
                "CREATE INDEX IF NOT EXISTS idx_topics_course ON courses_topic(course_id);",
                "CREATE INDEX IF NOT EXISTS idx_topics_title ON courses_topic(title);",
                "CREATE INDEX IF NOT EXISTS idx_topics_order ON courses_topic(order);",
                
                # CourseEnrollment indexes
                "CREATE INDEX IF NOT EXISTS idx_enrollment_user ON courses_courseenrollment(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_enrollment_course ON courses_courseenrollment(course_id);",
                "CREATE INDEX IF NOT EXISTS idx_enrollment_status ON courses_courseenrollment(status);",
                "CREATE INDEX IF NOT EXISTS idx_enrollment_enrolled_at ON courses_courseenrollment(enrolled_at);",
                
                # TopicProgress indexes
                "CREATE INDEX IF NOT EXISTS idx_progress_user ON courses_topicprogress(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_progress_topic ON courses_topicprogress(topic_id);",
                "CREATE INDEX IF NOT EXISTS idx_progress_status ON courses_topicprogress(status);",
                "CREATE INDEX IF NOT EXISTS idx_progress_completed_at ON courses_topicprogress(completed_at);",
                
                # Quiz indexes
                "CREATE INDEX IF NOT EXISTS idx_quiz_course ON quiz_quiz(course_id);",
                "CREATE INDEX IF NOT EXISTS idx_quiz_creator ON quiz_quiz(creator_id);",
                "CREATE INDEX IF NOT EXISTS idx_quiz_is_active ON quiz_quiz(is_active);",
                
                # QuizAttempt indexes
                "CREATE INDEX IF NOT EXISTS idx_attempt_user ON quiz_quizattempt(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_attempt_quiz ON quiz_quizattempt(quiz_id);",
                "CREATE INDEX IF NOT EXISTS idx_attempt_started_at ON quiz_quizattempt(started_at);",
                
                # Branch indexes
                "CREATE INDEX IF NOT EXISTS idx_branch_slug ON branches_branch(slug);",
                "CREATE INDEX IF NOT EXISTS idx_branch_is_active ON branches_branch(is_active);",
                
                # Session indexes
                "CREATE INDEX IF NOT EXISTS idx_session_expire_date ON django_session(expire_date);",
                "CREATE INDEX IF NOT EXISTS idx_session_session_key ON django_session(session_key);",
            ]
            
            for index_sql in indexes:
                try:
                    cursor.execute(index_sql)
                    self.stdout.write(f'✓ Created index: {index_sql.split("idx_")[1].split(" ")[0]}')
                except Exception as e:
                    self.stdout.write(f'✗ Failed to create index: {e}')
                    logger.error(f"Failed to create index: {e}")
            
            # Analyze tables for better query planning
            try:
                cursor.execute("ANALYZE;")
                self.stdout.write('✓ Database statistics updated')
            except Exception as e:
                self.stdout.write(f'✗ Failed to analyze database: {e}')
                logger.error(f"Failed to analyze database: {e}")
        
        self.stdout.write(
            self.style.SUCCESS('Database optimization completed successfully!')
        )
