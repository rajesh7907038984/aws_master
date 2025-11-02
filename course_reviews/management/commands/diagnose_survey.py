"""
Management command to diagnose survey-related issues
Usage: python manage.py diagnose_survey <course_id>
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from courses.models import Course, CourseEnrollment
from course_reviews.models import Survey, SurveyField, SurveyResponse, CourseReview

User = get_user_model()


class Command(BaseCommand):
    help = 'Diagnose survey issues for a specific course'

    def add_arguments(self, parser):
        parser.add_argument('course_id', type=int, help='Course ID to diagnose')
        parser.add_argument(
            '--user-id',
            type=int,
            help='Optional: Specific user ID to check'
        )

    def handle(self, *args, **options):
        course_id = options['course_id']
        user_id = options.get('user_id')

        self.stdout.write(self.style.SUCCESS(f'\n=== Diagnosing Survey for Course {course_id} ===\n'))

        # Check if course exists
        try:
            course = Course.objects.get(id=course_id)
            self.stdout.write(self.style.SUCCESS(f'✓ Course found: {course.title}'))
        except Course.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Course {course_id} does not exist!'))
            return

        # Check if course has a survey
        if not hasattr(course, 'survey') or not course.survey:
            self.stdout.write(self.style.ERROR('✗ Course has NO survey assigned!'))
            self.stdout.write(self.style.WARNING('  → Solution: Assign a survey to this course in the admin panel'))
            return
        
        survey = course.survey
        self.stdout.write(self.style.SUCCESS(f'✓ Survey found: {survey.title}'))
        self.stdout.write(f'  - Survey ID: {survey.id}')
        self.stdout.write(f'  - Active: {survey.is_active}')
        self.stdout.write(f'  - Description: {survey.description or "(none)"}')

        # Check survey fields
        fields = survey.fields.all()
        field_count = fields.count()
        
        if field_count == 0:
            self.stdout.write(self.style.ERROR('✗ Survey has NO fields/questions!'))
            self.stdout.write(self.style.WARNING('  → Solution: Add fields to the survey'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'✓ Survey has {field_count} field(s)'))
        for field in fields:
            self.stdout.write(f'  - {field.label} ({field.field_type}, required: {field.is_required})')

        # Check enrollments
        enrollments = CourseEnrollment.objects.filter(course=course)
        total_enrollments = enrollments.count()
        completed_enrollments = enrollments.filter(completed=True).count()
        
        self.stdout.write(f'\n✓ Course Enrollments:')
        self.stdout.write(f'  - Total: {total_enrollments}')
        self.stdout.write(f'  - Completed: {completed_enrollments}')

        # Check reviews
        reviews = CourseReview.objects.filter(course=course, survey=survey)
        review_count = reviews.count()
        self.stdout.write(f'\n✓ Survey Responses: {review_count}')

        # User-specific checks
        if user_id:
            self.stdout.write(f'\n=== User-Specific Checks (User ID: {user_id}) ===\n')
            try:
                user = User.objects.get(id=user_id)
                self.stdout.write(self.style.SUCCESS(f'✓ User found: {user.username}'))
                
                # Check enrollment
                try:
                    enrollment = CourseEnrollment.objects.get(user=user, course=course)
                    self.stdout.write(f'✓ User is enrolled')
                    self.stdout.write(f'  - Completed: {enrollment.completed}')
                    self.stdout.write(f'  - Enrolled at: {enrollment.enrolled_at}')
                    if enrollment.completion_date:
                        self.stdout.write(f'  - Completed at: {enrollment.completion_date}')
                    
                    if not enrollment.completed:
                        self.stdout.write(self.style.WARNING('  ⚠ User has NOT completed the course yet'))
                except CourseEnrollment.DoesNotExist:
                    self.stdout.write(self.style.ERROR('✗ User is NOT enrolled in this course!'))
                
                # Check if user has submitted a review
                user_review = CourseReview.objects.filter(user=user, course=course, survey=survey).first()
                if user_review:
                    self.stdout.write(f'✓ User has submitted a review')
                    self.stdout.write(f'  - Rating: {user_review.average_rating}')
                    self.stdout.write(f'  - Submitted at: {user_review.submitted_at}')
                else:
                    self.stdout.write('ℹ User has NOT submitted a review yet')
                    
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'✗ User {user_id} does not exist!'))

        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Diagnostic Summary ==='))
        if field_count > 0 and survey.is_active:
            self.stdout.write(self.style.SUCCESS('✓ Survey is properly configured and should work'))
            self.stdout.write(f'\nℹ Survey URL: /course-reviews/course/{course_id}/survey/')
        else:
            self.stdout.write(self.style.ERROR('✗ Survey has configuration issues that need to be fixed'))

