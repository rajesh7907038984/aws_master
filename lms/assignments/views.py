import logging
import json
import os
import re
import shutil
import uuid
import mimetypes
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Count, F, Max, OuterRef, Q, Subquery
from django.http import (FileResponse, Http404, HttpResponse,
                         HttpResponseForbidden, HttpResponseRedirect,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.core.files.storage import FileSystemStorage

from courses.models import Course, Topic, CourseEnrollment

try:
    from courses.models import CourseTopic
except ImportError:
    from courses.models import Course
    CourseTopic = Course.topics.through if hasattr(Course, "topics") else None

from courses.views import get_topic_course, check_instructor_management_access
from lms_rubrics.models import Rubric, RubricRating, RubricEvaluation, RubricCriterion, RubricEvaluationHistory
from users.models import CustomUser
from quiz.models import Quiz

from .forms import (AssignmentForm, AssignmentGradingForm, TextQuestionForm, SupportingDocQuestionForm)
from .models import (Assignment, AssignmentAttachment, AssignmentCourse,
                    AssignmentSubmission, AssignmentFeedback, GradeHistory,
                    TextQuestion, TextQuestionAnswer, TextSubmissionField,
                    TopicAssignment, TextSubmissionAnswer, 
                    SupportingDocQuestion, StudentAnswer, AssignmentComment,
                    TextQuestionAnswerIteration, TextQuestionIterationFeedback,
                    TextSubmissionAnswerIteration, TextSubmissionIterationFeedback,
                    AssignmentInteractionLog, AssignmentSessionLog)
from core.rbac_validators import ConditionalAccessValidator

# Configure logger
logger = logging.getLogger(__name__)


def create_or_get_latest_iteration(question_or_field, submission, iteration_type='question'):
    """
    Create or get the latest iteration for a question or field.
    Returns the iteration object and whether it was created.
    """
    if iteration_type == 'question':
        iteration_model = TextQuestionAnswerIteration
        filter_key = 'question'
    else:
        iteration_model = TextSubmissionAnswerIteration
        filter_key = 'field'
    
    # Get the latest iteration
    latest_iteration = iteration_model.objects.filter(
        **{filter_key: question_or_field}, 
        submission=submission
    ).order_by('-iteration_number').first()
    
    if not latest_iteration:
        # Create first iteration
        iteration_number = 1
        iteration = iteration_model.objects.create(
            **{filter_key: question_or_field},
            submission=submission,
            iteration_number=iteration_number,
            answer_text='',
            is_submitted=False
        )
        return iteration, True
    
    # Check if we can create a new iteration
    if latest_iteration.is_submitted and latest_iteration.can_submit_new_iteration():
        # Create new iteration
        iteration_number = latest_iteration.iteration_number + 1
        iteration = iteration_model.objects.create(
            **{filter_key: question_or_field},
            submission=submission,
            iteration_number=iteration_number,
            answer_text='',
            is_submitted=False
        )
        return iteration, True
    
    return latest_iteration, False


def get_iteration_data_for_question(question, submission):
    """
    Get all iteration data for a specific question and submission.
    Returns a dictionary with iteration information and current status.
    """
    iterations = TextQuestionAnswerIteration.objects.filter(
        question=question,
        submission=submission
    ).order_by('iteration_number').prefetch_related('feedback_entries__created_by')
    
    # Get or create current editable iteration
    current_iteration, created = create_or_get_latest_iteration(question, submission, 'question')
    
    # Allow learners to add new iterations ONLY if:
    # 1. Assignment is returned for revision, OR 
    # 2. No iterations exist yet (first submission)
    can_add_new = False
    
    # Check if assignment is returned for revision
    if submission.status == 'returned':
        can_add_new = True
    elif not iterations.exists():
        # If no iterations exist yet, allow first submission
        can_add_new = True
    
    return {
        'question': question,
        'iterations': iterations,
        'current_iteration': current_iteration,
        'can_add_new': can_add_new,
        'total_iterations': iterations.count()
    }


def get_iteration_data_for_field(field, submission):
    """
    Get all iteration data for a specific field and submission.
    Returns a dictionary with iteration information and current status.
    """
    # Include all iterations, even initial feedback (iteration_number=0, is_submitted=False)
    iterations = TextSubmissionAnswerIteration.objects.filter(
        field=field,
        submission=submission
    ).order_by('iteration_number').prefetch_related('feedback_entries__created_by')
    
    # Get or create current editable iteration
    current_iteration, created = create_or_get_latest_iteration(field, submission, 'field')
    
    # Allow learners to add new iterations ONLY if:
    # 1. Assignment is returned for revision, OR 
    # 2. No iterations exist yet (first submission)
    can_add_new = False
    
    # Check if assignment is returned for revision
    if submission.status == 'returned':
        can_add_new = True
    elif not iterations.exists():
        # If no iterations exist yet, allow first submission
        can_add_new = True
    
    return {
        'field': field,
        'iterations': iterations,
        'current_iteration': current_iteration,
        'can_add_new': can_add_new,
        'total_iterations': iterations.count()
    }


def get_user_display_name(user):
    """
    Helper function to get the best available display name for a user.
    Tries get_full_name() first, then falls back to given_names + family_name,
    then just first_name + last_name, finally username.
    """
    if not user:
        return "Unknown User"
    
    # Try the standard get_full_name method first
    full_name = user.get_full_name()
    if full_name and full_name.strip():
        return full_name.strip()
    
    # Fall back to given_names + family_name (custom fields)
    if hasattr(user, 'given_names') and hasattr(user, 'family_name'):
        if user.given_names and user.family_name:
            return f"{user.given_names} {user.family_name}".strip()
        elif user.given_names:
            return user.given_names.strip()
        elif user.family_name:
            return user.family_name.strip()
    
    # Fall back to first_name + last_name
    if user.first_name or user.last_name:
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    
    # Final fallback to username
    return user.username


def sync_assignment_courses(assignment):
    """
    Ensure an assignment has its courses properly synchronized between:
    1. The direct course field
    2. The many-to-many relationship through AssignmentCourse
    3. Any topics they're associated with
    """
    # First, get all possible courses this assignment should be linked to
    all_course_ids = set()
    
    # 1. Direct course field
    if assignment.course:
        all_course_ids.add(assignment.course.id)
    
    # 2. Courses via topics
    topic_course_ids = Course.objects.filter(
        coursetopic__topic__topicassignment__assignment=assignment
    ).values_list('id', flat=True).distinct()
    all_course_ids.update(topic_course_ids)
    
    # Ensure all identified courses exist in the many-to-many relationship
    for course_id in all_course_ids:
        try:
            course = Course.objects.get(id=course_id)
            
            # Check if already exists in the many-to-many relationship
            if not AssignmentCourse.objects.filter(assignment=assignment, course=course).exists():
                # Determine if this should be primary
                is_primary = assignment.course and assignment.course.id == course_id
                
                # If no primary relationship exists yet, make the first one primary
                if not is_primary and not AssignmentCourse.objects.filter(assignment=assignment, is_primary=True).exists():
                    is_primary = True
                
                # Create the relationship
                AssignmentCourse.objects.create(
                    assignment=assignment,
                    course=course,
                    is_primary=is_primary
                )
                logger.info(f"Added course {course.id} to assignment {assignment.id} via sync")
                
                # If this is primary and assignment has no primary course, set it
                if is_primary and not assignment.course:
                    assignment.course = course
                    assignment.save(update_fields=['course'])
                    logger.info(f"Set primary course {course.id} for assignment {assignment.id} via sync")
        except Course.DoesNotExist:
            logger.warning(f"Course ID {course_id} does not exist but was referenced in assignment {assignment.id}")
    
    # Make sure at least one course is set as primary if courses exist
    if all_course_ids and not AssignmentCourse.objects.filter(assignment=assignment, is_primary=True).exists():
        # Get the first relationship and make it primary
        first_ac = AssignmentCourse.objects.filter(assignment=assignment).first()
        if first_ac:
            first_ac.is_primary = True
            first_ac.save(update_fields=['is_primary'])
            
            # Update the direct course reference if not set
            if not assignment.course:
                assignment.course = first_ac.course
                assignment.save(update_fields=['course'])
                logger.info(f"Set primary course {first_ac.course.id} for assignment {assignment.id} via sync (fallback)")
    
    # Check for orphaned relationships that no longer correspond to topic associations
    current_ac_course_ids = AssignmentCourse.objects.filter(assignment=assignment).values_list('course_id', flat=True)
    orphaned_course_ids = set(current_ac_course_ids) - all_course_ids
    
    # Don't remove relationships that match the direct course
    if assignment.course and assignment.course.id in orphaned_course_ids:
        orphaned_course_ids.remove(assignment.course.id)
    
    # Log orphaned courses but don't remove them to avoid data loss
    for orphaned_id in orphaned_course_ids:
        logger.info(f"Course {orphaned_id} is linked to assignment {assignment.id} but not through topics or direct reference")

@login_required
def assignment_list(request):
    """View to display list of assignments"""
    # Get course filter parameter
    course_filter_id = request.GET.get('course_id')
    
    # RBAC v0.1 Compliant Access Control
    from core.rbac_validators import rbac_validator
    
    if request.user.role == 'globaladmin':
        # Global Admin: FULL access to all assignments
        assignments_list = Assignment.objects.all()
        available_courses = Course.objects.all().order_by('title')
        can_create = True
        can_edit = True
        is_student_view = False
        
        # Filter by course if specified
        if course_filter_id:
            try:
                course_filter_id = int(course_filter_id)
                assignments_list = assignments_list.filter(
                    Q(course_id=course_filter_id) | 
                    Q(courses__id=course_filter_id) |
                    Q(topicassignment__topic__courses__id=course_filter_id)
                ).distinct()
            except (ValueError, TypeError):
                pass
        assignments_list = assignments_list.order_by('-created_at')
        
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped assignments)
        if hasattr(request.user, 'business_assignments'):
            assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            assignments_list = Assignment.objects.filter(
                user__branch__business__in=assigned_businesses
            )
            available_courses = Course.objects.filter(branch__business__in=assigned_businesses).order_by('title')
        else:
            assignments_list = Assignment.objects.none()
            available_courses = Course.objects.none()
        can_create = True
        can_edit = True
        is_student_view = False
        
        # Filter by course if specified
        if course_filter_id:
            try:
                course_filter_id = int(course_filter_id)
                assignments_list = assignments_list.filter(
                    Q(course_id=course_filter_id) | 
                    Q(courses__id=course_filter_id) |
                    Q(topicassignment__topic__courses__id=course_filter_id)
                ).distinct()
            except (ValueError, TypeError):
                pass
        assignments_list = assignments_list.order_by('-created_at')
        
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped assignments, supports branch switching)
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        if effective_branch:
            assignments_list = Assignment.objects.filter(
                user__branch=effective_branch
            )
            available_courses = Course.objects.filter(branch=effective_branch).order_by('title')
        else:
            assignments_list = Assignment.objects.none()
            available_courses = Course.objects.none()
        can_create = True
        can_edit = True
        is_student_view = False
        
        # Filter by course if specified
        if course_filter_id:
            try:
                course_filter_id = int(course_filter_id)
                assignments_list = assignments_list.filter(
                    Q(course_id=course_filter_id) | 
                    Q(courses__id=course_filter_id) |
                    Q(topicassignment__topic__courses__id=course_filter_id)
                ).distinct()
            except (ValueError, TypeError):
                pass
        assignments_list = assignments_list.order_by('-created_at')
        
    elif request.user.role == 'instructor':
        # Instructor: CONDITIONAL access (own assignments + assigned courses + group-assigned courses)
        if request.user.branch:
            # Own assignments
            own_assignments = Assignment.objects.filter(user=request.user)
            
            # Assignments from directly assigned courses
            assigned_courses = Course.objects.filter(instructor=request.user)
            course_assignments = Assignment.objects.filter(
                Q(course__in=assigned_courses) | Q(courses__in=assigned_courses)
            )
            
            # Assignments from group-assigned courses
            group_assigned_courses = Course.objects.filter(
                accessible_groups__memberships__user=request.user,
                accessible_groups__memberships__is_active=True,
                accessible_groups__memberships__custom_role__name__icontains='instructor'
            )
            group_course_assignments = Assignment.objects.filter(
                Q(course__in=group_assigned_courses) | Q(courses__in=group_assigned_courses)
            )
            
            # Also include assignments from courses where they are enrolled as instructor
            enrolled_courses = Course.objects.filter(
                enrolled_users=request.user
            )
            enrolled_course_assignments = Assignment.objects.filter(
                Q(course__in=enrolled_courses) | Q(courses__in=enrolled_courses)
            )
            
            # Combine all assignment sources
            assignments_list = (own_assignments | course_assignments | group_course_assignments | enrolled_course_assignments).distinct()
            
            # Available courses: their assigned courses + group-assigned courses + enrolled courses
            available_courses = (assigned_courses | group_assigned_courses | enrolled_courses).distinct().order_by('title')
        else:
            # Fallback for instructors without branch assignment
            assignments_list = Assignment.objects.filter(user=request.user)
            available_courses = Course.objects.filter(instructor=request.user).order_by('title')
        can_create = True
        can_edit = True
        is_student_view = False
        
        # Filter by course if specified
        if course_filter_id:
            try:
                course_filter_id = int(course_filter_id)
                # Verify this is one of the instructor's accessible courses
                if available_courses.filter(id=course_filter_id).exists():
                    assignments_list = assignments_list.filter(
                        Q(course_id=course_filter_id) |
                        Q(courses__id=course_filter_id) |
                        Q(topicassignment__topic__courses__id=course_filter_id)
                    ).distinct()
            except (ValueError, TypeError):
                pass
        assignments_list = assignments_list.order_by('-created_at')
        
    else:  # learner
        # Learner: SELF access (enrolled courses only)
        enrolled_courses = Course.objects.filter(enrolled_users=request.user).values_list('id', flat=True)
        
        # Get assignments that are:
        # 1. Active
        # 2. Linked to enrolled courses (through any relationship)
        # 3. Either have active/published topics OR have no topics (direct course assignments)
        assignments_list = Assignment.objects.filter(
            is_active=True
        ).filter(
            # Must be linked to enrolled courses through any relationship
            Q(course__in=enrolled_courses) |  # Direct course relationship
            Q(courses__in=enrolled_courses) |  # M2M course relationship
            Q(topics__courses__in=enrolled_courses)  # Topic-based course relationship
        ).filter(
            # Either have active topics OR have no topics at all
            Q(topics__status='active') |  # Has active topics
            Q(topics__isnull=True)  # Has no topics (direct course assignment)
        ).distinct().order_by('-created_at')
        
        # Filter by course if specified
        if course_filter_id:
            try:
                # Verify this is one of the user's enrolled courses
                course_filter_id = int(course_filter_id)
                if course_filter_id in enrolled_courses:
                    assignments_list = assignments_list.filter(
                        Q(course_id=course_filter_id) |
                        Q(courses__id=course_filter_id) |
                        Q(topics__courses__id=course_filter_id)
                    ).distinct()
            except (ValueError, TypeError):
                pass
                
        # Get enrolled courses for learners
        available_courses = Course.objects.filter(enrolled_users=request.user).order_by('title')
        can_create = False
        can_edit = False
        is_student_view = True
    
    # Get linked courses for each assignment
    assignment_linked_courses = {}
    
    for assignment in assignments_list:
        # Use the get_course_info method to get primary course info
        course_info = assignment.get_course_info()
        
        if course_info:
            if request.user.role == 'learner':
                # For learners, only show if they're enrolled in the course
                if course_info.id in enrolled_courses:
                    assignment_linked_courses[assignment.id] = [course_info]
                else:
                    assignment_linked_courses[assignment.id] = []
            else:
                # For instructors/admins, show the course
                assignment_linked_courses[assignment.id] = [course_info]
        else:
            assignment_linked_courses[assignment.id] = []
    

    
    # Pagination
    paginator = Paginator(assignments_list, 10)  # Show 10 assignments per page
    page = request.GET.get('page')
    assignments = paginator.get_page(page)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Assignments', 'icon': 'fa-tasks'}
    ]
    
    context = {
        'assignments': assignments,
        'title': 'Assignments',
        'breadcrumbs': breadcrumbs,
        'available_courses': available_courses,
        'assignment_linked_courses': assignment_linked_courses,
        'can_create': can_create,
        'can_edit': can_edit,
        'is_student_view': is_student_view,
        'selected_course_id': course_filter_id
    }
    
    # Add branch context for template (enables branch switcher for admin users)
    from core.branch_filters import filter_context_by_branch
    context = filter_context_by_branch(context, request.user, request)
    
    return render(request, 'assignments/assignment_list.html', context)

