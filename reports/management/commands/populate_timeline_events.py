from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from courses.models import CourseEnrollment
from quiz.models import QuizAttempt
from assignments.models import AssignmentSubmission
from discussions.models import Discussion
from reports.models import Event
from datetime import timedelta
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate timeline with events based on existing data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing events before populating',
        )

    def handle(self, *args, **options):
        if options['clear_existing']:
            Event.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared existing events.'))

        # Create login events for active users
        self.create_login_events()
        
        # Create course enrollment events
        self.create_course_events()
        
        # Create quiz attempt events
        self.create_quiz_events()
        
        # Create assignment submission events
        self.create_assignment_events()
        
        # Create forum post events
        self.create_forum_events()

        self.stdout.write(self.style.SUCCESS('Successfully populated timeline with events.'))

    def create_login_events(self):
        """Create login events for active users in the last 30 days"""
        active_users = User.objects.filter(
            last_login__gte=timezone.now() - timedelta(days=30)
        )
        
        for user in active_users:
            # Create 1-3 login events per user
            login_count = random.randint(1, 3)
            for _ in range(login_count):
                login_date = user.last_login - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                
                Event.objects.get_or_create(
                    user=user,
                    type='LOGIN',
                    created_at=login_date,
                    defaults={
                        'description': f"{user.get_full_name() or user.username} logged in"
                    }
                )
        
        self.stdout.write(f'Created login events for {active_users.count()} users.')

    def create_course_events(self):
        """Create course enrollment and completion events"""
        enrollments = CourseEnrollment.objects.select_related('user', 'course')
        
        for enrollment in enrollments:
            # Create enrollment event
            Event.objects.get_or_create(
                user=enrollment.user,
                course=enrollment.course,
                type='COURSE_START',
                created_at=enrollment.enrolled_at,
                defaults={
                    'description': f"{enrollment.user.get_full_name() or enrollment.user.username} enrolled in {enrollment.course.title}"
                }
            )
            
            # Create completion event if completed
            if enrollment.completed and enrollment.completion_date:
                Event.objects.get_or_create(
                    user=enrollment.user,
                    course=enrollment.course,
                    type='COURSE_COMPLETE',
                    created_at=enrollment.completion_date,
                    defaults={
                        'description': f"{enrollment.user.get_full_name() or enrollment.user.username} completed {enrollment.course.title}"
                    }
                )
        
        self.stdout.write(f'Created course events for {enrollments.count()} enrollments.')

    def create_quiz_events(self):
        """Create quiz attempt events"""
        attempts = QuizAttempt.objects.select_related('user', 'quiz')
        
        for attempt in attempts:
            course = None
            if hasattr(attempt.quiz, 'course'):
                course = attempt.quiz.course
            
            Event.objects.get_or_create(
                user=attempt.user,
                course=course,
                type='QUIZ_TAKE',
                created_at=attempt.start_time,
                defaults={
                    'description': f"{attempt.user.get_full_name() or attempt.user.username} took quiz: {attempt.quiz.title}",
                    'metadata': {
                        'quiz_id': attempt.quiz.id,
                        'score': getattr(attempt, 'score', None),
                        'passed': getattr(attempt, 'passed', None)
                    }
                }
            )
        
        self.stdout.write(f'Created quiz events for {attempts.count()} attempts.')

    def create_assignment_events(self):
        """Create assignment submission events"""
        submissions = AssignmentSubmission.objects.select_related('user', 'assignment')
        
        for submission in submissions:
            course = None
            if hasattr(submission.assignment, 'course'):
                course = submission.assignment.course
            
            Event.objects.get_or_create(
                user=submission.user,
                course=course,
                type='ASSIGNMENT_SUBMIT',
                created_at=submission.submitted_at,
                defaults={
                    'description': f"{submission.user.get_full_name() or submission.user.username} submitted assignment: {submission.assignment.title}",
                    'metadata': {
                        'assignment_id': submission.assignment.id,
                        'submission_id': submission.id
                    }
                }
            )
        
        self.stdout.write(f'Created assignment events for {submissions.count()} submissions.')

    def create_forum_events(self):
        """Create forum post events"""
        discussions = Discussion.objects.select_related('user')
        
        for discussion in discussions:
            course = None
            if hasattr(discussion, 'course'):
                course = discussion.course
            
            Event.objects.get_or_create(
                user=discussion.user,
                course=course,
                type='FORUM_POST',
                created_at=discussion.created_at,
                defaults={
                    'description': f"{discussion.user.get_full_name() or discussion.user.username} created a forum post: {discussion.title[:50]}...",
                    'metadata': {
                        'discussion_id': discussion.id,
                        'title': discussion.title
                    }
                }
            )
        
        self.stdout.write(f'Created forum events for {discussions.count()} discussions.') 