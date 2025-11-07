import json
import logging
import math
import random
import traceback
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
import ipaddress  # Add this import for IP validation

import pytz
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import (
    Q, Count, Max, F, Sum, Min, Avg, Case, When, Value, IntegerField, 
    Prefetch, BooleanField, DateTimeField, ExpressionWrapper, Subquery, OuterRef
)
from django.http import (
    HttpResponse, HttpResponseRedirect, JsonResponse, 
    HttpResponseForbidden, HttpResponseBadRequest, Http404
)
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from categories.models import CourseCategory
from courses.models import Course, Section, Topic, TopicProgress
from courses.views import check_course_permission
from users.models import CustomUser, UserRole
from role_management.models import RoleCapability

from .forms import (
    QuizForm, QuestionForm, AnswerFormSet, MatchingPairFormSet, 
    MultipleChoiceQuestionForm, TrueFalseQuestionForm, FillBlankQuestionForm,
    MultiBlankQuestionForm, MatchingQuestionForm, MultipleSelectQuestionForm,
    QuizGradeFilterForm
)
from .models import (
    Quiz, Question, Answer, MatchingPair, QuizAttempt, 
    QuizTag, UserAnswer, QuizGradeOverride, QuizRubricEvaluation
)

# Import from lms_rubrics app
from lms_rubrics.models import Rubric, RubricCriterion, RubricRating

# Ensure Redis fallback is loaded
try:
    from core.utils.redis_fallback import *
    logger_fallback = logging.getLogger(__name__)
    logger_fallback.info("Redis fallback mechanism loaded in quiz views")
except ImportError:
    logger_fallback = logging.getLogger(__name__)
    logger_fallback.warning("WARNING: Redis fallback mechanism could not be loaded in quiz views")

# Set up logger
logger = logging.getLogger(__name__)

def safe_cache_set(key, value, timeout=None):
    """
    Safely set a cache value with Redis error handling.
    Returns True if successful, False if Redis is unavailable.
    """
    try:
        cache.set(key, value, timeout=timeout)
        return True
    except Exception as e:
        # Check for Redis connection errors specifically
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['connection refused', 'redis', 'connecting to', 'connection error']):
            logger.warning(f"Redis connection failed for cache set on key '{key}': {str(e)}. Continuing without cache.")
        else:
            logger.error(f"Unexpected cache error for key '{key}': {str(e)}. Continuing without cache.")
        return False

def safe_cache_get(key, default=None):
    """
    Safely get a cache value with Redis error handling.
    Returns the cached value or default if Redis is unavailable.
    """
    try:
        return cache.get(key, default)
    except Exception as e:
        # Check for Redis connection errors specifically  
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['connection refused', 'redis', 'connecting to', 'connection error']):
            logger.warning(f"Redis connection failed for cache get on key '{key}': {str(e)}. Returning default value.")
        else:
            logger.error(f"Unexpected cache error for key '{key}': {str(e)}. Returning default value.")
        return default

def safe_cache_delete(key):
    """
    Safely delete a cache value with Redis error handling.
    Returns True if successful, False if Redis is unavailable.
    """
    try:
        cache.delete(key)
        return True
    except Exception as e:
        # Check for Redis connection errors specifically
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['connection refused', 'redis', 'connecting to', 'connection error']):
            logger.warning(f"Redis connection failed for cache delete on key '{key}': {str(e)}. Continuing without cache.")
        else:
            logger.error(f"Unexpected cache error for key '{key}': {str(e)}. Continuing without cache.")
        return False

def safe_cache_incr(key, delta=1):
    """
    Safely increment a cache value with Redis error handling.
    Returns the new value if successful, delta if Redis is unavailable.
    """
    try:
        return cache.incr(key, delta)
    except Exception as e:
        # Check for Redis connection errors specifically
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ['connection refused', 'redis', 'connecting to', 'connection error']):
            logger.warning(f"Redis connection failed for cache incr on key '{key}': {str(e)}. Returning delta value.")
        else:
            logger.error(f"Unexpected cache error for key '{key}': {str(e)}. Returning delta value.")
        return delta

def check_quiz_edit_permission(user, quiz):
    """
    Check if the user has permission to edit a quiz.
    """
    # Explicitly deny access to learners
    if user.role == 'learner':
        return False
        
    # Always allow superusers
    if user.is_superuser:
        return True
    
    # Allow quiz creator
    if quiz.creator == user:
        return True
    
    # For admins: check branch access through course or creator
    if user.role == 'admin':
        if quiz.course and quiz.course.branch == user.branch:
            return True
        elif not quiz.course and quiz.creator.branch == user.branch:
            return True
    
    # For instructors: check if they're the course instructor or quiz creator
    if user.role == 'instructor':
        if quiz.course and quiz.course.instructor == user:
            return True
        # Also check if instructor has access through course groups
        if quiz.course and quiz.course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            course_access__can_modify=True
        ).exists():
            return True
    
    return False