@login_required
def assignment_detail(request, assignment_id):
    """View to display assignment details"""
    assignment = get_object_or_404(
        Assignment.objects.select_related('rubric', 'course').prefetch_related(
            'rubric__criteria__ratings',
            'text_fields',
            'text_fields__answers__submission__user',
            'attachments'
        ), 
        id=assignment_id
    )
    
    # Log assignment view interaction
    AssignmentInteractionLog.log_interaction(
        assignment=assignment,
        user=request.user,
        interaction_type='view',
        request=request,
        page_url=request.get_full_path()
    )
    
    # Track or update session log
    session_key = request.session.session_key
    if session_key:
        session_log, created = AssignmentSessionLog.objects.get_or_create(
            assignment=assignment,
            user=request.user,
            session_key=session_key,
            is_active=True,
            defaults={
                'ip_address': AssignmentInteractionLog.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'page_views': 1,
                'interactions_count': 1,
            }
        )
        if not created:
            session_log.page_views += 1
            session_log.interactions_count += 1
            session_log.update_activity()

    # Ensure assignment has course association properly synchronized
    sync_assignment_courses(assignment)
    
    # Simplified permission check with better user experience
    has_access = False
    
    # Global admins and super admins always have access
    if request.user.role in ['globaladmin', 'superadmin']:
        has_access = True
    
    # Assignment creator has access
    elif assignment.user == request.user:
        has_access = True
    
    # Check if user has access through course enrollment or teaching
    elif assignment.is_available_for_user(request.user):
        has_access = True
        
    # Admins can access assignments in their effective branch (supports branch switching)
    elif request.user.role == 'admin':
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        if assignment.user and assignment.user.branch == effective_branch:
            has_access = True
        elif assignment.course and assignment.course.branch == effective_branch:
            has_access = True
    
    if not has_access:
        # Provide helpful error messages
        if request.user.role == 'learner':
            messages.error(request, "You need to be enrolled in the course to access this assignment.")
        elif request.user.role == 'instructor':
            messages.error(request, "This assignment is not linked to any courses you teach.")
        elif request.user.role == 'admin':
            messages.error(request, "This assignment is not in your branch.")
        else:
            messages.error(request, "You don't have permission to access this assignment.")
        
        logger.info(f"Access denied for user {request.user.username} (role: {request.user.role}) to assignment {assignment_id}")
        return redirect('assignments:assignment_list')
    
    # Process description and instructions if they are in JSON format
    if assignment.description:
        try:
            if isinstance(assignment.description, str) and assignment.description.strip().startswith('{'):
                description_data = json.loads(assignment.description)
                if isinstance(description_data, dict) and 'html' in description_data:
                    # Keep the JSON but extract the HTML content for template rendering
                    assignment.description = description_data
                    print(f"Processed description as JSON: {str(description_data)[:100]}")
        except json.JSONDecodeError:
            # Not valid JSON, leave as is
            print(f"Description is not valid JSON: {assignment.description[:100]}")
            pass
            
    if assignment.instructions:
        try:
            if isinstance(assignment.instructions, str) and assignment.instructions.strip().startswith('{'):
                instructions_data = json.loads(assignment.instructions)
                if isinstance(instructions_data, dict) and 'html' in instructions_data:
                    # Keep the JSON but extract the HTML content for template rendering
                    assignment.instructions = instructions_data
                    print(f"Processed instructions as JSON: {str(instructions_data)[:100]}")
        except json.JSONDecodeError:
            # Not valid JSON, leave as is
            print(f"Instructions is not valid JSON: {assignment.instructions[:100]}")
            pass
    
    # Get attachments
    attachments = list(assignment.attachments.all())

    # Check if already submitted (get latest submission for general logic)
    try:
        submission = AssignmentSubmission.objects.select_related('user', 'graded_by').prefetch_related(
            'field_answer_iterations__field',
            'field_answer_iterations__feedback_entries',
            'text_answer_iterations__question',
            'text_answer_iterations__feedback_entries',
        ).filter(assignment=assignment, user=request.user).order_by('-submitted_at').first()
    except:
        submission = None
    
    # Get ALL submissions by the current user for this assignment (for learners to see their submission history)
    user_all_submissions = AssignmentSubmission.objects.filter(
        assignment=assignment, 
        user=request.user
    ).select_related('user', 'graded_by').prefetch_related(
        'field_answer_iterations__field', 
        'field_answer_iterations__feedback_entries',
        'text_answer_iterations__question',
        'text_answer_iterations__feedback_entries',
        'feedback_entries',
        'rubric_evaluations__criterion',
        'rubric_evaluations__rating',
        'file_iterations__feedback_entries'  # Add file iterations prefetch
    ).order_by('-submitted_at')
    
    # Get file submission iteration data for timeline display
    file_iteration_data = {}
    if submission:
        file_iterations = submission.file_iterations.filter(
            file__isnull=False  # Only include iterations that actually have files
        ).exclude(file='').order_by('iteration_number')
        if file_iterations.exists():
            iterations_list = []
            for iteration in file_iterations:
                feedback_entries = iteration.feedback_entries.all().order_by('-created_at')
                # Get file extension safely
                file_extension = 'unknown'
                if iteration.file:
                    try:
                        if iteration.file and hasattr(iteration.file, 'name') and iteration.file.name:
                            file_extension = iteration.file.name.split('.')[-1].lower() if '.' in iteration.file.name else 'unknown'
                        else:
                            file_extension = 'unknown'
                    except (AttributeError, ValueError, Exception):
                        file_extension = 'unknown'
                
                iterations_list.append({
                    'iteration': iteration,
                    'feedback_entries': feedback_entries,
                    'latest_feedback': feedback_entries.first() if feedback_entries.exists() else None,
                    'can_upload_new': not feedback_entries.exists() or feedback_entries.first().allows_new_iteration,
                    'file_extension': file_extension
                })
            
            file_iteration_data = {
                'has_iterations': True,
                'iterations': iterations_list,
                'latest_iteration': file_iterations.last(),
                'can_upload_new': not file_iterations.exists() or (
                    file_iterations.last().feedback_entries.exists() and 
                    file_iterations.last().feedback_entries.first().allows_new_iteration
                ) or not file_iterations.last().feedback_entries.exists()
            }
        else:
            file_iteration_data = {
                'has_iterations': False,
                'iterations': [],
                'latest_iteration': None,
                'can_upload_new': True
            }
    
    # For instructors, get all submissions with prefetched related data
    submissions = []
    if request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser:
        submissions = AssignmentSubmission.objects.filter(
            assignment=assignment
        ).select_related(
            'user__branch', 
            'graded_by',
            'assignment__course'
        ).prefetch_related(
            'grade_history__changed_by',
            'feedback_entries__created_by',
            'rubric_evaluations__criterion',
            'rubric_evaluations__rating',
            'text_answer_iterations__question',
            'field_answer_iterations__field',
            'assignment__rubric__criteria__ratings'
        ).order_by('-submitted_at')
        
        # Enhanced submission data for the table
        enhanced_submissions = []
        for submission in submissions:
            # Get course information for this submission - prioritize the submitting user's enrolled course
            from courses.models import Course, CourseEnrollment
            course_info = None
            instructor_name = "Not assigned"
            
            # First, try to find the course through the user's enrollment
            if submission.user:
                # Look for courses this user is enrolled in that are related to this assignment
                user_enrolled_courses = Course.objects.filter(
                    enrolled_users=submission.user
                ).distinct()
                
                # Check if any of these enrolled courses match assignment's linked courses
                assignment_courses = []
                
                # Get all courses linked to this assignment
                if assignment.course:
                    assignment_courses.append(assignment.course)
                assignment_courses.extend(assignment.courses.all())
                
                # Also get courses through topics
                topic_courses = Course.objects.filter(
                    coursetopic__topic__topicassignment__assignment=assignment
                ).distinct()
                assignment_courses.extend(topic_courses)
                
                # Find the intersection - courses user is enrolled in AND assignment is linked to
                matching_courses = user_enrolled_courses.filter(
                    id__in=[c.id for c in assignment_courses]
                )
                
                if matching_courses.exists():
                    course_info = matching_courses.first()
                else:
                    # If no matching course, use the first enrolled course
                    course_info = user_enrolled_courses.first()
            
            # Fallback to assignment's default course info if no user-specific course found
            if not course_info:
                course_info = assignment.get_course_info()
            
            # Determine instructor name based on course info and enrollments
            if course_info:
                if course_info.instructor:
                    # Course has an assigned instructor
                    instructor_name = get_user_display_name(course_info.instructor)
                else:
                    # Course has no assigned instructor, check for enrolled instructors
                    enrolled_instructors = CourseEnrollment.objects.filter(
                        course=course_info,
                        user__role='instructor'
                    ).select_related('user')
                    
                    if enrolled_instructors.exists():
                        # Use the first enrolled instructor
                        instructor_name = get_user_display_name(enrolled_instructors.first().user)
            
            # Get rubric evaluations
            rubric_evaluations = list(submission.rubric_evaluations.all()) if assignment.rubric else []
            
            # Get text question iterations
            text_answers = []
            text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
            for question in text_questions:
                # Get the latest submitted iteration for this question
                latest_iteration = TextQuestionAnswerIteration.objects.filter(
                    question=question,
                    submission=submission,
                    is_submitted=True
                ).order_by('-iteration_number').first()
                
                if latest_iteration:
                    # Get the latest feedback for this iteration
                    latest_feedback = latest_iteration.feedback_entries.first()
                    text_answers.append({
                        'question': question,
                        'answer': latest_iteration,
                        'feedback': latest_feedback
                    })
                else:
                    text_answers.append({
                        'question': question,
                        'answer': None,
                        'feedback': None
                    })
            
            # Get overall feedback
            latest_feedback = submission.feedback_entries.first() if submission.feedback_entries.exists() else None
            
            # Calculate grade percentage
            grade_percentage = None
            if submission.grade and assignment.max_score and assignment.max_score > 0:
                grade_percentage = (float(submission.grade) / float(assignment.max_score)) * 100
            
            # Get text field iterations for this submission
            field_answers = []
            text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
            for field in text_fields:
                # Get the latest submitted iteration for this field
                latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                    field=field,
                    submission=submission,
                    is_submitted=True
                ).order_by('-iteration_number').first()
                
                if latest_iteration:
                    # Get the latest feedback for this iteration by current instructor
                    latest_feedback = latest_iteration.feedback_entries.filter(created_by=request.user).first()
                    field_answers.append({
                        'field': field,
                        'answer': latest_iteration,
                        'feedback': latest_feedback
                    })
                else:
                    field_answers.append({
                        'field': field,
                        'answer': None,
                        'feedback': None
                    })
            
            # Get student display name
            student_name = get_user_display_name(submission.user)
            
            # Get submission-specific comments for this submission
            submission_comments = AssignmentComment.objects.filter(
                assignment=assignment,
                submission=submission,
                parent__isnull=True  # Only root comments, replies will be fetched via relations
            ).select_related('author').prefetch_related(
                'replies__author'
            ).order_by('created_at')
            
            # Filter submission comments based on visibility permissions and add edit permissions
            visible_submission_comments = []
            for comment in submission_comments:
                if comment.can_view(request.user):
                    # Add edit permission as attribute for template access
                    comment.can_edit_by_user = comment.can_edit(request.user)
                    # Process replies too
                    for reply in comment.get_replies():
                        reply.can_edit_by_user = reply.can_edit(request.user)
                    visible_submission_comments.append(comment)

            enhanced_submissions.append({
                'submission': submission,
                'student_name': student_name,
                'course_name': course_info.title if course_info else "No course assigned",
                'course_id': course_info.id if course_info else None,
                'instructor_name': instructor_name,
                'rubric_evaluations': rubric_evaluations,
                'text_answers': text_answers,
                'field_answers': field_answers,  # Add field answers
                'latest_feedback': latest_feedback,
                'has_uploaded_files': bool(submission.submission_file),
                'has_text_submission': bool(submission.submission_text),
                'total_rubric_score': sum(eval.points for eval in rubric_evaluations) if rubric_evaluations else 0,
                'max_rubric_score': assignment.rubric.total_points if assignment.rubric else 0,
                'grade_percentage': grade_percentage,
                'submission_comments': visible_submission_comments,  # Add submission-specific comments
                'file_iteration_data': file_iteration_data
            })
        
        submissions = enhanced_submissions
    else:
        # For learners, show ALL their submission attempts with date/time
        submissions = []
        if user_all_submissions.exists():
            # Process each submission attempt separately
            for submission_attempt in user_all_submissions:
                # Create enhanced submission data for each submission attempt
                from courses.models import Course, CourseEnrollment
                course_info = None
                instructor_name = "Not assigned"
                
                # Get course information for this submission - prioritize the submitting user's enrolled course
                if submission_attempt.user:
                    # Look for courses this user is enrolled in that are related to this assignment
                    user_enrolled_courses = Course.objects.filter(
                        enrolled_users=submission_attempt.user
                    ).distinct()
                    
                    # Check if any of these enrolled courses match assignment's linked courses
                    assignment_courses = []
                    
                    # Get all courses linked to this assignment
                    if assignment.course:
                        assignment_courses.append(assignment.course)
                    assignment_courses.extend(assignment.courses.all())
                    
                    # Also get courses through topics
                    topic_courses = Course.objects.filter(
                        coursetopic__topic__topicassignment__assignment=assignment
                    ).distinct()
                    assignment_courses.extend(topic_courses)
                    
                    # Find the intersection - courses user is enrolled in AND assignment is linked to
                    matching_courses = user_enrolled_courses.filter(
                        id__in=[c.id for c in assignment_courses]
                    )
                    
                    if matching_courses.exists():
                        course_info = matching_courses.first()
                    else:
                        # If no matching course, use the first enrolled course
                        course_info = user_enrolled_courses.first()
                
                # Fallback to assignment's default course info if no user-specific course found
                if not course_info:
                    course_info = assignment.get_course_info()
                
                # Determine instructor name based on course info and enrollments
                if course_info:
                    if course_info.instructor:
                        # Course has an assigned instructor
                        instructor_name = get_user_display_name(course_info.instructor)
                    else:
                        # Course has no assigned instructor, check for enrolled instructors
                        enrolled_instructors = CourseEnrollment.objects.filter(
                            course=course_info,
                            user__role='instructor'
                        ).select_related('user')
                        
                        if enrolled_instructors.exists():
                            # Use the first enrolled instructor
                            instructor_name = get_user_display_name(enrolled_instructors.first().user)
                
                # Get rubric evaluations for this submission attempt
                rubric_evaluations = list(submission_attempt.rubric_evaluations.all()) if assignment.rubric else []
                
                # Get text question answers for this submission attempt
                text_answers = []
                text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
                for question in text_questions:
                    # Get the latest submitted iteration for this question
                    latest_iteration = TextQuestionAnswerIteration.objects.filter(
                        question=question,
                        submission=submission_attempt,
                        is_submitted=True
                    ).order_by('-iteration_number').first()
                    
                    if latest_iteration:
                        # Get the latest feedback for this iteration (from any instructor)
                        latest_feedback = latest_iteration.feedback_entries.first()
                        text_answers.append({
                            'question': question,
                            'answer': latest_iteration,
                            'feedback': latest_feedback
                        })
                    else:
                        text_answers.append({
                            'question': question,
                            'answer': None,
                            'feedback': None
                        })
                
                # Get overall feedback for this submission attempt
                latest_feedback = submission_attempt.feedback_entries.first() if submission_attempt.feedback_entries.exists() else None
                
                # Calculate grade percentage for this submission attempt
                grade_percentage = None
                if submission_attempt.grade and assignment.max_score and assignment.max_score > 0:
                    grade_percentage = (float(submission_attempt.grade) / float(assignment.max_score)) * 100
                
                # Get student display name
                student_name = get_user_display_name(submission_attempt.user)
                
                # Get submission-specific comments for this submission attempt
                submission_comments = AssignmentComment.objects.filter(
                    assignment=assignment,
                    submission=submission_attempt,
                    parent__isnull=True  # Only root comments, replies will be fetched via relations
                ).select_related('author').prefetch_related(
                    'replies__author'
                ).order_by('created_at')
                
                # Filter submission comments based on visibility permissions and add edit permissions
                visible_submission_comments = []
                for comment in submission_comments:
                    if comment.can_view(request.user):
                        # Add edit permission as attribute for template access
                        comment.can_edit_by_user = comment.can_edit(request.user)
                        
                        # Process replies and filter them for visibility too
                        visible_replies = []
                        for reply in comment.get_replies():
                            if reply.can_view(request.user):
                                reply.can_edit_by_user = reply.can_edit(request.user)
                                visible_replies.append(reply)
                        
                        # Replace the replies with only visible ones
                        comment._visible_replies = visible_replies
                        visible_submission_comments.append(comment)

                # Create enhanced submission data for this submission attempt
                submissions.append({
                    'submission': submission_attempt,
                    'student_name': student_name,
                    'course_name': course_info.title if course_info else "No course assigned",
                    'course_id': course_info.id if course_info else None,
                    'instructor_name': instructor_name,
                    'rubric_evaluations': rubric_evaluations,
                    'text_answers': text_answers,
                    'latest_feedback': latest_feedback,
                    'has_uploaded_files': bool(submission_attempt.submission_file),
                    'has_text_submission': bool(submission_attempt.submission_text),
                    'total_rubric_score': sum(eval.points for eval in rubric_evaluations) if rubric_evaluations else 0,
                    'max_rubric_score': assignment.rubric.total_points if assignment.rubric else 0,
                    'grade_percentage': grade_percentage,
                    'submission_comments': visible_submission_comments,  # Add submission-specific comments
                    'submission_attempt_number': submission_attempt.get_submission_attempt_number(),  # Use the model method
                    'is_latest_submission': submission_attempt == user_all_submissions.first(),  # Mark if this is the latest attempt
                    'can_be_edited': submission_attempt.can_be_edited_by_student(),  # Add edit permission flag
                    'is_final': submission_attempt.is_final_submission()  # Add final submission flag
                })
    
    # Handle assignment submission
    if request.method == 'POST' and 'submit_assignment' in request.POST:
        # Check if student is allowed to submit/edit
        if request.user.role == 'learner':
            if submission and not submission.can_be_edited_by_student():
                messages.error(request, "You cannot edit this submission. It has already been submitted and is being graded, or has been graded.")
                return redirect('assignments:assignment_detail', assignment_id=assignment.id)
        
        # FILE UPLOAD VALIDATION: Made optional - removed required validation
        uploaded_file = request.FILES.get('submission_file')
        submission_text = request.POST.get('submission_text', '').strip()
        
        # Note: File and text submissions are now optional to allow flexible submission workflows
        # Users can submit files, text, or both based on their preference
        
        if submission:
            # Check if we need to create a new submission (if status was 'returned')
            if submission.status == 'returned':
                # Create a new submission for revision or update existing one
                
                try:
                    # Try to get or create a new submission - this handles the unique constraint properly
                    new_submission, created = AssignmentSubmission.objects.get_or_create(
                        assignment=assignment,
                        user=request.user,
                        defaults={
                            'submission_text': submission_text,
                            'status': 'not_graded'  # New submission starts as not graded
                        }
                    )
                    
                    # If submission already exists, update it instead of creating duplicate
                    if not created:
                        new_submission.submission_text = submission_text
                        new_submission.status = 'not_graded'
                        new_submission.last_modified = timezone.now()
                    
                    if uploaded_file:
                        # Handle file upload with iteration system
                        # Get the next iteration number
                        from assignments.models import FileSubmissionIteration
                        last_iteration = FileSubmissionIteration.objects.filter(
                            submission=new_submission
                        ).order_by('-iteration_number').first()
                        
                        next_iteration_number = (last_iteration.iteration_number + 1) if last_iteration else 1
                        
                        # Create new file iteration
                        file_iteration = FileSubmissionIteration.objects.create(
                            submission=new_submission,
                            iteration_number=next_iteration_number,
                            file=uploaded_file,
                            file_name=uploaded_file.name,
                            file_size=uploaded_file.size,
                            is_submitted=True,
                            submitted_at=timezone.now()
                        )
                        
                        # Register file in media database for tracking
                        try:
                            from lms_media.utils import register_media_file
                            register_media_file(
                                file_path=str(file_iteration.file),
                                uploaded_by=request.user,
                                source_type='assignment_submission',
                                source_model='FileSubmissionIteration',
                                source_object_id=file_iteration.id,
                                course=assignment.course if hasattr(assignment, 'course') else None,
                                filename=uploaded_file.name,
                                description=f'Assignment submission iteration {next_iteration_number} for: {assignment.title}'
                            )
                        except Exception as e:
                            logger.error(f"Error registering assignment file iteration in media database: {str(e)}")
                        
                        # Also update the main submission file for backward compatibility
                        new_submission.submission_file = uploaded_file
                    
                    new_submission.save()
                    submission = new_submission  # Update reference to new submission
                    
                    # Log the revision in grade history only if we actually created or meaningfully updated
                    if created or new_submission.status != 'returned':
                        GradeHistory.objects.create(
                            submission=new_submission,
                            previous_status='returned',
                            new_status='not_graded',
                            changed_by=request.user,
                            comment="Student submitted revision after assignment was returned"
                        )
                        
                except Exception as e:
                    logger.error(f"Error creating/updating submission for assignment {assignment.id}, user {request.user.id}: {e}")
                    messages.error(request, "There was an error submitting your assignment. Please try again.")
                    return redirect('assignments:assignment_detail', assignment_id=assignment.id)
                
            elif submission.can_be_edited_by_student():
                # Update existing submission (only if it can be edited)
                submission.submission_text = submission_text
                
                if uploaded_file:
                    # Handle file upload with iteration system
                    # Get the next iteration number
                    from assignments.models import FileSubmissionIteration
                    last_iteration = FileSubmissionIteration.objects.filter(
                        submission=submission
                    ).order_by('-iteration_number').first()
                    
                    next_iteration_number = (last_iteration.iteration_number + 1) if last_iteration else 1
                    
                    # Create new file iteration
                    file_iteration = FileSubmissionIteration.objects.create(
                        submission=submission,
                        iteration_number=next_iteration_number,
                        file=uploaded_file,
                        file_name=uploaded_file.name,
                        file_size=uploaded_file.size,
                            content_type=uploaded_file.content_type,
                        is_submitted=True,
                        submitted_at=timezone.now()
                    )
                    
                    # Register file in media database for tracking
                    try:
                        from lms_media.utils import register_media_file
                        register_media_file(
                            file_path=str(file_iteration.file),
                            uploaded_by=request.user,
                            source_type='assignment_submission',
                            source_model='FileSubmissionIteration',
                            source_object_id=file_iteration.id,
                            course=assignment.course if hasattr(assignment, 'course') else None,
                            filename=uploaded_file.name,
                            description=f'Assignment submission iteration {next_iteration_number} for: {assignment.title}'
                        )
                    except Exception as e:
                        logger.error(f"Error registering assignment file iteration in media database: {str(e)}")
                    
                    # Also update the main submission file for backward compatibility
                    submission.submission_file = uploaded_file
                
                submission.last_modified = timezone.now()
                submission.status = 'not_graded'
                submission.save()
            else:
                messages.error(request, "You cannot edit this submission. It has already been submitted.")
                return redirect('assignments:assignment_detail', assignment_id=assignment.id)
        else:
            # Create new submission - use get_or_create to prevent duplicates
            try:
                submission, created = AssignmentSubmission.objects.get_or_create(
                    assignment=assignment,
                    user=request.user,
                    defaults={
                        'submission_text': submission_text,
                        'status': 'not_graded'
                    }
                )
                
                # If submission already exists, update it instead of creating duplicate
                if not created:
                    submission.submission_text = submission_text
                    submission.status = 'not_graded'
                    submission.last_modified = timezone.now()
                
                if uploaded_file:
                    # Handle file upload with iteration system
                    # Get the next iteration number
                    from assignments.models import FileSubmissionIteration
                    last_iteration = FileSubmissionIteration.objects.filter(
                        submission=submission
                    ).order_by('-iteration_number').first()
                    
                    next_iteration_number = (last_iteration.iteration_number + 1) if last_iteration else 1
                    
                    # Create new file iteration
                    file_iteration = FileSubmissionIteration.objects.create(
                        submission=submission,
                        iteration_number=next_iteration_number,
                        file=uploaded_file,
                        file_name=uploaded_file.name,
                        file_size=uploaded_file.size,
                            content_type=uploaded_file.content_type,
                        is_submitted=True,
                        submitted_at=timezone.now()
                    )
                    
                    # Register file in media database for tracking
                    try:
                        from lms_media.utils import register_media_file
                        register_media_file(
                            file_path=str(file_iteration.file),
                            uploaded_by=request.user,
                            source_type='assignment_submission',
                            source_model='FileSubmissionIteration',
                            source_object_id=file_iteration.id,
                            course=assignment.course if hasattr(assignment, 'course') else None,
                            filename=uploaded_file.name,
                            description=f'Assignment submission iteration {next_iteration_number} for: {assignment.title}'
                        )
                    except Exception as e:
                        logger.error(f"Error registering assignment file iteration in media database: {str(e)}")
                    
                    # Also update the main submission file for backward compatibility
                    submission.submission_file = uploaded_file
                
                submission.save()
                
            except Exception as e:
                logger.error(f"Error creating submission for assignment {assignment.id}, user {request.user.id}: {e}")
                messages.error(request, "There was an error submitting your assignment. Please try again.")
                return redirect('assignments:assignment_detail', assignment_id=assignment.id)
        
        # Handle custom text field answers using iteration system
        text_fields = TextSubmissionField.objects.filter(assignment=assignment)
        if text_fields.exists():
            all_fields_valid = True
            missing_fields = []
            
            for field in text_fields:
                field_name = f'text_field_{field.id}'
                if field_name in request.POST:
                    field_content = request.POST.get(field_name, '').strip()
                    
                    if field_content:  # Only create iteration if content is provided
                        # Use iteration system instead of overwriting
                        iteration, created = create_or_get_latest_iteration(field, submission, 'field')
                        if iteration:
                            iteration.answer_text = field_content
                            iteration.is_submitted = True
                            iteration.submitted_at = timezone.now()
                            iteration.save()
                    else:
                        all_fields_valid = False
                        missing_fields.append(field.label or f"Question {field.order + 1}")
                else:
                    # Check if this field has any existing iterations - if not, it's missing
                    existing_iterations = TextSubmissionAnswerIteration.objects.filter(
                        field=field,
                        submission=submission,
                        is_submitted=True
                    ).exists()
                    
                    if not existing_iterations:
                        all_fields_valid = False
                        missing_fields.append(field.label or f"Question {field.order + 1}")
            
            if not all_fields_valid:
                # Handle validation errors
                messages.error(request, f"Please provide valid answers (minimum 10 characters) for all questions: {', '.join(missing_fields)}")
                return redirect('assignments:assignment_detail', assignment_id=assignment.id)
            
        # Handle text question answers using iteration system
        text_questions = TextQuestion.objects.filter(assignment=assignment)
        if text_questions.exists():
            for question in text_questions:
                question_name = f'text_question_{question.id}'
                if question_name in request.POST:
                    answer_content = request.POST.get(question_name, '').strip()
                    
                    if answer_content:  # Only create iteration if content is provided
                        # Use iteration system instead of overwriting
                        iteration, created = create_or_get_latest_iteration(question, submission, 'question')
                        if iteration:
                            iteration.answer_text = answer_content
                            iteration.is_submitted = True
                            iteration.submitted_at = timezone.now()
                            iteration.save()
            
        messages.success(request, "Assignment submitted successfully")
        return redirect('assignments:assignment_detail', assignment_id=assignment.id)
        
    # Handle SupportingDocQuestion form submission from instructors
    elif request.method == 'POST' and 'supporting_doc_question' in request.POST:
        question_form = SupportingDocQuestionForm(request.POST)
        if question_form.is_valid():
            question = question_form.save(commit=False)
            question.assignment = assignment
            question.user = request.user
            question.save()
            messages.success(request, "Question added successfully")
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)
    # Handle student answers to questions
    elif request.method == 'POST' and 'supporting_doc_answer' in request.POST:
        question_id = request.POST.get('question_id')
        answer_text = request.POST.get('answer')
        
        if question_id and answer_text:
            try:
                question = SupportingDocQuestion.objects.get(id=question_id, assignment=assignment)
                
                # Create or update student's answer
                student_answer, created = StudentAnswer.objects.update_or_create(
                    question=question,
                    student=request.user,
                    defaults={'answer': answer_text}
                )
                
                messages.success(request, "Your answer has been submitted successfully")
            except SupportingDocQuestion.DoesNotExist:
                messages.error(request, "Question not found")
            
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)
    else:
        question_form = SupportingDocQuestionForm()
    
    # Get existing supporting doc questions
    supporting_doc_questions = SupportingDocQuestion.objects.filter(assignment=assignment)
    
    # Get student answers for each question (for non-instructor users)
    student_answers = {}
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        # Get all student answers for this user
        student_answers_queryset = StudentAnswer.objects.filter(
            question__in=supporting_doc_questions,
            student=request.user
        )
        # Create a dictionary mapping question_id to answer text
        for answer in student_answers_queryset:
            student_answers[str(answer.question.id)] = answer.answer
    
    # Prepare questions with answers for the template
    questions_with_answers = []
    for question in supporting_doc_questions:
        question_data = {
            'id': question.id,
            'question': question.question,
            'answer': question.answer,
            'user': question.user,
            'created_at': question.created_at,
            'student_answer': student_answers.get(str(question.id), '')
        }
        questions_with_answers.append(question_data)
    
    # Get the first topic assignment to get the course
    topic_assignment = assignment.topicassignment_set.first()
    if topic_assignment:
        course = get_topic_course(topic_assignment.topic)
    else:
        course = None
    
    # Note: submissions is already set above for instructors with enhanced data
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-tasks'},
    ]
    
    if course:
        breadcrumbs.append({
            'url': reverse('courses:course_details', args=[course.id]),
            'label': course.title,
            'icon': 'fa-book'
        })
    
    breadcrumbs.append({
        'label': assignment.title,
        'icon': 'fa-file-alt'
    })
    
    # Get rubric data if the assignment has a rubric
    rubric_data = None
    if assignment.rubric:
        rubric = assignment.rubric
        criteria = rubric.criteria.all().prefetch_related('ratings').order_by('position')
        rubric_data = {
            'rubric': rubric,
            'criteria': criteria,
            'total_points': rubric.total_points
        }
    
    # Get existing attachments
    existing_attachments = list(assignment.attachments.all())
    
        # Get existing text submission fields
    existing_text_fields = list(assignment.text_fields.all().values('id', 'label', 'placeholder', 'order', 'content'))
    
    # Ensure content is properly formatted for the editor
    for field in existing_text_fields:
        if field.get('content') is None:
            # Create default content structure
            field['content'] = json.dumps({"delta": {}, "html": ""})
        elif isinstance(field['content'], dict):
            # Convert dict to JSON string for template
            field['content'] = json.dumps(field['content'])
        # If it's already a string, make sure it's proper JSON
        elif isinstance(field['content'], str):
            try:
                # First check if it's already valid JSON
                json_obj = json.loads(field['content'])
                # If it doesn't have an html property, add it
                if not isinstance(json_obj, dict) or 'html' not in json_obj:
                    field['content'] = json.dumps({"delta": {}, "html": field['content']})
            except json.JSONDecodeError:
                # Not valid JSON, so wrap it in our JSON structure
                field['content'] = json.dumps({"delta": {}, "html": field['content']})
            except Exception as e:
                print(f"Error formatting field content: {e}")
                field['content'] = json.dumps({"delta": {}, "html": ""})

    # Progress percentage not available without start_date field
    progress_percentage = 0

    # Get iteration data for text questions and fields if we have a submission
    question_iteration_data = {}
    field_iteration_data = {}
    
    if submission:
        # Get text questions for this assignment
        text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
        for question in text_questions:
            iteration_data = get_iteration_data_for_question(question, submission)
            question_iteration_data[question.id] = iteration_data
        
        # Get text fields for this assignment
        text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
        for field in text_fields:
            iteration_data = get_iteration_data_for_field(field, submission)
            field_iteration_data[field.id] = iteration_data

    # Get general assignment comments (not linked to specific submissions)
    comments = AssignmentComment.objects.filter(
        assignment=assignment,
        submission__isnull=True,  # Only general assignment comments, not submission-specific
        parent__isnull=True  # Only root comments, replies will be fetched via relations
    ).select_related('author').prefetch_related(
        'replies__author'
    ).order_by('created_at')
    
    # Filter comments based on visibility permissions and add edit permissions
    visible_comments = []
    for comment in comments:
        if comment.can_view(request.user):
            # Add edit permission as attribute for template access
            comment.can_edit_by_user = comment.can_edit(request.user)
            
            # Process replies and filter them for visibility too
            visible_replies = []
            for reply in comment.get_replies():
                if reply.can_view(request.user):
                    reply.can_edit_by_user = reply.can_edit(request.user)
                    visible_replies.append(reply)
            
            # Replace the replies with only visible ones
            comment._visible_replies = visible_replies
            visible_comments.append(comment)
    
    # Get rubric evaluation history across ALL submissions for the current user (learner view)
    rubric_evaluation_history = []
    if submission and assignment.rubric and request.user.role == 'learner':
        # Get all submissions by this learner for this assignment
        all_learner_submissions = AssignmentSubmission.objects.filter(
            assignment=assignment,
            user=request.user
        ).values_list('id', flat=True)
        
        rubric_evaluation_history = RubricEvaluationHistory.objects.filter(
            submission__in=all_learner_submissions
        ).select_related(
            'submission', 'criterion', 'rating', 'evaluated_by'
        ).order_by('submission__submitted_at', 'criterion__position', '-version')

    context = {
        'assignment': assignment,
        'submission': submission,
        'submissions': submissions,
        'breadcrumbs': breadcrumbs,
        'rubric_data': rubric_data,
        'attachments': attachments,
        'supporting_doc_questions': supporting_doc_questions,
        'student_answers': student_answers,
        'questions_with_answers': questions_with_answers,
        'question_form': question_form,
        'disable_text_question_form': True,  # Flag to disable the text-based question form
        'existing_attachments': existing_attachments,
        'existing_text_fields': existing_text_fields,
        'question_iteration_data': question_iteration_data,
        'field_iteration_data': field_iteration_data,
        'file_iteration_data': file_iteration_data,
        'progress_percentage': progress_percentage,
        'current_time': timezone.now(),
        'comments': visible_comments,
        'rubric_evaluation_history': rubric_evaluation_history,
    }
    return render(request, 'assignments/assignment_detail.html', context)

