from django.core.management.base import BaseCommand
from django.db import transaction
from courses.models import Topic, CourseTopic
from assignments.models import Assignment, AssignmentCourse

class Command(BaseCommand):
    help = 'Fix missing AssignmentCourse relationships for assignments linked through topics'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting assignment-topic-course fix...'))
        self.stdout.write('-' * 60)
        
        # Get all topics that are assignments
        assignment_topics = Topic.objects.filter(
            content_type='Assignment',
            assignment__isnull=False
        ).select_related('assignment')
        
        self.stdout.write(self.style.SUCCESS(f'Found {assignment_topics.count()} assignment topics'))
        
        fixed_count = 0
        already_linked_count = 0
        no_course_count = 0
        
        with transaction.atomic():
            for topic in assignment_topics:
                assignment = topic.assignment
                
                # Find all courses this topic belongs to
                course_topics = CourseTopic.objects.filter(topic=topic).select_related('course')
                
                if not course_topics.exists():
                    self.stdout.write(self.style.WARNING(
                        f'Topic "{topic.title}" (ID: {topic.id}) with assignment "{assignment.title}" '
                        f'(ID: {assignment.id}) is not linked to any course'
                    ))
                    no_course_count += 1
                    continue
                
                for course_topic in course_topics:
                    course = course_topic.course
                    
                    # Check if AssignmentCourse relationship exists
                    assignment_course, created = AssignmentCourse.objects.get_or_create(
                        assignment=assignment,
                        course=course,
                        defaults={'is_primary': True}
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f'✓ Fixed: Linked assignment "{assignment.title}" (ID: {assignment.id}) '
                            f'to course "{course.title}" (ID: {course.id})'
                        ))
                        fixed_count += 1
                    else:
                        self.stdout.write(
                            f'  Already linked: Assignment "{assignment.title}" (ID: {assignment.id}) '
                            f'to course "{course.title}" (ID: {course.id})'
                        )
                        already_linked_count += 1
        
        self.stdout.write('-' * 60)
        self.stdout.write(self.style.SUCCESS(f'\nSummary:'))
        self.stdout.write(f'  - Fixed (new links created): {fixed_count}')
        self.stdout.write(f'  - Already linked (no action needed): {already_linked_count}')
        self.stdout.write(f'  - Not linked to any course: {no_course_count}')
        self.stdout.write(f'  - Total: {fixed_count + already_linked_count + no_course_count}')
        self.stdout.write(self.style.SUCCESS('\n✅ Fix completed!'))