def can_user_access_quiz(user, quiz):
    """
    Check if the user can access a quiz (for viewing, not editing).
    This is different from edit permissions - learners can view quizzes they're enrolled in.
    """
    # Use the new can_view_quiz method from the Quiz model
    return quiz.can_view_quiz(user)

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def validate_ip(ip):
    """Validate IP address"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

from core.rbac_validators import ConditionalAccessValidator

@login_required
def quiz_list(request):
    """View to display list of quizzes"""
    # RBAC v0.1 Compliant Access Control
    from core.rbac_validators import rbac_validator
    
    if request.user.role == 'globaladmin':
        # Global Admin: FULL access to all quizzes
        quizzes_list = Quiz.objects.all().order_by('-created_at')
        available_courses = Course.objects.all()
        can_create = True
        
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped quizzes)
        if hasattr(request.user, 'business_assignments'):
            assigned_businesses = request.user.business_assignments.filter().values_list('business', flat=True)
            quizzes_list = Quiz.objects.filter(
                creator__branch__business__in=assigned_businesses
            ).order_by('-created_at')
            available_courses = Course.objects.filter(branch__business__in=assigned_businesses)
        else:
            quizzes_list = Quiz.objects.none()
            available_courses = Course.objects.none()
        can_create = True
        
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (branch-scoped quizzes, supports branch switching)
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        if effective_branch:
            quizzes_list = Quiz.objects.filter(
                creator__branch=effective_branch
            ).order_by('-created_at')
            available_courses = Course.objects.filter(branch=effective_branch)
        else:
            quizzes_list = Quiz.objects.none()
            available_courses = Course.objects.none()
        can_create = True
        
    elif request.user.role == 'instructor':
        # Instructor: CONDITIONAL access (own quizzes + assigned courses + group-assigned courses)
        if request.user.branch:
            # Own quizzes
            own_quizzes = Quiz.objects.filter(creator=request.user)
            
            # Quizzes from directly assigned courses
            assigned_courses = Course.objects.filter(instructor=request.user)
            course_quizzes = Quiz.objects.filter(course__in=assigned_courses)
            
            # Quizzes from group-assigned courses
            group_assigned_courses = Course.objects.filter(
                accessible_groups__memberships__user=request.user,
                accessible_groups__memberships__custom_role__name__icontains='instructor'
            )
            group_course_quizzes = Quiz.objects.filter(course__in=group_assigned_courses)
            
            quizzes_list = (own_quizzes | course_quizzes | group_course_quizzes).distinct().order_by('-created_at')
            available_courses = (assigned_courses | group_assigned_courses).distinct()
        else:
            quizzes_list = Quiz.objects.filter(creator=request.user).order_by('-created_at')
            available_courses = Course.objects.filter(instructor=request.user)
        can_create = True
        
    else:  # learner
        # Learner: SELF access (enrolled courses only)
        enrolled_courses = Course.objects.filter(courseenrollment__user=request.user).values_list('id', flat=True)
        
        # Get quizzes that are:
        # 1. Active
        # 2. Have at least one active/published topic
        # 3. NOT linked to any draft topics
        # 4. Linked to enrolled courses (through any relationship)
        quizzes_list = Quiz.objects.filter(
            topics__status='active'  # Must have at least one active topic
        ).exclude(
            topics__status='draft'  # Exclude quizzes with any draft topics
        ).filter(
            # AND must be linked to enrolled courses through any relationship
            Q(course__in=enrolled_courses) |  # Direct course relationship
            Q(topics__courses__in=enrolled_courses)  # Topic-based course relationship
        ).distinct().order_by('-created_at')
        
        # Get enrolled courses for learners
        available_courses = Course.objects.filter(courseenrollment__user=request.user)
        can_create = False
    
    # Pagination
    paginator = Paginator(quizzes_list, 10)  # Show 10 quizzes per page
    page = request.GET.get('page')
    quizzes = paginator.get_page(page)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Quizzes', 'icon': 'fa-tasks'}
    ]
    
    context = {
        'quizzes': quizzes,
        'title': 'Quizzes',
        'breadcrumbs': breadcrumbs,
        'available_courses': available_courses,
        'can_create': can_create
    }
    
    # Add branch context for template (enables branch switcher for admin users)
    from core.branch_filters import filter_context_by_branch
    context = filter_context_by_branch(context, request.user, request)
    
    return render(request, 'quiz/quiz_list.html', context)


@login_required
def clean_stale_attempts(request, quiz_id):
    """View to clean up stale attempts for a quiz"""
    if request.method != 'POST':
        return HttpResponseForbidden("Invalid request method")
        
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Use the efficient cleanup method from the model
    cleaned_count = quiz.cleanup_user_attempts(request.user)
    
    if cleaned_count > 0:
        messages.success(request, f"Successfully cleaned up {cleaned_count} old quiz attempts.")
    else:
        messages.info(request, "No old attempts found to clean up.")
    
    # Redirect to appropriate view
    if request.GET.get('redirect') == 'view':
        return redirect('quiz:quiz_view', quiz_id=quiz_id)
    else:
        return redirect('quiz:quiz_detail', quiz_id=quiz_id)

@login_required
def create_quiz(request, course_id=None):
    """View to create a new quiz with improved error handling"""
    # RBAC v0.1 Compliant Access Control
    user = request.user
    can_create = False
    
    if user.role == 'globaladmin':
        can_create = True  # FULL access
    elif user.role == 'superadmin':
        can_create = True  # CONDITIONAL access (business-scoped)
    elif user.role == 'admin':
        can_create = True  # CONDITIONAL access (branch-scoped)
    elif user.role == 'instructor':
        can_create = True  # CONDITIONAL access (branch-scoped)
    
    if not can_create:
        return HttpResponseForbidden("You don't have permission to create quizzes")
    
    # Get the course if course_id is provided
    course = None
    if course_id:
        try:
            course = get_object_or_404(Course, id=course_id)
            
            # Additional validation for course access
            if not check_course_permission(request.user, course):
                return HttpResponseForbidden("You don't have permission to create quizzes for this course")
        except Exception as e:
            messages.error(request, f"Error accessing course: {str(e)}")
            return redirect('quiz:quiz_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                form = QuizForm(request.POST, user=request.user)
                
                if form.is_valid():
                    # Use the form's save method for proper validation
                    quiz = form.save(commit=False)
                    quiz.creator = request.user
                    
                    if course:
                        quiz.course = course
                    
                    # Save the quiz
                    quiz.save()
                    
                    messages.success(request, "Quiz created successfully!")
                    
                    # Handle AJAX requests
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': 'Quiz created successfully!',
                            'quiz_id': quiz.id,
                            'redirect_url': reverse('quiz:edit_quiz', args=[quiz.id])
                        })
                    
                    return redirect('quiz:edit_quiz', quiz_id=quiz.id)
                else:
                    # Form validation failed
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'errors': form.errors,
                            'message': 'Please correct the errors below.'
                        }, status=400)
                        
        except ValidationError as ve:
            # Handle Django validation errors
            error_message = "Validation error: " + str(ve)
            messages.error(request, error_message)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': [error_message]}
                }, status=400)
                
        except Exception as e:
            # Handle database and other errors
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating quiz: {str(e)}", exc_info=True)
            
            error_message = "An error occurred while creating the quiz. Please try again."
            messages.error(request, error_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': [error_message]}
                }, status=500)
    else:
        # GET request - create empty form
        form = QuizForm(user=request.user)
            
    context = {
        'form': form,
        'quiz': getattr(form, 'instance', None),
        'course': course,
        'page_title': f'Create Quiz{" for " + course.title if course else ""}'
    }
    
    # Get available rubrics for current user
    try:
        from lms_rubrics.models import Rubric
        if hasattr(request.user, 'branch'):
            # Filter rubrics by user's branch business
            context['rubrics'] = Rubric.objects.filter(
                branch__business=request.user.branch.business
            ).order_by('title')
        else:
            context['rubrics'] = Rubric.objects.all().order_by('title')
    except ImportError:
        context['rubrics'] = []
    
    # Set navigation context based on course
    if course:
        context['back_url'] = reverse('courses:course_detail', args=[course.id])
        context['breadcrumbs'] = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_detail', args=[course.id]), 'label': course.title, 'icon': 'fa-book'},
            {'label': 'Create Quiz', 'icon': 'fa-plus-circle'}
        ]
    else:
        context['back_url'] = reverse('quiz:quiz_list')
        context['breadcrumbs'] = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quiz List', 'icon': 'fa-list'},
            {'label': 'Create Quiz', 'icon': 'fa-plus-circle'}
        ]
    
    return render(request, 'quiz/quiz_form.html', context)




@login_required
def add_question(request, quiz_id):
    """API endpoint to add a new question to a quiz"""
    print(f"\n=== Starting Question Creation ===")
    print(f"Quiz ID: {quiz_id}")
    print(f"User: {request.user.username}")
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request POST data: {dict(request.POST)}")
    
    # Get quiz and check permissions - this should be done for both GET and POST requests
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, 'You do not have permission to add questions to this quiz')
        return redirect('quiz:edit_quiz', quiz_id=quiz_id)
    
    if request.method == 'POST':
        try:
            print(f"Found quiz: {quiz.title}")
            
            form = QuestionForm(request.POST, quiz=quiz)
            print(f"Form data received: {dict(request.POST)}")
            print(f"Form is valid: {form.is_valid()}")
            if not form.is_valid():
                print(f"Form errors: {form.errors}")
            
            if form.is_valid():
                try:
                    question = form.save(commit=False)
                    question.quiz = quiz
                    
                    # Get the question type
                    question_type = form.cleaned_data['question_type']
                    
                    # Set question order
                    if not question.order:
                        max_order = quiz.questions.aggregate(Max('order'))['order__max']
                        question.order = (max_order or 0) + 1
                    
                    # Save question
                    question.save()
                    
                    # Update answers based on question type
                    question.answers.all().delete()
                    
                    # Clean up matching pairs if question type is not matching
                    if question_type not in ['matching', 'drag_drop_matching']:
                        question.matching_pairs.all().delete()
                    
                    # Create answers based on question type
                    if question_type in ['multiple_choice', 'multiple_select']:
                        options = request.POST.getlist('options[]')
                        is_vak_test = quiz.is_vak_test
                        
                        if is_vak_test:
                            # For VAK tests, create answers with learning styles
                            learning_styles = request.POST.getlist('learning_styles[]')
                            for i, option in enumerate(options):
                                if option.strip():
                                    learning_style = learning_styles[i] if i < len(learning_styles) else None
                                    Answer.objects.create(
                                        question=question,
                                        answer_text=option.strip(),
                                        is_correct=False,  # VAK tests don't have "correct" answers
                                        answer_order=i,
                                        learning_style=learning_style
                                    )
                        else:
                            # For regular quizzes, create answers with correct/incorrect flags
                            if question_type == 'multiple_choice':
                                # For multiple choice, use correct_answers[] (single value from radio buttons)
                                correct_answers = request.POST.getlist('correct_answers[]')
                                for i, option in enumerate(options):
                                    if option.strip():
                                        is_correct = str(i) in correct_answers or f'{i}' in correct_answers
                                        Answer.objects.create(
                                            question=question,
                                            answer_text=option.strip(),
                                            is_correct=is_correct,
                                            answer_order=i
                                        )
                            else:
                                # For multiple select, use correct_answers[] (multiple values)
                                correct_answers = request.POST.getlist('correct_answers[]')
                                for i, option in enumerate(options):
                                    if option.strip():
                                        is_correct = str(i) in correct_answers or f'{i}' in correct_answers
                                        Answer.objects.create(
                                            question=question,
                                            answer_text=option.strip(),
                                            is_correct=is_correct,
                                            answer_order=i
                                        )
                    
                    elif question_type == 'true_false':
                        correct_answer = request.POST.get('correct_answer')
                        Answer.objects.create(
                            question=question,
                            answer_text='True',
                            is_correct=(correct_answer == 'True'),
                            answer_order=0
                        )
                        Answer.objects.create(
                            question=question,
                            answer_text='False',
                            is_correct=(correct_answer == 'False'),
                            answer_order=1
                        )
                    
                    elif question_type == 'fill_blank':
                        blank_answer = request.POST.get('blank_answer', '').strip()
                        if blank_answer:
                            Answer.objects.create(
                                question=question,
                                answer_text=blank_answer,
                                is_correct=True,
                                answer_order=0
                            )
                    
                    elif question_type == 'multi_blank':
                        multi_blank_answers = request.POST.getlist('multi_blank_answers[]')
                        for i, answer in enumerate(multi_blank_answers):
                            if answer.strip():
                                Answer.objects.create(
                                    question=question,
                                    answer_text=answer.strip(),
                                    is_correct=True,
                                    answer_order=i
                                )
                    
                    elif question_type == 'short_answer':
                        # Short answer questions may have multiple acceptable answers
                        short_answers = request.POST.getlist('short_answers[]')
                        for i, answer in enumerate(short_answers):
                            if answer.strip():
                                Answer.objects.create(
                                    question=question,
                                    answer_text=answer.strip(),
                                    is_correct=True,
                                    answer_order=i
                                )
                    
                    elif question_type in ['matching', 'drag_drop_matching']:
                        # Handle matching questions
                        left_items = request.POST.getlist('matching_left[]')
                        right_items = request.POST.getlist('matching_right[]')
                        
                        # Create MatchingPair objects
                        from .models import MatchingPair
                        for i, (left, right) in enumerate(zip(left_items, right_items)):
                            if left.strip() and right.strip():
                                MatchingPair.objects.create(
                                    question=question,
                                    left_item=left.strip(),
                                    right_item=right.strip(),
                                    pair_order=i
                                )
                        
                        # Also store in Answer format for compatibility
                        for i, (left, right) in enumerate(zip(left_items, right_items)):
                            if left.strip() and right.strip():
                                Answer.objects.create(
                                    question=question,
                                    answer_text=f"{left.strip()}|{right.strip()}",
                                    is_correct=True,
                                    answer_order=i
                                )
                    
                    messages.success(request, f'Question "{question.question_text[:50]}..." added successfully!')
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': 'Question added successfully!',
                            'question_id': question.id,
                            'redirect_url': reverse('quiz:edit_quiz', args=[quiz.id])
                        })
                    else:
                        # Regular form submission - redirect to edit quiz page
                        return redirect('quiz:edit_quiz', quiz_id=quiz.id)
                    
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error creating question: {str(e)}", exc_info=True)
                    
                    error_message = 'An error occurred while creating the question. Please try again.'
                    messages.error(request, error_message)
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'message': error_message,
                            'errors': {'__all__': [str(e)]}
                        }, status=500)
                    # For regular form submission, the form will be re-rendered with errors
            else:
                # Form is invalid - check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': 'Please correct the errors below.',
                        'errors': form.errors
                    }, status=400)
                else:
                    # For regular form submissions, add errors to messages and re-render form
                    messages.error(request, 'Please correct the errors below.')
                    # Form will have errors attached and will be re-rendered
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in add_question view: {str(e)}", exc_info=True)
            
            error_message = 'An unexpected error occurred. Please try again.'
            messages.error(request, error_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': [str(e)]}
                }, status=500)
            # If not AJAX, fall through to render form with error
    else:
        # GET request - render empty form
        form = QuestionForm(quiz=quiz)
    
    # Prepare context for form rendering
    context = {
        'quiz': quiz,
        'form': form,
        'page_title': f'Add Question to: {quiz.title}',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quiz List', 'icon': 'fa-list'},
            {'url': reverse('quiz:edit_quiz', args=[quiz.id]), 'label': f'Edit: {quiz.title}', 'icon': 'fa-edit'},
            {'label': 'Add Question', 'icon': 'fa-plus-circle'}
        ],
        # Required JSON context variables for the template
        'options_json': '[]',  # Empty array for new questions
        'correct_answers_json': '[]',  # Empty array for new questions
        'learning_styles_json': '[]',  # Empty array for new questions
        'multiple_blank_answers_json': '[]',  # Empty array for new questions  
        'matching_pairs_json': '[]',  # Empty array for new questions
        'blank_answer': '""',  # Empty string for new questions
        'is_edit': False  # This is a new question, not editing
    }
    
    return render(request, 'quiz/question_form.html', context)


@login_required
def edit_quiz(request, quiz_id):
    """View to edit an existing quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions using the new permission function
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to edit this quiz.")
        return redirect('quiz:quiz_list')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                form = QuizForm(request.POST, instance=quiz, user=request.user)
                
                if form.is_valid():
                    quiz = form.save()
                    messages.success(request, "Quiz updated successfully!")
                    return redirect('quiz:edit_quiz', quiz_id=quiz.id)
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'errors': form.errors,
                            'message': 'Please correct the errors below.'
                        }, status=400)
                        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating quiz: {str(e)}", exc_info=True)
            
            error_message = "An error occurred while updating the quiz. Please try again."
            messages.error(request, error_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': [error_message]}
                }, status=500)
    else:
        form = QuizForm(instance=quiz, user=request.user)
    
    # Get available rubrics
    try:
        from lms_rubrics.models import Rubric
        if hasattr(request.user, 'branch'):
            rubrics = Rubric.objects.filter(
                branch__business=request.user.branch.business
            ).order_by('title')
        else:
            rubrics = Rubric.objects.all().order_by('title')
    except ImportError:
        rubrics = []
        
    questions = quiz.questions.all().order_by('order')
    
    context = {
        'quiz': quiz,
        'form': form,
        'questions': questions,
        'rubrics': rubrics,
        'is_edit': True,
        'page_title': f'Edit Quiz: {quiz.title}',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quiz List', 'icon': 'fa-list'},
            {'label': f'Edit Quiz: {quiz.title}', 'icon': 'fa-edit'}
        ]
    }
    return render(request, 'quiz/quiz_form.html', context)