@login_required
def create_assignment(request, course_id=None):
    """View to create a new assignment"""
    import json  # Add the import here
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to create assignments")
    
    # Get the course if course_id is provided
    course = None
    if course_id:
        course = get_object_or_404(Course, id=course_id)
    
    # Check if we're coming from a topic
    topic = None
    topic_id = request.GET.get('topic_id')
    if topic_id:
        try:
            topic = Topic.objects.get(id=topic_id)
            # If topic is provided but no course_id, get the course from the topic
            if not course and topic:
                topic_course = Course.objects.filter(coursetopic__topic=topic).first()
                if topic_course:
                    course = topic_course
                    course_id = course.id
        except Topic.DoesNotExist:
            pass
    
    # Get available courses for dropdown (hidden but needed for form validation)
    available_courses = None
    if request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser:
        available_courses = Course.objects.all().order_by('title')
    
    # Get available rubrics based on user role using centralized function
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    available_rubrics = get_filtered_rubrics_for_user(request.user, course)
    
    if request.method == 'POST':
        print("Received POST request for create_assignment")
        
        # If creating from a course, pre-select it
        initial_data = {}
        if course_id:
            initial_data = {'course': course_id, 'course_ids': [course_id]}
            # Add to POST data to ensure it's included
            post_data = request.POST.copy()
            if 'course_ids' not in post_data:
                post_data.setlist('course_ids', [course_id])
            if 'course' not in post_data:
                post_data['course'] = course_id
            form = AssignmentForm(post_data, request.FILES, user=request.user)
        else:
            form = AssignmentForm(request.POST, request.FILES, user=request.user)
            
        if form.is_valid():
            print("Form is valid")
            try:
                with transaction.atomic():
                    # Create the assignment
                    assignment = form.save(commit=False)
                    
                    # CRITICAL: Always set creator for new assignments
                    if not assignment.id:
                        assignment.user = request.user
                    
                    # Associate with a course if one was provided through URL
                    if course_id and course and not assignment.course:
                        assignment.course = course
                    
                    # CRITICAL: Ensure user field is preserved during save
                    if not assignment.user:
                        assignment.user = request.user
                    
                    # Finally save the assignment and any attachments
                    assignment = form.save(user=request.user)
                
                # If coming from a topic, add to the topicassignment table
                if topic_id:
                    try:
                        topic = Topic.objects.get(id=topic_id)
                        # Create or update topic assignment relationship - prevents duplicate key errors
                        TopicAssignment.objects.update_or_create(
                            topic=topic,
                            assignment=assignment,
                            defaults={'order': 0}  # Default order
                        )
                        
                        # Make sure the course is added to the assignment's courses
                        topic_courses = Course.objects.filter(coursetopic__topic=topic)
                        for topic_course in topic_courses:
                            # Check if already associated
                            if not AssignmentCourse.objects.filter(assignment=assignment, course=topic_course).exists():
                                # Determine if this should be the primary course
                                is_primary = not AssignmentCourse.objects.filter(assignment=assignment, is_primary=True).exists()
                                AssignmentCourse.objects.create(
                                    assignment=assignment,
                                    course=topic_course,
                                    is_primary=is_primary
                                )
                                
                    except Topic.DoesNotExist:
                        pass
                
                # Handle questions from the form
                question_ids = request.POST.getlist('question_ids[]', [])
                for question_id in question_ids:
                    question_text = request.POST.get(f'question_text_{question_id}', '')
                    question_html = request.POST.get(f'question_html_{question_id}', '')
                    question_order = request.POST.get(f'question_order_{question_id}', 0)
                    
                    # If the question ID is negative, it's a new question (created in the frontend)
                    if question_id.startswith('-'):
                        TextQuestion.objects.create(
                            assignment=assignment,
                            question_text=question_text,
                            question_html=question_html,
                            order=int(question_order) if question_order else 0
                        )
                
                # Handle temporary text questions if any
                temp_questions = request.POST.get('tempTextQuestions', '')
                if temp_questions:
                    try:
                        import json
                        print(f"Temporary questions data: {temp_questions}")
                        questions_data = json.loads(temp_questions)
                        print(f"Parsed questions data: {questions_data}")
                        for i, question_data in enumerate(questions_data):
                            question_text = question_data.get('question_text', question_data.get('text', ''))
                            question_html = question_data.get('question_html', '')
                            order = question_data.get('order', i+1)
                            print(f"Creating question {i}: {question_text}")
                            question = TextQuestion.objects.create(
                                assignment=assignment,
                                question_text=question_text,
                                question_html=question_html,
                                order=order
                            )
                            print(f"Created question: {question.id}")
                    except (json.JSONDecodeError, KeyError, Exception) as e:
                        # Log the error but continue with assignment creation
                        print(f"Error processing temporary questions: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Handle text submission fields if any
                text_fields = request.POST.get('text_submission_fields', '')
                if text_fields:
                    try:
                        import json
                        print(f"Text submission fields data: {text_fields}")
                        
                        # Parse JSON data directly without attempting sanitization
                        try:
                            fields_data = json.loads(text_fields)
                            print(f"Parsed fields data: {fields_data}")
                            
                            # Delete all existing fields that aren't in the new data
                            existing_field_ids = set()
                            new_field_ids = set()
                            
                            # Collect IDs, converting to integers where possible
                            for field in fields_data:
                                field_id = field.get('id', 0)
                                # Only add to new_field_ids if it's a valid existing field ID (integer)
                                if isinstance(field_id, int) and field_id > 0:
                                    new_field_ids.add(field_id)
                                elif isinstance(field_id, str) and field_id.isdigit():
                                    new_field_ids.add(int(field_id))
                                # Skip string IDs like 'new_0' - these are new fields
                            
                            # Get existing fields for the assignment
                            existing_fields = TextSubmissionField.objects.filter(assignment=assignment)
                            
                            # Delete fields that are no longer in the data
                            for field in existing_fields:
                                if field.id not in new_field_ids:
                                    field.delete()
                                    print(f"Deleted field {field.id}")
                            
                            # Create or update fields
                            for i, field_data in enumerate(fields_data):
                                # Check if this is an existing field with a numeric ID
                                field_id = field_data.get('id', 0)
                                
                                # Convert string numeric IDs to int
                                is_existing_field = False
                                if isinstance(field_id, int) and field_id > 0:
                                    is_existing_field = True
                                elif isinstance(field_id, str) and field_id.isdigit():
                                    field_id = int(field_id)
                                    is_existing_field = True
                                # String IDs like 'new_0' indicate new fields
                                
                                # Get content from field data - this is crucial for edit page display
                                content_json = field_data.get('content', '{"delta":{},"html":""}')
                                print(f"Field {i} content: {content_json[:100]}...")  # Log first 100 chars
                                
                                # Parse content JSON to store in the database
                                content_data = None
                                
                                # If content is a string representation of JSON
                                if isinstance(content_json, str):
                                    try:
                                        content_data = json.loads(content_json)
                                        print(f"Parsed content string to JSON")
                                    except json.JSONDecodeError:
                                        # If not valid JSON, create a proper structure
                                        content_data = {"delta": {}, "html": content_json}
                                        print(f"Created JSON structure for invalid content")
                                # If it's already a dict
                                elif isinstance(content_json, dict):
                                    content_data = content_json
                                    print(f"Content is already a dict")
                                # Fallback for any other type
                                else:
                                    content_data = {"delta": {}, "html": str(content_json)}
                                    print(f"Created fallback JSON for content")
                                
                                # Ensure content has the required keys
                                if not isinstance(content_data, dict) or 'html' not in content_data:
                                    content_data = {"delta": {}, "html": str(content_data)}
                                    print(f"Fixed malformed content data")
                                
                                try:
                                    if is_existing_field:
                                        # Try to get and update existing field
                                        field = TextSubmissionField.objects.get(id=field_id, assignment=assignment)
                                        field.label = field_data.get('label', f"Question {i+1}")
                                        field.placeholder = field_data.get('placeholder', "Enter your answer here...")
                                        field.order = i
                                        field.content = content_data
                                        field.save()
                                        print(f"Updated field {field.id}")
                                    else:
                                        # Create new field
                                        field = TextSubmissionField.objects.create(
                                            assignment=assignment,
                                            label=field_data.get('label', f"Question {i+1}"),
                                            placeholder=field_data.get('placeholder', "Enter your answer here..."),
                                            order=i,
                                            content=content_data
                                        )
                                        print(f"Created new field: {field.id}")
                                except TextSubmissionField.DoesNotExist:
                                    # If field doesn't exist, create a new one
                                    field = TextSubmissionField.objects.create(
                                        assignment=assignment,
                                        label=field_data.get('label', f"Question {i+1}"),
                                        placeholder=field_data.get('placeholder', "Enter your answer here..."),
                                        order=i,
                                        content=content_data
                                    )
                                    print(f"Created field (after DoesNotExist): {field.id}")
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                            print(f"Raw data: {text_fields}")
                            # Try a more flexible approach to parse the JSON
                            import re
                            # Try to create a single default field
                            TextSubmissionField.objects.create(
                                assignment=assignment,
                                label="Text submission",
                                placeholder="Enter your answer here...",
                                order=1  # Order 1 to follow general field
                            )
                    except Exception as e:
                        # Log the error but continue with assignment creation
                        print(f"Error processing text submission fields: {e}")
                        import traceback
                        traceback.print_exc()
                
                messages.success(request, "Assignment created successfully")
                
                # If we came from a topic page, redirect back to topic edit
                if topic_id:
                    return redirect(f'/courses/topic/{topic_id}/edit/')
                
                # Check if we should redirect to edit page
                if request.POST.get('redirect_to_edit') == 'true':
                    # Redirect to edit page with unsaved changes flag
                    return redirect(f"{reverse('assignments:edit_assignment', args=[assignment.id])}?show_warning=true")
                
                # If redirect_to_list is explicitly set or no specific redirect requested,
                # redirect to assignment list
                return redirect('assignments:assignment_list')
                
            except ValidationError as ve:
                # Handle Django validation errors
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Assignment validation error: {str(ve)}")
                
                error_message = "Validation error: " + str(ve)
                messages.error(request, error_message)
                
            except IntegrityError as ie:
                # Handle database integrity errors
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Assignment database integrity error: {str(ie)}")
                
                error_message = "Database error occurred. Please try again."
                messages.error(request, error_message)
                
            except Exception as e:
                # Log any unexpected errors with proper logging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Unexpected error creating assignment: {e}", exc_info=True)
                
                error_message = "An error occurred while creating the assignment. Please try again."
                messages.error(request, error_message)
        else:
            print("Form is invalid. Errors:")
            for field, errors in form.errors.items():
                print(f"Field: {field} - Errors: {errors}")
            
            # More specific error messages
            if form.errors:
                error_messages = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if field == '__all__':
                            error_messages.append(str(error))
                        else:
                            field_name = field.replace('_', ' ').title()
                            if field == 'attachments':
                                field_name = 'File Attachments (Optional)'
                            elif field == 'course_ids':
                                field_name = 'Courses'
                            error_messages.append(f"{field_name}: {error}")
                
                # Create a comprehensive error message
                if error_messages:
                    messages.error(request, f"Please correct the following errors: {'; '.join(error_messages)}")
                else:
                    messages.error(request, "Please correct the errors below before submitting.")
            else:
                messages.error(request, "Please correct the errors below before submitting.")
    else:
        form = AssignmentForm(user=request.user)
    
    # Define breadcrumbs based on whether we have a course or not
    context = {
        'form': form,
        'is_edit': False,
        'is_edit_mode': False,
        'profile_user': request.user,  # Fix: Use current user instead of None to prevent template errors
        'course': course,
        'topic_course': course,  # For template to display the related course
        'available_rubrics': available_rubrics,
        'available_courses': available_courses,
    }
    
    if course:
        context['back_url'] = reverse('courses:course_edit', args=[course_id])
        context['breadcrumbs'] = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_edit', args=[course_id]), 'label': f'Edit {course.title}', 'icon': 'fa-edit'},
            {'label': 'Create Assignment', 'icon': 'fa-plus'}
        ]
    else:
        context['back_url'] = reverse('assignments:assignment_list')
        context['breadcrumbs'] = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-tasks'},
            {'label': 'Create Assignment', 'icon': 'fa-plus'}
        ]
    
    # If from topic, adjust breadcrumbs and back URL
    if topic:
        context['back_url'] = f'/courses/topic/{topic.id}/edit/'
        context['breadcrumbs'] = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_edit', args=[course.id]) if course else '#', 'label': course.title if course else 'Course', 'icon': 'fa-book'},
            {'url': f'/courses/topic/{topic.id}/edit/', 'label': topic.title, 'icon': 'fa-list'},
            {'label': 'Create Assignment', 'icon': 'fa-plus'}
        ]
    
    return render(request, 'assignments/assignment_form.html', context)

