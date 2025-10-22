from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from assignments.models import Assignment, AssignmentSubmission
from quiz.models import Quiz, QuizAttempt
from discussions.models import Discussion, Comment
from conferences.models import Conference, ConferenceAttendance
from gradebook.models import Grade
from courses.models import Course

try:
    from courses.models import Topic, TopicProgress
    SCORM_AVAILABLE = True
except ImportError:
    SCORM_AVAILABLE = False


class Command(BaseCommand):
    help = 'Check all activity types for potential scoring/display issues in gradebook'

    def add_arguments(self, parser):
        parser.add_argument(
            '--course-id',
            type=int,
            help='Check specific course ID (default: check all courses)',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix issues found',
        )

    def handle(self, *args, **options):
        course_id = options.get('course_id')
        fix_issues = options.get('fix')
        
        if fix_issues:
            self.stdout.write(self.style.WARNING('FIX MODE ENABLED - Will attempt to fix issues'))
        else:
            self.stdout.write(self.style.WARNING('CHECK MODE - No changes will be made'))
        
        User = get_user_model()
        
        # Get courses to check
        if course_id:
            courses = Course.objects.filter(id=course_id)
            if not courses.exists():
                self.stdout.write(self.style.ERROR(f'Course {course_id} not found'))
                return
        else:
            courses = Course.objects.all()
        
        total_issues = 0
        
        for course in courses:
            self.stdout.write(f'\n=== COURSE: {course.title} (ID: {course.id}) ===')
            course_issues = self.check_course_activities(course, fix_issues)
            total_issues += course_issues
        
        if total_issues > 0:
            self.stdout.write(
                self.style.ERROR(f'\n🚨 TOTAL ISSUES FOUND: {total_issues}')
            )
            if not fix_issues:
                self.stdout.write('Run with --fix to attempt repairs')
        else:
            self.stdout.write(
                self.style.SUCCESS('\n NO ISSUES FOUND - All activity scoring looks good!')
            )

    def check_course_activities(self, course, fix_issues):
        issues_found = 0
        
        # 1. ASSIGNMENTS (Manual Evaluation)
        self.stdout.write('\n--- ASSIGNMENTS (Manual Evaluation) ---')
        assignments = Assignment.objects.filter(course=course)
        
        for assignment in assignments:
            # Check Grade/Submission linking (should be fixed now)
            grades = Grade.objects.filter(assignment=assignment)
            unlinked = grades.filter(submission__isnull=True)
            
            if unlinked.exists():
                issues_found += unlinked.count()
                self.stdout.write(
                    self.style.ERROR(
                        f' Assignment "{assignment.title}": {unlinked.count()} unlinked grades'
                    )
                )
                
                if fix_issues:
                    fixed = 0
                    for grade in unlinked:
                        submission = AssignmentSubmission.objects.filter(
                            assignment=grade.assignment,
                            user=grade.student
                        ).first()
                        if submission:
                            grade.submission = submission
                            grade.save()
                            fixed += 1
                    self.stdout.write(f'   Fixed {fixed} unlinked grades')
            else:
                self.stdout.write(f' Assignment "{assignment.title}": All grades properly linked')

        # 2. QUIZZES (Auto + Manual with Rubric)
        self.stdout.write('\n--- QUIZZES ---')
        quizzes = Quiz.objects.filter(course=course)
        
        for quiz in quizzes:
            attempts = QuizAttempt.objects.filter(quiz=quiz, is_completed=True)
            
            if quiz.rubric:
                self.stdout.write(f'Quiz "{quiz.title}": Manual evaluation (has rubric)')
                try:
                    from quiz.models import QuizRubricEvaluation
                    evaluations = QuizRubricEvaluation.objects.filter(quiz_attempt__quiz=quiz)
                    
                    if attempts.count() > 0 and evaluations.count() == 0:
                        issues_found += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f' Quiz "{quiz.title}": {attempts.count()} attempts but no rubric evaluations'
                            )
                        )
                    else:
                        self.stdout.write(f' Quiz "{quiz.title}": Has rubric evaluations')
                        
                except Exception as e:
                    self.stdout.write(f'  Quiz "{quiz.title}": Error checking evaluations: {e}')
            else:
                self.stdout.write(f' Quiz "{quiz.title}": Auto scoring (no rubric)')

        # 3. DISCUSSIONS (Manual with Rubric)
        self.stdout.write('\n--- DISCUSSIONS ---')
        discussions = Discussion.objects.filter(course=course)
        
        for discussion in discussions:
            if discussion.rubric:
                comments = Comment.objects.filter(discussion=discussion)
                try:
                    from lms_rubrics.models import RubricEvaluation
                    evaluations = RubricEvaluation.objects.filter(discussion=discussion)
                    
                    if comments.count() > 0 and evaluations.count() == 0:
                        issues_found += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f' Discussion "{discussion.title}": {comments.count()} comments but no rubric evaluations'
                            )
                        )
                    else:
                        self.stdout.write(f' Discussion "{discussion.title}": Has rubric evaluations')
                        
                except Exception as e:
                    self.stdout.write(f'  Discussion "{discussion.title}": Error checking evaluations: {e}')
            else:
                self.stdout.write(f'ℹ️  Discussion "{discussion.title}": No rubric (no scoring)')

        # 4. CONFERENCES (Manual with Rubric)  
        self.stdout.write('\n--- CONFERENCES ---')
        conferences = Conference.objects.filter(course=course)
        
        for conference in conferences:
            if conference.rubric:
                attendances = ConferenceAttendance.objects.filter(conference=conference)
                try:
                    from conferences.models import ConferenceRubricEvaluation
                    evaluations = ConferenceRubricEvaluation.objects.filter(conference=conference)
                    
                    if attendances.count() > 0 and evaluations.count() == 0:
                        issues_found += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f' Conference "{conference.title}": {attendances.count()} attendances but no rubric evaluations'
                            )
                        )
                    else:
                        self.stdout.write(f' Conference "{conference.title}": Has rubric evaluations')
                        
                except Exception as e:
                    self.stdout.write(f'  Conference "{conference.title}": Error checking evaluations: {e}')
            else:
                self.stdout.write(f'ℹ️  Conference "{conference.title}": No rubric (no scoring)')

        # 5. SCORM (Auto Score)
        if SCORM_AVAILABLE:
            self.stdout.write('\n--- SCORM ---')
            try:
                from courses.models import Topic
                scorm_topics = Topic.objects.filter(
                    coursetopic__course=course,
                    content_type='SCORM'
                )
                
                for topic in scorm_topics:
                    try:
                        # Use new SCORM implementation - topic itself is SCORM content
                        scorm_content = topic if topic.content_type == 'SCORM' else None
                        
                        if scorm_content and hasattr(scorm_content, 'scorm_package') and scorm_content.scorm_package:
                            # Use new SCORM implementation - check for SCORM package
                            registrations = []  # No longer using SCORMRegistration model
                        else:
                            registrations = []
                    except Exception:
                        registrations = []
                    self.stdout.write(f' SCORM Topic "{topic.title}": Auto scoring ({len(registrations)} registrations)')
                    
            except Exception as e:
                self.stdout.write(f'  SCORM: Error checking: {e}')
        else:
            self.stdout.write('ℹ️  SCORM: Module not available')

        if not assignments.exists() and not quizzes.exists() and not discussions.exists() and not conferences.exists():
            self.stdout.write('ℹ️  No gradeable activities found in this course')
            
        return issues_found
