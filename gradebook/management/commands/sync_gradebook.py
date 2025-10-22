from django.core.management.base import BaseCommand
from gradebook.models import Grade
from assignments.models import AssignmentSubmission
from courses.models import Course, Topic
from django.db import transaction

class Command(BaseCommand):
    help = 'Sync assignment submissions with grades to create missing Grade records in the gradebook'

    def add_arguments(self, parser):
        parser.add_argument(
            '--course',
            type=int,
            help='Limit sync to a specific course ID',
        )

    def handle(self, *args, **options):
        course_id = options.get('course')
        self.stdout.write(self.style.HTTP_INFO('Starting gradebook sync...'))
        
        # Get all assignment submissions with grades
        query = AssignmentSubmission.objects.filter(grade__isnull=False)
        
        if course_id:
            # Get all assignment topics for the course
            try:
                course = Course.objects.get(pk=course_id)
                topics = Topic.objects.filter(courses=course, content_type='Assignment')
                assignments = [t.assignment for t in topics if t.assignment]
                
                # Filter submissions for these assignments
                query = query.filter(assignment__in=assignments)
                self.stdout.write(self.style.HTTP_INFO(f"Syncing grades for course ID {course_id} only"))
            except Course.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Course with ID {course_id} not found"))
                return
        
        submissions = query.select_related('assignment', 'user')
        
        created_count = 0
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for submission in submissions:
                try:
                    # Make sure the assignment has a course
                    if not hasattr(submission.assignment, 'course') or not submission.assignment.course:
                        # Try to find course through topics
                        topics = Topic.objects.filter(assignment=submission.assignment)
                        if topics.exists():
                            topic = topics.first()
                            course_topic = topic.coursetopic_set.first()
                            course = course_topic.course if course_topic else None
                            
                            if course:
                                # Update assignment course
                                submission.assignment.course = course
                                submission.assignment.save(update_fields=['course'])
                                self.stdout.write(self.style.SUCCESS(
                                    f"Updated assignment {submission.assignment.id} to link to course {course.id}"
                                ))
                            else:
                                errors.append(f"Could not find course for assignment {submission.assignment.id}")
                                continue
                        else:
                            errors.append(f"Could not find topic for assignment {submission.assignment.id}")
                            continue
                    
                    # Get or create the grade record
                    grade, created = Grade.objects.update_or_create(
                        student=submission.user,
                        course=submission.assignment.course,
                        assignment=submission.assignment,
                        defaults={
                            'score': submission.grade,
                            'feedback': '',  # Add any feedback if necessary
                        }
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f"Created grade record: Student {submission.user.id}, "
                            f"Assignment {submission.assignment.id}, Score {submission.grade}"
                        ))
                        created_count += 1
                    else:
                        # Update existing grade if it doesn't match submission
                        if grade.score != submission.grade:
                            grade.score = submission.grade
                            grade.save()
                            self.stdout.write(self.style.SUCCESS(
                                f"Updated grade record: Student {submission.user.id}, "
                                f"Assignment {submission.assignment.id}, Score {submission.grade}"
                            ))
                            updated_count += 1
                
                except Exception as e:
                    errors.append(f"Error processing submission {submission.id}: {str(e)}")
        
        self.stdout.write(self.style.SUCCESS(f"\nGrade sync complete:"))
        self.stdout.write(self.style.SUCCESS(f"- Created {created_count} new grade records"))
        self.stdout.write(self.style.SUCCESS(f"- Updated {updated_count} existing grade records"))
        
        if errors:
            self.stdout.write(self.style.WARNING(f"- Encountered {len(errors)} errors:"))
            for error in errors:
                self.stdout.write(self.style.WARNING(f"  - {error}"))
        else:
            self.stdout.write(self.style.SUCCESS("- No errors encountered")) 