@login_required
def edit_assignment(request, assignment_id):
    """View to edit an existing assignment"""
    try:
        assignment = Assignment.objects.get(id=assignment_id)
    except Assignment.DoesNotExist:
        return redirect('assignments:assignment_list')
    except Exception as e:
        # Handle database connection errors and other exceptions
        import logging
        logger = logging.getLogger('assignments')
        logger.error(f"Database error in edit_assignment for assignment_id {assignment_id}: {e}")
        
        # For AJAX requests, return JSON error
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'error': 'Database connection error',
                'message': 'Unable to connect to database. Please try again later.'
            }, status=503)
        
        # For regular requests, show a user-friendly error page
        return render(request, 'assignments/assignment_error.html', {
            'error_title': 'Assignment Not Available',
            'error_message': 'We are unable to load the assignment at this time. Please try again later.',
            'error_details': 'Database connection issue',
            'back_url': reverse('assignments:assignment_list'),
            'back_text': 'Back to Assignments'
        }, status=503)
    
    # Get the topic ID if it's provided in the URL
    topic_id = request.GET.get('topic_id')
    
    # Initialize form and breadcrumbs
    # Get available rubrics based on user role using centralized function
    from lms_rubrics.utils import get_filtered_rubrics_for_user
    
    # Get the course associated with the assignment
    course = None
    if assignment.assignmentcourse_set.exists():
        course = assignment.assignmentcourse_set.first().course
    
    available_rubrics = get_filtered_rubrics_for_user(request.user, course)
    
    existing_attachments = AssignmentAttachment.objects.filter(assignment=assignment)
    # Get existing text submission fields (using only the newer TextSubmissionField system)
    # The older TextQuestion system has been disabled to prevent duplication
    existing_text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
    
    # Get available courses
    available_courses = []
    if request.user.is_superuser:
        available_courses = Course.objects.all()
    elif request.user.role == 'admin':
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        if effective_branch:
            available_courses = Course.objects.filter(branch=effective_branch)
    elif request.user.role == 'instructor':
        available_courses = Course.objects.filter(instructor=request.user)
    
    # Get the courses related to this assignment
    assignment_related_courses = Course.objects.filter(assignmentcourse__assignment=assignment)
    
    # Get the topics related to this assignment
    assignment_related_topics = Topic.objects.filter(topicassignment__assignment=assignment)
    
    # Default breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-tasks'},
        {'label': 'Edit Assignment', 'icon': 'fa-edit'}
    ]
    
    # Check if we came from a course page
    course_id = request.GET.get('course_id')
    course = None
    
    if course_id:
        try:
            course = Course.objects.get(id=course_id)
            
            # Update breadcrumbs
            breadcrumbs = [
                {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                {'url': reverse('courses:course_edit', args=[course.id]), 'label': course.title, 'icon': 'fa-book'},
                {'label': 'Edit Assignment', 'icon': 'fa-edit'}
            ]
        except Course.DoesNotExist:
            pass
    
    # Check if form has been submitted
    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment, user=request.user)
        
        if form.is_valid():
            try:
                # CRITICAL: Preserve the original creator during edit
                updated_assignment = form.save(commit=False)
                
                # Ensure the user field is preserved (don't let form override it)
                if assignment.user and not updated_assignment.user:
                    updated_assignment.user = assignment.user
                elif not updated_assignment.user:
                    # Fallback: if no user is set, use current user
                    updated_assignment.user = request.user
                
                # Save the assignment
                updated_assignment = form.save(user=request.user)
                
                
                
                # Handle text submission fields
                text_fields = request.POST.get('text_submission_fields', '')
                if text_fields:
                    try:
                        import json
                        print(f"Text submission fields data: {text_fields}")
                        
                        # Parse JSON data directly without attempting sanitization
                        try:
                            fields_data = json.loads(text_fields)
                            print(f"Parsed fields data: {fields_data}")
                            
                            # Delete all existing fields that aren't in the new data
                            existing_field_ids = set()
                            new_field_ids = set()
                            
                            # Collect IDs, converting to integers where possible
                            for field in fields_data:
                                field_id = field.get('id', 0)
                                # Only add to new_field_ids if it's a valid existing field ID (integer)
                                if isinstance(field_id, int) and field_id > 0:
                                    new_field_ids.add(field_id)
                                elif isinstance(field_id, str) and field_id.isdigit():
                                    new_field_ids.add(int(field_id))
                                # Skip string IDs like 'new_0' - these are new fields
                            
                            # Get existing fields for the assignment
                            existing_fields = TextSubmissionField.objects.filter(assignment=updated_assignment)
                            
                            # Delete fields that are no longer in the data
                            for field in existing_fields:
                                if field.id not in new_field_ids:
                                    field.delete()
                                    print(f"Deleted field {field.id}")
                            
                            # Create or update fields
                            for i, field_data in enumerate(fields_data):
                                # Check if this is an existing field with a numeric ID
                                field_id = field_data.get('id', 0)
                                
                                # Convert string numeric IDs to int
                                is_existing_field = False
                                if isinstance(field_id, int) and field_id > 0:
                                    is_existing_field = True
                                elif isinstance(field_id, str) and field_id.isdigit():
                                    field_id = int(field_id)
                                    is_existing_field = True
                                # String IDs like 'new_0' indicate new fields
                                
                                # Get content from field data - this is crucial for edit page display
                                content_json = field_data.get('content', '{"delta":{},"html":""}')
                                print(f"Field {i} content: {content_json[:100]}...")  # Log first 100 chars
                                
                                # Parse content JSON to store in the database
                                content_data = None
                                
                                # If content is a string representation of JSON
                                if isinstance(content_json, str):
                                    try:
                                        content_data = json.loads(content_json)
                                        print(f"Parsed content string to JSON")
                                    except json.JSONDecodeError:
                                        # If not valid JSON, create a proper structure
                                        content_data = {"delta": {}, "html": content_json}
                                        print(f"Created JSON structure for invalid content")
                                # If it's already a dict
                                elif isinstance(content_json, dict):
                                    content_data = content_json
                                    print(f"Content is already a dict")
                                # Fallback for any other type
                                else:
                                    content_data = {"delta": {}, "html": str(content_json)}
                                    print(f"Created fallback JSON for content")
                                
                                # Ensure content has the required keys
                                if not isinstance(content_data, dict) or 'html' not in content_data:
                                    content_data = {"delta": {}, "html": str(content_data)}
                                    print(f"Fixed malformed content data")
                                
                                try:
                                    if is_existing_field:
                                        # Try to get and update existing field
                                        field = TextSubmissionField.objects.get(id=field_id, assignment=updated_assignment)
                                        field.label = field_data.get('label', f"Question {i+1}")
                                        field.placeholder = field_data.get('placeholder', "Enter your answer here...")
                                        field.order = i
                                        field.content = content_data
                                        field.save()
                                        print(f"Updated field {field.id}")
                                    else:
                                        # Create new field
                                        field = TextSubmissionField.objects.create(
                                            assignment=updated_assignment,
                                            label=field_data.get('label', f"Question {i+1}"),
                                            placeholder=field_data.get('placeholder', "Enter your answer here..."),
                                            order=i,
                                            content=content_data
                                        )
                                        print(f"Created new field: {field.id}")
                                except TextSubmissionField.DoesNotExist:
                                    # If field doesn't exist, create a new one
                                    field = TextSubmissionField.objects.create(
                                        assignment=updated_assignment,
                                        label=field_data.get('label', f"Question {i+1}"),
                                        placeholder=field_data.get('placeholder', "Enter your answer here..."),
                                        order=i,
                                        content=content_data
                                    )
                                    print(f"Created field (after DoesNotExist): {field.id}")
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error: {e}")
                            print(f"Raw data: {text_fields}")
                        except Exception as e:
                            print(f"Error processing text submission fields: {e}")
                            import traceback
                            traceback.print_exc()
                    except Exception as e:
                        print(f"Error processing text submission fields: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Handle attachments to delete
                attachments_to_delete = request.POST.getlist('delete_attachments', [])
                if attachments_to_delete:
                    for attachment_id in attachments_to_delete:
                        try:
                            attachment = AssignmentAttachment.objects.get(id=attachment_id, assignment=updated_assignment)
                            # Delete the file from storage
                            if attachment.file:
                                try:
                                    if os.path.isfile(attachment.file.path):
                                        os.remove(attachment.file.path)
                                except NotImplementedError:
                                    # Cloud storage doesn't support absolute paths, skip local file deletion
                                    pass
                            # Delete the database record
                            attachment.delete()
                        except AssignmentAttachment.DoesNotExist:
                            pass
                
                # Redirect appropriately
                if topic_id:
                    return redirect(f'/courses/topic/{topic_id}/edit/')
                
                # Check if there's a next parameter in the URL
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                
                # Default redirect to the assignment list
                return redirect('assignments:assignment_list')
                
            except Exception as e:
                messages.error(request, f"Error saving assignment: {str(e)}")
        else:
            print("Form is invalid during edit. Errors:")
            for field, errors in form.errors.items():
                print(f"Field: {field} - Errors: {errors}")
            
            # More specific error messages
            if form.errors:
                error_messages = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if field == '__all__':
                            error_messages.append(str(error))
                        else:
                            field_name = field.replace('_', ' ').title()
                            if field == 'attachments':
                                field_name = 'File Attachments (Optional)'
                            elif field == 'course_ids':
                                field_name = 'Courses'
                            error_messages.append(f"{field_name}: {error}")
                
                # Create a comprehensive error message
                if error_messages:
                    messages.error(request, f"Please correct the following errors: {'; '.join(error_messages)}")
                else:
                    messages.error(request, "Please correct the errors below before submitting.")
            else:
                messages.error(request, "Please correct the errors below before submitting.")
    else:
        form = AssignmentForm(instance=assignment, user=request.user)
    
    # Check if we're coming from a topic
    if topic_id:
        try:
            topic = Topic.objects.get(id=topic_id)
            course = None
            
            # Try to get the course for this topic
            if topic:
                topic_course = Course.objects.filter(coursetopic__topic=topic).first()
                if topic_course:
                    course = topic_course
            
            # Update breadcrumbs
            if course and topic:
                breadcrumbs = [
                    {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                    {'url': reverse('courses:course_edit', args=[course.id]), 'label': course.title, 'icon': 'fa-book'},
                    {'url': f'/courses/topic/{topic.id}/edit/', 'label': topic.title, 'icon': 'fa-list'},
                    {'label': 'Edit Assignment', 'icon': 'fa-edit'}
                ]
        except Topic.DoesNotExist:
            pass
    
    context = {
        'form': form,
        'assignment': assignment,
        'object': assignment,
        'is_edit': True,
        'is_edit_mode': True,
        'profile_user': request.user,  # Fix: Use current user instead of None to prevent template errors
        'breadcrumbs': breadcrumbs,
        'back_url': reverse('assignments:assignment_list'),
        'available_rubrics': available_rubrics,
        'existing_attachments': existing_attachments,
        'existing_text_fields': existing_text_fields,
        'show_warning': request.GET.get('show_warning') == 'true',
        'available_courses': available_courses,
        'assignment_related_courses': assignment_related_courses,
        'assignment_related_topics': assignment_related_topics,
    }
    
    # If from topic, adjust back URL
    if topic_id:
        context['back_url'] = f'/courses/topic/{topic_id}/edit/'
    
    return render(request, 'assignments/assignment_form.html', context)

@login_required
def download_file(request, file_type, file_id):
    """View to download assignment or submission files"""
    if file_type == 'assignment':
        obj = get_object_or_404(Assignment, id=file_id)
        file_field = obj.attachment
        
        # Log file download interaction
        AssignmentInteractionLog.log_interaction(
            assignment=obj,
            user=request.user,
            interaction_type='file_download',
            request=request,
            file_name=os.path.basename(file_field.name) if file_field else None,
            file_type='assignment_attachment'
        )
        
        # Check permissions
        if request.user.role == 'learner' and (
            not obj.is_active or 
            not request.user.enrolled_courses.filter(id=obj.course.id).exists()
        ):
            return HttpResponseForbidden("You don't have access to this file")
    
    elif file_type == 'submission':
        obj = get_object_or_404(AssignmentSubmission, id=file_id)
        file_field = obj.submission_file
        
        # Log file download interaction
        AssignmentInteractionLog.log_interaction(
            assignment=obj.assignment,
            user=request.user,
            interaction_type='file_download',
            request=request,
            submission=obj,
            file_name=os.path.basename(file_field.name) if file_field else None,
            file_type='submission_file'
        )
        
        # Get the course - from direct relationship or from a topic
        course = None
        if obj.assignment.course:
            course = obj.assignment.course
        else:
            # Try to get course from the first topic assignment
            topic_assignment = obj.assignment.topicassignment_set.first()
            if topic_assignment:
                course = get_topic_course(topic_assignment.topic)
        
        # Check permissions
        if request.user.role == 'learner' and request.user != obj.user:
            return HttpResponseForbidden("You don't have access to this file")
        elif request.user.role == 'instructor' and course:
            # Check if instructor has management access to the course (direct or through groups)
            if not check_instructor_management_access(request.user, course):
                return HttpResponseForbidden("You don't have access to this file")
    
    else:
        return HttpResponseForbidden("Invalid file type")
    
    if not file_field:
        return HttpResponseForbidden("No file available")
    
    file_path = file_field.path
    content_type, encoding = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'
    
    response = HttpResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
    return response

@login_required
def view_pdf_inline(request, submission_id):
    """View to display PDF files inline in the browser"""
    from django.http import FileResponse
    
    submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    
    # Check permissions
    assignment = submission.assignment
    course = None
    if assignment.course:
        course = assignment.course
    else:
        topic_assignment = assignment.topicassignment_set.first()
        if topic_assignment:
            course = get_topic_course(topic_assignment.topic)
    
    # Check if user has permission to view this submission
    if request.user.role == 'learner' and request.user != submission.user:
        return HttpResponseForbidden("You don't have access to this file")
    elif request.user.role == 'instructor' and course:
        # Check if instructor has management access to the course (direct or through groups)
        if not check_instructor_management_access(request.user, course):
            return HttpResponseForbidden("You don't have access to this file")
    
    if not submission.submission_file:
        return HttpResponseForbidden("No file available")
    
    file_path = submission.submission_file.path
    
    # Check if file exists
    if not os.path.exists(file_path):
        return Http404("File not found")
    
    # Check if it's a PDF
    content_type, encoding = mimetypes.guess_type(file_path)
    if content_type != 'application/pdf':
        return HttpResponseForbidden("This viewer only supports PDF files")
    
    try:
        # Use FileResponse for better PDF serving
        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf',
            as_attachment=False,
            filename=os.path.basename(file_path)
        )
        
        # Set comprehensive headers for iframe compatibility
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        response['Accept-Ranges'] = 'bytes'
        
        # Remove restrictive headers
        if 'X-Frame-Options' in response:
            del response['X-Frame-Options']
        if 'X-Content-Type-Options' in response:
            del response['X-Content-Type-Options']
            
        # Set permissive CSP for iframe embedding
        response['Content-Session-Policy'] = "frame-ancestors 'self' "
        
        # Add cache headers
        response['Cache-Control'] = 'public, max-age=3600'
        
        return response
    except Exception as e:
        logger.error(f"Error serving PDF: {str(e)}")
        return HttpResponse("Error loading PDF file", status=500)

@login_required
def assignment_management(request):
    """View for instructors to manage assignments"""
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to access this page")
    
    assignments = Assignment.objects.all().order_by('-created_at')
    
    # Add breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Assignment Management', 'icon': 'fa-tasks'}
    ]
    
    context = {
        'assignments': assignments,
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'assignments/assignment_management.html', context)

