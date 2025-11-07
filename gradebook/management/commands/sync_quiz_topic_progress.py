"""
Management command to sync missing TopicProgress records for historical quiz attempts.

This command creates TopicProgress records for quiz attempts that were completed
before the signal was implemented, ensuring consistent data across gradebook
and learning activities reports.

Usage:
    python manage.py sync_quiz_topic_progress
    python manage.py sync_quiz_topic_progress --course-id 83
    python manage.py sync_quiz_topic_progress --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from quiz.models import QuizAttempt, Quiz
from courses.models import Course, Topic, TopicProgress, CourseTopic
from users.models import CustomUser


class Command(BaseCommand):
    help = 'Sync TopicProgress records for historical quiz attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--course-id',
            type=int,
            help='Sync only for specific course ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually creating records'
        )

    def handle(self, *args, **options):
        course_id = options.get('course_id')
        dry_run = options.get('dry_run')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get completed quiz attempts
        attempts_query = QuizAttempt.objects.filter(is_completed=True).select_related('quiz', 'user')
        
        if course_id:
            # Filter by course
            course = Course.objects.get(id=course_id)
            # Get quizzes for this course
            quizzes = Quiz.objects.filter(
                Q(course=course) | Q(topics__courses=course)
            ).distinct()
            attempts_query = attempts_query.filter(quiz__in=quizzes)
            self.stdout.write(f'Syncing quiz attempts for course: {course.title} (ID: {course_id})')
        else:
            self.stdout.write('Syncing all quiz attempts')
        
        attempts = attempts_query.order_by('end_time')
        total_attempts = attempts.count()
        self.stdout.write(f'Found {total_attempts} completed quiz attempts')
        
        synced_count = 0
        skipped_count = 0
        error_count = 0
        
        for attempt in attempts:
            try:
                # Find topics that contain this quiz
                topics = Topic.objects.filter(quiz=attempt.quiz)
                
                if not topics.exists():
                    self.stdout.write(self.style.WARNING(
                        f'  Skipping attempt {attempt.id}: No topics found for quiz {attempt.quiz.id} ({attempt.quiz.title})'
                    ))
                    skipped_count += 1
                    continue
                
                # Get all courses this topic belongs to
                for topic in topics:
                    course_topics = CourseTopic.objects.filter(topic=topic).select_related('course')
                    
                    for course_topic in course_topics:
                        # Check if TopicProgress already exists
                        existing_tp = TopicProgress.objects.filter(
                            user=attempt.user,
                            topic=topic,
                            course=course_topic.course
                        ).first()
                        
                        if existing_tp:
                            # TopicProgress already exists
                            skipped_count += 1
                            continue
                        
                        if not dry_run:
                            # Create TopicProgress record
                            topic_progress = TopicProgress.objects.create(
                                user=attempt.user,
                                topic=topic,
                                course=course_topic.course,
                                completed=attempt.passed if hasattr(attempt, 'passed') else False,
                                last_score=attempt.score,
                                best_score=attempt.score,
                                attempts=1,
                                progress_data={
                                    'quiz_attempt_id': attempt.id,
                                    'quiz_score': float(attempt.score),
                                    'quiz_passed': attempt.passed if hasattr(attempt, 'passed') else False,
                                    'quiz_completed_at': attempt.end_time.isoformat() if attempt.end_time else None,
                                    'quiz_passing_score': float(attempt.quiz.passing_score) if attempt.quiz.passing_score else 70.0,
                                    'synced_from_historical_data': True
                                },
                                first_accessed=attempt.start_time,
                                last_accessed=attempt.end_time if attempt.end_time else attempt.start_time,
                                completed_at=attempt.end_time if (attempt.passed if hasattr(attempt, 'passed') else False) else None
                            )
                            
                            self.stdout.write(self.style.SUCCESS(
                                f'  ✓ Created TopicProgress: User={attempt.user.username}, '
                                f'Quiz={attempt.quiz.title}, Course={course_topic.course.title}, Score={attempt.score}%'
                            ))
                            synced_count += 1
                        else:
                            self.stdout.write(self.style.SUCCESS(
                                f'  [DRY RUN] Would create TopicProgress: User={attempt.user.username}, '
                                f'Quiz={attempt.quiz.title}, Course={course_topic.course.title}, Score={attempt.score}%'
                            ))
                            synced_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  ✗ Error processing attempt {attempt.id}: {str(e)}'
                ))
                error_count += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(self.style.SUCCESS('SYNC COMPLETE'))
        self.stdout.write(self.style.SUCCESS(f'Total attempts processed: {total_attempts}'))
        self.stdout.write(self.style.SUCCESS(f'TopicProgress records {"created" if not dry_run else "to be created"}: {synced_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped (already exists or no topic): {skipped_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        self.stdout.write(self.style.SUCCESS('='*60))