# Note: Additional views and functions would continue here 
# The original IndentationError at line 390 has been resolved by removing the misplaced code blocks  
# that were causing syntax errors in the GET request handler of the create_quiz function
#
# Status:  FIXED - Django server can now start without IndentationError
@login_required
def delete_quiz(request, quiz_id):
    """View to delete a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to delete this quiz.")
        return redirect('quiz:quiz_list')
    
    if request.method == 'POST':
        # Get all questions and their answers for debugging
        questions = list(quiz.questions.all().prefetch_related(
            Prefetch('answers', queryset=Answer.objects.order_by('answer_order'))
        ))
        
        quiz.delete()
        messages.success(request, "Quiz successfully deleted")
        return redirect('quiz:quiz_list')
    
    context = {
        'quiz': quiz,
    }
    return render(request, 'quiz/quiz_delete_confirm.html', context)


@login_required
def clone_quiz(request, quiz_id):
    """View to clone an existing quiz"""
    original_quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    if not check_quiz_edit_permission(request.user, original_quiz):
        messages.error(request, "You don't have permission to clone this quiz.")
        return redirect('quiz:quiz_list')
    
    try:
        with transaction.atomic():
            # Clone the quiz
            cloned_quiz = Quiz.objects.get(pk=original_quiz.pk)
            cloned_quiz.pk = None
            cloned_quiz.id = None
            cloned_quiz.title = f"{original_quiz.title} (Copy)"
            cloned_quiz.creator = request.user
            cloned_quiz.created_at = timezone.now()
            cloned_quiz.updated_at = timezone.now()
            cloned_quiz.save()
            
            # Clone questions and their answers
            for question in original_quiz.questions.all():
                original_question_pk = question.pk
                question.pk = None
                question.id = None
                question.quiz = cloned_quiz
                question.save()
                
                # Clone answers for this question
                original_question = Question.objects.get(pk=original_question_pk)
                for answer in original_question.answers.all():
                    answer.pk = None
                    answer.id = None
                    answer.question = question
                    answer.save()
                
                # Clone matching pairs if any
                for pair in original_question.matching_pairs.all():
                    pair.pk = None
                    pair.id = None
                    pair.question = question
                    pair.save()
            
            messages.success(request, f"Quiz '{original_quiz.title}' has been successfully cloned as '{cloned_quiz.title}'")
            return redirect('quiz:quiz_list')
            
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error cloning quiz: {str(e)}", exc_info=True)
        messages.error(request, f"An error occurred while cloning the quiz: {str(e)}")
        return redirect('quiz:quiz_list')


@login_required
def attempt_quiz(request, quiz_id):
    """View to attempt a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check if user can view the quiz first
    if not quiz.can_view_quiz(request.user):
        messages.error(request, "You don't have permission to access this quiz.")
        return redirect('quiz:quiz_list')
    
    # Check if user can start a new attempt
    if not quiz.is_available_for_user(request.user):
        # Check if it's because attempts are exhausted
        completed_attempts = quiz.get_completed_attempts(request.user)
        if quiz.attempts_allowed != -1 and completed_attempts >= quiz.attempts_allowed:
            messages.info(request, "You have reached the maximum number of attempts for this quiz.")
        else:
            messages.error(request, "You cannot start a new attempt at this time.")
        return redirect('quiz:quiz_view', quiz_id=quiz.id)

    # Handle GET request with start=true parameter (from Start Quiz button)
    if request.method == 'GET' and request.GET.get('start') == 'true':
        try:
            # Check if this is a force_new request (from "Start New" button)
            force_new = request.GET.get('force_new') == 'true'
            
            if force_new:
                # For force_new, clean up any existing incomplete attempts
                quiz.clean_stale_attempts(request.user)
                # Also clean up any incomplete attempts (not just stale ones)
                incomplete_attempts = quiz.attempts.filter(
                    user=request.user,
                    is_completed=False
                )
                if incomplete_attempts.exists():
                    # Delete associated answers first for data integrity
                    from .models import UserAnswer
                    UserAnswer.objects.filter(attempt__in=incomplete_attempts).delete()
                    incomplete_attempts.delete()
            
            # Check if user can start a new attempt
            if not quiz.can_start_new_attempt(request.user):
                messages.error(request, "You cannot start a new attempt at this time.")
                return redirect('quiz:quiz_view', quiz_id=quiz.id)
            
            # Check if there are remaining attempts
            remaining_attempts = quiz.get_remaining_attempts(request.user)
            if quiz.attempts_allowed != -1 and remaining_attempts <= 0:
                messages.error(request, "You have no attempts remaining for this quiz.")
                return redirect('quiz:quiz_view', quiz_id=quiz.id)
            
            # Clean up any stale attempts first (if not already done for force_new)
            if not force_new:
                quiz.clean_stale_attempts(request.user)
            
            # Create new quiz attempt
            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Redirect to the actual quiz
            return redirect('quiz:take_quiz', attempt_id=attempt.id)
            
        except Exception as e:
            messages.error(request, f"Error starting quiz attempt: {str(e)}")
            return redirect('quiz:quiz_view', quiz_id=quiz.id)

    if request.method == 'POST':
        # Handle starting a new quiz attempt
        try:
            # Check if this is a force_new request (from "Start New" button)
            force_new = request.GET.get('force_new') == 'true'
            
            if force_new:
                # For force_new, clean up any existing incomplete attempts
                quiz.clean_stale_attempts(request.user)
                # Also clean up any incomplete attempts (not just stale ones)
                incomplete_attempts = quiz.attempts.filter(
                    user=request.user,
                    is_completed=False
                )
                if incomplete_attempts.exists():
                    # Delete associated answers first for data integrity
                    from .models import UserAnswer
                    UserAnswer.objects.filter(attempt__in=incomplete_attempts).delete()
                    incomplete_attempts.delete()
            
            # Check if user can start a new attempt
            if not quiz.can_start_new_attempt(request.user):
                messages.error(request, "You cannot start a new attempt at this time.")
                return redirect('quiz:quiz_view', quiz_id=quiz.id)
            
            # Check if there are remaining attempts
            remaining_attempts = quiz.get_remaining_attempts(request.user)
            if quiz.attempts_allowed != -1 and remaining_attempts <= 0:
                messages.error(request, "You have no attempts remaining for this quiz.")
                return redirect('quiz:quiz_view', quiz_id=quiz.id)
            
            # Clean up any stale attempts first (if not already done for force_new)
            if not force_new:
                quiz.clean_stale_attempts(request.user)
            
            # Create new quiz attempt
            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # Redirect to the actual quiz
            return redirect('quiz:take_quiz', attempt_id=attempt.id)
            
        except Exception as e:
            messages.error(request, f"Error starting quiz attempt: {str(e)}")
            return redirect('quiz:quiz_view', quiz_id=quiz.id)
    
    # Handle other GET requests (show attempt quiz page)
    if request.method == 'GET':
        # Show quiz start page (GET request)
        context = {
            'quiz': quiz,
            'server_time': timezone.now(),
            'attempts': quiz.attempts.filter(user=request.user).order_by('-start_time'),
            'completed_attempts': quiz.get_completed_attempts(request.user),
            'remaining_attempts': quiz.get_remaining_attempts(request.user)
        }
        return render(request, 'quiz/attempt_quiz.html', context)