@login_required
def delete_assignment(request, assignment_id):
    """View to delete an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if not (request.user.is_superuser or request.user.role in ['instructor', 'admin', 'superadmin']):
        return HttpResponseForbidden("You don't have permission to delete this assignment")
    
    if request.method == 'POST':
        assignment.delete()
        messages.success(request, "Assignment deleted successfully")
        return redirect('assignments:assignment_list')
    
    context = {
        'assignment': assignment,
    }
    return render(request, 'assignments/assignment_confirm_delete.html', context)

@login_required
def submit_assignment(request, assignment_id):
    """Handle assignment submission"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Log assignment submission page view
    AssignmentInteractionLog.log_interaction(
        assignment=assignment,
        user=request.user,
        interaction_type='start_submission',
        request=request
    )
    
    # Track or update session log
    session_key = request.session.session_key
    if session_key:
        session_log, created = AssignmentSessionLog.objects.get_or_create(
            assignment=assignment,
            user=request.user,
            session_key=session_key,
            is_active=True,
            defaults={
                'ip_address': AssignmentInteractionLog.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'page_views': 1,
                'interactions_count': 1,
            }
        )
        if not created:
            session_log.page_views += 1
            session_log.interactions_count += 1
            session_log.update_activity()
    
    # Check permissions
    if not assignment.is_available_for_user(request.user):
        messages.error(request, "You don't have permission to submit to this assignment.")
        return redirect('assignments:assignment_list')
    
    # Get existing submission for this user
    submission = AssignmentSubmission.objects.filter(
        assignment=assignment,
        user=request.user
    ).first()
    
    # Check if submission can be edited
    if submission and not submission.can_be_edited_by_student():
        messages.error(request, "This submission can no longer be edited.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    if request.method == 'POST':
        # Log submission attempt
        AssignmentInteractionLog.log_interaction(
            assignment=assignment,
            user=request.user,
            interaction_type='submission_submit',
            request=request,
            submission=submission
        )
        
        try:
            with transaction.atomic():
                # Handle file upload
                uploaded_file = request.FILES.get('submission_file')
                submission_text = request.POST.get('submission_text', '').strip()
                
                # Import required models for validation
                from .models import FileSubmissionIteration, TextSubmissionAnswerIteration, TextQuestionAnswerIteration
                
                # Validate that at least one type of submission is provided
                # Enhanced validation that matches assignment_detail view logic
                if assignment.submission_type == 'file':
                    # File-only assignment: require file on initial submission OR when revising without existing file
                    if not uploaded_file:
                        if not submission or not submission.submission_file:
                            # Check if there are any file iterations
                            has_file_iterations = False
                            if submission:
                                has_file_iterations = FileSubmissionIteration.objects.filter(
                                    submission=submission,
                                    file__isnull=False
                                ).exclude(file='').exists()
                            
                            if not has_file_iterations:
                                messages.error(request, 'A file submission is required for this assignment.')
                                return redirect('assignments:submit_assignment', assignment_id=assignment_id)
                
                elif assignment.submission_type == 'text':
                    # Text-only assignment: require text
                    if not submission_text:
                        # Check if there are any text field or question iterations
                        has_text_content = False
                        if submission:
                            has_text_content = (
                                TextSubmissionAnswerIteration.objects.filter(
                                    submission=submission,
                                    is_submitted=True
                                ).exists() or
                                TextQuestionAnswerIteration.objects.filter(
                                    submission=submission,
                                    is_submitted=True
                                ).exists()
                            )
                        
                        if not has_text_content:
                            messages.error(request, 'A text submission is required for this assignment.')
                            return redirect('assignments:submit_assignment', assignment_id=assignment_id)
                
                elif assignment.submission_type == 'both':
                    # Both file and text: require at least one
                    has_existing_file = False
                    has_text_content = False
                    
                    if submission:
                        # Check for existing file
                        has_existing_file = submission.submission_file or FileSubmissionIteration.objects.filter(
                            submission=submission,
                            file__isnull=False
                        ).exclude(file='').exists()
                        
                        # Check for existing text content
                        has_text_content = (
                            TextSubmissionAnswerIteration.objects.filter(
                                submission=submission,
                                is_submitted=True
                            ).exists() or
                            TextQuestionAnswerIteration.objects.filter(
                                submission=submission,
                                is_submitted=True
                            ).exists()
                        )
                    
                    if not uploaded_file and not submission_text and not has_existing_file and not has_text_content:
                        messages.error(request, 'Either a file or text submission (or both) is required for this assignment.')
                        return redirect('assignments:submit_assignment', assignment_id=assignment_id)
                
                # Log file upload if provided
                if uploaded_file:
                    AssignmentInteractionLog.log_interaction(
                        assignment=assignment,
                        user=request.user,
                        interaction_type='file_upload',
                        request=request,
                        submission=submission,
                        file_name=uploaded_file.name,
                        file_size=uploaded_file.size,
                            content_type=uploaded_file.content_type,
                        file_type=uploaded_file.content_type
                    )
                    
                    # Register file in media database for tracking
                    try:
                        from lms_media.utils import register_media_file
                        # For new submissions, the file is saved directly to submission_file field
                        if hasattr(uploaded_file, 'name'):
                            register_media_file(
                                file_path=f"assignment_content/submissions/{assignment.id}/{request.user.id}/{uploaded_file.name}",
                                uploaded_by=request.user,
                                source_type='assignment_submission',
                                source_model='AssignmentSubmission',
                                course=assignment.course if hasattr(assignment, 'course') else None,
                                filename=uploaded_file.name,
                                description=f'Assignment submission for: {assignment.title}'
                            )
                    except Exception as e:
                        logger.error(f"Error registering assignment submission file in media database: {str(e)}")
                
                # Create or update submission
                if submission:
                    # Update existing submission
                    old_status = submission.status
                    if uploaded_file:
                        submission.submission_file = uploaded_file
                    if submission_text:
                        submission.submission_text = submission_text
                    submission.status = 'submitted'
                    submission.submitted_at = timezone.now()
                    submission.save()
                    
                    # Log submission edit if this was an update
                    if old_status != 'submitted':
                        AssignmentInteractionLog.log_interaction(
                            assignment=assignment,
                            user=request.user,
                            interaction_type='submission_edit',
                            request=request,
                            submission=submission,
                            previous_status=old_status,
                            new_status='submitted'
                        )
                    
                    submission_type = 'resubmission' if old_status == 'submitted' else 'submission'
                else:
                    # Create new submission
                    submission = AssignmentSubmission.objects.create(
                        assignment=assignment,
                        user=request.user,
                        submission_file=uploaded_file,
                        submission_text=submission_text,
                        status='submitted'
                    )
                    submission_type = 'submission'
                
                # Handle text question answer iterations
                text_questions = TextQuestion.objects.filter(assignment=assignment)
                for question in text_questions:
                    answer_text = request.POST.get(f'text_question_{question.id}', '').strip()
                    if answer_text:
                        # Get or create the current iteration for this question
                        current_iteration, created = create_or_get_latest_iteration(question, submission, 'question')
                        
                        # Update the current iteration with the answer and mark as submitted
                        current_iteration.answer_text = answer_text
                        current_iteration.is_submitted = True
                        current_iteration.submitted_at = timezone.now()
                        current_iteration.save()
                
                # Handle text field answer iterations
                text_fields = TextSubmissionField.objects.filter(assignment=assignment)
                for field in text_fields:
                    answer_text = request.POST.get(f'text_field_{field.id}', '').strip()
                    if answer_text:
                        # Get or create the current iteration for this field
                        current_iteration, created = create_or_get_latest_iteration(field, submission, 'field')
                        
                        # Update the current iteration with the answer and mark as submitted
                        current_iteration.answer_text = answer_text
                        current_iteration.is_submitted = True
                        current_iteration.submitted_at = timezone.now()
                        current_iteration.save()
                
                # Log successful submission
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='submission_submit',
                    request=request,
                    submission=submission,
                    submission_type=submission_type,
                    success=True
                )
                
                messages.success(request, f'Your {submission_type} has been submitted successfully!')
                return redirect('assignments:assignment_detail', assignment_id=assignment_id)
                
        except Exception as e:
            # Log submission error
            AssignmentInteractionLog.log_interaction(
                assignment=assignment,
                user=request.user,
                interaction_type='submission_submit',
                request=request,
                submission=submission,
                success=False,
                error_message=str(e)
            )
            
            logger.error(f"Assignment submission error for user {request.user.id}: {str(e)}")
            messages.error(request, 'An error occurred while submitting your assignment. Please try again.')
            return redirect('assignments:submit_assignment', assignment_id=assignment_id)
    
    # GET request - show submission form
    # Get text questions and fields
    text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
    text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
    
    # Get existing answer iterations if this is an edit
    existing_text_answers = {}
    existing_field_answers = {}
    question_iteration_data = {}
    field_iteration_data = {}
    
    if submission:
        # For text questions, get iteration data
        for question in text_questions:
            iteration_data = get_iteration_data_for_question(question, submission)
            question_iteration_data[question.id] = iteration_data
            
            # For form display, use the current iteration's answer if it's not submitted yet
            if iteration_data['current_iteration'] and not iteration_data['current_iteration'].is_submitted:
                existing_text_answers[question.id] = iteration_data['current_iteration'].answer_text
        
        # For text fields, get iteration data
        for field in text_fields:
            iteration_data = get_iteration_data_for_field(field, submission)
            field_iteration_data[field.id] = iteration_data
            
            # For form display, use the current iteration's answer if it's not submitted yet
            if iteration_data['current_iteration'] and not iteration_data['current_iteration'].is_submitted:
                existing_field_answers[field.id] = iteration_data['current_iteration'].answer_text
    
    # Get course info for breadcrumbs
    course_info = assignment.get_course_info()
    
    # Build breadcrumbs
    breadcrumbs = [
        {'name': 'Assignments', 'url': reverse('assignments:assignment_list')},
        {'name': assignment.title, 'url': reverse('assignments:assignment_detail', args=[assignment.id])},
        {'name': 'Submit', 'url': None}
    ]
    
    context = {
        'assignment': assignment,
        'submission': submission,
        'text_questions': text_questions,
        'text_fields': text_fields,
        'existing_text_answers': existing_text_answers,
        'existing_field_answers': existing_field_answers,
        'question_iteration_data': question_iteration_data,
        'field_iteration_data': field_iteration_data,
        'course_info': course_info,
        'breadcrumbs': breadcrumbs,
        'can_edit': not submission or submission.can_be_edited_by_student(),
        'is_resubmission': submission and submission.status == 'submitted',
    }
    
    return render(request, 'assignments/submit.html', context)


