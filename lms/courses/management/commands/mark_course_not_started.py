"""
Django management command to mark all topics in a course as not started.
"""

import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment, TopicProgress

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Mark all topics in a course as not started for a specific user'

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

    def handle(self, *args, **options):
        course_id = options['course_id']
        username = options['username']
        
        try:
            course = Course.objects.get(id=course_id)
            user = User.objects.get(username=username)
        except Course.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Course with ID {course_id} not found'))
            return
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User with username {username} not found'))
            return
            
        # Delete any enrollment
        CourseEnrollment.objects.filter(course=course, user=user).delete()
        self.stdout.write(self.style.SUCCESS(f'Removed enrollment for user {username} in course "{course.title}"'))
        
        # Delete any topic progress
        count = TopicProgress.objects.filter(
            user=user,
            topic__coursetopic__course=course
        ).delete()[0]
        
        self.stdout.write(self.style.SUCCESS(f'Removed {count} topic progress records for user {username} in course "{course.title}"'))
        self.stdout.write(self.style.SUCCESS(f'Course is now in NOT STARTED state')) 