@login_required
def quiz_view(request, quiz_id):
    """View quiz details"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check if user can view the quiz
    if not quiz.can_view_quiz(request.user):
        messages.error(request, "You don't have permission to access this quiz.")
        return redirect('quiz:quiz_list')
    
    # Get user's attempts
    user_attempts = quiz.attempts.filter(user=request.user).order_by('-start_time')
    completed_attempts = quiz.get_completed_attempts(request.user)
    remaining_attempts = quiz.get_remaining_attempts(request.user)
    
    # Calculate highest score
    highest_score = None
    if completed_attempts > 0:
        highest_attempt = user_attempts.filter(is_completed=True).first()
        if highest_attempt:
            highest_score = highest_attempt.score
    
    # Check if user has completed the quiz
    has_completed = completed_attempts > 0
    
    # Build breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
        {'label': quiz.title, 'icon': 'fa-tasks'}
    ]
    
    context = {
        'quiz': quiz,
        'can_attempt': quiz.is_available_for_user(request.user),
        'attempts': user_attempts,
        'completed_attempts_count': completed_attempts,
        'attempts_remaining': remaining_attempts,
        'highest_score': highest_score,
        'has_completed': has_completed,
        'attempt_url': reverse('quiz:attempt_quiz', args=[quiz.id]),
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'quiz/quiz_view.html', context)


# Stub functions for other missing views
@login_required 
def view_quiz_feedback(request, quiz_id):
    """View to show quiz feedback for learners"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Only allow the user to see their own feedback
    if request.user.role == 'learner':
        # Get the user's latest completed attempt
        latest_attempt = QuizAttempt.objects.filter(
            quiz=quiz,
            user=request.user,
            is_completed=True
        ).order_by('-end_time').first()
        
        if not latest_attempt:
            messages.error(request, "You haven't completed this quiz yet.")
            return redirect('quiz:quiz_view', quiz_id=quiz_id)
        
        # Check if the quiz is configured to show correct answers
        if not quiz.show_correct_answers:
            messages.info(request, "Correct answers are not available for this quiz.")
            return redirect('quiz:quiz_view', quiz_id=quiz_id)
        
        # Get the user's answers for this attempt
        user_answers = UserAnswer.objects.filter(
            attempt=latest_attempt
        ).select_related('question', 'answer').order_by('question__order')
        
        context = {
            'quiz': quiz,
            'attempt': latest_attempt,
            'user_answers': user_answers,
            'breadcrumbs': [
                {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
                {'url': reverse('quiz:quiz_view', args=[quiz.id]), 'label': quiz.title, 'icon': 'fa-tasks'},
                {'label': 'Feedback', 'icon': 'fa-comments'}
            ]
        }
        
        return render(request, 'quiz/quiz_feedback.html', context)
    else:
        messages.error(request, "You don't have permission to view this feedback.")
        return redirect('quiz:quiz_list')

@login_required
def take_quiz(request, attempt_id):
    """View to take a quiz"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    # Check if attempt is valid
    if attempt.is_completed:
        return redirect('quiz:quiz_results', quiz_id=attempt.quiz.id)
    
    # Get quiz questions with answers - use randomized order if enabled
    questions = attempt.quiz.get_randomized_questions().prefetch_related('answers', 'matching_pairs')
    
    # Pre-shuffle matching pairs for each question to avoid template filter issues
    import random
    for question in questions:
        if hasattr(question, 'matching_pairs'):
            matching_pairs = list(question.matching_pairs.all())
            random.shuffle(matching_pairs)
            question.shuffled_matching_pairs = matching_pairs
    
    # Get user's existing answers for this attempt
    user_answers = UserAnswer.objects.filter(attempt=attempt)
    user_answers_dict = {}
    for ua in user_answers:
        if ua.question_id not in user_answers_dict:
            user_answers_dict[ua.question_id] = []
        user_answers_dict[ua.question_id].append(ua)
    
    # Calculate remaining time for the quiz
    remaining_time = attempt.get_remaining_time()
    
    # Calculate attempt number for this user
    user_attempts = attempt.quiz.attempts.filter(user=request.user).order_by('start_time')
    attempt_number = list(user_attempts).index(attempt) + 1
    
    # Get timezone information for the user
    from core.timezone_utils import TimezoneManager
    timezone_info = TimezoneManager.get_timezone_info(request.user)
    
    context = {
        'quiz': attempt.quiz,
        'attempt': attempt,
        'questions': questions,
        'user_answers': user_answers_dict,
        'remaining_time': remaining_time,
        'server_time': timezone.now(),
        'timezone_info': timezone_info,
        'attempt_number': attempt_number,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
            {'label': f'Taking: {attempt.quiz.title}', 'icon': 'fa-pencil-alt'}
        ]
    }
    
    return render(request, 'quiz/quiz_attempt.html', context)

def process_quiz_answers(request, attempt):
    """Process and save user answers from form data with improved error handling and logging"""
    saved_count = 0
    errors = []
    
    # Get all questions for this quiz
    questions = attempt.quiz.questions.all().order_by('order')
    
    logger.info(f"Processing answers for attempt {attempt.id}, quiz {attempt.quiz.id} with {questions.count()} questions")
    
    for question in questions:
        question_key = f'question_{question.id}'
        logger.debug(f"Processing question {question.id} of type {question.question_type}")
        
        # Clear existing answers for this question
        UserAnswer.objects.filter(attempt=attempt, question=question).delete()
        
        try:
            if question.question_type == 'multiple_choice':
                # Single answer selection
                answer_id = request.POST.get(question_key)
                logger.debug(f"Multiple choice answer_id: {answer_id}")
                if answer_id:
                    try:
                        answer = Answer.objects.get(id=answer_id, question=question)
                        user_answer = UserAnswer.objects.create(
                            attempt=attempt,
                            question=question,
                            answer=answer,
                            text_answer=answer.answer_text
                        )
                        is_correct = user_answer.check_answer()
                        logger.debug(f"Multiple choice answer saved: {answer_id}, correct: {is_correct}")
                        saved_count += 1
                    except Answer.DoesNotExist:
                        logger.warning(f"Answer {answer_id} not found for question {question.id}")
                        errors.append(f"Answer {answer_id} not found for question {question.id}")
                        
            elif question.question_type == 'multiple_select':
                # Multiple answer selection - handle both array format and JSON string format
                answer_ids = request.POST.getlist(f'{question_key}[]')
                
                # Also check for JSON string format from frontend
                json_answer = request.POST.get(question_key)
                if json_answer and not answer_ids:
                    try:
                        import json
                        answer_ids = json.loads(json_answer)
                        logger.debug(f"Parsed JSON multiple select answers: {answer_ids}")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON for question {question.id}: {json_answer}")
                
                logger.debug(f"Multiple select answer_ids: {answer_ids}")
                if answer_ids:
                    try:
                        # Store as JSON in text_answer field
                        import json
                        user_answer = UserAnswer.objects.create(
                            attempt=attempt,
                            question=question,
                            text_answer=json.dumps(answer_ids)
                        )
                        is_correct = user_answer.check_answer()
                        logger.debug(f"Multiple select answer saved: {answer_ids}, correct: {is_correct}")
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"Error saving multiple select answer for question {question.id}: {e}")
                        errors.append(f"Error saving multiple select answer: {str(e)}")
                        
            elif question.question_type == 'true_false':
                # True/False selection
                answer_id = request.POST.get(question_key)
                logger.debug(f"True/False answer_id: {answer_id}")
                if answer_id:
                    try:
                        answer = Answer.objects.get(id=answer_id, question=question)
                        user_answer = UserAnswer.objects.create(
                            attempt=attempt,
                            question=question,
                            answer=answer,
                            text_answer=answer.answer_text
                        )
                        is_correct = user_answer.check_answer()
                        logger.debug(f"True/False answer saved: {answer_id}, correct: {is_correct}")
                        saved_count += 1
                    except Answer.DoesNotExist:
                        logger.warning(f"Answer {answer_id} not found for question {question.id}")
                        errors.append(f"Answer {answer_id} not found for question {question.id}")
                        
            elif question.question_type == 'fill_blank':
                # Text input
                text_answer = request.POST.get(question_key, '').strip()
                logger.debug(f"Fill blank answer: '{text_answer}'")
                if text_answer:
                    user_answer = UserAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        text_answer=text_answer
                    )
                    is_correct = user_answer.check_answer()
                    logger.debug(f"Fill blank answer saved: '{text_answer}', correct: {is_correct}")
                    saved_count += 1
                    
            elif question.question_type == 'multi_blank':
                # Multiple text inputs
                blank_answers = []
                for i in range(question.answers.count()):
                    blank_key = f'{question_key}_{i}'
                    blank_answer = request.POST.get(blank_key, '').strip()
                    if blank_answer:
                        blank_answers.append(blank_answer)
                
                logger.debug(f"Multi blank answers: {blank_answers}")
                if blank_answers:
                    import json
                    user_answer = UserAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        text_answer=json.dumps(blank_answers)
                    )
                    is_correct = user_answer.check_answer()
                    logger.debug(f"Multi blank answer saved: {blank_answers}, correct: {is_correct}")
                    saved_count += 1
                    
            elif question.question_type == 'matching':
                # Matching questions
                matching_answers = []
                matching_data = request.POST.get(f'{question_key}_matching')
                logger.debug(f"Matching data: {matching_data}")
                if matching_data:
                    try:
                        import json
                        matching_answers = json.loads(matching_data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse matching data for question {question.id}: {e}")
                
                if matching_answers:
                    # Convert to proper format for matching
                    formatted_answers = []
                    for i, right_item in enumerate(matching_answers):
                        if i < question.matching_pairs.count():
                            left_item = question.matching_pairs.all()[i].left_item
                            formatted_answers.append({
                                'left_item': left_item,
                                'right_item': right_item,
                                'was_selected': True
                            })
                    
                    user_answer = UserAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        matching_answers=formatted_answers
                    )
                    is_correct = user_answer.check_answer()
                    logger.debug(f"Matching answer saved: {formatted_answers}, correct: {is_correct}")
                    saved_count += 1
                    
            elif question.question_type == 'drag_drop_matching':
                # Drag and drop matching
                drag_drop_data = request.POST.get(f'{question_key}_drag_drop')
                logger.debug(f"Drag drop data: {drag_drop_data}")
                if drag_drop_data:
                    try:
                        import json
                        drag_drop_answers = json.loads(drag_drop_data)
                        
                        # Convert to proper format for matching
                        formatted_answers = []
                        for left_item, right_item in drag_drop_answers.items():
                            formatted_answers.append({
                                'left_item': left_item,
                                'right_item': right_item,
                                'was_selected': True
                            })
                        
                        user_answer = UserAnswer.objects.create(
                            attempt=attempt,
                            question=question,
                            matching_answers=formatted_answers
                        )
                        is_correct = user_answer.check_answer()
                        logger.debug(f"Drag drop answer saved: {formatted_answers}, correct: {is_correct}")
                        saved_count += 1
                    except (json.JSONDecodeError, Exception) as e:
                        logger.error(f"Error processing drag drop matching for question {question.id}: {e}")
                        errors.append(f"Error processing drag drop matching: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error processing question {question.id}: {e}")
            errors.append(f"Unexpected error processing question {question.id}: {str(e)}")
    
    logger.info(f"Processed {saved_count} answers for attempt {attempt.id}, errors: {len(errors)}")
    if errors:
        logger.warning(f"Errors in answer processing: {errors}")
    
    return saved_count

@login_required
def save_quiz_progress(request, attempt_id):
    """Save quiz progress and user answers with improved error handling"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    logger.info(f"Save progress request for attempt {attempt_id} by user {request.user.username}")
    
    if attempt.is_completed:
        logger.warning(f"Attempt {attempt_id} already completed, cannot save progress")
        return JsonResponse({'status': 'error', 'message': 'Quiz already completed'})
    
    if request.method != 'POST':
        logger.warning(f"Invalid request method {request.method} for save progress")
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})
    
    try:
        # Process and save user answers
        logger.info(f"Processing answers for save progress, attempt {attempt_id}")
        saved_count = process_quiz_answers(request, attempt)
        logger.info(f"Saved {saved_count} answers for progress save, attempt {attempt_id}")
        
        # Get and save active time if provided (from periodic updates)
        active_time_seconds = request.POST.get('active_time_seconds')
        if active_time_seconds:
            try:
                active_time = int(active_time_seconds)
                if active_time > 0 and active_time > attempt.active_time_seconds:
                    attempt.active_time_seconds = active_time
                    logger.debug(f"Updated active_time_seconds to {active_time} during progress save, attempt {attempt_id}")
            except (ValueError, TypeError):
                pass  # Ignore invalid values during progress save
        
        # Update last activity
        attempt.update_last_activity()
        
        return JsonResponse({
            'status': 'success', 
            'message': 'Progress saved successfully',
            'saved_count': saved_count,
            'active_time_seconds': attempt.active_time_seconds
        })
        
    except Exception as e:
        logger.error(f"Error saving quiz progress for attempt {attempt_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error', 
            'message': f'Error saving progress: {str(e)}'
        })

