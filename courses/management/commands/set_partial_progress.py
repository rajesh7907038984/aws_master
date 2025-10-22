"""
Django management command to manually set a course enrollment's completion status.
"""

import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Manually set a course enrollment completion status without modifying topics'

    def add_arguments(self, parser):
        parser.add_argument(
            'course_id',
            type=int,
            help='ID of the course to modify'
        )
        parser.add_argument(
            'username',
            type=str,
            help='Username of the user'
        )
        parser.add_argument(
            '--completed',
            action='store_true',
            help='Mark as completed (if not specified, marks as not completed)'
        )

    def handle(self, *args, **options):
        course_id = options['course_id']
        username = options['username']
        completed = options['completed']
        
        try:
            course = Course.objects.get(id=course_id)
            user = User.objects.get(username=username)
        except Course.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Course with ID {course_id} not found'))
            return
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User with username {username} not found'))
            return
            
        try:
            enrollment = CourseEnrollment.objects.get(course=course, user=user)
        except CourseEnrollment.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'No enrollment found for user {username} in course {course.title}'))
            return
            
        # Update completion status
        enrollment.completed = completed
        if completed:
            from django.utils import timezone
            enrollment.completion_date = timezone.now()
            self.stdout.write(self.style.SUCCESS(f'Marked course "{course.title}" as COMPLETED for {username}'))
        else:
            enrollment.completion_date = None
            self.stdout.write(self.style.SUCCESS(f'Marked course "{course.title}" as NOT COMPLETED for {username}'))
                
        enrollment.save() 