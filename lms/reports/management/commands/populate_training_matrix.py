from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from courses.models import Course, Topic, CourseEnrollment, TopicProgress, CourseTopic
from django.utils import timezone
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Populates dummy data for training matrix'

    def handle(self, *args, **kwargs):
        # Create dummy courses
        course_titles = [
            'Python Programming Basics',
            'Web Development Fundamentals',
            'Data Science Essentials',
            'Project Management',
            'Leadership Skills',
            'Communication Skills',
            'Time Management',
            'Customer Service Excellence'
        ]

        # Create courses if they don't exist
        for title in course_titles:
            course, created = Course.objects.get_or_create(
                title=title,
                defaults={
                    'description': f'Learn {title} with our comprehensive course',
                    'is_active': True,
                    'catalog_visibility': 'visible',
                    'public_enrollment': True,
                    'enforce_sequence': False,
                    'completion_percentage': 100,
                    'passing_score': 70
                }
            )
            
            if created:
                self.stdout.write(f"Created course: {title}")
                # Create topics for each course
                for i in range(1, 6):
                    topic_title = f'Topic {i} - {title}'
                    topic, topic_created = Topic.objects.get_or_create(
                        title=topic_title,
                        defaults={
                            'description': f'Description for Topic {i} of {title}',
                            'content_type': random.choice(['Text', 'Video', 'Document', 'Web']),
                            'status': 'active',
                            'order': i,
                        }
                    )
                    
                    if topic_created:
                        self.stdout.write(f"Created topic: {topic_title}")
                    
                    # Connect topic to course
                    CourseTopic.objects.get_or_create(
                        course=course,
                        topic=topic,
                        defaults={'order': i}
                    )

        # Create dummy users if they don't exist
        usernames = ['learner1', 'learner2', 'learner3', 'learner4', 'learner5']
        for username in usernames:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': f'First {username}',
                    'last_name': f'Last {username}'
                }
            )
            if created:
                self.stdout.write(f"Created user: {username}")

        # Create enrollments and progress
        courses = Course.objects.all()
        users = User.objects.filter(username__in=usernames)

        for user in users:
            for course in courses:
                # Random enrollment status
                status = random.choice(['not_started', 'in_progress', 'completed'])
                
                enrollment, created = CourseEnrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={
                        'enrolled_at': timezone.now(),
                        'completed': status == 'completed',
                        'completion_date': timezone.now() if status == 'completed' else None,
                        'last_accessed': timezone.now() if status != 'not_started' else None
                    }
                )
                
                if created:
                    self.stdout.write(f"Enrolled {user.username} in {course.title} with status: {status}")

                # Create topic progress
                course_topics = CourseTopic.objects.filter(course=course)
                for course_topic in course_topics:
                    topic = course_topic.topic
                    if status != 'not_started':
                        progress = 100 if status == 'completed' else random.randint(0, 100)
                        topic_progress, progress_created = TopicProgress.objects.get_or_create(
                            user=user,
                            topic=topic,
                            defaults={
                                'progress_data': {'progress': progress},
                                'completed': progress == 100,
                                'last_score': random.randint(70, 100) if progress == 100 else None,
                                'completed_at': timezone.now() if progress == 100 else None
                            }
                        )
                        
                        if progress_created:
                            progress_status = "completed" if progress == 100 else f"{progress}% complete"
                            self.stdout.write(f"Created progress for {user.username} on {topic.title}: {progress_status}")

        self.stdout.write(self.style.SUCCESS('Successfully populated training matrix data')) 