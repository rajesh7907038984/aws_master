from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from courses.models import CourseEnrollment, Course

User = get_user_model()


class Command(BaseCommand):
    help = 'Check course enrollments for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to check enrollments for')

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f"\n=== Course Enrollments for user: {username} ===")
            self.stdout.write(f"User ID: {user.id}")
            self.stdout.write(f"User Role: {user.role}")
            self.stdout.write(f"Branch: {user.branch.name if user.branch else 'None'}")
            
            # Get all enrollments
            enrollments = CourseEnrollment.objects.filter(
                user=user,
                course__is_active=True
            ).select_related('course', 'course__branch').order_by('course__title')
            
            self.stdout.write(f"\nTotal Active Course Enrollments: {enrollments.count()}")
            self.stdout.write("\n" + "="*70)
            
            if enrollments.exists():
                for i, enrollment in enumerate(enrollments, 1):
                    course = enrollment.course
                    self.stdout.write(f"\n{i}. Course: {course.title}")
                    self.stdout.write(f"   Course ID: {course.id}")
                    self.stdout.write(f"   Branch: {course.branch.name if course.branch else 'None'}")
                    self.stdout.write(f"   Active: {course.is_active}")
                    self.stdout.write(f"   Enrolled At: {enrollment.enrolled_at}")
                    self.stdout.write(f"   Completed: {enrollment.completed}")
                    if enrollment.completion_date:
                        self.stdout.write(f"   Completion Date: {enrollment.completion_date}")
            else:
                self.stdout.write(self.style.WARNING("\nNo active course enrollments found for this user."))
            
            # Show inactive course enrollments too
            inactive_enrollments = CourseEnrollment.objects.filter(
                user=user,
                course__is_active=False
            ).select_related('course', 'course__branch').count()
            
            if inactive_enrollments > 0:
                self.stdout.write(f"\n{inactive_enrollments} enrollment(s) in inactive courses (not shown above)")
            
            self.stdout.write("\n" + "="*70)
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"\nUser '{username}' not found in the database."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nError: {str(e)}"))