@login_required
def submit_quiz(request, attempt_id):
    """View to submit a quiz attempt with improved error handling and logging"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    logger.info(f"Quiz submission started for attempt {attempt_id} by user {request.user.username}")
    
    if attempt.is_completed:
        logger.warning(f"Attempt {attempt_id} already completed, redirecting to results")
        return redirect('quiz:quiz_results', quiz_id=attempt.quiz.id)
    
    # Validate request
    if request.method != 'POST':
        logger.warning(f"Invalid request method {request.method} for attempt {attempt_id}")
        return HttpResponseForbidden("Invalid request method")
    
    try:
        # Process and save user answers first
        logger.info(f"Processing answers for attempt {attempt_id}")
        saved_count = process_quiz_answers(request, attempt)
        logger.info(f"Saved {saved_count} answers for attempt {attempt_id}")
        
        # Get and save active time from form submission
        active_time_seconds = request.POST.get('active_time_seconds')
        if active_time_seconds:
            try:
                active_time = int(active_time_seconds)
                if active_time > 0:
                    # Update active time - ensure we don't lose any time
                    # If the form value is greater than current, use it (includes current session)
                    if active_time > attempt.active_time_seconds:
                        attempt.active_time_seconds = active_time
                        logger.info(f"Updated active_time_seconds to {active_time} for attempt {attempt_id}")
                    # Also ensure page is unfocused when submitting
                    attempt.set_page_focus(is_focused=False)
            except (ValueError, TypeError):
                logger.warning(f"Invalid active_time_seconds value: {active_time_seconds}")
        
        # Mark the attempt as completed
        attempt.is_completed = True
        attempt.end_time = timezone.now()
        
        # Calculate score based on saved answers
        total_questions = attempt.quiz.questions.count()
        logger.info(f"Calculating score for attempt {attempt_id}, total questions: {total_questions}")
        
        if total_questions > 0:
            # Use the model's calculate_score method which properly checks answers
            calculated_score = attempt.calculate_score()
            logger.info(f"Calculated score for attempt {attempt_id}: {calculated_score}%")
        else:
            attempt.score = 0
            logger.warning(f"No questions found for quiz {attempt.quiz.id}")
        
        attempt.save()
        
        # Ensure time is synced to TopicProgress (safety check in case signal was missed)
        if hasattr(attempt, 'sync_time_to_topic_progress'):
            try:
                attempt.sync_time_to_topic_progress()
                logger.info(f"Ensured time sync for attempt {attempt_id} after submission")
            except Exception as e:
                logger.warning(f"Failed to sync time for attempt {attempt_id} after submission: {e}")
        
        # Log the final attempt details
        user_answers_count = attempt.user_answers.count()
        logger.info(f"Quiz submission completed for attempt {attempt_id}: "
                   f"Score: {attempt.score}%, User answers: {user_answers_count}, "
                   f"Total questions: {total_questions}, Active time: {attempt.active_time_seconds}s")
        
        messages.success(request, f"Quiz submitted successfully! Your score: {attempt.score:.1f}%")
        return redirect('quiz:view_attempt', attempt_id=attempt.id)
        
    except Exception as e:
        logger.error(f"Error submitting quiz attempt {attempt_id}: {str(e)}", exc_info=True)
        messages.error(request, f"Error submitting quiz: {str(e)}")
        return redirect('quiz:take_quiz', attempt_id=attempt_id)

@login_required
def quiz_results(request, quiz_id):
    """View to show quiz results"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check if user can access this quiz
    if not can_user_access_quiz(request.user, quiz):
        messages.error(request, "You don't have permission to view this quiz.")
        return redirect('quiz:quiz_list')
    
    if request.user.role == 'learner':
        # Show user's own results
        attempts = QuizAttempt.objects.filter(
            quiz=quiz, 
            user=request.user,
            is_completed=True
        ).order_by('-end_time')
        
        if not attempts:
            messages.info(request, "You haven't completed this quiz yet.")
            return redirect('quiz:quiz_view', quiz_id=quiz_id)
        
        latest_attempt = attempts.first()
        
        # Get user answers for the latest attempt
        user_answers = UserAnswer.objects.filter(attempt=latest_attempt).select_related('question', 'answer')
        
        # Create a responses list for template compatibility
        responses = []
        for user_answer in user_answers:
            response_data = {
                'question': user_answer.question,
                'answer': user_answer.answer,
                'text_answer': user_answer.text_answer,
                'matching_answers': user_answer.matching_answers,
                'is_correct': user_answer.is_correct,
                'points_earned': user_answer.points_earned,
                'selected_options': user_answer.get_selected_options_for_admin() if user_answer.question.question_type == 'multiple_select' else [],
                'parsed_matching_answers': user_answer.matching_answers if user_answer.matching_answers else []
            }
            responses.append(response_data)
        
        # Check if there are no user answers (quiz was submitted but no answers were saved)
        has_no_answers = user_answers.count() == 0
        
        # Add VAK test results if applicable
        vak_results = None
        if quiz.is_vak_test and not quiz.is_initial_assessment:
            vak_results = latest_attempt.get_vak_results()
        
        context = {
            'quiz': quiz,
            'attempts': attempts,
            'latest_attempt': latest_attempt,
            'past_attempts': attempts[1:] if len(attempts) > 1 else [],
            'user_answers': user_answers,
            'responses': responses,
            'has_no_answers': has_no_answers,
            'viewing_individual_attempt': False,
            'can_attempt': quiz.is_available_for_user(request.user),
            'vak_results': vak_results,
            'show_correct_answers': quiz.show_correct_answers,
            'breadcrumbs': [
                {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
                {'url': reverse('quiz:quiz_view', args=[quiz.id]), 'label': quiz.title, 'icon': 'fa-tasks'},
                {'label': 'Results', 'icon': 'fa-chart-bar'}
            ]
        }
        
        return render(request, 'quiz/quiz_results.html', context)
    else:
        # Instructors/admins can see all results
        attempts = QuizAttempt.objects.filter(
            quiz=quiz,
            is_completed=True
        ).select_related('user').order_by('-end_time')
        
        context = {
            'quiz': quiz,
            'attempts': attempts,
            'breadcrumbs': [
                {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
                {'url': reverse('quiz:edit_quiz', args=[quiz.id]), 'label': f'Edit {quiz.title}', 'icon': 'fa-edit'},
                {'label': 'All Results', 'icon': 'fa-chart-bar'}
            ]
        }
        
        return render(request, 'quiz/quiz_results.html', context)

@login_required
def quiz_detailed_report(request, quiz_id):
    """View to show detailed quiz report for instructors"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions - only instructors/admins can view detailed reports
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to view detailed reports.")
        return redirect('quiz:quiz_list')
    
    # Get all completed attempts with related data
    attempts = QuizAttempt.objects.filter(
        quiz=quiz,
        is_completed=True
    ).select_related('user').prefetch_related('user_answers__question', 'user_answers__answer')
    
    # Calculate statistics
    total_attempts = attempts.count()
    if total_attempts > 0:
        avg_score = attempts.aggregate(avg_score=Avg('score'))['avg_score']
        max_score = attempts.aggregate(max_score=Max('score'))['max_score']
        min_score = attempts.aggregate(min_score=Min('score'))['min_score']
    else:
        avg_score = max_score = min_score = 0
    
    # Get question-level statistics
    questions = quiz.questions.all().order_by('order')
    question_stats = []
    
    for question in questions:
        correct_count = UserAnswer.objects.filter(
            attempt__in=attempts,
            question=question,
            answer__is_correct=True
        ).count()
        
        question_stats.append({
            'question': question,
            'correct_count': correct_count,
            'total_attempts': total_attempts,
            'accuracy': (correct_count / total_attempts * 100) if total_attempts > 0 else 0
        })
    
    context = {
        'quiz': quiz,
        'attempts': attempts,
        'total_attempts': total_attempts,
        'avg_score': avg_score,
        'max_score': max_score,
        'min_score': min_score,
        'question_stats': question_stats,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
            {'url': reverse('quiz:edit_quiz', args=[quiz.id]), 'label': f'Edit {quiz.title}', 'icon': 'fa-edit'},
            {'label': 'Detailed Report', 'icon': 'fa-chart-line'}
        ]
    }
    
    return render(request, 'quiz/detailed_report_comprehensive.html', context)

@login_required
def preview_quiz(request, quiz_id):
    """View to preview a quiz before publishing to students"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions using the same permission function as edit
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to preview this quiz.")
        return redirect('quiz:quiz_list')
    
    # Get all questions for this quiz
    questions = quiz.questions.all().order_by('order').prefetch_related('answers', 'matching_pairs')
    
    context = {
        'quiz': quiz,
        'questions': questions,
        'is_preview': True,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-tasks'},
            {'url': reverse('quiz:edit_quiz', kwargs={'quiz_id': quiz.id}), 'label': f'Edit {quiz.title}', 'icon': 'fa-edit'},
            {'label': 'Preview Quiz', 'icon': 'fa-eye'}
        ]
    }
    
    return render(request, 'quiz/quiz_preview.html', context)

@login_required
def edit_question(request, question_id):
    """View to edit a question"""
    try:
        question = get_object_or_404(Question, id=question_id)
        quiz = question.quiz
    except Exception as e:
        messages.error(request, f"Question with ID {question_id} not found or access denied.")
        return redirect('quiz:quiz_list')
    
    # Check permissions
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to edit this question.")
        return redirect('quiz:quiz_list')
    
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question, quiz=quiz)
        if form.is_valid():
            question = form.save()
            
            # Get the question type
            question_type = form.cleaned_data['question_type']
            
            # Update answers based on question type
            question.answers.all().delete()
            
            # Clean up matching pairs if question type is not matching
            if question_type not in ['matching', 'drag_drop_matching']:
                question.matching_pairs.all().delete()
            
            # Create answers based on question type - same logic as add_question
            if question_type in ['multiple_choice', 'multiple_select']:
                options = request.POST.getlist('options[]')
                is_vak_test = quiz.is_vak_test
                
                if is_vak_test:
                    # For VAK tests, create answers with learning styles
                    learning_styles = request.POST.getlist('learning_styles[]')
                    for i, option in enumerate(options):
                        if option.strip():
                            learning_style = learning_styles[i] if i < len(learning_styles) else None
                            Answer.objects.create(
                                question=question,
                                answer_text=option.strip(),
                                is_correct=False,  # VAK tests don't have "correct" answers
                                answer_order=i,
                                learning_style=learning_style
                            )
                else:
                    # For regular quizzes, create answers with correct/incorrect flags
                    if question_type == 'multiple_choice':
                        # For multiple choice, use correct_answers[] (single value from radio buttons)
                        correct_answers = request.POST.getlist('correct_answers[]')
                        for i, option in enumerate(options):
                            if option.strip():
                                is_correct = str(i) in correct_answers or f'{i}' in correct_answers
                                Answer.objects.create(
                                    question=question,
                                    answer_text=option.strip(),
                                    is_correct=is_correct,
                                    answer_order=i
                                )
                    else:
                        # For multiple select, use correct_answers[] (multiple values)
                        correct_answers = request.POST.getlist('correct_answers[]')
                        for i, option in enumerate(options):
                            if option.strip():
                                is_correct = str(i) in correct_answers or f'{i}' in correct_answers
                                Answer.objects.create(
                                    question=question,
                                    answer_text=option.strip(),
                                    is_correct=is_correct,
                                    answer_order=i
                                )
            
            elif question_type == 'true_false':
                correct_answer = request.POST.get('correct_answer')
                Answer.objects.create(
                    question=question,
                    answer_text='True',
                    is_correct=(correct_answer == 'True'),
                    answer_order=0
                )
                Answer.objects.create(
                    question=question,
                    answer_text='False',
                    is_correct=(correct_answer == 'False'),
                    answer_order=1
                )
            
            elif question_type == 'fill_blank':
                blank_answer = request.POST.get('blank_answer', '').strip()
                if blank_answer:
                    Answer.objects.create(
                        question=question,
                        answer_text=blank_answer,
                        is_correct=True,
                        answer_order=0
                    )
            
            elif question_type == 'multi_blank':
                multi_blank_answers = request.POST.getlist('multi_blank_answers[]')
                for i, answer in enumerate(multi_blank_answers):
                    if answer.strip():
                        Answer.objects.create(
                            question=question,
                            answer_text=answer.strip(),
                            is_correct=True,
                            answer_order=i
                        )
            
            elif question_type == 'short_answer':
                # Short answer questions may have multiple acceptable answers
                short_answers = request.POST.getlist('short_answers[]')
                for i, answer in enumerate(short_answers):
                    if answer.strip():
                        Answer.objects.create(
                            question=question,
                            answer_text=answer.strip(),
                            is_correct=True,
                            answer_order=i
                        )
            
            elif question_type in ['matching', 'drag_drop_matching']:
                # Handle matching questions
                left_items = request.POST.getlist('matching_left[]')
                right_items = request.POST.getlist('matching_right[]')
                
                # Create MatchingPair objects
                from .models import MatchingPair
                for i, (left, right) in enumerate(zip(left_items, right_items)):
                    if left.strip() and right.strip():
                        MatchingPair.objects.create(
                            question=question,
                            left_item=left.strip(),
                            right_item=right.strip(),
                            pair_order=i
                        )
                
                # Also store in Answer format for compatibility
                for i, (left, right) in enumerate(zip(left_items, right_items)):
                    if left.strip() and right.strip():
                        Answer.objects.create(
                            question=question,
                            answer_text=f"{left.strip()}|{right.strip()}",
                            is_correct=True,
                            answer_order=i
                        )
            
            messages.success(request, 'Question updated successfully')
            return redirect('quiz:edit_quiz', quiz_id=quiz.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = QuestionForm(instance=question, quiz=quiz)
    
    # Prepare existing answers data for the template
    existing_answers = question.answers.all().order_by('answer_order', 'id')
    
    # Validate that we have answers for the question type
    if question.question_type in ['multiple_choice', 'multiple_select', 'true_false'] and not existing_answers.exists():
        messages.warning(request, f"No answers found for this {question.question_type} question. Please add answers.")
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)
    
    options_json = json.dumps([answer.answer_text for answer in existing_answers])
    # Fix: Convert correct answers to array format expected by frontend
    # Use the actual index position in the ordered list, not the answer ID
    correct_answers_array = [str(i) for i, answer in enumerate(existing_answers) if answer.is_correct]
    correct_answers_json = json.dumps(correct_answers_array)
    # Fix: Convert learning styles to array format expected by frontend
    learning_styles_array = [answer.learning_style or '' for answer in existing_answers]
    learning_styles_json = json.dumps(learning_styles_array)
    
    # Debug logging for existing data (only in development)
    print(f"Quiz Question Edit: Question ID {question_id}, Type: {question.question_type}")
    print(f"Quiz Question Edit: Found {existing_answers.count()} existing answers")
    
    # Handle different question types for existing data
    if question.question_type == 'fill_blank':
        blank_answer = json.dumps(existing_answers.first().answer_text if existing_answers.exists() else "")
    else:
        blank_answer = '""'
    
    if question.question_type == 'multi_blank':
        multiple_blank_answers_json = json.dumps([answer.answer_text for answer in existing_answers])
    else:
        multiple_blank_answers_json = '[]'
    
    # Handle matching pairs
    if question.question_type in ['matching', 'drag_drop_matching']:
        matching_pairs = question.matching_pairs.all().order_by('pair_order')
        if matching_pairs.exists():
            # Use matching pairs from the database
            matching_pairs_data = [{
                'left': pair.left_item, 
                'right': pair.right_item
            } for pair in matching_pairs]
        else:
            # Fallback to answers if no matching pairs exist
            matching_pairs_data = [{
                'left': answer.answer_text.split('|')[0] if '|' in answer.answer_text else '',
                'right': answer.answer_text.split('|')[1] if '|' in answer.answer_text else ''
            } for answer in existing_answers]
        
        # Convert to the format expected by the frontend
        matching_pairs_json = json.dumps({
            'left': [pair['left'] for pair in matching_pairs_data],
            'right': [pair['right'] for pair in matching_pairs_data]
        })
    else:
        matching_pairs_json = '{"left": [], "right": []}'
    
    context = {
        'quiz': quiz,
        'question': question,
        'form': form,
        'is_edit': True,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quiz List', 'icon': 'fa-list'},
            {'url': reverse('quiz:edit_quiz', args=[quiz.id]), 'label': quiz.title, 'icon': 'fa-edit'},
            {'label': 'Edit Question', 'icon': 'fa-pencil-alt'}
        ],
        # Existing data for template
        'options_json': options_json,
        'correct_answers_json': correct_answers_json,
        'learning_styles_json': learning_styles_json,
        'multiple_blank_answers_json': multiple_blank_answers_json,
        'matching_pairs_json': matching_pairs_json,
        'blank_answer': blank_answer,
    }
    return render(request, 'quiz/question_form.html', context)