@login_required
@require_POST
def submit_iteration(request, assignment_id):
    """Handle submission of a new iteration for text questions or fields"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if not assignment.is_available_for_user(request.user):
        messages.error(request, "You don't have permission to submit to this assignment.")
        return redirect('assignments:assignment_list')
    
    # Get or create submission
    submission, created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        user=request.user,
        defaults={'status': 'draft'}
    )
    
    try:
        with transaction.atomic():
            # Handle text question iterations
            for key, value in request.POST.items():
                if key.startswith('new_iteration_question_'):
                    question_id = int(key.replace('new_iteration_question_', ''))
                    answer_text = value.strip()
                    
                    if answer_text:
                        question = get_object_or_404(TextQuestion, id=question_id, assignment=assignment)
                        
                        # Check if learner can submit a new iteration
                        latest_iteration = TextQuestionAnswerIteration.objects.filter(
                            question=question,
                            submission=submission
                        ).order_by('-iteration_number').first()
                        
                        if latest_iteration:
                            latest_feedback = latest_iteration.feedback_entries.first()
                            if latest_feedback and not latest_feedback.allows_new_iteration:
                                # Check if assignment is returned - if so, always allow new iterations
                                if submission.status != 'returned':
                                    messages.error(request, f"You cannot submit a new iteration for question {question_id}. The instructor has closed feedback for this question.")
                                    continue
                        
                        # Create new iteration
                        iteration_number = (latest_iteration.iteration_number + 1) if latest_iteration else 1
                        TextQuestionAnswerIteration.objects.create(
                            question=question,
                            submission=submission,
                            iteration_number=iteration_number,
                            answer_text=answer_text,
                            is_submitted=True,
                            submitted_at=timezone.now()
                        )
                
                elif key.startswith('new_iteration_field_'):
                    field_id = int(key.replace('new_iteration_field_', ''))
                    answer_text = value.strip()
                    
                    if answer_text:
                        field = get_object_or_404(TextSubmissionField, id=field_id, assignment=assignment)
                        
                        # Check if learner can submit a new iteration
                        latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                            field=field,
                            submission=submission
                        ).order_by('-iteration_number').first()
                        
                        if latest_iteration:
                            latest_feedback = latest_iteration.feedback_entries.first()
                            if latest_feedback and not latest_feedback.allows_new_iteration:
                                # Check if assignment is returned - if so, always allow new iterations
                                if submission.status != 'returned':
                                    messages.error(request, f"You cannot submit a new iteration for field {field_id}. The instructor has closed feedback for this field.")
                                    continue
                        
                        # Create new iteration
                        iteration_number = (latest_iteration.iteration_number + 1) if latest_iteration else 1
                        TextSubmissionAnswerIteration.objects.create(
                            field=field,
                            submission=submission,
                            iteration_number=iteration_number,
                            answer_text=answer_text,
                            is_submitted=True,
                            submitted_at=timezone.now()
                        )
            
            messages.success(request, 'Your new iteration has been submitted successfully!')
            
    except Exception as e:
        logger.error(f"Error submitting iteration for user {request.user.id}: {str(e)}")
        messages.error(request, 'An error occurred while submitting your iteration. Please try again.')
    
    return redirect('assignments:assignment_detail', assignment_id=assignment_id)

@login_required
def grade_submission(request, submission_id):
    """View for grading assignment submissions"""
    submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    assignment = submission.assignment

    # Always ensure we are grading the learner's latest submission attempt
    # Fetch the most recent submission (by submitted_at) for this learner & assignment
    latest_submission = (
        AssignmentSubmission.objects
        .filter(assignment=submission.assignment, user=submission.user)
        .order_by('-submitted_at', '-id')
        .first()
    )

    # If the current submission is not the latest, redirect to grade the latest one
    # Avoid infinite redirect by checking IDs
    if latest_submission and latest_submission.id != submission.id:
        return redirect('assignments:grade_submission', submission_id=latest_submission.id)

    # Check permissions
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to grade submissions.")
        return redirect('assignments:assignment_detail', assignment_id=assignment.id)

    # Get existing rubric evaluations
    rubric_evaluations = list(submission.rubric_evaluations.all()) if assignment.rubric else []
    
    # Get rubric evaluation history across ALL submissions for this student and assignment
    # This gives instructors a complete view of how evaluations have changed across submission attempts
    all_student_submissions = AssignmentSubmission.objects.filter(
        assignment=assignment,
        user=submission.user
    ).values_list('id', flat=True)
    
    rubric_evaluation_history = RubricEvaluationHistory.objects.filter(
        submission__in=all_student_submissions
    ).select_related(
        'submission', 'criterion', 'rating', 'evaluated_by'
    ).order_by('submission__submitted_at', 'criterion__position', '-version')

    if request.method == 'POST':
        form = AssignmentGradingForm(request.POST, request.FILES, assignment=assignment, submission=submission, current_user=request.user)
        if form.is_valid():
            grade = form.cleaned_data.get('grade')
            feedback = form.cleaned_data.get('feedback')
            audio_feedback = form.cleaned_data.get('audio_feedback')
            video_feedback = form.cleaned_data.get('video_feedback')
            is_private = form.cleaned_data.get('is_private', False)

            # Process question iteration feedback - Updated for iteration system
            question_feedbacks_given = []
            for key, value in request.POST.items():
                if key.startswith('iteration_feedback_'):
                    try:
                        iteration_id = int(key.replace('iteration_feedback_', ''))
                        iteration = TextQuestionAnswerIteration.objects.get(id=iteration_id, submission=submission)
                        
                        if value.strip():  # Only create feedback if there's content
                            # Get the 'allows_new_iteration' checkbox value
                            allows_new_key = f'allows_new_iteration_{iteration_id}'
                            allows_new_iteration = allows_new_key in request.POST
                            
                            # Create feedback entry for this iteration
                            feedback_obj = TextQuestionIterationFeedback.objects.create(
                                iteration=iteration,
                                feedback_text=value,
                                allows_new_iteration=allows_new_iteration,
                                created_by=request.user
                            )
                            question_feedbacks_given.append({
                                'question': iteration.question,
                                'iteration': iteration,
                                'feedback': feedback_obj,
                                'action': 'created'
                            })
                    except (ValueError, TextQuestionAnswerIteration.DoesNotExist):
                        continue
            
            # Log question feedback interactions
            if question_feedbacks_given:
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='feedback_viewed',
                    request=request,
                    submission=submission,
                    feedback_type='question_feedback',
                    questions_count=len(question_feedbacks_given),
                    feedback_details=[{
                        'question_id': item['question'].id,
                        'question_text': item['question'].question_text[:100],
                        'action': item['action'],
                        'has_feedback': item['feedback'] is not None
                    } for item in question_feedbacks_given]
                )
            
            # Process text field iteration feedback - Updated for iteration system
            field_feedbacks_given = []
            for key, value in request.POST.items():
                if key.startswith('field_iteration_feedback_'):
                    try:
                        iteration_id = int(key.replace('field_iteration_feedback_', ''))
                        field_iteration = TextSubmissionAnswerIteration.objects.get(id=iteration_id, submission=submission)
                        
                        if value.strip():  # Only create feedback if there's content
                            # Always allow new iterations (removed checkbox)
                            allows_new_iteration = True
                            
                            # Create feedback entry for this field iteration
                            feedback_obj = TextSubmissionIterationFeedback.objects.create(
                                iteration=field_iteration,
                                feedback_text=value,
                                allows_new_iteration=allows_new_iteration,
                                created_by=request.user
                            )
                            field_feedbacks_given.append({
                                'field': field_iteration.field,
                                'iteration': field_iteration,
                                'feedback': feedback_obj,
                                'action': 'created'
                            })
                    except (ValueError, TextSubmissionAnswerIteration.DoesNotExist) as e:
                        continue
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        continue
            
            # Process file iteration feedback - New for file iteration system
            file_feedbacks_given = []
            for key, value in request.POST.items():
                if key.startswith('file_iteration_feedback_'):
                    try:
                        iteration_id = int(key.replace('file_iteration_feedback_', ''))
                        from assignments.models import FileSubmissionIteration, FileSubmissionIterationFeedback
                        file_iteration = FileSubmissionIteration.objects.get(id=iteration_id, submission=submission)
                        
                        if value.strip():  # Only create feedback if there's content
                            # Get the 'allows_new_iteration' checkbox value for files
                            allows_new_key = f'file_allows_new_iteration_{iteration_id}'
                            allows_new_iteration = allows_new_key in request.POST
                            
                            # Create feedback entry for this file iteration
                            feedback_obj = FileSubmissionIterationFeedback.objects.create(
                                iteration=file_iteration,
                                feedback_text=value,
                                allows_new_iteration=allows_new_iteration,
                                created_by=request.user
                            )
                            file_feedbacks_given.append({
                                'iteration': file_iteration,
                                'feedback': feedback_obj,
                                'action': 'created'
                            })
                    except (ValueError, FileSubmissionIteration.DoesNotExist) as e:
                        continue
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        continue
                
                # Process initial feedback for fields without iterations
                elif key.startswith('field_initial_feedback_'):
                    try:
                        field_id = int(key.replace('field_initial_feedback_', ''))
                        field = TextSubmissionField.objects.get(id=field_id, assignment=assignment)
                        
                        if value.strip():  # Only create feedback if there's content
                            # Create a placeholder iteration for initial feedback
                            field_iteration = TextSubmissionAnswerIteration.objects.create(
                                field=field,
                                submission=submission,
                                answer_text="[Awaiting learner response]",
                                iteration_number=0,  # Use 0 to indicate initial feedback
                                is_submitted=False  # Not submitted by learner
                            )
                            
                            # Create feedback entry for this initial iteration
                            feedback_obj = TextSubmissionIterationFeedback.objects.create(
                                iteration=field_iteration,
                                feedback_text=value,
                                allows_new_iteration=True,  # Always allow response for initial feedback
                                created_by=request.user
                            )
                            field_feedbacks_given.append({
                                'field': field,
                                'iteration': field_iteration,
                                'feedback': feedback_obj,
                                'action': 'initial_feedback'
                            })
                    except (ValueError, TextSubmissionField.DoesNotExist) as e:
                        continue
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        continue
            
            # Log text field feedback interactions
            if field_feedbacks_given:
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='feedback_viewed',
                    request=request,
                    submission=submission,
                    feedback_type='field_feedback',
                    fields_count=len(field_feedbacks_given),
                    feedback_details=[{
                        'field_id': item['field'].id,
                        'field_label': item['field'].label,
                        'action': item['action'],
                        'has_feedback': item['feedback'] is not None
                    } for item in field_feedbacks_given]
                )
            
            # Log file feedback interactions
            if file_feedbacks_given:
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='feedback_viewed',
                    request=request,
                    submission=submission,
                    feedback_type='file_feedback',
                    files_count=len(file_feedbacks_given),
                    feedback_details=[{
                        'iteration_id': item['iteration'].id,
                        'file_name': item['iteration'].file_name,
                        'action': item['action'],
                        'has_feedback': item['feedback'] is not None,
                        'allows_new_iteration': item['feedback'].allows_new_iteration if item['feedback'] else None
                    } for item in file_feedbacks_given]
                )

            # Process overall feedback
            if feedback or audio_feedback or video_feedback:
                # Check if feedback has actually changed from the last entry
                # Get the most recent feedback from the current instructor
                last_feedback = AssignmentFeedback.objects.filter(
                    submission=submission,
                    created_by=request.user
                ).order_by('-created_at').first()
                
                # Determine if feedback has changed
                feedback_changed = True
                if last_feedback and not audio_feedback and not video_feedback:
                    # If no new multimedia files and text hasn't changed, don't create duplicate
                    if (last_feedback.feedback or '') == (feedback or '') and last_feedback.is_private == is_private:
                        feedback_changed = False
                
                if feedback_changed:
                    feedback_obj = AssignmentFeedback.objects.create(
                        submission=submission,
                        feedback=feedback,
                        audio_feedback=audio_feedback,
                        video_feedback=video_feedback,
                        created_by=request.user,
                        is_private=is_private
                    )
                    
                    # Log feedback interaction
                    AssignmentInteractionLog.log_interaction(
                        assignment=assignment,
                        user=request.user,
                        interaction_type='feedback_viewed',
                        request=request,
                        submission=submission,
                        feedback_type='overall',
                        has_text_feedback=bool(feedback),
                        has_audio_feedback=bool(audio_feedback),
                        has_video_feedback=bool(video_feedback),
                        is_private=is_private
                    )

            # Process grade and status
            status = form.cleaned_data.get('status', 'graded')
            if grade is not None:
                old_grade = submission.grade
                old_status = submission.status
                submission.grade = grade
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.status = status
                submission.save()
                
                # Log grade change interaction
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='grade_change',
                    request=request,
                    submission=submission,
                    previous_grade=float(old_grade) if old_grade else None,
                    new_grade=float(grade),
                    previous_status=old_status,
                    new_status=status
                )
            elif status == 'returned':
                # Handle returning for revision without grade
                old_status = submission.status
                submission.status = 'returned'
                submission.graded_by = request.user  # Set who returned it for revision
                submission.save()
                
                # Log status change interaction
                AssignmentInteractionLog.log_interaction(
                    assignment=assignment,
                    user=request.user,
                    interaction_type='submission_edit',
                    request=request,
                    submission=submission,
                    previous_status=old_status,
                    new_status='returned'
                )

            # Process rubric evaluations
            if assignment.rubric:
                try:
                    rubric_data = json.loads(request.POST.get('rubric_data', '{}'))
                    rubric_evaluations_created = []
                    for criterion_id, evaluation in rubric_data.items():
                        points = float(evaluation.get('points', 0))
                        rating_id = evaluation.get('rating_id')  # Fixed: was 'rating', should be 'rating_id'
                        comments = evaluation.get('comments', '')
                        
                        # Get or create the evaluation first
                        try:
                            rubric_eval = RubricEvaluation.objects.get(
                                submission=submission,
                                criterion_id=criterion_id
                            )
                            # Store old values for comparison
                            old_points = rubric_eval.points
                            old_rating_id = rubric_eval.rating_id if rubric_eval.rating else None
                            old_comments = rubric_eval.comments
                            
                            # Prepare new values
                            new_rating = None
                            if rating_id:
                                try:
                                    new_rating = RubricRating.objects.get(id=rating_id)
                                except RubricRating.DoesNotExist:
                                    pass
                            
                            # Check if any values have actually changed
                            # This prevents duplicate history entries when only instructor feedback changes
                            # but rubric evaluations remain the same
                            has_changed = (
                                old_points != points or 
                                old_rating_id != (new_rating.id if new_rating else None) or 
                                old_comments != comments
                            )
                            
                            if has_changed:
                                # Update the evaluation only if values have changed
                                rubric_eval.points = points
                                rubric_eval.comments = comments
                                rubric_eval.evaluated_by = request.user
                                rubric_eval.rating = new_rating
                                
                                # Save once with all data set
                                rubric_eval.save()
                            
                            created = False
                            
                        except RubricEvaluation.DoesNotExist:
                            # Create new evaluation with all data set
                            rating = None
                            if rating_id:
                                try:
                                    rating = RubricRating.objects.get(id=rating_id)
                                except RubricRating.DoesNotExist:
                                    pass
                            
                            rubric_eval = RubricEvaluation.objects.create(
                                submission=submission,
                                criterion_id=criterion_id,
                                points=points,
                                comments=comments,
                                evaluated_by=request.user,
                                rating=rating
                            )
                            created = True
                        
                        rubric_evaluations_created.append(rubric_eval)
                    
                    # Log rubric evaluation interaction
                    if rubric_evaluations_created:
                        AssignmentInteractionLog.log_interaction(
                            assignment=assignment,
                            user=request.user,
                            interaction_type='rubric_evaluation',
                            request=request,
                            submission=submission,
                            rubric_title=assignment.rubric.title,
                            evaluations_count=len(rubric_evaluations_created),
                            total_points=sum(eval.points for eval in rubric_evaluations_created),
                            max_points=assignment.rubric.total_points if hasattr(assignment.rubric, 'total_points') else None
                        )
                except json.JSONDecodeError:
                    messages.warning(request, "Error processing rubric data.")

            messages.success(request, "Submission graded successfully.")
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = AssignmentGradingForm(assignment=assignment, submission=submission, current_user=request.user)

    # Get outcome evaluations for this student
    outcome_evaluations = []
    outcome_preview = {}
    try:
        from lms_outcomes.models import RubricCriterionOutcome, OutcomeEvaluation
        
        if assignment.rubric:
            # Get outcomes connected to this rubric's criteria
            connected_outcomes = RubricCriterionOutcome.objects.filter(
                criterion__rubric=assignment.rubric
            ).select_related('outcome', 'criterion').order_by('outcome__title')
            
            for connection in connected_outcomes:
                outcome = connection.outcome
                criterion = connection.criterion
                weight = connection.weight
                
                # Get current outcome evaluation for this student
                try:
                    current_evaluation = OutcomeEvaluation.objects.get(
                        student=submission.user,
                        outcome=outcome
                    )
                    current_score = current_evaluation.score
                    current_level = current_evaluation.proficiency_level
                except OutcomeEvaluation.DoesNotExist:
                    current_score = 0
                    current_level = "Not Assessed"
                
                # Calculate preview of how this rubric evaluation might affect the outcome
                evidence_scores = outcome._get_evidence_scores(submission.user)
                evidence_count = len(evidence_scores)
                
                outcome_evaluations.append({
                    'outcome': outcome,
                    'criterion': criterion,
                    'weight': weight,
                    'current_score': current_score,
                    'current_level': current_level,
                    'evidence_count': evidence_count,
                    'calculation_method': outcome.get_calculation_method_display()
                })
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching outcome evaluations: {str(e)}")
        outcome_evaluations = []

    # Get the student's iterations for text questions if any
    text_answers = []
    text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
    if text_questions.exists():
        for question in text_questions:
            # Get the latest submitted iteration for this question
            latest_iteration = TextQuestionAnswerIteration.objects.filter(
                question=question,
                submission=submission,
                is_submitted=True
            ).order_by('-iteration_number').first()
            
            if latest_iteration:
                # Get the latest feedback for this iteration by current instructor
                latest_feedback = latest_iteration.feedback_entries.filter(created_by=request.user).first()
                text_answers.append({
                    'question': question,
                    'answer': latest_iteration,
                    'feedback': latest_feedback
                })
            else:
                text_answers.append({
                    'question': question,
                    'answer': None,
                    'feedback': None
                })

    # Get any text field iterations
    text_field_submissions = []
    text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
    # Loading text fields for assignment
    if text_fields.exists():
        for field in text_fields:
            # Get the latest submitted iteration for this field
            latest_iteration = TextSubmissionAnswerIteration.objects.filter(
                field=field,
                submission=submission,
                is_submitted=True
            ).order_by('-iteration_number').first()
            
            if latest_iteration:
                feedback = latest_iteration.feedback_entries.filter(created_by=request.user).first()
                print(f"Field {field.id} - Iteration {latest_iteration.id} - User: {request.user.username} - Feedback: {feedback}")
                if feedback:
                    print(f"  Feedback text: {feedback.feedback_text[:50]}...")
                text_field_submissions.append({
                    'field': field,
                    'answer': latest_iteration,
                    'feedback': feedback  # Latest feedback by current instructor
                })
            else:
                text_field_submissions.append({
                    'field': field,
                    'answer': None,
                    'feedback': None
                })
    
    # Prepare rubric data for the template
    rubric_data = None
    if assignment.rubric:
        rubric = assignment.rubric
        criteria = rubric.criteria.all()
        ratings_by_criterion = {}
        
        # Get all ratings for each criterion
        for criterion in criteria:
            criterion_ratings = RubricRating.objects.filter(
                criterion=criterion
            ).order_by('-points')
            ratings_by_criterion[criterion.id] = criterion_ratings
        
        # Get existing evaluations by criterion id
        evaluations_by_criterion = {}
        if rubric_evaluations:
            for evaluation in rubric_evaluations:
                evaluations_by_criterion[evaluation.criterion_id] = evaluation
        
        criteria_with_data = []
        for criterion in criteria:
            # Get history for this criterion
            criterion_history = rubric_evaluation_history.filter(criterion=criterion)
            
            criteria_with_data.append({
                'criterion': criterion,
                'ratings': ratings_by_criterion.get(criterion.id, []),
                'evaluation': evaluations_by_criterion.get(criterion.id),
                'history': criterion_history  # Add history for this criterion
            })
        
        rubric_data = {
            'rubric': rubric,
            'criteria_with_data': criteria_with_data
        }
    
    # Get feedback if any
    try:
        feedback = AssignmentFeedback.objects.filter(submission=submission).order_by('-created_at').first()
    except AssignmentFeedback.DoesNotExist:
        feedback = None
    
    # Get iteration data for questions and fields
    question_iteration_data = {}
    text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
    for question in text_questions:
        question_iteration_data[question.id] = get_iteration_data_for_question(question, submission)
    
    field_iteration_data = {}
    text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
    for field in text_fields:
        field_iteration_data[field.id] = get_iteration_data_for_field(field, submission)

    # Get all file iterations from this learner for this assignment  
    from assignments.models import FileSubmissionIteration
    file_iterations = FileSubmissionIteration.objects.filter(
        submission__assignment=assignment,
        submission__user=submission.user,
        file__isnull=False  # Only include iterations that actually have files
    ).exclude(file='').select_related('submission').prefetch_related(
        'feedback_entries__created_by'
    ).order_by('-submitted_at')
    
    # Prepare file submission history data with iteration support
    file_submission_history = []
    
    # Group iterations by submission for timeline display
    file_iteration_data = {}
    if file_iterations.exists():
        iterations_list = []
        for iteration in file_iterations:
            feedback_entries = iteration.feedback_entries.all().order_by('-created_at')
            # Get file extension safely
            file_extension = 'unknown'
            if iteration.file:
                try:
                    file_extension = iteration.file.name.split('.')[-1].lower() if '.' in iteration.file.name else 'unknown'
                except (AttributeError, ValueError):
                    file_extension = 'unknown'
            
            iterations_list.append({
                'iteration': iteration,
                'feedback_entries': feedback_entries,
                'latest_feedback': feedback_entries.first() if feedback_entries.exists() else None,
                'can_upload_new': not feedback_entries.exists() or feedback_entries.first().allows_new_iteration,
                'file_extension': file_extension,
                'is_current': iteration.submission.id == submission.id
            })
        
        file_iteration_data = {
            'has_iterations': True,
            'iterations': iterations_list,
            'latest_iteration': file_iterations.first(),
        }
    else:
        file_iteration_data = {
            'has_iterations': False,
            'iterations': [],
            'latest_iteration': None,
        }
    
    # Always ensure file_iteration_data exists in context, even if empty
        file_iteration_data = {
            'has_iterations': False,
            'iterations': [],
            'latest_iteration': None,
        }
    
    # Maintain backward compatibility with old file submission history
    all_submissions = AssignmentSubmission.objects.filter(
        assignment=assignment,
        user=submission.user,
        submission_file__isnull=False
    ).exclude(submission_file='').order_by('-submitted_at')
    
    for sub in all_submissions:
        if sub.submission_file:
            file_submission_history.append({
                'submission': sub,
                'is_current': sub.id == submission.id,
                'file_extension': sub.submission_file.name.split('.')[-1].lower() if '.' in sub.submission_file.name else 'unknown'
            })

    context = {
        'submission': submission,
        'assignment': assignment,
        'text_answers': text_answers,
        'text_field_submissions': text_field_submissions,
        'question_iteration_data': question_iteration_data,
        'field_iteration_data': field_iteration_data,
        'file_submission_history': file_submission_history,
        'file_iteration_data': file_iteration_data,
        'feedback': feedback,
        'rubric_data': rubric_data,
        'rubric_evaluation_history': rubric_evaluation_history,  # Add full history
        'form': form,
        'outcome_evaluations': outcome_evaluations,  # Add outcome evaluation data
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-tasks'},
            {'url': reverse('assignments:assignment_detail', args=[assignment.id]), 'label': assignment.title, 'icon': 'fa-file-alt'},
            {'label': 'Grade Submission', 'icon': 'fa-check-circle'}
        ]
    }
    
    return render(request, 'assignments/grade_submission.html', context)


@login_required
def view_assignment_feedback(request, assignment_id):
    """View for students to see feedback on their assignment submissions"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Log feedback viewing interaction
    AssignmentInteractionLog.log_interaction(
        assignment=assignment,
        user=request.user,
        interaction_type='feedback_viewed',
        request=request
    )
    
    # Get the user's latest submission for this assignment
    submission = AssignmentSubmission.objects.filter(
        assignment=assignment,
        user=request.user
    ).select_related('graded_by').prefetch_related(
        'feedback_entries__created_by',
        'rubric_evaluations__criterion',
        'rubric_evaluations__rating',
        'text_answer_iterations__question',
        'text_answer_iterations__feedback_entries',
        'field_answer_iterations__field',
        'field_answer_iterations__feedback_entries'
    ).order_by('-submitted_at').first()
    
    if not submission:
        messages.error(request, "You haven't submitted this assignment yet.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Check if there's any feedback to display
    has_feedback = (
        submission.feedback_entries.exists() or 
        submission.rubric_evaluations.exists() or
        submission.grade is not None
    )
    
    if not has_feedback:
        messages.info(request, "No feedback available yet for this assignment.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Get feedback entries
    feedback_entries = submission.feedback_entries.all().order_by('-created_at')
    
    # Get rubric evaluations
    rubric_evaluations = submission.rubric_evaluations.all()
    
    # Get text question iterations with feedback
    text_answers = []
    text_questions = TextQuestion.objects.filter(assignment=assignment).order_by('order')
    for question in text_questions:
        # Get the latest submitted iteration for this question
        latest_iteration = TextQuestionAnswerIteration.objects.filter(
            question=question,
            submission=submission,
            is_submitted=True
        ).order_by('-iteration_number').first()
        
        if latest_iteration:
            # Get the latest feedback for this iteration by any instructor
            latest_feedback = latest_iteration.feedback_entries.first()
            text_answers.append({
                'question': question,
                'answer': latest_iteration,
                'feedback': latest_feedback
            })
        else:
            text_answers.append({
                'question': question,
                'answer': None,
                'feedback': None
            })
    
    # Get text field iterations with feedback
    text_field_answers = []
    text_fields = TextSubmissionField.objects.filter(assignment=assignment).order_by('order')
    for field in text_fields:
        # Get the latest submitted iteration for this field
        latest_iteration = TextSubmissionAnswerIteration.objects.filter(
            field=field,
            submission=submission,
            is_submitted=True
        ).order_by('-iteration_number').first()
        
        if latest_iteration:
            # Get the latest feedback for this iteration by any instructor
            latest_feedback = latest_iteration.feedback_entries.first()
            text_field_answers.append({
                'field': field,
                'answer': latest_iteration,
                'feedback': latest_feedback
            })
        else:
            text_field_answers.append({
                'field': field,
                'answer': None,
                'feedback': None
            })
    
    # Prepare rubric data
    rubric_data = None
    if assignment.rubric and rubric_evaluations:
        rubric = assignment.rubric
        criteria = rubric.criteria.all()
        
        # Get existing evaluations by criterion id
        evaluations_by_criterion = {}
        for evaluation in rubric_evaluations:
            evaluations_by_criterion[evaluation.criterion_id] = evaluation
        
        criteria_with_data = []
        for criterion in criteria:
            criteria_with_data.append({
                'criterion': criterion,
                'evaluation': evaluations_by_criterion.get(criterion.id)
            })
        
        rubric_data = {
            'rubric': rubric,
            'criteria_with_data': criteria_with_data,
            'total_score': sum(eval.points for eval in rubric_evaluations)
        }
    
    # Calculate grade percentage
    grade_percentage = None
    if submission.grade and assignment.max_score and assignment.max_score > 0:
        grade_percentage = (float(submission.grade) / float(assignment.max_score)) * 100
    
    context = {
        'assignment': assignment,
        'submission': submission,
        'feedback_entries': feedback_entries,
        'text_answers': text_answers,
        'text_field_answers': text_field_answers,
        'rubric_data': rubric_data,
        'grade_percentage': grade_percentage,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-file-text'},
            {'url': reverse('assignments:assignment_detail', args=[assignment.id]), 'label': assignment.title, 'icon': 'fa-file-text'},
            {'label': 'Feedback', 'icon': 'fa-comments'}
        ]
    }
    
    return render(request, 'assignments/view_feedback.html', context)


@login_required
def submission_grade_history(request, submission_id):
    """API endpoint to get grade history for a submission"""
    try:
        submission = AssignmentSubmission.objects.get(id=submission_id)
        # Check if user has permission to view this submission
        if not (request.user.is_staff or request.user.is_superuser or 
                submission.user == request.user or 
                request.user.role in ['instructor', 'admin']):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        history = submission.grade_history.all().select_related('changed_by')
        history_data = [{
            'changed_at': entry.changed_at.isoformat(),
            'previous_grade': float(entry.previous_grade) if entry.previous_grade is not None else None,
            'new_grade': float(entry.new_grade) if entry.new_grade is not None else None,
            'previous_status': entry.previous_status,
            'new_status': entry.new_status,
            'changed_by_name': entry.changed_by.get_full_name() if entry.changed_by else 'System',
            'comment': entry.comment
        } for entry in history]
        
        return JsonResponse({'history': history_data})
    except AssignmentSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def test_pdf_viewer(request, submission_id):
    """Test view to debug PDF display issues"""
    from django.http import FileResponse
    from django.urls import reverse
    import os
    import mimetypes
    
    submission = get_object_or_404(AssignmentSubmission, id=submission_id)
    
    if not submission.submission_file:
        return HttpResponse("No file available")
    
    # Create a simple HTML page with different PDF viewing methods
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PDF Viewer Test</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .viewer {{ margin: 20px 0; padding: 20px; border: 1px solid #ccc; }}
            .viewer h3 {{ margin-top: 0; }}
            iframe, embed, object {{ width: 100%; height: 500px; border: 1px solid #999; }}
        </style>
    </head>
    <body>
        <h1>PDF Viewer Test for: {os.path.basename(submission.submission_file.name)}</h1>
        
        <div class="viewer">
            <h3>Method 1: Direct Embed</h3>
            <embed src="{submission.submission_file.url}" type="application/pdf" />
        </div>
        
        <div class="viewer">
            <h3>Method 2: Object Tag</h3>
            <object data="{submission.submission_file.url}" type="application/pdf">
                <p>PDF cannot be displayed</p>
            </object>
        </div>
        
        <div class="viewer">
            <h3>Method 3: IFrame with Django View</h3>
            <iframe src="{request.build_absolute_uri(reverse('assignments:view_pdf_inline', args=[submission_id]))}"></iframe>
        </div>
        
        <div class="viewer">
            <h3>Method 4: Direct Link</h3>
            <a href="{submission.submission_file.url}" target="_blank">Open PDF in new tab</a>
        </div>
        
        <div class="viewer">
            <h3>Debug Info:</h3>
            <ul>
                <li>File URL: {submission.submission_file.url}</li>
                <li>File Path: {submission.submission_file.name}</li>
                <li>File Exists: {hasattr(submission.submission_file, 'url')}</li>
                <li>Content Type: {mimetypes.guess_type(submission.submission_file.name)[0]}</li>
            </ul>
        </div>
    </body>
    </html>
    """
    
    response = HttpResponse(html, content_type='text/html')
    # Remove restrictive headers for this test page
    if 'X-Frame-Options' in response:
        del response['X-Frame-Options']
    return response


@login_required
def question_delete(request, question_id):
    """View to delete a question"""
    from quiz.models import Quiz
    question = get_object_or_404(Quiz.Question, id=question_id)
    quiz = question.quiz
    
    # Check permissions
    if request.user != quiz.creator and not (request.user.role == 'admin' or request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
        return HttpResponseForbidden("You don't have permission to delete this question")
    
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question deleted successfully")
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)
    
    return render(request, 'assignments/question_delete_confirm.html', {'question': question})


@login_required
def question_create(request, quiz_id):
    """View to create a new question for a quiz"""
    from quiz.models import Quiz
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    if request.user != quiz.creator and not (request.user.role == 'admin' or request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
        return HttpResponseForbidden("You don't have permission to add questions to this quiz")
    
    if request.method == 'POST':
        # Process form submission for creating question
        # This would depend on your specific Question model and form
        # For example:
        # form = QuestionForm(request.POST)
        # if form.is_valid():
        #     question = form.save(commit=False)
        #     question.quiz = quiz
        #     question.save()
        #     messages.success(request, "Question added successfully")
        #     return redirect('quiz:edit_quiz', quiz_id=quiz.id)
        pass
    else:
        # Display empty form
        # form = QuestionForm()
        pass
    
    context = {
        'quiz': quiz,
        # 'form': form,
    }
    
    return render(request, 'assignments/question_form.html', context)


@login_required
def text_question_create(request, assignment_id):
    """Create a new text question for an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to add questions to this assignment")
    
    # For AJAX requests, return the form HTML
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from .forms import TextQuestionForm
        form = TextQuestionForm()
        return render(request, 'assignments/text_question_form.html', {
            'form': form,
            'assignment': assignment,
            'is_ajax': True
        })
    
    # Handle form submission
    if request.method == 'POST':
        from .forms import TextQuestionForm
        form = TextQuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.assignment = assignment
            
            # Set default order if not provided
            if not question.order:
                max_order = TextQuestion.objects.filter(assignment=assignment).aggregate(Max('order'))['order__max'] or 0
                question.order = max_order + 1
                
            # The HTML is already processed by the TinyMCE form field
            question.save()
            
            # If this is an AJAX request, return a JSON response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.utils.html import strip_tags
                # Extract the first 100 characters of text for display
                display_text = strip_tags(question.question_html or question.question_text)[:100]
                
                return JsonResponse({
                    'success': True,
                    'question': {
                        'id': question.id,
                        'question_text': display_text,
                        'question_html': question.question_html or '',
                        'order': question.order
                    }
                })
            
            messages.success(request, "Question added successfully")
            return redirect('assignments:edit_assignment', assignment_id=assignment.id)
        elif request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Return form errors via JSON
            return JsonResponse({
                'success': False,
                'errors': form.errors.as_json(),
                'message': 'Please correct the errors below.'
            })
    else:
        from .forms import TextQuestionForm
        form = TextQuestionForm()
    
    return render(request, 'assignments/text_question_form.html', {
        'form': form,
        'assignment': assignment,
        'is_ajax': False
    })


@login_required
def text_question_edit(request, question_id):
    """Edit a text question"""
    question = get_object_or_404(TextQuestion, id=question_id)
    assignment = question.assignment
    
    # Check permissions
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to edit this question")
    
    # For AJAX requests, return the form HTML
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from .forms import TextQuestionForm
        form = TextQuestionForm(instance=question)
        return render(request, 'assignments/text_question_form.html', {
            'form': form,
            'question': question,
            'assignment': assignment,
            'is_ajax': True,
            'is_edit': True
        })
    
    # Handle form submission
    if request.method == 'POST':
        from .forms import TextQuestionForm
        form = TextQuestionForm(request.POST, instance=question)
        if form.is_valid():
            question = form.save(commit=False)
            
            # The HTML is already processed by the TinyMCE form field
            question.save()
            
            # If this is an AJAX request, return a JSON response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.utils.html import strip_tags
                # Extract the first 100 characters of text for display
                display_text = strip_tags(question.question_html or question.question_text)[:100]
                
                return JsonResponse({
                    'success': True,
                    'question': {
                        'id': question.id,
                        'question_text': display_text,
                        'question_html': question.question_html or '',
                        'order': question.order
                    },
                    'reload': False
                })
            
            messages.success(request, "Question updated successfully")
            return redirect('assignments:edit_assignment', assignment_id=assignment.id)
        elif request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Return form errors via JSON
            return JsonResponse({
                'success': False,
                'errors': form.errors.as_json(),
                'message': 'Please correct the errors below.'
            })
    else:
        from .forms import TextQuestionForm
        form = TextQuestionForm(instance=question)
    
    return render(request, 'assignments/text_question_form.html', {
        'form': form,
        'question': question,
        'assignment': assignment,
        'is_edit': True,
        'is_ajax': False
    })


@login_required
def text_question_delete(request, question_id):
    """View to delete a text question"""
    question = get_object_or_404(TextQuestion, id=question_id)
    assignment = question.assignment
    
    # Check permissions
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to delete this question")
    
    if request.method == 'POST':
        question_id = question.id  # Store ID before deleting
        question.delete()
        
        # Reorder remaining questions
        for i, q in enumerate(assignment.text_questions.all().order_by('order')):
            q.order = i + 1
            q.save()
        
        # If this is an AJAX request, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'question_id': question_id,
                'reload': False
            })
            
        messages.success(request, "Question deleted successfully")
        return redirect('assignments:edit_assignment', assignment_id=assignment.id)
    
    # If this is an AJAX request, return confirmation dialog
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'assignments/text_question_delete_confirm_partial.html', {
            'question': question,
            'assignment': assignment
        })
    
    return render(request, 'assignments/text_question_delete_confirm.html', {
        'question': question,
        'assignment': assignment
    })


@login_required
def update_text_question_order(request, assignment_id):
    """View to update the order of text questions"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to reorder questions")
    
    if request.method == 'POST':
        try:
            # Handle JSON data from fetch API
            if request.headers.get('Content-Type') == 'application/json':
                import json
                data = json.loads(request.body)
                questions = data.get('questions', [])
                
                from django.db import transaction
                with transaction.atomic():
                    for item in questions:
                        question = TextQuestion.objects.get(id=int(item['id']))
                        question.order = item['order']
                        question.save()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True})
                else:
                    messages.success(request, 'Question order updated successfully')
                    return redirect('assignments:assignment_edit', assignment_id=assignment.id)
            # Handle form data for backward compatibility
            else:
                question_order = request.POST.get('question_order')
                question_order = question_order.split(',')
                
                from django.db import transaction
                with transaction.atomic():
                    for i, question_id in enumerate(question_order):
                        if question_id:
                            question = TextQuestion.objects.get(id=int(question_id))
                            question.order = i + 1
                            question.save()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True})
                else:
                    messages.success(request, 'Question order updated successfully')
                    return redirect('assignments:assignment_edit', assignment_id=assignment.id)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def assignment_detailed_report(request, assignment_id):
    """Comprehensive detailed report for a specific student's assignment submission with complete timeline"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions - only instructors, admins, and superadmins can access
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to access this report.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Get student_id from query parameters
    student_id = request.GET.get('student_id')
    if not student_id:
        messages.error(request, "Student ID is required.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Get the specific student and their submission
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # Get the main submission
    try:
        submission = AssignmentSubmission.objects.get(
            assignment=assignment,
            user=student
        )
    except AssignmentSubmission.DoesNotExist:
        submission = None
    
    # Get all file iterations (resubmissions) if any
    file_iterations = []
    if submission:
        file_iterations = submission.file_iterations.all().prefetch_related('feedback_entries__created_by').order_by('iteration_number')
    
    # Get feedback entries
    feedback_entries = []
    if submission:
        feedback_entries = submission.feedback_entries.all().select_related('created_by').order_by('created_at')
    
    # Get text answers if assignment has text questions
    text_answers = []
    if submission and assignment.text_questions.exists():
        text_answers = submission.text_answers.all().select_related('question').order_by('question__order')
    
    # Get field answers if assignment has text fields
    field_answers = []
    if submission and assignment.text_fields.exists():
        field_answers = submission.field_answers.all().select_related('field').order_by('field__order')
    
    # Get rubric evaluations if exist
    rubric_evaluations = []
    rubric_total_score = 0
    if submission and assignment.rubric:
        from lms_rubrics.models import RubricEvaluation
        rubric_evaluations = RubricEvaluation.objects.filter(
            submission=submission,
            criterion__rubric=assignment.rubric
        ).select_related('criterion', 'rating', 'evaluated_by').order_by('criterion__position')
        
        # Calculate total score
        rubric_total_score = sum(eval.points for eval in rubric_evaluations)
    
    # === ENHANCED TIMELINE DATA GATHERING ===
    
    # Get Grade History
    grade_history = []
    if submission:
        grade_history = submission.grade_history.all().select_related('changed_by').order_by('-changed_at')
    
    # Get Rubric Evaluation History
    rubric_history = []
    if submission and assignment.rubric:
        from lms_rubrics.models import RubricEvaluationHistory
        rubric_history = RubricEvaluationHistory.objects.filter(
            submission=submission,
            criterion__rubric=assignment.rubric
        ).select_related('criterion', 'rating', 'evaluated_by').order_by('created_at')
    
    # Get Text Question Answer Iterations
    text_question_iterations = []
    if submission and assignment.text_questions.exists():
        text_question_iterations = TextQuestionAnswerIteration.objects.filter(
            submission=submission,
            question__assignment=assignment
        ).select_related('question').prefetch_related('feedback_entries__created_by').order_by('question__order', 'iteration_number')
    
    # Get Text Field Answer Iterations  
    text_field_iterations = []
    if submission and assignment.text_fields.exists():
        text_field_iterations = TextSubmissionAnswerIteration.objects.filter(
            submission=submission,
            field__assignment=assignment
        ).select_related('field').prefetch_related('feedback_entries__created_by').order_by('field__order', 'iteration_number')
    
    # Get Assignment Comments
    assignment_comments = []
    if submission:
        assignment_comments = AssignmentComment.objects.filter(
            assignment=assignment,
            submission=submission
        ).select_related('author').order_by('created_at')
    
    # Get Interaction Logs
    interaction_logs = []
    if submission:
        interaction_logs = AssignmentInteractionLog.objects.filter(
            assignment=assignment,
            user=student
        ).select_related('user').order_by('-created_at')[:50]  # Latest 50 interactions
    
    # === BUILD COMPREHENSIVE TIMELINE ===
    timeline_events = []
    
    # Add submission event
    if submission:
        timeline_events.append({
            'type': 'submission',
            'timestamp': submission.submitted_at,
            'actor': submission.user,
            'title': 'Initial Submission',
            'description': 'Assignment submitted for review',
            'data': {
                'status': submission.status,
                'has_file': bool(submission.submission_file),
                'has_text': bool(submission.submission_text),
                'submission_text': submission.submission_text
            }
        })
    
    # Add feedback timeline
    for feedback in feedback_entries:
        timeline_events.append({
            'type': 'feedback',
            'timestamp': feedback.created_at,
            'actor': feedback.created_by,
            'title': 'Instructor Feedback',
            'description': f'Feedback provided by {feedback.created_by.get_full_name()}',
            'data': {
                'feedback': feedback.feedback,
                'has_audio': bool(feedback.audio_feedback),
                'has_video': bool(feedback.video_feedback),
                'is_private': feedback.is_private
            }
        })
    
    # Add file iteration timeline
    for iteration in file_iterations:
        timeline_events.append({
            'type': 'file_iteration',
            'timestamp': iteration.submitted_at if iteration.submitted_at else iteration.created_at,
            'actor': student,
            'title': f'File Resubmission #{iteration.iteration_number}',
            'description': f'File resubmitted - Iteration {iteration.iteration_number}',
            'data': {
                'file_name': iteration.file_name,
                'file_size': iteration.file_size,
                'content_type': iteration.content_type,
                'description': iteration.description,
                'is_submitted': iteration.is_submitted
            }
        })
        
        # Add feedback for each file iteration
        for feedback in iteration.feedback_entries.all():
            timeline_events.append({
                'type': 'iteration_feedback',
                'timestamp': feedback.created_at,
                'actor': feedback.created_by,
                'title': f'Feedback on Resubmission #{iteration.iteration_number}',
                'description': f'Feedback on file iteration by {feedback.created_by.get_full_name()}',
                'data': {
                    'feedback_text': feedback.feedback_text,
                    'allows_new_iteration': feedback.allows_new_iteration,
                    'iteration_number': iteration.iteration_number
                }
            })
    
    # Add text question iteration timeline
    for iteration in text_question_iterations:
        if iteration.submitted_at:
            timeline_events.append({
                'type': 'text_question_iteration',
                'timestamp': iteration.submitted_at,
                'actor': student,
                'title': f'Text Response #{iteration.iteration_number}',
                'description': f'Answer submitted for: {iteration.question.question_text[:50]}...',
                'data': {
                    'question_text': iteration.question.question_text,
                    'answer_text': iteration.answer_text,
                    'iteration_number': iteration.iteration_number
                }
            })
        
        # Add feedback for each text iteration
        for feedback in iteration.feedback_entries.all():
            timeline_events.append({
                'type': 'text_iteration_feedback',
                'timestamp': feedback.created_at,
                'actor': feedback.created_by,
                'title': f'Feedback on Text Response #{iteration.iteration_number}',
                'description': f'Feedback on text answer by {feedback.created_by.get_full_name()}',
                'data': {
                    'feedback_text': feedback.feedback_text,
                    'allows_new_iteration': feedback.allows_new_iteration,
                    'iteration_number': iteration.iteration_number,
                    'question_text': iteration.question.question_text
                }
            })
    
    # Add text field iteration timeline
    for iteration in text_field_iterations:
        if iteration.submitted_at:
            timeline_events.append({
                'type': 'text_field_iteration',
                'timestamp': iteration.submitted_at,
                'actor': student,
                'title': f'Field Response #{iteration.iteration_number}',
                'description': f'Answer submitted for: {iteration.field.label}',
                'data': {
                    'field_label': iteration.field.label,
                    'answer_text': iteration.answer_text,
                    'iteration_number': iteration.iteration_number
                }
            })
        
        # Add feedback for each field iteration
        for feedback in iteration.feedback_entries.all():
            timeline_events.append({
                'type': 'field_iteration_feedback',
                'timestamp': feedback.created_at,
                'actor': feedback.created_by,
                'title': f'Feedback on Field Response #{iteration.iteration_number}',
                'description': f'Feedback on field answer by {feedback.created_by.get_full_name()}',
                'data': {
                    'feedback_text': feedback.feedback_text,
                    'allows_new_iteration': feedback.allows_new_iteration,
                    'iteration_number': iteration.iteration_number,
                    'field_label': iteration.field.label
                }
            })
    
    # Add rubric evaluation timeline
    for evaluation in rubric_evaluations:
        timeline_events.append({
            'type': 'rubric_evaluation',
            'timestamp': evaluation.created_at,
            'actor': evaluation.evaluated_by,
            'title': 'Rubric Evaluation',
            'description': f'Rubric evaluated by {evaluation.evaluated_by.get_full_name()}',
            'data': {
                'criterion': evaluation.criterion.description,
                'points': evaluation.points,
                'max_points': evaluation.criterion.points,
                'rating': evaluation.rating.title if evaluation.rating else None,
                'comments': evaluation.comments
            }
        })
    
    # Add rubric evaluation history
    for history in rubric_history:
        timeline_events.append({
            'type': 'rubric_history',
            'timestamp': history.evaluation_date if history.evaluation_date else history.created_at,
            'actor': history.evaluated_by,
            'title': f'Rubric Evaluation - Version {history.version}',
            'description': f'Rubric evaluation by {history.evaluated_by.get_full_name() if history.evaluated_by else "Unknown"}',
            'data': {
                'criterion': history.criterion.description,
                'points': history.points,
                'max_points': history.criterion.points,
                'rating': history.rating.title if history.rating else None,
                'comments': history.comments,
                'version': history.version,
                'is_current': history.is_current
            }
        })
    
    # Add grade history timeline
    for grade in grade_history:
        timeline_events.append({
            'type': 'grade_change',
            'timestamp': grade.changed_at,
            'actor': grade.changed_by,
            'title': 'Grade Changed',
            'description': f'Grade modified by {grade.changed_by.get_full_name() if grade.changed_by else "System"}',
            'data': {
                'previous_grade': grade.previous_grade,
                'new_grade': grade.new_grade,
                'previous_status': grade.previous_status,
                'new_status': grade.new_status,
                'comment': grade.comment
            }
        })
    
    # Add assignment comments
    for comment in assignment_comments:
        timeline_events.append({
            'type': 'comment',
            'timestamp': comment.created_at,
            'actor': comment.author,
            'title': 'Comment Added',
            'description': f'Comment by {comment.author.get_full_name()}',
            'data': {
                'content': comment.content,
                'is_private': comment.is_private,
                'is_reply': comment.is_reply
            }
        })
    
    # Sort timeline events by timestamp (most recent first)
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # === ADMIN APPROVAL LOGIC ===
    
    # Get admin approval history
    admin_approval_history = []
    has_activities_after_approval = False
    needs_re_verification = False
    latest_activity_date = None
    detected_activities = []  # Store detailed activity information
    
    if submission:
        # Import the new model (assuming it will be created)
        from django.apps import apps
        try:
            AdminApprovalHistory = apps.get_model('assignments', 'AdminApprovalHistory')
            admin_approval_history = AdminApprovalHistory.objects.filter(
                submission=submission
            ).select_related('approved_by').order_by('-approval_date')[:10]  # Latest 10 approvals
        except LookupError:
            # Model doesn't exist yet, fallback to empty list
            admin_approval_history = []
        
        # Check if there are activities after the latest admin approval
        if submission.admin_approval_date:
            approval_date = submission.admin_approval_date
            
            # === DETAILED ACTIVITY DETECTION ===
            
            # 1. Check for new instructor feedback
            new_feedback = submission.feedback_entries.filter(
                created_at__gt=approval_date
            ).select_related('created_by').order_by('-created_at')
            
            for feedback in new_feedback:
                # Generate target_id that matches the actual HTML element ID format
                target_id = f'feedback-{feedback.id}-{feedback.created_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                
                detected_activities.append({
                    'type': 'instructor_feedback',
                    'title': 'New Instructor Feedback',
                    'description': f'Feedback provided by {feedback.created_by.get_full_name()}',
                    'timestamp': feedback.created_at,
                    'actor': feedback.created_by,
                    'target_id': target_id,
                    'details': {
                        'has_text': bool(feedback.feedback),
                        'has_audio': bool(feedback.audio_feedback),
                        'has_video': bool(feedback.video_feedback),
                        'is_private': feedback.is_private
                    }
                })
            
            # 2. Check for new file resubmissions
            new_file_iterations = submission.file_iterations.filter(
                submitted_at__gt=approval_date
            ).order_by('-submitted_at')
            
            for iteration in new_file_iterations:
                # Generate target_id that matches the actual HTML element ID format
                timestamp = (iteration.submitted_at or iteration.created_at)
                target_id = f'file-iteration-{iteration.id}-{timestamp.strftime("%Y-%m-%d-%H-%M-%S")}'
                
                detected_activities.append({
                    'type': 'file_resubmission',
                    'title': f'File Resubmission #{iteration.iteration_number}',
                    'description': f'New file uploaded by {submission.user.get_full_name()}',
                    'timestamp': iteration.submitted_at,
                    'actor': submission.user,
                    'target_id': target_id,
                    'details': {
                        'file_name': iteration.file_name,
                        'iteration_number': iteration.iteration_number,
                        'description': iteration.description
                    }
                })
            
            # 3. Check for new text question revisions
            new_text_iterations = submission.text_answer_iterations.filter(
                submitted_at__gt=approval_date
            ).select_related('question').order_by('-submitted_at')
            
            for iteration in new_text_iterations:
                # Generate target_id that matches the actual HTML element ID format
                target_id = f'text-iteration-{iteration.id}-{iteration.submitted_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                
                detected_activities.append({
                    'type': 'text_revision',
                    'title': f'Text Response Revision #{iteration.iteration_number}',
                    'description': f'Revised answer submitted by {submission.user.get_full_name()}',
                    'timestamp': iteration.submitted_at,
                    'actor': submission.user,
                    'target_id': target_id,
                    'details': {
                        'question_text': iteration.question.question_text[:100] + '...' if len(iteration.question.question_text) > 100 else iteration.question.question_text,
                        'iteration_number': iteration.iteration_number
                    }
                })
            
            # 4. Check for new field revisions
            new_field_iterations = submission.field_answer_iterations.filter(
                submitted_at__gt=approval_date
            ).select_related('field').order_by('-submitted_at')
            
            for iteration in new_field_iterations:
                # Generate target_id that matches the actual HTML element ID format  
                target_id = f'field-iteration-{iteration.id}-{iteration.submitted_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                
                detected_activities.append({
                    'type': 'field_revision',
                    'title': f'Field Response Revision #{iteration.iteration_number}',
                    'description': f'Revised field answer submitted by {submission.user.get_full_name()}',
                    'timestamp': iteration.submitted_at,
                    'actor': submission.user,
                    'target_id': target_id,
                    'details': {
                        'field_label': iteration.field.label,
                        'iteration_number': iteration.iteration_number
                    }
                })
            
            # 5. Check for new and updated rubric evaluations
            if assignment.rubric:
                from lms_rubrics.models import RubricEvaluation, RubricEvaluationHistory
                
                # Check for newly created rubric evaluations
                new_rubric_evaluations = RubricEvaluation.objects.filter(
                    submission=submission,
                    criterion__rubric=assignment.rubric,
                    created_at__gt=approval_date
                ).select_related('criterion', 'rating', 'evaluated_by').order_by('-created_at')
                
                for evaluation in new_rubric_evaluations:
                    # Generate target_id that matches the actual HTML element ID format
                    target_id = f'rubric-{evaluation.id}-{evaluation.created_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                    
                    detected_activities.append({
                        'type': 'rubric_evaluation',
                        'title': 'New Rubric Evaluation',
                        'description': f'Rubric scored by {evaluation.evaluated_by.get_full_name()}',
                        'timestamp': evaluation.created_at,
                        'actor': evaluation.evaluated_by,
                        'target_id': target_id,
                        'details': {
                            'criterion': evaluation.criterion.description,
                            'points': evaluation.points,
                            'max_points': evaluation.criterion.points,
                            'rating': evaluation.rating.title if evaluation.rating else None
                        }
                    })
                
                # Check for updated rubric evaluations (created before approval but updated after)
                updated_rubric_evaluations = RubricEvaluation.objects.filter(
                    submission=submission,
                    criterion__rubric=assignment.rubric,
                    created_at__lte=approval_date,  # Created before or on approval date
                    updated_at__gt=approval_date    # But updated after approval date
                ).select_related('criterion', 'rating', 'evaluated_by').order_by('-updated_at')
                
                for evaluation in updated_rubric_evaluations:
                    # Generate target_id that matches the actual HTML element ID format  
                    target_id = f'rubric-{evaluation.id}-{evaluation.created_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                    
                    detected_activities.append({
                        'type': 'rubric_evaluation',
                        'title': 'Rubric Evaluation Updated',
                        'description': f'Rubric re-evaluated by {evaluation.evaluated_by.get_full_name()}',
                        'timestamp': evaluation.updated_at,  # Use updated_at for timestamp
                        'actor': evaluation.evaluated_by,
                        'target_id': target_id,
                        'details': {
                            'criterion': evaluation.criterion.description,
                            'points': evaluation.points,
                            'max_points': evaluation.criterion.points,
                            'rating': evaluation.rating.title if evaluation.rating else None
                        }
                    })
                
                # Also check rubric evaluation history for additional changes
                new_rubric_history = RubricEvaluationHistory.objects.filter(
                    submission=submission,
                    criterion__rubric=assignment.rubric,
                    evaluation_date__gt=approval_date
                ).select_related('criterion', 'rating', 'evaluated_by').order_by('-evaluation_date')
                
                # Track unique evaluations to avoid duplicates
                processed_evaluations = set()
                
                for history in new_rubric_history:
                    # Create a unique key for this evaluation to avoid duplicates
                    eval_key = (history.criterion.id, history.evaluation_date.strftime("%Y-%m-%d-%H-%M-%S"))
                    
                    if eval_key not in processed_evaluations:
                        processed_evaluations.add(eval_key)
                        
                        # Use a different target_id format for history records
                        target_id = f'rubric-{history.id}-{history.evaluation_date.strftime("%Y-%m-%d-%H-%M-%S")}'
                        
                        detected_activities.append({
                            'type': 'rubric_evaluation',
                            'title': f'Rubric Evaluation Change (v{history.version})',
                            'description': f'Rubric modified by {history.evaluated_by.get_full_name() if history.evaluated_by else "Unknown"}',
                            'timestamp': history.evaluation_date,
                            'actor': history.evaluated_by,
                            'target_id': target_id,
                            'details': {
                                'criterion': history.criterion.description,
                                'points': history.points,
                                'max_points': history.criterion.points,
                                'rating': history.rating.title if history.rating else None,
                                'version': history.version,
                                'is_current': history.is_current
                            }
                        })
            
            # 6. Check for new grade changes
            new_grade_changes = submission.grade_history.filter(
                changed_at__gt=approval_date
            ).select_related('changed_by').order_by('-changed_at')
            
            for grade_change in new_grade_changes:
                # Generate target_id that matches the actual HTML element ID format
                # Grade history uses format: grade-history-{id}-{timestamp}
                target_id = f'grade-history-{grade_change.id}-{grade_change.changed_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                
                # Determine activity title based on what changed
                if grade_change.previous_grade != grade_change.new_grade and grade_change.previous_status != grade_change.new_status:
                    title = 'Grade & Status Changed'
                elif grade_change.previous_grade != grade_change.new_grade:
                    title = 'Grade Modified'
                elif grade_change.previous_status != grade_change.new_status:
                    title = 'Status Changed'
                else:
                    title = 'Assignment Updated'
                
                detected_activities.append({
                    'type': 'grade_change',
                    'title': title,
                    'description': f'{title.replace(" Modified", "").replace(" Changed", "")} by {grade_change.changed_by.get_full_name() if grade_change.changed_by else "System"}',
                    'timestamp': grade_change.changed_at,
                    'actor': grade_change.changed_by,
                    'target_id': target_id,
                    'details': {
                        'previous_grade': grade_change.previous_grade,
                        'new_grade': grade_change.new_grade,
                        'previous_status': grade_change.previous_status,
                        'new_status': grade_change.new_status,
                        'comment': grade_change.comment
                    }
                })
            
            # 7. Check for new comments
            new_comments = submission.comments.filter(
                created_at__gt=approval_date
            ).select_related('author').order_by('-created_at')
            
            for comment in new_comments:
                # Generate target_id that matches the actual HTML element ID format
                # Comments use format: comment-content-{id}
                target_id = f'comment-content-{comment.id}'
                
                detected_activities.append({
                    'type': 'comment',
                    'title': 'New Comment',
                    'description': f'Comment added by {comment.author.get_full_name()}',
                    'timestamp': comment.created_at,
                    'actor': comment.author,
                    'target_id': target_id,
                    'details': {
                        'content_preview': comment.content[:100] + '...' if len(comment.content) > 100 else comment.content,
                        'is_private': comment.is_private,
                        'is_reply': comment.is_reply
                    }
                })
            
            # 8. Check for new iteration feedback
            for iteration in submission.text_answer_iterations.all():
                new_iteration_feedback = iteration.feedback_entries.filter(
                    created_at__gt=approval_date
                ).select_related('created_by').order_by('-created_at')
                
                for feedback in new_iteration_feedback:
                    # Iteration feedback doesn't have specific timeline elements,
                    # but the feedback appears within the iteration element, so use the iteration's target_id
                    target_id = f'text-iteration-{iteration.id}-{iteration.submitted_at.strftime("%Y-%m-%d-%H-%M-%S")}'
                    
                    detected_activities.append({
                        'type': 'iteration_feedback',
                        'title': f'Feedback on Text Response #{iteration.iteration_number}',
                        'description': f'Feedback provided by {feedback.created_by.get_full_name()}',
                        'timestamp': feedback.created_at,
                        'actor': feedback.created_by,
                        'target_id': target_id,
                        'details': {
                            'iteration_number': iteration.iteration_number,
                            'question_text': iteration.question.question_text[:50] + '...' if len(iteration.question.question_text) > 50 else iteration.question.question_text,
                            'allows_new_iteration': feedback.allows_new_iteration
                        }
                    })
            
            # Sort detected activities by timestamp (most recent first)
            detected_activities.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Update flags based on detected activities
            if detected_activities:
                has_activities_after_approval = True
                latest_activity_date = detected_activities[0]['timestamp']
                needs_re_verification = submission.admin_approval_status
        
        # Also check timeline events as fallback
        if submission.admin_approval_date and timeline_events and not detected_activities:
            # Find the latest activity date from timeline
            for event in timeline_events:
                if event['timestamp'] and event['timestamp'] > submission.admin_approval_date:
                    if not latest_activity_date or event['timestamp'] > latest_activity_date:
                        latest_activity_date = event['timestamp']
                        has_activities_after_approval = True
        
        # Determine if re-verification is needed
        needs_re_verification = has_activities_after_approval and submission.admin_approval_status
    
    # Add admin approval timeline events
    for approval in admin_approval_history:
        timeline_events.append({
            'type': 'admin_approval',
            'timestamp': approval.approval_date,
            'actor': approval.approved_by,
            'title': f'Internal Verification - {approval.get_approval_status_display()}',
            'description': f'Report {approval.get_approval_status_display().lower()} by {approval.approved_by.get_full_name() if approval.approved_by else "Unknown"}',
            'data': {
                'approval_status': approval.approval_status,
                'admin_feedback': approval.admin_feedback,
                'is_current': approval.is_current,
                'trigger_reason': approval.trigger_reason
            }
        })
    
    # Re-sort timeline events after adding admin approvals
    timeline_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Build breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('assignments:assignment_list'), 'label': 'Assignments', 'icon': 'fa-tasks'},
        {'url': reverse('assignments:assignment_detail', args=[assignment.id]), 'label': assignment.title[:30] + ('...' if len(assignment.title) > 30 else ''), 'icon': 'fa-clipboard-list'},
        {'label': f'Report: {student.get_full_name()}', 'icon': 'fa-user'}
    ]
    
    context = {
        'assignment': assignment,
        'student': student,
        'submission': submission,
        'file_iterations': file_iterations,
        'feedback_entries': feedback_entries,
        'text_answers': text_answers,
        'field_answers': field_answers,
        'rubric_evaluations': rubric_evaluations,
        'rubric_total_score': rubric_total_score,
        'grade_history': grade_history,
        'rubric_history': rubric_history,
        'text_question_iterations': text_question_iterations,
        'text_field_iterations': text_field_iterations,
        'assignment_comments': assignment_comments,
        'interaction_logs': interaction_logs,
        'timeline_events': timeline_events,
        'breadcrumbs': breadcrumbs,
        
        # New admin approval context variables
        'admin_approval_history': admin_approval_history,
        'has_activities_after_approval': has_activities_after_approval,
        'needs_re_verification': needs_re_verification,
        'latest_activity_date': latest_activity_date,
        'detected_activities': detected_activities,
    }
    
    return render(request, 'assignments/detailed_report_comprehensive.html', context)


@login_required
@require_POST
def admin_approve_report(request, assignment_id):
    """Handle admin approval of assignment detailed report"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions - only admins and superadmins can approve
    if not (request.user.role in ['admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to approve this report.")
        return redirect('assignments:assignment_detailed_report', assignment_id=assignment_id)
    
    # Get student_id from query parameters
    student_id = request.GET.get('student_id')
    if not student_id:
        messages.error(request, "Student ID is required.")
        return redirect('assignments:assignment_detailed_report', assignment_id=assignment_id)
    
    # Get the specific student and their submission
    from django.contrib.auth import get_user_model
    User = get_user_model()
    student = get_object_or_404(User, id=student_id)
    
    # Get the submission
    try:
        submission = AssignmentSubmission.objects.get(
            assignment=assignment,
            user=student
        )
    except AssignmentSubmission.DoesNotExist:
        messages.error(request, "No submission found for this student.")
        from django.urls import reverse
        detailed_report_url = reverse('assignments:assignment_detailed_report', args=[assignment_id])
        return redirect(f"{detailed_report_url}?student_id={student_id}")
    
    # Get form data
    approval_status = request.POST.get('approval_status')
    admin_feedback = request.POST.get('admin_feedback', '').strip()
    
    # Validate approval status
    valid_statuses = ['approved', 'needs_revision']
    if approval_status not in valid_statuses:
        messages.error(request, "Invalid approval status.")
        from django.urls import reverse
        detailed_report_url = reverse('assignments:assignment_detailed_report', args=[assignment_id])
        return redirect(f"{detailed_report_url}?student_id={student_id}")
    
    # Determine trigger reason based on activities after last approval
    trigger_reason = None
    if submission.admin_approval_date:
        # Check what type of activity happened after last approval
        recent_activities = []
        current_time = timezone.now()
        
        # Check for recent feedback
        if submission.feedback_entries.filter(created_at__gt=submission.admin_approval_date).exists():
            recent_activities.append('new_feedback')
        
        # Check for recent file iterations
        if submission.file_iterations.filter(submitted_at__gt=submission.admin_approval_date).exists():
            recent_activities.append('file_resubmission')
            
        # Check for recent text iterations
        if submission.text_answer_iterations.filter(submitted_at__gt=submission.admin_approval_date).exists():
            recent_activities.append('text_revision')
            
        if submission.field_answer_iterations.filter(submitted_at__gt=submission.admin_approval_date).exists():
            recent_activities.append('field_revision')
        
        # Check for recent rubric evaluations (new or updated)
        if assignment.rubric:
            from lms_rubrics.models import RubricEvaluation, RubricEvaluationHistory
            
            # Check for new or updated rubric evaluations
            rubric_changes = RubricEvaluation.objects.filter(
                submission=submission,
                criterion__rubric=assignment.rubric,
                updated_at__gt=submission.admin_approval_date
            ).exists()
            
            # Also check rubric evaluation history
            if not rubric_changes:
                rubric_changes = RubricEvaluationHistory.objects.filter(
                    submission=submission,
                    criterion__rubric=assignment.rubric,
                    evaluation_date__gt=submission.admin_approval_date
                ).exists()
            
            if rubric_changes:
                recent_activities.append('rubric_evaluation')
        
        # Check for recent grade/status changes
        if submission.grade_history.filter(changed_at__gt=submission.admin_approval_date).exists():
            recent_activities.append('grade_status_change')
        
        if recent_activities:
            trigger_reason = ', '.join(recent_activities)
    
    # Update submission with admin approval
    submission.admin_approval_status = approval_status
    submission.admin_approval_feedback = admin_feedback if admin_feedback else None
    submission.admin_approved_by = request.user
    submission.admin_approval_date = timezone.now()
    submission.save()
    
    # Create approval history entry
    try:
        from django.apps import apps
        AdminApprovalHistory = apps.get_model('assignments', 'AdminApprovalHistory')
        AdminApprovalHistory.objects.create(
            submission=submission,
            approval_status=approval_status,
            admin_feedback=admin_feedback if admin_feedback else None,
            approved_by=request.user,
            is_current=True,
            trigger_reason=trigger_reason
        )
    except LookupError:
        # Model doesn't exist yet, skip history creation
        pass
    
    # Success message based on approval status
    status_messages = {
        'approved': 'Report has been approved successfully.',
        'needs_revision': 'Report has been returned for revision.',
    }
    
    messages.success(request, status_messages.get(approval_status, 'Report status updated.'))
    
    # Preserve the student_id in the redirect URL
    from django.urls import reverse
    detailed_report_url = reverse('assignments:assignment_detailed_report', args=[assignment_id])
    return redirect(f"{detailed_report_url}?student_id={student_id}")


@login_required
@require_POST
def confirm_detailed_report(request, assignment_id):
    """View for branch admin to confirm detailed report"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions - only branch admins can confirm
    if not (request.user.role in ['admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to confirm this report.")
        return redirect('assignments:assignment_detailed_report', assignment_id=assignment_id)
    
    messages.success(request, "Report has been confirmed.")
    
    # Preserve the student_id in the redirect URL if present
    student_id = request.GET.get('student_id')
    if student_id:
        from django.urls import reverse
        detailed_report_url = reverse('assignments:assignment_detailed_report', args=[assignment_id])
        return redirect(f"{detailed_report_url}?student_id={student_id}")
    else:
        return redirect('assignments:assignment_detailed_report', assignment_id=assignment_id)


@login_required
def download_detailed_report(request, assignment_id):
    """View for instructors to download the confirmed detailed report"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check permissions
    if not (request.user.role in ['instructor', 'admin', 'superadmin'] or request.user.is_superuser):
        messages.error(request, "You don't have permission to download this report.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    messages.info(request, "Report download functionality is under development.")
    
    # Preserve the student_id in the redirect URL if present
    student_id = request.GET.get('student_id')
    if student_id:
        from django.urls import reverse
        detailed_report_url = reverse('assignments:assignment_detailed_report', args=[assignment_id])
        return redirect(f"{detailed_report_url}?student_id={student_id}")
    else:
        return redirect('assignments:assignment_detailed_report', assignment_id=assignment_id)


@login_required
@require_POST
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
def upload_editor_image(request):
    """Handle image uploads from the rich text editor for assignments."""
    if request.method == 'POST' and request.FILES.get('image'):
        image = request.FILES['image']
        
        # Use Django's default storage (works with both local and S3)
        from django.core.files.storage import default_storage
        import os
        
        # Generate unique filename to avoid conflicts
        import uuid
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        image_filename = f"{timestamp}_{unique_id}_{image.name}"
        
        # Save using default storage
        file_path = f"editor_uploads/{image_filename}"
        saved_path = default_storage.save(file_path, image)
        uploaded_file_url = default_storage.url(saved_path)
        filename = image_filename
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=saved_path,
                uploaded_by=request.user if request.user.is_authenticated else None,
                source_type='editor_upload',
                filename=image.name,
                description=f'Assignment editor image upload'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error registering assignment editor image in media database: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'url': uploaded_file_url,
            'location': uploaded_file_url,
            'filename': filename
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request or missing image file'
    })


@login_required
@require_POST
@ensure_csrf_cookie
def upload_editor_video(request):
    """Handle video uploads from the rich text editor for assignments."""
    if request.method == 'POST' and request.FILES.get('video'):
        video = request.FILES['video']
        
        # Use Django's default storage (works with both local and S3)
        from django.core.files.storage import default_storage
        import os
        
        # Generate unique filename to avoid conflicts
        import uuid
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        video_filename = f"{timestamp}_{unique_id}_{video.name}"
        
        # Save using default storage
        file_path = f"editor_uploads/{video_filename}"
        saved_path = default_storage.save(file_path, video)
        uploaded_file_url = default_storage.url(saved_path)
        filename = video_filename
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=saved_path,
                uploaded_by=request.user if request.user.is_authenticated else None,
                source_type='editor_upload',
                filename=video.name,
                description=f'Assignment editor video upload'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error registering assignment editor video in media database: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'url': uploaded_file_url,
            'filename': filename
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request or missing video file'
    })


@login_required
@require_POST
def add_comment(request, assignment_id):
    """Add a comment to an assignment"""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Check if user has access to the assignment
    if not assignment.is_available_for_user(request.user):
        messages.error(request, "You don't have permission to comment on this assignment.")
        return redirect('assignments:assignment_list')
    
    content = request.POST.get('content', '').strip()
    if not content:
        messages.error(request, "Comment content cannot be empty.")
        return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Get optional parameters
    submission_id = request.POST.get('submission_id')
    parent_id = request.POST.get('parent_id')
    is_private = request.POST.get('is_private') == 'on' if request.user.role == 'instructor' else False
    
    # Validate submission exists and user has access
    submission = None
    if submission_id:
        try:
            submission = AssignmentSubmission.objects.get(id=submission_id, assignment=assignment)
            # Check if user can comment on this submission
            if request.user.role == 'learner' and submission.user != request.user:
                messages.error(request, "You can only comment on your own submissions.")
                return redirect('assignments:assignment_detail', assignment_id=assignment_id)
        except AssignmentSubmission.DoesNotExist:
            messages.error(request, "Invalid submission.")
            return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Validate parent comment exists if provided
    parent_comment = None
    if parent_id:
        try:
            parent_comment = AssignmentComment.objects.get(id=parent_id, assignment=assignment)
        except AssignmentComment.DoesNotExist:
            messages.error(request, "Invalid parent comment.")
            return redirect('assignments:assignment_detail', assignment_id=assignment_id)
    
    # Create the comment
    try:
        comment = AssignmentComment.objects.create(
            assignment=assignment,
            submission=submission,
            author=request.user,
            content=content,
            parent=parent_comment,
            is_private=is_private
        )
        
        if parent_comment:
            messages.success(request, "Reply posted successfully.")
        else:
            messages.success(request, "Comment posted successfully.")
        
    except Exception as e:
        messages.error(request, f"Error posting comment: {str(e)}")
    
    return redirect('assignments:assignment_detail', assignment_id=assignment_id)


@login_required
@require_POST
def edit_comment(request, comment_id):
    """Edit a comment"""
    comment = get_object_or_404(AssignmentComment, id=comment_id)
    
    # Check if user can edit this comment
    if not comment.can_edit(request.user):
        messages.error(request, "You don't have permission to edit this comment.")
        return redirect('assignments:assignment_detail', assignment_id=comment.assignment.id)
    
    content = request.POST.get('content', '').strip()
    if not content:
        messages.error(request, "Comment content cannot be empty.")
        return redirect('assignments:assignment_detail', assignment_id=comment.assignment.id)
    
    # Update the comment
    try:
        comment.content = content
        comment.save()
        messages.success(request, "Comment updated successfully.")
        
        # For AJAX requests, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'message': 'Comment updated successfully.',
                'content': content
            })
        
    except Exception as e:
        error_msg = f"Error updating comment: {str(e)}"
        messages.error(request, error_msg)
        
        # For AJAX requests, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_msg})
    
    return redirect('assignments:assignment_detail', assignment_id=comment.assignment.id)


@login_required
@require_POST
def delete_comment(request, comment_id):
    """Delete a comment"""
    comment = get_object_or_404(AssignmentComment, id=comment_id)
    
    # Check if user can delete this comment
    if not comment.can_edit(request.user):
        messages.error(request, "You don't have permission to delete this comment.")
        return redirect('assignments:assignment_detail', assignment_id=comment.assignment.id)
    
    assignment_id = comment.assignment.id
    
    # Delete the comment (this will also delete replies due to CASCADE)
    try:
        comment.delete()
        messages.success(request, "Comment deleted successfully.")
        
        # For AJAX requests, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'message': 'Comment deleted successfully.'
            })
        
    except Exception as e:
        error_msg = f"Error deleting comment: {str(e)}"
        messages.error(request, error_msg)
        
        # For AJAX requests, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_msg})
    
    return redirect('assignments:assignment_detail', assignment_id=assignment_id)


@login_required
def assignment_api_list(request):
    """API endpoint to list assignments for frontend JavaScript"""
    try:
        # Get assignments based on user role with simplified logic
        if request.user.role == 'globaladmin':
            assignments_queryset = Assignment.objects.all()
        elif request.user.role == 'superadmin':
            assignments_queryset = Assignment.objects.filter(
                Q(branch=request.user.branch) |
                Q(branch__isnull=True)
            )
        elif request.user.role in ['admin', 'instructor']:
            if request.user.role == 'admin':
                # Support branch switching for admin users
                from core.branch_filters import BranchFilterManager
                effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
                assignments_queryset = Assignment.objects.filter(
                    Q(branch=effective_branch) |
                    Q(branch__isnull=True)
                )
            else:  # instructor
                # Include both branch-based and group-assigned assignments
                branch_assignments = Q(branch=request.user.branch) | Q(branch__isnull=True)
                group_assignments = Q(
                    course__accessible_groups__memberships__user=request.user,
                    course__accessible_groups__memberships__is_active=True,
                    course__accessible_groups__memberships__custom_role__name__icontains='instructor'
                ) | Q(
                    courses__accessible_groups__memberships__user=request.user,
                    courses__accessible_groups__memberships__is_active=True,
                    courses__accessible_groups__memberships__custom_role__name__icontains='instructor'
                )
                assignments_queryset = Assignment.objects.filter(branch_assignments | group_assignments).distinct()
        else:  # learner
            # For learners, get assignments from enrolled courses
            from courses.models import CourseEnrollment
            enrolled_courses = CourseEnrollment.objects.filter(
                user=request.user
            ).values_list('course_id', flat=True)
            
            assignments_queryset = Assignment.objects.filter(
                Q(course_id__in=enrolled_courses) |
                Q(courses__id__in=enrolled_courses) |
                Q(topics__courses__id__in=enrolled_courses)
            ).distinct()
        
        # Convert to list with id and title
        assignments_data = []
        for assignment in assignments_queryset.order_by('title'):
            assignments_data.append({
                'id': assignment.id,
                'title': assignment.title
            })
        
        return JsonResponse({
            'assignments': assignments_data,
            'success': True
        })
        
    except Exception as e:
        return JsonResponse({
            'assignments': [],
            'success': False,
            'error': str(e)
        }, status=500)