@login_required
def delete_question(request, question_id):
    """View to delete a question"""
    question = get_object_or_404(Question, id=question_id)
    quiz = question.quiz
    
    # Check permissions
    if not check_quiz_edit_permission(request.user, quiz):
        messages.error(request, "You don't have permission to delete this question.")
        return redirect('quiz:quiz_list')
    
    if request.method == 'POST':
        # Delete all answers first to avoid foreign key constraint issues
        question.answers.all().delete()
        
        # Delete matching pairs if they exist
        question.matching_pairs.all().delete()
        
        # Delete the question itself
        question.delete()
        
        messages.success(request, "Question successfully deleted")
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)
    
    # For GET requests, redirect back to quiz edit page
    messages.info(request, "Use the delete button on the quiz edit page to delete questions.")
    return redirect('quiz:edit_quiz', quiz_id=quiz.id)


@login_required
def view_attempt(request, attempt_id):
    """View to show details of a specific quiz attempt"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id)
    
    # Check permissions - users can only view their own attempts, instructors can view any
    if request.user.role == 'learner' and attempt.user != request.user:
        messages.error(request, "You can only view your own quiz attempts.")
        return redirect('quiz:quiz_list')
    elif request.user.role not in ['learner'] and not check_quiz_edit_permission(request.user, attempt.quiz):
        messages.error(request, "You don't have permission to view this attempt.")
        return redirect('quiz:quiz_list')
    
    # Ensure score is calculated if attempt is completed
    if attempt.is_completed and attempt.score == 0:
        attempt.calculate_score()
    
    # Get user's answers for this attempt
    user_answers = UserAnswer.objects.filter(
        attempt=attempt
    ).select_related('question', 'answer').order_by('question__order')
    
    # Log user answers for debugging
    logger.debug(f"Found {user_answers.count()} user answers for attempt {attempt.id}")
    for ua in user_answers:
        logger.debug(f"User answer - Question {ua.question.id}: {ua.text_answer or ua.answer}")
    
    # Organize answers by question
    answers_by_question = {}
    for user_answer in user_answers:
        question_id = user_answer.question.id
        if question_id not in answers_by_question:
            answers_by_question[question_id] = []
        answers_by_question[question_id].append(user_answer)
    
    # Get all questions with correct answers
    questions = attempt.quiz.questions.all().order_by('order').prefetch_related('answers', 'matching_pairs')
    
    # Calculate score breakdown for display
    total_points = sum(q.points for q in questions)
    earned_points = sum(answer.points_earned for answer in user_answers)
    calculated_score = round((earned_points / total_points) * 100, 1) if total_points > 0 else 0
    
    # Create responses list for template compatibility (same as quiz_results)
    responses = []
    for user_answer in user_answers:
        response_data = {
            'question': user_answer.question,
            'answer': user_answer.answer,
            'text_answer': user_answer.text_answer,
            'matching_answers': user_answer.matching_answers,
            'is_correct': user_answer.is_correct,
            'points_earned': user_answer.points_earned,
            'selected_options': user_answer.get_selected_options_for_admin() if user_answer.question.question_type == 'multiple_select' else [],
            'parsed_matching_answers': user_answer.matching_answers if user_answer.matching_answers else []
        }
        responses.append(response_data)
    
    # Add VAK test results if applicable
    vak_results = None
    if attempt.quiz.is_vak_test and not attempt.quiz.is_initial_assessment:
        vak_results = attempt.get_vak_results()
    
    # Get attempt number for this user
    user_attempts = attempt.quiz.attempts.filter(user=attempt.user).order_by('start_time')
    attempt_number = list(user_attempts).index(attempt) + 1
    total_attempts = user_attempts.count()
    
    context = {
        'quiz': attempt.quiz,
        'attempt': attempt,
        'latest_attempt': attempt,  # For template compatibility
        'questions': questions,
        'user_answers': user_answers,
        'answers_by_question': answers_by_question,
        'responses': responses,  # Add responses for template compatibility
        'total_points': total_points,
        'earned_points': earned_points,
        'calculated_score': calculated_score,
        'vak_results': vak_results,
        'show_correct_answers': attempt.quiz.show_correct_answers,
        'viewing_individual_attempt': True,
        'attempt_number': attempt_number,
        'total_attempts': total_attempts,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('quiz:quiz_list'), 'label': 'Quizzes', 'icon': 'fa-question-circle'},
            {'url': reverse('quiz:quiz_view', args=[attempt.quiz.id]), 'label': attempt.quiz.title, 'icon': 'fa-tasks'},
            {'label': f'Attempt #{attempt_number} Results', 'icon': 'fa-eye'}
        ]
    }
    
    return render(request, 'quiz/quiz_results.html', context)


@login_required
def get_remaining_time(request, attempt_id):
    """Get remaining time for a quiz attempt"""
    try:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
        
        # Check if attempt is completed
        if attempt.is_completed:
            return JsonResponse({'remaining_time': 0})
        
        # Get remaining time from the attempt model
        remaining_time = attempt.get_remaining_time()
        
        if remaining_time is None:
            # No time limit set
            return JsonResponse({'remaining_time': None})
        
        return JsonResponse({'remaining_time': remaining_time})
        
    except Exception as e:
        logger.error(f"Error getting remaining time for attempt {attempt_id}: {str(e)}")
        return JsonResponse({'remaining_time': None, 'error': str(e)})

@login_required
@require_POST
def update_active_time(request, attempt_id):
    """Update active time for a quiz attempt"""
    try:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
        
        # Check if attempt is completed
        if attempt.is_completed:
            return JsonResponse({'success': False, 'error': 'Quiz already completed'})
        
        # Get additional seconds from request
        data = json.loads(request.body) if request.body else {}
        additional_seconds = data.get('additional_seconds', 0)
        is_focused = data.get('is_focused', True)
        
        # Update active time
        if is_focused:
            # Set page focus
            attempt.set_page_focus(is_focused=True)
        else:
            # Unfocus - calculate time since last focus
            attempt.set_page_focus(is_focused=False)
        
        # If additional seconds provided, add them
        if additional_seconds > 0:
            attempt.update_active_time(additional_seconds=additional_seconds)
        
        # Get current active time (including current session)
        current_active_time = attempt.total_active_time_with_current_session
        
        return JsonResponse({
            'success': True,
            'active_time_seconds': attempt.active_time_seconds,
            'total_active_time_seconds': current_active_time,
            'is_currently_active': attempt.is_currently_active
        })
        
    except Exception as e:
        logger.error(f"Error updating active time for attempt {attempt_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def get_answer_texts(request, question_id):
    """Get text content of quiz answers by their IDs"""
    try:
        # Get answer IDs from query parameters
        answer_ids_param = request.GET.get('answer_ids', '[]')
        
        try:
            answer_ids = json.loads(answer_ids_param)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid answer_ids format'})
        
        if not answer_ids:
            return JsonResponse({'success': True, 'answers': []})
        
        # Get the question to ensure user has access
        question = get_object_or_404(Question, id=question_id)
        
        # Check if user has access to this question (through quiz attempts or course enrollment)
        user_has_access = (
            QuizAttempt.objects.filter(
                quiz=question.quiz,
                user=request.user
            ).exists() or
            question.quiz.course.enrollments.filter(user=request.user).exists()
        )
        
        if not user_has_access:
            return JsonResponse({'success': False, 'error': 'Access denied'})
        
        # Get the answers
        answers = Answer.objects.filter(
            id__in=answer_ids,
            question=question
        ).values_list('text', flat=True)
        
        return JsonResponse({
            'success': True,
            'answers': list(answers)
        })
        
    except Exception as e:
        logger.error(f"Error getting answer texts for question {question_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def debug_user_answer(request, attempt_id):
    """Debug endpoint to inspect quiz attempt and user answers"""
    try:
        attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
        
        # Get all questions and their answers
        questions = attempt.quiz.questions.all().order_by('order')
        user_answers = attempt.user_answers.all().select_related('question', 'answer')
        
        debug_data = {
            'attempt_id': attempt.id,
            'quiz_id': attempt.quiz.id,
            'quiz_title': attempt.quiz.title,
            'user': attempt.user.username,
            'is_completed': attempt.is_completed,
            'score': float(attempt.score),
            'start_time': attempt.start_time.isoformat(),
            'end_time': attempt.end_time.isoformat() if attempt.end_time else None,
            'total_questions': questions.count(),
            'user_answers_count': user_answers.count(),
            'questions': [],
            'raw_post_data': dict(request.POST) if request.method == 'POST' else {}
        }
        
        for question in questions:
            question_data = {
                'question_id': question.id,
                'question_type': question.question_type,
                'question_text': question.question_text[:100] + '...' if len(question.question_text) > 100 else question.question_text,
                'points': question.points,
                'answers': [],
                'user_answers': []
            }
            
            # Get correct answers
            for answer in question.answers.all():
                question_data['answers'].append({
                    'id': answer.id,
                    'text': answer.answer_text,
                    'is_correct': answer.is_correct,
                    'order': answer.answer_order
                })
            
            # Get user answers for this question
            for user_answer in user_answers.filter(question=question):
                question_data['user_answers'].append({
                    'id': user_answer.id,
                    'answer_id': user_answer.answer_id,
                    'text_answer': user_answer.text_answer,
                    'matching_answers': user_answer.matching_answers,
                    'is_correct': user_answer.is_correct,
                    'points_earned': float(user_answer.points_earned),
                    'submitted_at': user_answer.submitted_at.isoformat()
                })
            
            debug_data['questions'].append(question_data)
        
        return JsonResponse(debug_data, json_dumps_params={'indent': 2})
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
