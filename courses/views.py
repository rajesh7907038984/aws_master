from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, HttpResponseNotFound, StreamingHttpResponse, HttpResponseServerError, HttpResponseRedirect, FileResponse
from django.db.models import Q, Max, Count, F, Sum, Avg, Exists, OuterRef, Prefetch, Subquery, FloatField, ExpressionWrapper
from django.urls import reverse, NoReverseMatch
from django.core.exceptions import ValidationError
from django.template.exceptions import TemplateDoesNotExist
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect, csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.conf import settings
from django.db import transaction, IntegrityError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.storage import default_storage, FileSystemStorage
from django.http import Http404
from django.utils.translation import gettext as _
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.apps import apps

# Standard library imports
import os
import tempfile
import shutil
import time
import uuid
import logging
import requests
import json
import traceback
import mimetypes
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote, unquote
import re
from wsgiref.util import FileWrapper
import magic
from io import BytesIO
from urllib.parse import urlparse
from core.decorators.error_handling import comprehensive_error_handler, api_error_handler, safe_file_operation
# from core.utils.file_Session import FileSessionValidator
from core.utils.query_optimization import QueryOptimizer

# Third-party imports
from role_management.utils import require_capability, require_any_capability, PermissionManager

# Local imports
from .models import (
    Course, 
    Topic, 
    CourseEnrollment, 
    Section
)

# Import Comment and Attachment dynamically (they may not exist)
try:
    from .models import Comment
except ImportError:
    Comment = None

try:
    from .models import Attachment
except ImportError:
    Attachment = None

# Import TopicProgress and CourseTopic dynamically
try:
    from courses.models import TopicProgress
except ImportError:
    TopicProgress = None

try:
    from courses.models import CourseTopic
except ImportError:
    CourseTopic = Course.topics.through if hasattr(Course, "topics") else None
from .forms import CourseForm, TopicForm
from categories.models import CourseCategory
from categories.context_processors import get_user_accessible_categories
from quiz.models import Quiz
from assignments.models import Assignment
from conferences.models import Conference
from discussions.models import Discussion as DiscussionModel, Comment as DiscussionComment
from users.models import CustomUser, Branch
from role_management.models import RoleCapability, UserRole
from groups.models import CourseGroup, BranchGroup
from certificates.models import CertificateTemplate
from branches.models import Branch
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from django.http import HttpRequest

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)

@login_required
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def course_manage(request: HttpRequest) -> HttpResponse:
    """Handle course creation for all roles."""
    # Generate a sequential course code
    last_course = Course.objects.order_by('-id').first()
    next_id = (last_course.id + 1) if last_course else 1
    course_code = f"COURSE{next_id:04d}"  # Format: COURSE0001, COURSE0002, etc.
    
    # Get the next available ID in a database-agnostic way
    from django.db import connection
    
    # Create a new draft course
    course = Course(
        title=f"New Course {next_id}",
        description="",
        course_code=course_code,
        course_outcomes="",  # Set default empty string for course_outcomes
        is_active=True,  # Set to active by default to ensure visibility
        is_temporary=False,  # Set is_temporary field
        instructor=request.user if request.user.role == 'instructor' else None,
        branch=request.user.branch if request.user.role in ['instructor', 'admin', 'superadmin'] else None
    )
    course.save()
    
    # Ensure the course creator is enrolled in the course
    # This is important for branch admins and other non-instructor roles
    from core.utils.enrollment import EnrollmentService
    EnrollmentService.create_or_get_enrollment(
        user=request.user,
        course=course,
        source='manual'
    )
    
    # Create default section with order number 1
    Section.objects.create(
        name="Section 1",
        description="",
        course=course,
        order=1
    )
    
    # Redirect to edit page
    return redirect('courses:course_edit', course.id)

def get_appropriate_back_url(request: HttpRequest, course_id: int) -> str:
    """Return correct back URL based on user role and content viewing history"""
    try:
        # Check if course_id is valid
        if not course_id or course_id == '' or course_id == 0:
            logger.warning(f"Invalid course_id in get_appropriate_back_url: {course_id}")
            return reverse('dashboard_learner')
            
        current_path = request.path
        has_viewed_content = request.session.get('has_viewed_content', False)

        # For learner
        if request.user.role == 'learner':
            if '/topic/' in current_path:
                request.session['has_viewed_content'] = True
                return reverse('courses:course_view', kwargs={'course_id': course_id})
            elif '/course/' in current_path and '/view/' in current_path:
                return reverse('dashboard_learner')  # Changed from 'dashboard' to 'dashboard_learner'
            return reverse('dashboard_learner')  # Changed from 'dashboard' to 'dashboard_learner'

        # For instructor
        elif request.user.role == 'instructor':
            if '/topic/' in current_path:
                request.session['has_viewed_content'] = True
                return reverse('courses:course_view', kwargs={'course_id': course_id})
            elif '/course/' in current_path:
                if '/view/' in current_path or '/details/' in current_path:
                    return reverse('courses:course_list')
            return reverse('courses:course_list')

        # For admin
        elif request.user.role == 'admin':
            if '/topic/' in current_path:
                request.session['has_viewed_content'] = True
                return reverse('courses:course_view', kwargs={'course_id': course_id})
            elif '/course/' in current_path:
                if '/view/' in current_path or '/details/' in current_path:
                    return reverse('courses:admin_courses')
            return reverse('courses:admin_courses')

        # For superadmin
        elif request.user.role in ['globaladmin', 'superadmin']:
            return reverse('dashboard_superadmin')

        return reverse('dashboard_learner')  # Changed from 'dashboard' to 'dashboard_learner'
    except NoReverseMatch as e:
        logger.error(f"NoReverseMatch error in get_appropriate_back_url: {str(e)}")
        # Default fallback
        try:
            return reverse('users:role_based_redirect')
        except NoReverseMatch:
            return '/'

def clear_navigation_history(request: HttpRequest) -> None:
    """Clear navigation history from session"""
    if 'has_viewed_content' in request.session:
        del request.session['has_viewed_content']

def check_course_permission(user: CustomUser, course: Course) -> bool:
    """Check if user has permission to view course content - RBAC v0.1 Compliant with Fixed Role Logic"""
    
    # Use the improved Course model method
    return course.user_has_access(user)

def check_instructor_management_access(user: CustomUser, course: Course) -> bool:
    """Check if user has instructor-level management access to a course"""
    if user.role != 'instructor':
        return False
    
    # 1. Check if user is the direct instructor
    if course.instructor == user:
        return True
        
    # 2. Check if instructor was assigned to this course through groups with instructor roles
    invited_instructor = course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__custom_role__name__icontains='instructor',
    ).exists()
    
    # 3. Check general instructor access through groups (admin assigned)
    instructor_access = course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True
    ).exists()
    
    return invited_instructor or instructor_access

def check_course_edit_permission(user, course):
    """Check if user has permission to edit a course - RBAC v0.1 Compliant with Fixed Role Logic"""
    
    # Add comprehensive logging for debugging
    logger.info(f"Checking edit permission for user {user.id} ({user.role}) on course {course.id}")
    
    # Use the improved Course model method
    can_modify = course.user_can_modify(user)
    logger.info(f"Course.user_can_modify returned: {can_modify}")
    
    return can_modify

def check_topic_edit_permission(user, topic, course, check_for='edit'):
    """Check if user has permission to edit or delete a topic - RBAC v0.1 Compliant"""
    # First verify that the topic is actually associated with the course
    topic_belongs_to_course = CourseTopic.objects.filter(topic=topic, course=course).exists()
    if not topic_belongs_to_course:
        return False
        
    # Global Admin: FULL access
    if user.role == 'globaladmin' or user.is_superuser:
        return True
        
    # Super Admin: CONDITIONAL access (within their assigned businesses only)
    if user.role == 'superadmin':
        if hasattr(course, 'branch') and course.branch:
            # Check if user is assigned to the business that owns this course's branch
            return user.business_assignments.filter(
                business=course.branch.business, 
                is_active=True
            ).exists()
        return False
        
    # Branch Admin: CONDITIONAL access (within their branch only)
    if user.role == 'admin' and user.branch == course.branch:
        return True
    
    # Instructor: CONDITIONAL access (use course edit permission check)
    if user.role == 'instructor':
        # Use the improved course edit permission check that includes group access
        return check_course_edit_permission(user, course)
    
    # Learner: NONE access for editing topics
    if user.role == 'learner':
        return False
    
    # Check for manage_courses capability through role assignments
    from role_management.models import RoleCapability, UserRole
    try:
        user_roles = UserRole.objects.filter(user=user)
        if user_roles.exists():
            for user_role in user_roles:
                if RoleCapability.objects.filter(
                    role=user_role.role,
                    capability='manage_courses'
                ).exists():
                    # Even with capability, must respect business/branch scope
                    if user.role == 'superadmin':
                        if hasattr(course, 'branch') and course.branch:
                            return user.business_assignments.filter(
                                business=course.branch.business, 
                                is_active=True
                            ).exists()
                    elif user.branch and hasattr(course, 'branch'):
                        return course.branch == user.branch
                    return True
    except Exception:
        pass
    
    # Additional check for topic-specific permissions through group roles
    # This is redundant now since check_course_edit_permission handles group access,
    # but keeping it as a fallback for can_create_topics specific permission
    if course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__custom_role__can_create_topics=True,
    ).exists():
        return True
        
    return False

def check_course_catalog_permission(user, course):
    """Check if user can browse course catalog (preview mode)"""
    # Everyone can browse public courses for information
    if course.catalog_visibility == 'visible' and course.is_active:
        return True
        
    # Private courses only visible to enrolled users or those with permission
    return check_course_permission(user, course)

def check_course_content_permission(user, course):
    """Check if user can access course content (full access)"""
    # Use the main permission check which requires enrollment
    return check_course_permission(user, course)

def get_topic_course(topic):
    """Helper function to get the course associated with a topic"""
    try:
        course_topic = CourseTopic.objects.filter(topic=topic).select_related('course').first()
        if course_topic:
            return course_topic.course
        logger.warning(f"Topic {topic.id} not associated with any course")
        return None
    except Exception as e:
        logger.error(f"Error retrieving course for topic {topic.id}: {str(e)}")
        return None

def get_course_context(request, user, course):
    """Helper function to get common course context data."""
    if not hasattr(user, 'role'):
        return {
            'can_edit': False,
            'can_delete': False,
            'can_manage_topics': False,
            'viewing_mode': None,
            'back_url': get_appropriate_back_url(request, course.id)
        }

    # Check if user has edit permission - RBAC v0.1 Compliant
    can_edit = check_course_edit_permission(user, course)

    # Check delete permission - RBAC v0.1 Compliant
    # Delete permissions are more restrictive than edit permissions
    can_delete = (
        user.role == 'globaladmin' or 
        user.is_superuser or
        (user.role == 'superadmin' and hasattr(course, 'branch') and course.branch and
         user.business_assignments.filter(business=course.branch.business, is_active=True).exists()) or
        (user.role == 'admin' and course.branch == user.branch) or
        (user.role == 'instructor' and course.instructor == user)
    )
    
    # For group-assigned instructors, allow delete only if they have admin-level permissions in the group
    if not can_delete and user.role == 'instructor':
        from groups.models import CourseGroupAccess
        can_delete = CourseGroupAccess.objects.filter(
            course=course,
            group__memberships__user=user,
            group__memberships__is_active=True,
            group__memberships__custom_role__can_manage_content=True,
            can_modify=True
        ).exists()

    viewing_mode = request.session.get('viewing_mode')

    return {
        'can_edit': can_edit and viewing_mode != 'view',
        'can_delete': can_delete and viewing_mode != 'view',
        'can_manage_topics': can_edit and viewing_mode != 'view',
        'viewing_mode': viewing_mode,
        'back_url': get_appropriate_back_url(request, course.id)
    }

@login_required
@require_capability('view_courses')
def course_list(request):
    """Display list of courses based on user role and group access."""
    user = request.user
    
    # Import needed models
    from courses.models import CourseEnrollment
    
    # Import TopicProgress dynamically
    try:
        from courses.models import TopicProgress
    except ImportError:
        TopicProgress = None
    
    # Remove automatic group check functionality
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Course Catalog', 'icon': 'fa-book'}
    ]
    
    # Get filter parameters from URL
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    progress_filter = request.GET.get('progress', '')
    instructor_filter = request.GET.get('instructor', '')
    sort_by = request.GET.get('sort', '')
    
    # Log course access for debugging
    logger.info(f"User {user.username} (role: {user.role}) accessing course list page")
    logger.info(f"Filters applied - Search: '{search_query}', Category: '{category_filter}', Progress: '{progress_filter}', Instructor: '{instructor_filter}', Sort: '{sort_by}'")

    # Check if instructor has manage_courses capability
    has_manage_courses = False
    if request.user.role == 'instructor':
        from role_management.models import RoleCapability, UserRole
        try:
            user_roles = UserRole.objects.filter(user=request.user)
            if user_roles.exists():
                for user_role in user_roles:
                    if RoleCapability.objects.filter(
                        role=user_role.role,
                        capability='manage_courses'
                    ).exists():
                        has_manage_courses = True
                        break
        except Exception:
            pass

    # Get unique course IDs first - Updated to use new role-based permission system
    if request.user.role == 'learner':
        # For learners, show only ACTIVE courses they are enrolled in
        course_ids = CourseEnrollment.objects.filter(
            user=request.user,
            course__is_active=True
        ).values_list('course_id', flat=True).distinct()
        
        # Add group-assigned courses for learners
        group_course_ids = Course.objects.filter(
            is_active=True,
            accessible_groups__memberships__user=request.user,
            accessible_groups__memberships__is_active=True,
            accessible_groups__memberships__user__role='learner'
        ).values_list('id', flat=True).distinct()
        
        # Combine enrolled and group-assigned courses
        all_learner_courses = set(course_ids) | set(group_course_ids)
        course_ids = list(all_learner_courses)
        
        # Log for debugging
        logger.info(f"Learner {request.user.username} (ID: {request.user.id}) can see {len(course_ids)} courses")
        logger.info(f"Course IDs for learner: {course_ids}")
    elif request.user.role == 'instructor' and has_manage_courses:
        # Instructors with manage_courses capability can see all courses, including drafts
        course_ids = Course.objects.all().values_list('id', flat=True).distinct()
    elif request.user.role == 'instructor':
        # Instructors see courses they are assigned to (primary), enrolled in (invited), or have group access to
        course_ids = Course.objects.filter(
            Q(instructor=request.user) |  # Primary instructor
            Q(enrolled_users=request.user, enrolled_users__role='instructor') |  # Enrolled as instructor
            Q(accessible_groups__memberships__user=request.user,
              accessible_groups__memberships__is_active=True,
              accessible_groups__memberships__user__role='instructor')  # Group access as instructor
        ).values_list('id', flat=True).distinct()
        
        # Ensure primary instructors are enrolled in their own courses
        instructor_courses = Course.objects.filter(instructor=request.user)
        for course in instructor_courses:
            from core.utils.enrollment import EnrollmentService
            EnrollmentService.create_or_get_enrollment(
                user=request.user,
                course=course,
                source='auto_instructor'
            )
            
        # Log for debugging
        logger.info(f"Instructor {request.user.username} (ID: {request.user.id}) has access to {len(list(course_ids))} courses")
        logger.info(f"Course IDs found: {list(course_ids)}")
    elif request.user.role == 'admin':
        # Admins can see all visible courses in their branch plus any they have direct access to
        course_ids = Course.objects.filter(
            is_active=True
        ).filter(
            Q(branch=request.user.branch, catalog_visibility='visible') |
            Q(accessible_groups__memberships__user=request.user,
              accessible_groups__memberships__is_active=True) |
            # Add direct enrollment check
            Q(enrolled_users=request.user)
        ).values_list('id', flat=True).distinct()
    elif request.user.role == 'globaladmin' or request.user.is_superuser:
        # Global Admin sees all courses
        course_ids = Course.objects.filter(
            is_active=True
        ).values_list('id', flat=True).distinct()
    elif request.user.role == 'superadmin':
        # Super Admin sees courses within their assigned businesses only
        from core.utils.business_filtering import filter_courses_by_business
        business_courses = filter_courses_by_business(request.user).filter(is_active=True)
        course_ids = business_courses.values_list('id', flat=True).distinct()
    else:
        course_ids = Course.objects.none().values_list('id', flat=True).distinct()

    # Now get the full course objects with all needed relations
    # Use the distinct IDs to ensure uniqueness
    # OPTIMIZATION: Add prefetch_related for enrollments to prevent N+1 queries
    from django.db.models import Prefetch
    
    courses = Course.objects.filter(id__in=course_ids).select_related(
        'instructor',
        'branch',
        'category'
    ).prefetch_related(
        Prefetch(
            'courseenrollment_set',
            queryset=CourseEnrollment.objects.filter(user=request.user).select_related('user'),
            to_attr='user_enrollments'
        )
    )

    # Log the number of courses found
    logger.info(f"Found {courses.count()} courses for user {user.username}")

    # Apply filters
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by category if provided
    if category_filter:
        try:
            courses = courses.filter(category_id=int(category_filter))
        except (ValueError, TypeError):
            logger.warning(f"Invalid category filter value: {category_filter}")
    
    # Filter by instructor if provided
    if instructor_filter:
        try:
            courses = courses.filter(instructor_id=int(instructor_filter))
        except (ValueError, TypeError):
            logger.warning(f"Invalid instructor filter value: {instructor_filter}")
    
    # Apply progress filter - requires additional query to course progress
    if progress_filter:
        try:
            # Get progress state for current user using CourseEnrollment model
            
            if progress_filter == 'not_started':
                # Get courses with no progress or no enrollment
                # A course is not started if there's no enrollment or if no topics are completed
                enrollment_course_ids = CourseEnrollment.objects.filter(
                    user=request.user
                ).values_list('course_id', flat=True)
                
                completed_topic_courses = TopicProgress.objects.filter(
                    user=request.user,
                    completed=True
                ).values_list('topic__coursetopic__course_id', flat=True).distinct()
                
                # Include courses with no enrollment or no completed topics
                courses = courses.filter(
                    ~Q(id__in=completed_topic_courses)
                )
                
            elif progress_filter == 'in_progress':
                # Courses with at least one completed topic but not all topics completed
                # Get courses where user has at least one completed topic
                in_progress_course_ids = set(TopicProgress.objects.filter(
                    user=request.user,
                    completed=True
                ).values_list('topic__coursetopic__course_id', flat=True).distinct())
                
                # Remove courses where all topics are completed
                completed_courses = []
                
                for course_id in in_progress_course_ids:
                    total_topics = Course.objects.get(id=course_id).topics.count()
                    completed_count = TopicProgress.objects.filter(
                        user=request.user,
                        topic__coursetopic__course_id=course_id,
                        completed=True
                    ).count()
                    
                    # If all topics are completed, add to completed list
                    if total_topics > 0 and completed_count == total_topics:
                        completed_courses.append(course_id)
                
                # Filter to only include in-progress courses
                courses = courses.filter(
                    id__in=[cid for cid in in_progress_course_ids if cid not in completed_courses]
                )
                
            elif progress_filter == 'completed':
                # Get all courses
                all_courses = courses.values_list('id', flat=True)
                completed_courses = []
                
                # Check each course to see if all topics are completed
                for course_id in all_courses:
                    total_topics = Course.objects.get(id=course_id).topics.count()
                    if total_topics == 0:
                        continue  # Skip courses with no topics
                        
                    completed_count = TopicProgress.objects.filter(
                        user=request.user,
                        topic__coursetopic__course_id=course_id,
                        completed=True
                    ).count()
                    
                    # If all topics are completed, add to completed list
                    if completed_count == total_topics:
                        completed_courses.append(course_id)
                
                courses = courses.filter(id__in=completed_courses)
                
        except Exception as e:
            logger.warning(f"Error applying progress filter: {str(e)}")
    
    # Apply sorting
    if sort_by == 'title_asc':
        courses = courses.order_by('title')
    elif sort_by == 'title_desc':
        courses = courses.order_by('-title')
    elif sort_by == 'date_added':
        courses = courses.order_by('-created_at')
    else:
        # Default sorting: recently accessed or title
        courses = courses.order_by('title')  # Default fallback

    # Annotate courses with user's membership status
    # Note: Removed problematic annotation that caused SQL syntax error
    # The user_is_member check is now handled in the template or view logic
    from django.db.models import Exists, OuterRef, Subquery
    from groups.models import GroupMembership, CourseGroupAccess
    
    # Fix: Use proper subquery for ManyToMany relationship
    courses = courses.annotate(
        user_is_member=Exists(
            CourseGroupAccess.objects.filter(
                course=OuterRef('pk'),
                group__memberships__user=request.user,
                group__memberships__is_active=True
            )
        )
    ).distinct()
    
    # Log first few courses to verify titles
    for i, course in enumerate(courses[:5]):
        logger.info(f"Course {i+1}: ID={course.id}, Title='{course.title}', Active={course.is_active}, Visibility={course.catalog_visibility}")
    
    # Get categories for the filter dropdown with role-based filtering
    categories = get_user_accessible_categories(request.user)
    
    # Add pagination
    from django.core.paginator import Paginator
    paginator = Paginator(courses, 12)  # Show 12 courses per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    logger.info(f"Displaying page {page_obj.number} of {paginator.num_pages} pages")

    # Add enrollment status and permission information for each course in the page
    # OPTIMIZATION: Use prefetched data instead of querying the database
    courses_with_status = []
    for course in page_obj:
        # Check enrollment status using prefetched data
        user_enrollments = getattr(course, 'user_enrollments', [])
        is_enrolled = len(user_enrollments) > 0
        enrollment = user_enrollments[0] if is_enrolled else None
        
        # Check permissions
        can_access_content = check_course_permission(request.user, course)
        can_browse_catalog = check_course_catalog_permission(request.user, course)
        can_edit_course = check_course_edit_permission(request.user, course)
        
        courses_with_status.append({
            'course': course,
            'is_enrolled': is_enrolled,
            'enrollment': enrollment,  # Add enrollment object for progress display
            'can_access_content': can_access_content,
            'can_browse_catalog': can_browse_catalog,
            'can_edit_course': can_edit_course,
        })

    context = {
        'courses': page_obj,
        'courses_with_status': courses_with_status,
        'categories': categories,
        'search_query': search_query,
        'category_filter': category_filter,
        'progress_filter': progress_filter,
        'instructor_filter': instructor_filter,
        'sort_by': sort_by,
        'back_url': reverse('dashboard_learner') if request.user.role == 'learner' else reverse('users:role_based_redirect'),
        'username': request.user.username,
        'breadcrumbs': breadcrumbs
    }
    
    # Add branch context for template (enables branch switcher for admin users)
    from core.branch_filters import filter_context_by_branch
    context = filter_context_by_branch(context, request.user, request)

    return render(request, 'courses/list/course_list.html', context)

@login_required
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
def admin_manage_courses(request):
    """Admin course management view."""
    if request.user.role != 'admin':
        return HttpResponseForbidden("You don't have permission to manage courses")

    # Get effective branch (supports branch switching)
    from core.branch_filters import BranchFilterManager
    effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
    
    if not effective_branch:
        messages.error(request, "You need to be assigned to a branch to manage courses")
        return redirect('dashboard_admin')

    # Get courses accessible to admin (branch courses and group-accessible courses)
    # Note: In management view, admin should see all courses in their effective branch regardless of catalog_visibility
    courses = Course.objects.filter(
        Q(branch=effective_branch) |
        Q(accessible_groups__memberships__user=request.user,
          accessible_groups__memberships__is_active=True)
    ).distinct()

    instructors = CustomUser.objects.filter(
        role='instructor',
        branch=effective_branch
    )

    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            course = form.save(commit=False)
            course.branch = effective_branch
            course.is_active = True  # Ensure course is active by default
            # Default to visible in catalog unless specified
            if not course.catalog_visibility:
                course.catalog_visibility = 'visible'
            course.save()
            form.save_m2m()  # Save group relationships
            
            # Ensure admin is enrolled in the course
            from core.utils.enrollment import EnrollmentService
            EnrollmentService.create_or_get_enrollment(
                user=request.user,
                course=course,
                source='auto_admin'
            )
            
            messages.success(request, f"Course '{course.title}' created successfully")
            return redirect('courses:admin_courses')
    else:
        form = CourseForm(user=request.user)

    # Add branch access context for header branch switcher
    from core.branch_filters import filter_context_by_branch
    
    context = {
        'courses': courses.order_by('-created_at'),
        'instructors': instructors,
        'form': form,
        'branch': effective_branch,
        'back_url': reverse('courses:admin_courses')
    }
    
    # Add branch context for template (enables branch switcher)
    context = filter_context_by_branch(context, request.user, request)

    return render(request, 'users/dashboards/manage_courses_admin.html', context)

# @login_required
# def instructor_manage_courses(request):
#     # All references have been updated to point to 'courses:course_list'
#     pass

@login_required
def super_admin_manage_courses(request):
    """Superadmin course management view."""
    if request.user.role != 'superadmin':
        return HttpResponseForbidden("You don't have permission to manage courses")

    # Apply business filtering for Super Admin users
    from core.utils.business_filtering import filter_courses_by_business, filter_branches_by_business
    courses = filter_courses_by_business(request.user).select_related('branch', 'instructor')
    branches = filter_branches_by_business(request.user)

    # Get filter parameters
    search_query = request.GET.get('q', '').strip()
    branch_id = request.GET.get('branch')
    status = request.GET.get('status')

    # Apply filters
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if branch_id:
        courses = courses.filter(branch_id=branch_id)
    if status:
        is_active = status == 'active'
        courses = courses.filter(is_active=is_active)

    # Handle CSV export
    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="courses_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Course ID',
            'Title',
            'Description',
            'Branch',
            'Instructor',
            'Status',
            'Created Date',
            'Last Updated'
        ])
        
        for course in courses.order_by('-created_at'):
            writer.writerow([
                course.id,
                course.title,
                course.description[:100] + '...' if len(course.description) > 100 else course.description,
                course.branch.name if course.branch else 'N/A',
                course.instructor.get_full_name() if course.instructor else 'N/A',
                'Active' if course.is_active else 'Inactive',
                course.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                course.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        return response

    context = {
        'courses': courses.order_by('-created_at'),
        'branches': branches,
        'search_query': search_query,
        'selected_branch': branch_id,
        'selected_status': status,
        'back_url': reverse('courses:course_list')
    }

    return render(request, 'users/dashboards/manage_courses_superadmin.html', context)

@login_required
@require_capability('view_courses')
def course_details(request, course_id):
    """Display details of a specific course."""
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # Import services for safe operations
    from core.utils.enrollment import EnrollmentService
    from core.utils.progress import ProgressCalculationService
    
    # Check if the user has permission to access this course
    if not check_course_permission(user, course):
        # For instructors, check if they have manage_courses capability
        if user.role == 'instructor':
            if not PermissionManager.user_has_capability(user, 'manage_courses'):
                messages.error(request, "You don't have permission to access this course.")
                return redirect('dashboard_instructor')
        else:
            messages.error(request, "You don't have permission to access this course.")
            # Determine correct dashboard URL based on user role
            if user.is_superuser or user.role == 'superadmin':
                return redirect('dashboard_superadmin')
            elif user.role == 'admin':
                return redirect('dashboard_admin')
            elif user.role == 'instructor':
                return redirect('dashboard_instructor')
            else:
                return redirect('dashboard_learner')
    
    # Check prerequisites for learners and instructors who don't have management access to the course
    prerequisite_check = {'can_access': True, 'missing_prerequisites': [], 'completed_prerequisites': []}
    if user.role == 'learner' or (user.role == 'instructor' and not check_instructor_management_access(user, course)):
        from .utils import check_prerequisites_completion
        prerequisite_check = check_prerequisites_completion(user, course)
        
        # If user doesn't have access due to missing prerequisites, we'll show the modal
        # but still let them view the course details (not the content)
    
    # Define breadcrumbs for this view
    dashboard_url = None
    if user.is_superuser:
        dashboard_url = reverse('dashboard_superadmin')
    elif user.role == 'admin':
        dashboard_url = reverse('dashboard_admin')
    elif user.role == 'instructor':
        dashboard_url = reverse('dashboard_instructor')
    else:
        dashboard_url = reverse('dashboard_learner')

    breadcrumbs = [
        {'url': dashboard_url, 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'label': course.title, 'icon': 'fa-graduation-cap'}
    ]
    
    # Log course image information for debugging
    if course.course_image:
        logger.info(f"Course {course_id} image: {course.course_image}")
        # Check if course_image has a url attribute
        if hasattr(course.course_image, 'url'):
            logger.info(f"Course {course_id} image URL: {course.course_image.url}")
            try:
                # For S3 storage, we can't check if file exists using path
                # Instead, we'll just log the URL which is what we need for display
                logger.info(f"Course {course_id} image URL available for display")
            except Exception as e:
                logger.error(f"Error accessing course image: {str(e)}")
        else:
            logger.info(f"Course {course_id} image doesn't have a URL attribute")
    else:
        logger.info(f"Course {course_id} has no image")

    # Check basic access
    if not request.user.is_authenticated:
        return redirect('users:login')
        
    if not request.user.is_superuser:
        if request.user.role == 'admin' and course.branch != request.user.branch:
            # Admin from different branch - no access
            messages.error(request, "You don't have permission to access this course.")
            return redirect('dashboard_admin')
        elif request.user.role == 'instructor':
            # Instructors have access if they're the primary instructor or invited instructor
            # This is already checked in check_course_permission, no need for additional checks here
            pass
        elif request.user.role == 'learner':
            # Explicitly check both enrollment and group access
            has_access = (
                course.enrolled_users.filter(id=request.user.id).exists() or
                course.accessible_groups.filter(
                    memberships__user=request.user,
                    memberships__is_active=True,
                    memberships__custom_role__can_view=True
                ).exists()
            )
            if not has_access:
                messages.error(request, "You don't have permission to access this course.")
                return redirect('dashboard_learner')

    # Get sections and topics
    sections = Section.objects.filter(course=course).order_by('order')
    
    # Filter topics differently based on user role
    if request.user.role == 'learner':
        # For learners, exclude draft topics and restricted topics
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).exclude(
            status='draft'  # Hide draft topics from learners
        ).exclude(
            restrict_to_learners=True,
            restricted_learners=request.user  # Hide topics where learner is restricted
        ).order_by('order', 'coursetopic__order', 'created_at')
    else:
        # For instructors, admins, and superusers, show all topics including drafts
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).order_by('order', 'coursetopic__order', 'created_at')
    
    # Get topics that don't belong to any section (standalone topics)
    topics_without_section = topics.filter(section__isnull=True)
    
    # Filter sections to only include those that have visible topics for all users
    visible_sections = []
    for section in sections:
        if request.user.role == 'learner':
            # Check if the section has any non-draft and non-restricted topics
            has_visible_topics = section.topics.exclude(status='draft').exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            ).exists()
        else:
            # For instructors, admins, and superusers, check if section has any topics
            has_visible_topics = section.topics.exists()
        
        if has_visible_topics:
            visible_sections.append(section)
    
    sections = visible_sections
    
    # Get the first topic for the Start/Resume button
    # Find the actual first topic based on course structure
    first_topic = None
    
    # First check if there are topics in sections
    first_section = sections[0] if sections else None
    if first_section:
        # Get the first topic from the first section
        first_topic = topics.filter(section=first_section).order_by('coursetopic__order', 'created_at').first()
    
    # If no topics in sections, get the first standalone topic
    if not first_topic and hasattr(topics_without_section, 'exists'):
        if topics_without_section.exists():
            first_topic = topics_without_section.order_by('coursetopic__order', 'created_at').first()
    elif not first_topic and topics_without_section:
        # If topics_without_section is a list
        if topics_without_section:
            first_topic = topics_without_section[0]
    
    # If still no topic found, fall back to just the first topic overall
    if not first_topic:
        if hasattr(topics, 'first'):
            first_topic = topics.first()
        elif topics:
            first_topic = topics[0]

    # Calculate user's progress
    progress = 0
    is_enrolled = False
    total_topics_count = topics.count()
    completed_topics_count = 0
    
    if request.user.is_authenticated:
        # Check if the user is enrolled
        is_enrolled = course.enrolled_users.filter(id=request.user.id).exists()
        
        # Get all existing progress records for this user and these topics
        existing_progress = TopicProgress.objects.filter(
            user=request.user,
            topic__in=topics
        )
        
        # Count completed topics directly from the database
        completed_topics_count = existing_progress.filter(completed=True).count()
        
        # Calculate overall progress percentage
        if total_topics_count > 0:
            progress = round((completed_topics_count / total_topics_count) * 100)
        else:
            progress = 0
        
        # Initialize enrollment and progress tracking
        if is_enrolled:
            # Get or create enrollment
            enrollment, created = CourseEnrollment.objects.get_or_create(
                user=request.user, 
                course=course,
                defaults={'completed': False}
            )
            
            # Create a dict of topic ID to progress for quick lookup
            progress_by_topic_id = {p.topic_id: p for p in existing_progress}
            
            # Create missing progress records
            for topic in topics:
                if topic.id not in progress_by_topic_id:
                    try:
                        topic_progress, created = EnrollmentService.create_or_update_topic_progress(
                            user=request.user,
                            topic=topic,
                            completed=False
                        )
                    except Exception as e:
                        logger.error(f"Error creating progress record for topic {topic.id}: {str(e)}")
            
            # Update enrollment progress safely
            if enrollment:
                progress_updated = EnrollmentService.update_enrollment_progress(
                    enrollment, progress
                )
                
                if not progress_updated:
                    logger.warning(f"Failed to update enrollment progress for {request.user.username}")
                
                # Get fresh enrollment data after atomic update
                enrollment.refresh_from_db()
                enrollment_progress = enrollment.progress if hasattr(enrollment, 'progress') else progress
                
                # Log any significant discrepancies for investigation
                if abs(progress - enrollment_progress) > 5:  # Reduced tolerance for logging
                    logger.warning(f"Progress calculation discrepancy: calculated={progress}, enrollment={enrollment_progress} for user {request.user.username}")
    
    # Determine permissions using proper permission functions
    can_edit = check_course_edit_permission(request.user, course)
    
    # For delete permissions, use the context function which includes group-based checks
    course_context = get_course_context(request, request.user, course)
    can_delete = course_context['can_delete']

    # Check for user certificate if 100% progress
    user_certificate = None
    if progress == 100 and course.issue_certificate:
        try:
            from certificates.models import IssuedCertificate
            user_certificate = IssuedCertificate.objects.filter(
                recipient=request.user,
                course_name=course.title
            ).order_by('-issue_date').first()
        except Exception:
            pass

    # Check survey-related context
    has_survey = course.survey is not None
    user_has_submitted_survey = False
    user_can_submit_survey = False
    user_review = None
    
    if course.survey and request.user.is_authenticated:
        from course_reviews.models import CourseReview, SurveyResponse
        from courses.models import CourseEnrollment
        
        # Check if user has completed the course
        try:
            enrollment = CourseEnrollment.objects.get(user=request.user, course=course)
            if enrollment.completed:
                user_can_submit_survey = True
                
                # Check if user has already submitted survey
                existing_review = CourseReview.objects.filter(
                    user=request.user,
                    course=course,
                    survey=course.survey
                ).first()
                
                if existing_review:
                    user_has_submitted_survey = True
                    user_review = existing_review
        except CourseEnrollment.DoesNotExist:
            pass

    # Get course reviews for instructors/admins
    course_reviews = []
    if user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'] and has_survey:
        from course_reviews.models import CourseReview
        course_reviews = CourseReview.objects.filter(
            course=course,
            is_published=True
        ).select_related('user', 'survey').order_by('-submitted_at')

    context = {
        'course': course,
        'sections': sections,
        'topics': topics,
        'topics_without_section': topics_without_section,
        'first_topic': first_topic,
        'progress': progress,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'has_group_access': course.accessible_groups.filter(
            memberships__user=request.user,
            memberships__is_active=True,
            memberships__custom_role__can_view=True
        ).exists(),
        'is_enrolled': course.enrolled_users.filter(id=request.user.id).exists(),
        'breadcrumbs': breadcrumbs,
        'user_certificate': user_certificate,
        'completed_topics_count': completed_topics_count,
        'total_topics_count': total_topics_count,
        'prerequisite_check': prerequisite_check,
        # Survey-related context
        'has_survey': has_survey,
        'survey': course.survey,
        'user_has_submitted_survey': user_has_submitted_survey,
        'user_can_submit_survey': user_can_submit_survey,
        'user_review': user_review,
        'course_reviews': course_reviews
    }

    return render(request, 'courses/course_details.html', context)

@login_required
@require_capability('view_courses')
def course_view(request, course_id):
    """View-only display of course content with group access."""
    clear_navigation_history(request)
    request.session['viewing_mode'] = 'view'

    course = get_object_or_404(Course, id=course_id)
    
    # Log course access attempt
    logger.info(f"Course view access attempt by {request.user.username} (role: {request.user.role}) for course {course_id}: {course.title}")

    # Check access to course
    if not hasattr(request.user, 'role'):
        return redirect('account_login')

    if not check_course_permission(request.user, course):
        messages.error(request, "You don't have permission to access this course.")
        logger.warning(f"Access denied: User {request.user.username} (role: {request.user.role}) attempted to view course {course.id}")
        return redirect('users:role_based_redirect')
    else:
        # Log successful access
        if request.user.role == 'instructor' and course.instructor != request.user:
            # Check if this is an invited instructor
            invited_access = course.accessible_groups.filter(
                memberships__user=request.user,
                memberships__is_active=True
            ).exists()
            if invited_access:
                logger.info(f"Invited instructor {request.user.username} accessing course {course.id} in view mode")
    
    # Check prerequisites for learners and instructors who aren't managing the course
    prerequisite_check = {'can_access': True, 'missing_prerequisites': [], 'completed_prerequisites': []}
    if request.user.role == 'learner' or (request.user.role == 'instructor' and not check_instructor_management_access(request.user, course)):
        from .utils import check_prerequisites_completion
        prerequisite_check = check_prerequisites_completion(request.user, course)
    
    # Import enrollment service for safe operations
    from core.utils.enrollment import EnrollmentService
        
        # If user doesn't have access due to missing prerequisites, we'll show the modal
        # but still let them view the course details (not the content)

    # Get course sections and topics
    sections = Section.objects.filter(course=course).order_by('order')
    
    # Filter topics based on user role
    if request.user.role == 'learner':
        # For learners, exclude draft topics and restricted topics
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).exclude(
            status='draft'  # Hide draft topics from learners
        ).exclude(
            restrict_to_learners=True,
            restricted_learners=request.user  # Hide topics where learner is restricted
        ).order_by('order', 'coursetopic__order', 'created_at')
        
        # Filter sections to only include those that have visible topics for learners
        visible_sections = []
        for section in sections:
            # Check if the section has any non-draft and non-restricted topics
            has_visible_topics = section.topics.exclude(status='draft').exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            ).exists()
            if has_visible_topics:
                visible_sections.append(section)
        
        sections = visible_sections
    else:
        # Admin, instructors and other roles see all topics
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).order_by('order', 'coursetopic__order', 'created_at')
    
    topics_without_section = topics.filter(section__isnull=True)
    
    # Get the first topic for the Start/Resume button
    first_topic = None
    
    # First check if there are topics in sections
    first_section = sections[0] if sections else None
    if first_section:
        # Get the first topic from the first section
        first_topic = topics.filter(section=first_section).order_by('coursetopic__order', 'created_at').first()
    
    # If no topics in sections, get the first standalone topic
    if not first_topic and topics_without_section.exists():
        first_topic = topics_without_section.order_by('coursetopic__order', 'created_at').first()
    
    # If still no topic found, fall back to just the first topic overall
    if not first_topic:
        first_topic = topics.first()

    # Create breadcrumbs for the course view page
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Courses', 'icon': 'fa-book'},
        {'label': course.title}
    ]
    
    # Calculate user's progress
    progress = 0
    is_enrolled = False
    total_topics_count = topics.count()
    completed_topics_count = 0
    
    if request.user.is_authenticated:
        # Check if the user is enrolled
        is_enrolled = course.enrolled_users.filter(id=request.user.id).exists()
        
        # Get all existing progress records for this user and these topics
        existing_progress = TopicProgress.objects.filter(
            user=request.user,
            topic__in=topics
        )
        
        # Count completed topics directly from the database
        completed_topics_count = existing_progress.filter(completed=True).count()
        
        # Calculate overall progress percentage
        if total_topics_count > 0:
            progress = round((completed_topics_count / total_topics_count) * 100)
        else:
            progress = 0
        
        # Initialize enrollment and progress tracking
        if is_enrolled:
            # Get or create enrollment
            enrollment, created = CourseEnrollment.objects.get_or_create(
                user=request.user, 
                course=course,
                defaults={'completed': False}
            )
            
            # Create a dict of topic ID to progress for quick lookup
            progress_by_topic_id = {p.topic_id: p for p in existing_progress}
            
            # Create missing progress records
            for topic in topics:
                if topic.id not in progress_by_topic_id:
                    try:
                        topic_progress, created = EnrollmentService.create_or_update_topic_progress(
                            user=request.user,
                            topic=topic,
                            completed=False
                        )
                    except Exception as e:
                        logger.error(f"Error creating progress record for topic {topic.id}: {str(e)}")
            
            # Update enrollment progress safely
            if enrollment:
                progress_updated = EnrollmentService.update_enrollment_progress(
                    enrollment, progress
                )
                
                if not progress_updated:
                    logger.warning(f"Failed to update enrollment progress for {request.user.username}")
                
                # Get fresh enrollment data after atomic update
                enrollment.refresh_from_db()
                enrollment_progress = enrollment.progress if hasattr(enrollment, 'progress') else progress
                
                # Log any significant discrepancies for investigation
                if abs(progress - enrollment_progress) > 5:  # Reduced tolerance for logging
                    logger.warning(f"Progress calculation discrepancy: calculated={progress}, enrollment={enrollment_progress} for user {request.user.username}")
    
    # Check for user certificate if 100% progress
    user_certificate = None
    if progress == 100 and course.issue_certificate:
        try:
            from certificates.models import IssuedCertificate
            user_certificate = IssuedCertificate.objects.filter(
                recipient=request.user,
                course_name=course.title
            ).order_by('-issue_date').first()
        except Exception:
            pass

    # Log debug information
    logger.info(f"Course view: User {request.user.username} (role: {request.user.role}) - is_enrolled: {is_enrolled}, progress: {progress}")

    context = {
        'course': course,
        'sections': sections,
        'topics': topics,
        'topics_without_section': topics_without_section,
        'is_view_only': True,
        'first_topic': first_topic,
        'back_url': get_course_context(request, request.user, course)['back_url'],
        'breadcrumbs': breadcrumbs,
        'progress': progress,
        'is_enrolled': is_enrolled,
        'user': request.user,
        'total_topics_count': total_topics_count,
        'completed_topics_count': completed_topics_count,
        'user_certificate': user_certificate,
        'prerequisite_check': prerequisite_check
    }
    
    return render(request, 'courses/course_details.html', context)


@login_required
def debug_course_permissions(request, course_id):
    """Debug view to check course permissions for troubleshooting"""
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    
    user = request.user
    
    debug_info = {
        'user_id': user.id,
        'user_role': user.role,
        'user_branch': str(user.branch) if user.branch else None,
        'user_is_superuser': user.is_superuser,
        'course_id': course.id,
        'course_instructor': str(course.instructor) if course.instructor else None,
        'course_branch': str(course.branch) if course.branch else None,
        'course_business': str(course.branch.business) if course.branch and hasattr(course.branch, 'business') else None,
        'permissions': {
            'can_edit': check_course_edit_permission(user, course),
            'can_modify_model': course.user_can_modify(user),
            'can_delete': False  # Will be calculated separately
        }
    }
    
    # Check business assignments for superadmin
    if user.role == 'superadmin' and course.branch and hasattr(course.branch, 'business'):
        debug_info['business_assignments'] = list(user.business_assignments.filter(
            business=course.branch.business, 
            is_active=True
        ).values('business__name', 'is_active'))
    
    # Check group access for instructors
    if user.role == 'instructor':
        debug_info['group_access'] = list(course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__can_edit=True
        ).values('name', 'memberships__custom_role__can_edit'))
    
    # Calculate can_delete permission
    can_delete = (
        user.is_superuser or 
        user.role == 'globaladmin' or
        (user.role == 'superadmin' and hasattr(course, 'branch') and course.branch and
         user.business_assignments.filter(business=course.branch.business, is_active=True).exists()) or
        (user.role == 'admin' and course.branch == user.branch) or
        (user.role == 'instructor' and course.instructor == user)
    )
    
    # For group-assigned instructors, allow delete only if they have admin-level permissions in the group
    if not can_delete and user.role == 'instructor':
        from groups.models import CourseGroupAccess
        can_delete = CourseGroupAccess.objects.filter(
            course=course,
            group__memberships__user=user,
            group__memberships__is_active=True,
            group__memberships__custom_role__can_manage_content=True,
            can_modify=True
        ).exists()
    
    debug_info['permissions']['can_delete'] = can_delete
    
    return JsonResponse(debug_info)

# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
@login_required(login_url='/login/')
def course_edit(request, course_id):
    """Edit an existing course."""

    # Get the course with robust error handling
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        logger.info(f"Course edit attempted for non-existent course ID: {course_id} by user {request.user.username} - redirecting to create new course")
        messages.info(request, f"Course with ID {course_id} does not exist. Creating a new course...")
        # Create a new course with the requested ID instead of redirecting
        try:
            course = Course(
                id=course_id,  # Use the requested course ID
                title=f"New Course {course_id}",
                description="",
                course_code=f"COURSE{course_id:04d}",
                course_outcomes="",
                is_active=True,
                is_temporary=False,  # Set is_temporary field
                instructor=request.user if request.user.role == 'instructor' else None,
                branch=request.user.branch if request.user.role in ['instructor', 'admin', 'superadmin'] else None
            )
            course.save()
            
            # Create default section
            Section.objects.create(
                name="Section 1",
                description="",
                course=course,
                order=1
            )
            
            logger.info(f"Created new course with ID {course_id} for user {request.user.username}")
            messages.success(request, f"Created new course with ID {course_id}. You can now edit it.")
            
        except Exception as create_error:
            logger.error(f"Failed to create course with ID {course_id}: {str(create_error)}")
            messages.error(request, f"Could not create course with ID {course_id}. Please try again.")
            return redirect('courses:course_list')
    except Exception as e:
        logger.error(f"Database error when accessing course ID {course_id}: {str(e)}")
        messages.error(request, "There was an error accessing the course. Please try again.")
        return redirect('courses:course_list')
    
    # Check if the user is a learner who is enrolled in the course
    is_enrolled_learner = False
    if request.user.role == 'learner' and course.enrolled_users.filter(id=request.user.id).exists():
        is_enrolled_learner = True
        logger.info(f"User {request.user.id} is an enrolled learner in course {course_id}")
    
    # Only explicitly deny access to learners who are not enrolled
    if request.user.role == 'learner' and not is_enrolled_learner:
        messages.error(request, "Learners cannot edit courses they are not enrolled in.")
        return redirect('courses:course_details', course_id=course_id)
    
    # Check for course edit permission
    # RBAC v0.1 Compliant: Use proper permission check
    logger.info(f"User {request.user.id} ({request.user.role}) attempting to edit course {course_id}")
    logger.info(f"Course instructor: {course.instructor}")
    logger.info(f"Course branch: {course.branch}")
    logger.info(f"User branch: {request.user.branch}")
    
    if not check_course_edit_permission(request.user, course):
        logger.warning(f"Permission denied for user {request.user.id} to edit course {course_id}")
        messages.error(request, "You don't have permission to edit this course.")
        return redirect('courses:course_details', course_id=course_id)
    
    logger.info(f"Permission granted for user {request.user.id} to edit course {course_id}")
    
    if request.method == 'POST':
        # Log all form data for debugging
        logger.info("Form data received:")
        for key, value in request.POST.items():
            logger.info(f"{key}: {value}")
        
        logger.info(f"Processing course edit POST: {request.POST.keys()}")
        logger.info(f"Description present in form: {'description' in request.POST}")
        if 'description' in request.POST:
            logger.info(f"Description length: {len(request.POST['description'])}")
        logger.info(f"Files in request: {list(request.FILES.keys()) if request.FILES else 'None'}")
        
        # Process files directly before form validation to ensure structured storage
        image_field_updated = False
        video_field_updated = False
        
        # Handle image removal
        logger.info(f"'remove_image' value in POST: {request.POST.get('remove_image')}")
        if request.POST.get('remove_image') == 'true':
            logger.info("Remove image condition met")
            if course.course_image:
                try:
                    # Delete the file from database
                    logger.info(f"Attempting to delete course image: {course.course_image}")
                    course.course_image.delete(save=False)
                    course.course_image = None
                    image_field_updated = True
                    
                    logger.info("Course image removed successfully")
                except Exception as e:
                    logger.error(f"Error removing course image: {str(e)}")
            else:
                logger.info("No course image to remove")
        else:
            logger.info("Remove image condition NOT met")
        
        # Handle video removal
        logger.info(f"'remove_video' value in POST: {request.POST.get('remove_video')}")
        if request.POST.get('remove_video') == 'true':
            logger.info("Remove video condition met")
            if course.course_video:
                try:
                    # Delete the file from database
                    logger.info(f"Attempting to delete course video: {course.course_video}")
                    course.course_video.delete(save=False)
                    course.course_video = None
                    video_field_updated = True
                    
                    logger.info("Course video removed successfully")
                except Exception as e:
                    logger.error(f"Error removing course video: {str(e)}")
            else:
                logger.info("No course video to remove")
        else:
            logger.info("Remove video condition NOT met")
        
        # Handle image upload
        if 'course_image' in request.FILES:
            image_file = request.FILES['course_image']
            logger.info(f"Handling image upload: {image_file.name}")
            
            # Use Django's default storage (works with both local and S3)
            from django.core.files.storage import default_storage
            
            # Generate filename with timestamp to avoid collisions
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            image_filename = f"{timestamp}_{unique_id}_{image_file.name}"
            image_relative_path = f"course_images/{course.id}/{image_filename}"
            
            # Save file using Django's storage backend (works with S3 and local)
            saved_path = default_storage.save(image_relative_path, image_file)
            
            # Update course model with the saved path
            course.course_image = saved_path
            image_field_updated = True
            logger.info(f"Saved image to: {saved_path}")
            
            # Register file in media database for tracking
            try:
                from lms_media.utils import register_media_file
                register_media_file(
                    file_path=image_relative_path,
                    uploaded_by=request.user,
                    source_type='course_content',
                    source_model='Course',
                    source_object_id=course.id,
                    course=course,
                    filename=image_file.name,
                    description=f'Course featured image for: {course.title}'
                )
            except Exception as e:
                logger.error(f"Error registering course image in media database: {str(e)}")
        
        # Handle video upload
        if 'course_video' in request.FILES:
            video_file = request.FILES['course_video']
            logger.info(f"Handling video upload: {video_file.name}")
            
            # Create directory structure if needed
            import os
            from django.conf import settings
            
            # Use Django's default storage for video uploads
            from django.core.files.storage import default_storage
            
            # Generate filename with timestamp to avoid collisions
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            video_filename = f"{timestamp}_{unique_id}_{video_file.name}"
            video_relative_path = f"course_videos/{course.id}/{video_filename}"
            
            # Save file using default storage
            saved_path = default_storage.save(video_relative_path, video_file)
            
            # Update course model directly
            course.course_video = video_relative_path
            video_field_updated = True
            logger.info(f"Saved video to: {video_relative_path}")
            
            # Register file in media database for tracking
            try:
                from lms_media.utils import register_media_file
                register_media_file(
                    file_path=video_relative_path,
                    uploaded_by=request.user,
                    source_type='course_content',
                    source_model='Course',
                    source_object_id=course.id,
                    course=course,
                    filename=video_file.name,
                    description=f'Course introduction video for: {course.title}'
                )
            except Exception as e:
                logger.error(f"Error registering course video in media database: {str(e)}")
        
        # Now process form - exclude the file fields we just handled directly
        form = CourseForm(
            request.POST, 
            {k: v for k, v in request.FILES.items() if k not in ['course_image', 'course_video']} if request.FILES else None,
            instance=course, 
            user=request.user
        )
        
        if form.is_valid():
            try:
                # Save form but don't overwrite the files we handled manually
                updated_course = form.save(commit=False)
                
                # Log description content for debugging
                logger.info(f"Description from form: {form.cleaned_data.get('description', '')[:100]}...")
                
                # Ensure title is properly set
                title = request.POST.get('title', '').strip()
                if title:
                    updated_course.title = title
                    logger.info(f"Setting course title to: '{title}'")
                else:
                    logger.warning(f"Empty title submitted for course {course.id}, keeping existing title: '{course.title}'")
                    
                # Restore manually updated fields
                if image_field_updated:
                    updated_course.course_image = course.course_image
                if video_field_updated:
                    updated_course.course_video = course.course_video
                    
                # Handle course status
                course_status = request.POST.get('course_status')
                if course_status:
                    updated_course.is_active = (course_status == 'published')
                    # Make sure visible courses are in the catalog
                    if updated_course.is_active:
                        updated_course.catalog_visibility = 'visible'
                        
                # Set superadmin flag if needed for validation bypass
                if request.user.role == 'superadmin':
                    updated_course._created_by_superadmin = True
                    
                # Save the course with error handling
                try:
                    updated_course.save()
                    form.save_m2m()
                    logger.info(f"Course {updated_course.id} saved successfully")
                except Exception as save_error:
                    logger.error(f"Error saving course: {str(save_error)}")
                    messages.error(request, f"Error saving course: {str(save_error)}")
                    # Handle AJAX requests with save errors
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': f'Error saving course: {str(save_error)}'
                        }, status=400)
                    # Re-render form with error
                    form = CourseForm(instance=course, user=request.user)
                    return render(request, 'courses/edit_course.html', {
                        'form': form,
                        'course': course,
                        'sections': Section.objects.filter(course=course).order_by('order').prefetch_related(
                            Prefetch('topics', 
                                     queryset=Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at'))
                        ),
                        'topics': Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at'),
                        'topics_without_section': Topic.objects.filter(coursetopic__course=course, section__isnull=True),
                        'categories': get_user_accessible_categories(request.user),
                        'breadcrumbs': [
                            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                            {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
                            {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
                            {'label': f"Edit {course.title}", 'icon': 'fa-edit'}
                        ],
                        'order_management_enabled': False
                    })
                
                logger.info(f"After save - description length: {len(str(updated_course.description))}")
                logger.info(f"After save - course_image: {updated_course.course_image}")
                logger.info(f"After save - course_video: {updated_course.course_video}")
                
                messages.success(request, f"Course '{updated_course.title}' updated successfully")
                
                # Handle AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f"Course '{updated_course.title}' updated successfully",
                        'redirect_url': reverse('courses:course_details', kwargs={'course_id': updated_course.id})
                    })
                
                return redirect('courses:course_edit', updated_course.id)
            except Exception as e:
                logger.error(f"Unexpected error during course update: {str(e)}")
                messages.error(request, f"An unexpected error occurred: {str(e)}")
                
                # Handle AJAX requests with unexpected errors
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': f'An unexpected error occurred: {str(e)}'
                    }, status=500)
        else:
            logger.error(f"Form validation errors: {form.errors}")
            logger.error(f"Form non-field errors: {form.non_field_errors()}")
            
            # Show specific error messages
            error_messages = []
            for field, errors in form.errors.items():
                if field == '__all__':
                    error_messages.extend(errors)
                else:
                    for error in errors:
                        error_messages.append(f"{field}: {error}")
            
            if error_messages:
                messages.error(request, "Please correct the following errors: " + "; ".join(error_messages))
            else:
                messages.error(request, "Please correct the errors below.")
            
            # Handle AJAX requests with errors
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Please correct the errors below.',
                    'errors': form.errors,
                    'error_messages': error_messages
                }, status=400)
    else:
        form = CourseForm(instance=course, user=request.user)
    
    # Get categories accessible to the current user based on their role
    categories = get_user_accessible_categories(request.user)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'label': f"Edit {course.title}", 'icon': 'fa-edit'}
    ]
    
    # Get all sections for this course, ordered by their order field
    # Prefetch topics to avoid N+1 queries and ensure consistent ordering
    sections = Section.objects.filter(course=course).order_by('order').prefetch_related(
        Prefetch('topics', 
                 queryset=Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at'))
    )
    
    # Get all topics for this course - prioritize Topic.order over CourseTopic.order
    # Now using Topic.order as primary sorting and coursetopic__order as secondary
    topics = Topic.objects.filter(coursetopic__course=course).order_by('order', 'coursetopic__order', 'created_at')
    
    # Get topics that don't belong to any section
    topics_without_section = topics.filter(section__isnull=True)
    
    # Log debug info
    logger.debug(f"Total topics: {topics.count()}")
    logger.debug(f"Topics without section: {topics_without_section.count()}")
    
    # Check if order management is enabled for the course's branch
    order_management_enabled = False
    try:
        # Import at module level would be better, but this prevents circular imports
        GlobalAdminSettings = apps.get_model('account_settings', 'GlobalAdminSettings')
        global_settings = GlobalAdminSettings.get_settings()
        global_order_enabled = global_settings.order_management_enabled if global_settings else False
        
        # Check if order management is enabled for this specific branch
        branch_order_enabled = False
        if course.branch:
            branch_order_enabled = getattr(course.branch, 'order_management_enabled', False)
        
        # Order management is enabled only if both global and branch settings are enabled
        order_management_enabled = global_order_enabled and branch_order_enabled
        
    except Exception as e:
        logger.error(f"Error checking order management settings: {str(e)}")
        order_management_enabled = False
    
    # Define action for template context
    action = 'edit'
    
    context = {
        'form': form,
        'course': course,
        'action': action,
        'categories': categories,
        'breadcrumbs': breadcrumbs,
        'topics': topics,
        'topics_without_section': topics_without_section,
        'sections': sections,
        'order_management_enabled': order_management_enabled
    }
    
    # Template rendering with error handling
    try:
        return render(request, 'courses/edit_course.html', context)
    except Exception as template_error:
        # Comprehensive error handling for template rendering
        import traceback
        error_message = str(template_error)
        error_trace = traceback.format_exc()
        
        logger.error(f"Template rendering error in course_edit for course_id {course_id}: {error_message}")
        logger.error(f"Full traceback: {error_trace}")
        
        # Log request details for debugging
        logger.error(f"User: {request.user.username if request.user.is_authenticated else 'Anonymous'}")
        logger.error(f"Method: {request.method}")
        logger.error(f"Path: {request.path}")
        
        # Return user-friendly error page instead of 500
        messages.error(request, "An unexpected error occurred while loading the course editor. Please try again or contact support.")
        
        # Redirect to course list instead of crashing
        try:
            return redirect('courses:course_list')
        except:
            # If even redirect fails, return basic error response
            return HttpResponseServerError("An error occurred. Please contact support.")

@login_required
def course_delete(request, course_id):
    """Delete a course."""
    course = get_object_or_404(Course, id=course_id)
    logger = logging.getLogger(__name__)
    
    # Check permissions - RBAC v0.1 Compliant
    can_delete = (
        request.user.is_superuser or 
        request.user.role == 'globaladmin' or
        (request.user.role == 'superadmin' and hasattr(course, 'branch') and course.branch and
         request.user.business_assignments.filter(business=course.branch.business, is_active=True).exists()) or
        (request.user.role == 'admin' and course.branch == request.user.branch) or
        (request.user.role == 'instructor' and course.instructor == request.user)
    )
    
    if not can_delete:
        return HttpResponseForbidden("You don't have permission to delete this course.")

    if request.method == 'POST':
        try:
            # Log the start of deletion process
            logger.info(f"Starting deletion process for course {course_id}")
            
            # Delete course image if it exists
            if course.course_image:
                try:
                    logger.info(f"Deleting course image: {course.course_image.name}")
                    course.course_image.delete(save=False)
                    # Delete the directory if it's empty (handle cloud storage)
                    try:
                        image_dir = os.path.dirname(course.course_image.path)
                        if os.path.exists(image_dir) and not os.listdir(image_dir):
                            os.rmdir(image_dir)
                            logger.info(f"Deleted empty image directory: {image_dir}")
                    except NotImplementedError:
                        # Cloud storage doesn't support absolute paths, skip directory cleanup
                        logger.info("Skipping directory cleanup for cloud storage")
                except Exception as e:
                    logger.error(f"Error deleting course image: {str(e)}")

            # Delete course video if it exists
            if course.course_video:
                try:
                    logger.info(f"Deleting course video: {course.course_video.name}")
                    course.course_video.delete(save=False)
                    # Delete the directory if it's empty (handle cloud storage)
                    try:
                        video_dir = os.path.dirname(course.course_video.path)
                        if os.path.exists(video_dir) and not os.listdir(video_dir):
                            os.rmdir(video_dir)
                            logger.info(f"Deleted empty video directory: {video_dir}")
                    except NotImplementedError:
                        # Cloud storage doesn't support absolute paths, skip directory cleanup
                        logger.info("Skipping directory cleanup for cloud storage")
                except Exception as e:
                    logger.error(f"Error deleting course video: {str(e)}")

            # Delete course content directory - S3 permission-safe approach
            content_dir = f"course_content/{course.id}/"
            try:
                logger.info(f"Attempting to delete course content directory: {content_dir}")
                # Try to list and delete files without checking existence first
                try:
                    files, dirs = default_storage.listdir(content_dir)
                    files_to_delete = [f"{content_dir}{file}" for file in files]
                    
                    for file_path in files_to_delete:
                        try:
                            default_storage.delete(file_path)
                            logger.info(f"Deleted file: {file_path}")
                        except Exception as file_error:
                            # Handle individual file deletion errors gracefully
                            if "403" in str(file_error) or "Forbidden" in str(file_error):
                                logger.warning(f"S3 permission denied for file {file_path}: {file_error}")
                            else:
                                logger.error(f"Error deleting file {file_path}: {file_error}")
                    
                    logger.info(f"Successfully processed course content directory")
                except Exception as list_error:
                    # If listing fails due to permissions or non-existence, that's OK
                    if "403" in str(list_error) or "Forbidden" in str(list_error):
                        logger.warning(f"S3 permission denied for listing {content_dir}: {list_error}")
                    elif "NoSuchKey" in str(list_error) or "not found" in str(list_error):
                        logger.info(f"Course content directory {content_dir} does not exist - skipping")
                    else:
                        logger.error(f"Error listing course content directory {content_dir}: {list_error}")
                        
            except Exception as e:
                logger.error(f"Error processing course content directory: {str(e)}")

            # Delete any media folders related to this course - S3 permission-safe approach
            # Avoid exists() checks that trigger HeadObject operations causing 403 errors
            media_folders = [
                f"course_images/{course.id}",
                f"course_videos/{course.id}",
                f"courses/{course.id}",
                f"editor_uploads/courses/{course.id}"
            ]
            
            for folder in media_folders:
                try:
                    logger.info(f"Attempting to delete course media folder: {folder}")
                    # Try to list and delete files without checking folder existence first
                    try:
                        files, dirs = default_storage.listdir(folder)
                        for file in files:
                            file_path = f"{folder}/{file}"
                            try:
                                default_storage.delete(file_path)
                                logger.info(f"Deleted file: {file_path}")
                            except Exception as file_error:
                                # Handle individual file deletion errors gracefully
                                if "403" in str(file_error) or "Forbidden" in str(file_error):
                                    logger.warning(f"S3 permission denied for file {file_path}: {file_error}")
                                elif "NoSuchKey" in str(file_error) or "not found" in str(file_error):
                                    logger.info(f"File {file_path} does not exist - skipping")
                                else:
                                    logger.error(f"Error deleting file {file_path}: {file_error}")
                                    
                        # Also try to delete any subdirectories
                        for subdir in dirs:
                            subdir_path = f"{folder}/{subdir}"
                            try:
                                # Recursively process subdirectory
                                subfiles, subdirs = default_storage.listdir(subdir_path)
                                for subfile in subfiles:
                                    subfile_path = f"{subdir_path}/{subfile}"
                                    try:
                                        default_storage.delete(subfile_path)
                                        logger.info(f"Deleted subfile: {subfile_path}")
                                    except Exception as subfile_error:
                                        if "403" in str(subfile_error) or "Forbidden" in str(subfile_error):
                                            logger.warning(f"S3 permission denied for subfile {subfile_path}: {subfile_error}")
                                        else:
                                            logger.error(f"Error deleting subfile {subfile_path}: {subfile_error}")
                            except Exception as subdir_error:
                                if "403" not in str(subdir_error) and "Forbidden" not in str(subdir_error):
                                    logger.warning(f"Could not process subdirectory {subdir_path}: {subdir_error}")
                        
                        logger.info(f"Successfully processed course media folder: {folder}")
                        
                    except Exception as list_error:
                        # If listing fails due to permissions or non-existence, that's OK
                        if "403" in str(list_error) or "Forbidden" in str(list_error):
                            logger.warning(f"S3 permission denied for listing {folder}: {list_error}")
                        elif "NoSuchKey" in str(list_error) or "not found" in str(list_error):
                            logger.info(f"Course media folder {folder} does not exist - skipping")
                        else:
                            logger.error(f"Error listing course media folder {folder}: {list_error}")
                            
                except Exception as e:
                    logger.error(f"Error processing course media folder {folder}: {str(e)}")

            # Get all topics associated with this course and delete them
            course_topics = CourseTopic.objects.filter(course=course)
            topics_to_delete = []
            
            # Collect all topics that belong exclusively to this course
            for course_topic in course_topics:
                topic = course_topic.topic
                # Check if the topic is used in other courses
                if topic.coursetopic_set.count() <= 1:
                    topics_to_delete.append(topic.id)
            
            # Log the number of topics to be deleted
            logger.info(f"Deleting {len(topics_to_delete)} topics associated exclusively with course {course_id}")
            
            # Delete the topics
            for topic_id in topics_to_delete:
                try:
                    topic = Topic.objects.get(id=topic_id)
                    logger.info(f"Deleting topic: {topic.title} (ID: {topic.id})")
                    topic.delete()
                except Exception as e:
                    logger.error(f"Error deleting topic {topic_id}: {str(e)}")

            # Delete the course object
            course.delete()
            logger.info(f"Successfully deleted course {course_id}")
            messages.success(request, 'Course deleted successfully!')
            return redirect('courses:course_list')
            
        except Exception as e:
            logger.error(f"Error during course deletion: {str(e)}")
            messages.error(request, f'Error deleting course: {str(e)}')
            return redirect('courses:course_details', course_id=course.id)

    context = {
        'course': course,
        'back_url': reverse('courses:course_details', kwargs={'course_id': course.id})
    }

    return render(request, 'courses/course_delete_confirm.html', context)

@require_POST

@login_required
def course_enrollment_toggle(request, course_id):
    """Toggle enrollment status for the current user in the specified course"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user has permission to enroll/unenroll
    if not request.user.is_active:
        return JsonResponse({'error': 'Your account is not active'}, status=403)
    
    # Check if user is already enrolled
    enrollment = CourseEnrollment.objects.filter(user=request.user, course=course).first()
    
    if enrollment:
        # Unenroll user
        enrollment.delete()
        return JsonResponse({
            'success': True, 
            'enrolled': False,
            'message': f'You have been unenrolled from {course.title}'
        })
    else:
        # Enroll user
        CourseEnrollment.objects.create(
            user=request.user,
            course=course,
            enrollment_source='self'
        )
        return JsonResponse({
            'success': True, 
            'enrolled': True,
            'message': f'You have been enrolled in {course.title}'
        })

@login_required
@transaction.atomic
def enroll_learner(request, course_id, user_id):
    """Enroll a specific user in a course (admin/instructor function)"""
    from core.utils.enrollment import EnrollmentService
    
    # Ensure the request method is POST
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
    
    course = get_object_or_404(Course, id=course_id)
    user_to_enroll = get_object_or_404(CustomUser, id=user_id)
    
    # Check if the current user has permission to enroll others
    if not (request.user.is_superuser or 
            (request.user.role == 'admin' and course.branch == request.user.branch) or
            (request.user.role == 'instructor' and check_course_edit_permission(request.user, course))):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    from django.core.exceptions import ValidationError
    
    try:
        from groups.models import BranchGroup, GroupMembership, GroupMemberRole, CourseGroupAccess
        
        # Create enrollment using safe service with notification suppression
        enrollment, created, message = EnrollmentService.create_or_get_enrollment(
            user=user_to_enroll,
            course=course,
            source='manual'
        )
        
        # Suppress notifications for manual admin/instructor enrollments
        # to avoid unwanted notifications to users
        if created and user_to_enroll.role != 'learner':
            # For instructors and admins, we don't want to send enrollment notifications
            # as they are being added by other staff members
            pass
        
        # For instructors, just enroll them - no automatic group creation
        # Invited instructors will have edit permissions through role-based capabilities
        # Only primary instructors (course.instructor) have full delete permissions
        
        if created:
            role_info = " with editing permissions" if user_to_enroll.role == 'instructor' else ""
            auto_enrolled_courses = []
            
            # Detect circular dependencies first
            def has_circular_dependency(course_to_check, visited_courses=None, recursion_depth=0):
                """Check for circular dependencies in prerequisite chain"""
                if visited_courses is None:
                    visited_courses = set()
                
                # Prevent infinite recursion
                if recursion_depth > 10:
                    logger.warning(f"Possible circular dependency detected at depth {recursion_depth} for course {course_to_check.id}")
                    return True
                    
                if course_to_check.id in visited_courses:
                    return True
                    
                visited_courses.add(course_to_check.id)
                
                for prereq in course_to_check.prerequisites.all():
                    if has_circular_dependency(prereq, visited_courses.copy(), recursion_depth + 1):
                        return True
                
                return False
            
            # Check for circular dependencies before processing
            if has_circular_dependency(course):
                raise ValidationError(f"Circular dependency detected in prerequisite chain for course {course.title}")
            
            # Auto-enroll in prerequisite courses (courses that are required for this course)
            prerequisite_courses = course.prerequisites.all()
            auto_enrolled_in_prerequisites = []
            
            logger.info(f"Processing {prerequisite_courses.count()} prerequisite courses for {course.title}")
            
            for prereq_course in prerequisite_courses:
                try:
                    # Check if user is already enrolled in the prerequisite course
                    if not CourseEnrollment.objects.filter(user=user_to_enroll, course=prereq_course).exists():
                        # Auto-enroll in the prerequisite course
                        prereq_enrollment = CourseEnrollment.objects.create(
                            user=user_to_enroll,
                            course=prereq_course,
                            enrolled_at=timezone.now(),
                            enrollment_source='auto_prerequisite',
                            source_course=course
                        )
                        auto_enrolled_in_prerequisites.append(prereq_course.title)
                        auto_enrolled_courses.append(prereq_enrollment)
                        logger.info(f"Auto-enrolled user {user_to_enroll.username} in prerequisite course {prereq_course.title}")
                except Exception as prereq_error:
                    logger.error(f"Failed to auto-enroll in prerequisite {prereq_course.title}: {str(prereq_error)}")
                    # Continue with other prerequisites but log the error
                    continue
            
            # Auto-enroll in dependent courses (courses that have this course as a prerequisite) - More conservative
            dependent_courses = Course.objects.filter(prerequisites=course)
            auto_enrolled_in_dependents = []
            
            logger.info(f"Processing {dependent_courses.count()} dependent courses for {course.title}")
            
            for dependent_course in dependent_courses:
                try:
                    # Check if user is already enrolled in the dependent course
                    if not CourseEnrollment.objects.filter(user=user_to_enroll, course=dependent_course).exists():
                        # Check if user has completed all other prerequisites for the dependent course
                        other_prerequisites = dependent_course.prerequisites.exclude(id=course.id)
                        all_prerequisites_met = True
                        
                        for prereq in other_prerequisites:
                            if not CourseEnrollment.objects.filter(user=user_to_enroll, course=prereq).exists():
                                all_prerequisites_met = False
                                break
                        
                        # If all prerequisites are met, auto-enroll in the dependent course
                        if all_prerequisites_met:
                            dependent_enrollment = CourseEnrollment.objects.create(
                                user=user_to_enroll,
                                course=dependent_course,
                                enrolled_at=timezone.now(),
                                enrollment_source='auto_dependent',
                                source_course=course
                            )
                            auto_enrolled_in_dependents.append(dependent_course.title)
                            auto_enrolled_courses.append(dependent_enrollment)
                            logger.info(f"Auto-enrolled user {user_to_enroll.username} in dependent course {dependent_course.title}")
                except Exception as dependent_error:
                    logger.error(f"Failed to auto-enroll in dependent {dependent_course.title}: {str(dependent_error)}")
                    # Continue with other dependents but log the error
                    continue
            
            message = f'{user_to_enroll.get_full_name()} has been enrolled in {course.title}{role_info}'
            
            # Add messages for auto-enrollments
            auto_enrollment_messages = []
            if auto_enrolled_in_prerequisites:
                auto_enrollment_messages.append(f'prerequisite courses: {", ".join(auto_enrolled_in_prerequisites)}')
            if auto_enrolled_in_dependents:
                auto_enrollment_messages.append(f'dependent courses: {", ".join(auto_enrolled_in_dependents)}')
            
            if auto_enrollment_messages:
                message += f' and automatically enrolled in {" and ".join(auto_enrollment_messages)}'
            
            return JsonResponse({
                'success': True,
                'message': message,
                'auto_enrolled_count': len(auto_enrolled_courses)
            })
        else:
            return JsonResponse({
                'success': True,
                'message': f'{user_to_enroll.get_full_name()} was already enrolled in {course.title}'
            })
                
    except ValidationError as ve:
        logger.error(f"Validation error in enroll_learner for user {user_id} in course {course_id}: {str(ve)}")
        return JsonResponse({
            'success': False,
            'message': f'Enrollment validation error: {str(ve)}'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in enroll_learner for user {user_id} in course {course_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error enrolling user: {str(e)}'
        }, status=500)

@login_required
@transaction.atomic
def unenroll_learner(request, course_id, user_id):
    """Unenroll a specific learner from a course (admin/instructor function)"""
    course = get_object_or_404(Course, id=course_id)
    user_to_unenroll = get_object_or_404(CustomUser, id=user_id)
    
    # Check if the current user has permission to unenroll others
    if not (request.user.is_superuser or 
            (request.user.role == 'admin' and course.branch == request.user.branch) or
            (request.user.role == 'instructor' and course.instructor == request.user)):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Check if user is enrolled and unenroll them
    enrollment = CourseEnrollment.objects.filter(user=user_to_unenroll, course=course).first()
    
    if enrollment:
        enrollment.delete()
        return JsonResponse({
            'success': True,
            'message': f'{user_to_unenroll.get_full_name()} has been unenrolled from {course.title}'
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f'{user_to_unenroll.get_full_name()} is not enrolled in {course.title}'
        })

@login_required
def topic_discussion_view(request, topic_id):
    """View for displaying a topic's discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check permission
    if not check_course_permission(request.user, course):
        messages.error(request, "You don't have permission to access this discussion.")
        return redirect('users:role_based_redirect')
    
    # Check if topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Redirect to the discussion app's view
    try:
        return redirect('discussions:discussion_detail', discussion_id=topic.discussion.id)
    except NoReverseMatch:
        # Fallback if discussions app URL is not available
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def mark_topic_complete(request, topic_id):
    """Mark a topic as complete for the current user"""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check course access permission
    if not check_course_permission(request.user, course):
        messages.error(request, "You don't have permission to access this course.")
        return redirect('users:role_based_redirect')
    
    # Get or create progress record
    progress, created = TopicProgress.objects.get_or_create(
        user=request.user,
        topic=topic
    )
    
    # Always initialize progress_data to ensure consistent structure
    progress.init_progress_data()
    
    # Determine if the request body is JSON
    is_json_request = request.content_type == 'application/json'
    
    # Parse JSON data if it's a JSON request
    if is_json_request:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    
    # Determine completion method based on request headers
    is_auto_complete = request.headers.get('X-Auto-Complete') == 'true' or data.get('auto_complete') == True
    completion_method = 'auto' if is_auto_complete else 'manual'
    
    # For video or audio, set progress to 100%
    if topic.content_type in ['Video', 'EmbedVideo', 'Audio']:
        progress.progress_data['progress'] = 100.0
        progress.progress_data['completed'] = True
        progress.progress_data['completed_at'] = timezone.now().isoformat()
    
    # CRITICAL FIX: For SCORM content, explicitly sync score before marking complete
    # This ensures the gradebook reflects the learner's score
    if topic.content_type == 'SCORM':
        score_synced = progress.sync_scorm_score()
        if score_synced:
            logger.info(f"✅ SCORM Score synced for topic {topic_id} before marking complete (score: {progress.last_score})")
        else:
            logger.warning(f"⚠️  No SCORM score found to sync for topic {topic_id}")
    
    # Use the mark_complete method instead of manually setting fields
    # This ensures all necessary fields and completion_data are updated
    progress.mark_complete(completion_method)
    
    # Log the completion for debugging
    logger.info(f"Topic '{topic.title}' (ID: {topic_id}) marked as complete by user {request.user.username}")
    logger.info(f"Completion method: {completion_method}, Manually completed: {progress.manually_completed}")
    
    # Use the centralized course completion check from TopicProgress model
    # This ensures consistent logic with completion percentage and certificate generation
    progress._check_course_completion()
    
    # Check if course was just completed and sync enrollment progress
    try:
        enrollment = CourseEnrollment.objects.get(
            user=request.user,
            course=course
        )
        
        # SYNC ENROLLMENT PROGRESS: Calculate and update enrollment progress
        from core.utils.enrollment import EnrollmentService
        
        # Get all topics for accurate progress calculation
        if request.user.role == 'learner':
            all_course_topics = Topic.objects.filter(
                coursetopic__course=course
            ).exclude(status='draft').exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            )
        else:
            all_course_topics = Topic.objects.filter(coursetopic__course=course)
        
        total_topics = all_course_topics.count()
        completed_count = TopicProgress.objects.filter(
            user=request.user,
            topic__in=all_course_topics,
            completed=True
        ).count()
        
        # Calculate progress percentage
        calculated_progress = round((completed_count / total_topics) * 100) if total_topics > 0 else 0
        
        # Update enrollment progress
        EnrollmentService.update_enrollment_progress(enrollment, calculated_progress)
        enrollment.refresh_from_db()
        
        if enrollment.completed:
            messages.success(request, f"Congratulations! You have completed all topics in '{course.title}'!")
            
            # For non-AJAX requests, redirect to the course details page to show certificate
            if not is_json_request:
                return redirect('courses:course_details', course_id=course.id)
    except CourseEnrollment.DoesNotExist:
        # If enrollment doesn't exist (shouldn't happen), continue normally
        pass
    
    # Calculate current progress and completion status
    if request.user.role == 'learner':
        # Apply same restrictions as other views
        all_topics = Topic.objects.filter(
            coursetopic__course=course
        ).exclude(
            status='draft'  # Hide draft topics from learners
        ).exclude(
            restrict_to_learners=True,
            restricted_learners=request.user  # Hide topics where learner is restricted
        )
    else:
        all_topics = Topic.objects.filter(coursetopic__course=course)
    
    # Check if all topics are completed
    completed_topics_count = TopicProgress.objects.filter(
        user=request.user,
        topic__in=all_topics,
        completed=True
    ).count()
    
    all_completed = (completed_topics_count == all_topics.count()) if all_topics.count() > 0 else False
    
    # Find the next topic for redirection using section-aware navigation
    next_topic = None
    first_incomplete_topic = None
    
    try:
        # Build section_topics structure similar to topic_view
        from courses.models import Section
        sections = Section.objects.filter(course=course).order_by('order')
        section_topics = []
        
        for section in sections:
            # Get topics explicitly through course and section relationship
            section_topic_query = Topic.objects.filter(
                coursetopic__course=course,
                section=section
            )
            
            # Apply the same draft and restriction filtering
            if request.user.role == 'learner':
                section_topic_query = section_topic_query.exclude(status='draft').exclude(
                    restrict_to_learners=True,
                    restricted_learners=request.user
                )
            
            section_topic_objects = section_topic_query.order_by('order')
            
            if section_topic_objects.exists():
                section_topics.append({
                    'section': section,
                    'topics': section_topic_objects
                })
        
        # Get topics not in any section
        no_section_query = Topic.objects.filter(
            coursetopic__course=course, 
            section__isnull=True
        )
        
        if request.user.role == 'learner':
            no_section_query = no_section_query.exclude(status='draft').exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            )
            
        no_section_topics = no_section_query.order_by('order')
        
        if no_section_topics.exists():
            section_topics.append({
                'section': None,
                'topics': no_section_topics
            })
        
        # Find next topic using section-aware logic
        for section_index, section_item in enumerate(section_topics):
            section_topic_list = list(section_item['topics'])
            try:
                topic_index = section_topic_list.index(topic)
                
                # Check for next topic
                if topic_index < len(section_topic_list) - 1:
                    # Next topic is in same section
                    next_topic = section_topic_list[topic_index + 1]
                elif section_index < len(section_topics) - 1:
                    # Next topic is first topic of next section
                    next_section_topics = list(section_topics[section_index + 1]['topics'])
                    if next_section_topics:
                        next_topic = next_section_topics[0]
                
                break  # Found current topic, exit loop
            except ValueError:
                continue  # Topic not in this section, check next section
        
        # If no direct next topic or we've already found all topics are complete,
        # find the first incomplete topic in the course using section order
        if not next_topic and not all_completed:
            for section_item in section_topics:
                section_topic_list = list(section_item['topics'])
                for course_topic in section_topic_list:
                    # Skip the current topic
                    if course_topic.id == topic.id:
                        continue
                        
                    topic_progress = TopicProgress.objects.filter(
                        user=request.user,
                        topic=course_topic
                    ).first()
                    
                    if not topic_progress or not topic_progress.completed:
                        first_incomplete_topic = course_topic
                        logger.info(f"Found first incomplete topic: {first_incomplete_topic.title} (ID: {first_incomplete_topic.id})")
                        break
                
                if first_incomplete_topic:
                    break
                    
    except Exception as e:
        logger.error(f"Error finding next topic: {str(e)}")
    
    # Calculate current progress for response
    # Ensure all_topics is always available even if exception occurred
        if request.user.role == 'learner':
            all_topics = Topic.objects.filter(
                coursetopic__course=course
            ).exclude(
                status='draft'  # Hide draft topics from learners
            ).exclude(
                restrict_to_learners=True,
                restricted_learners=request.user  # Hide topics where learner is restricted
            )
        else:
            all_topics = Topic.objects.filter(coursetopic__course=course)
    
    total_topics = all_topics.count()
    completed_topics = completed_topics_count
    
    # For AJAX requests, return JSON response with next topic information and course completion status
    if is_json_request:
        response_data = {
            'success': True,
            'topic_id': topic_id,
            'title': topic.title,
            'completed': True,
            'completion_method': completion_method,
            'completed_at': progress.completed_at.isoformat() if progress.completed_at else None,
            'course_completed': all_completed,
            'progress': completed_topics,
            'total': total_topics
        }
        
        # Add course info if all completed
        if all_completed:
            response_data['course'] = {
                'id': course.id,
                'title': course.title,
                'url': reverse('courses:course_details', kwargs={'course_id': course.id})
            }
        # Add next topic info if available and not all completed
        elif next_topic:
            response_data['next_topic'] = {
                'id': next_topic.id,
                'title': next_topic.title,
                'url': reverse('courses:topic_view', kwargs={'topic_id': next_topic.id})
            }
        # Add first incomplete topic if available
        elif first_incomplete_topic:
            response_data['next_topic'] = {
                'id': first_incomplete_topic.id,
                'title': first_incomplete_topic.title,
                'url': reverse('courses:topic_view', kwargs={'topic_id': first_incomplete_topic.id}),
                'is_first_incomplete': True
            }
        
        return JsonResponse(response_data)
    
    # For regular form submissions, add a message and redirect
    if completion_method == 'manual':
        messages.success(request, f"Topic '{topic.title}' has been marked as complete!")
    else:
        messages.success(request, f"Topic '{topic.title}' has been automatically completed!")
    
    # If all topics are completed, we've already redirected above
    # Always redirect to next topic if available, or first incomplete topic, or stay on current topic
    if next_topic and not all_completed:
        return redirect('courses:topic_view', topic_id=next_topic.id)
    elif first_incomplete_topic and not all_completed:
        messages.info(request, f"Redirecting to an incomplete topic: '{first_incomplete_topic.title}'")
        return redirect('courses:topic_view', topic_id=first_incomplete_topic.id)
    elif all_completed:
        # If we reach here, it means we're handling a non-AJAX request and we want to show the certificate
        return redirect('courses:course_details', course_id=course.id)
    else:
        return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def mark_topic_incomplete(request, topic_id):
    """Mark a topic as incomplete for the current user"""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check course access permission
    if not check_course_permission(request.user, course):
        messages.error(request, "You don't have permission to access this course.")
        return redirect('users:role_based_redirect')
    
    # Get the progress record
    try:
        progress = TopicProgress.objects.get(user=request.user, topic=topic)
    except TopicProgress.DoesNotExist:
        # If no progress exists, create one that's incomplete by default
        progress = TopicProgress.objects.create(user=request.user, topic=topic)
        progress.init_progress_data()
    
    # Determine if the request body is JSON
    is_json_request = request.content_type == 'application/json'
    
    # Mark as incomplete
    progress.completed = False
    progress.manually_completed = False
    progress.completion_method = 'manual'  # Since user manually marked as incomplete
    progress.completed_at = None
    
    # Update progress_data to reflect incomplete status
    if not progress.progress_data:
        progress.progress_data = {}
    
    # For video or audio content, reset progress 
    if topic.content_type in ['Video', 'EmbedVideo', 'Audio']:
        progress.progress_data['progress'] = 0.0
        progress.progress_data['completed'] = False
        if 'completed_at' in progress.progress_data:
            del progress.progress_data['completed_at']
    
    # Update completion_data to reflect incomplete status
    if progress.completion_data:
        progress.completion_data.update({
            'marked_incomplete_at': timezone.now().isoformat(),
            'completion_method': 'manual',
            'manually_completed': False
        })
    
    progress.save()
    
    # Log the action
    logger.info(f"Topic '{topic.title}' (ID: {topic_id}) marked as incomplete by user {request.user.username}")
    
    # Update course enrollment and sync progress
    try:
        enrollment = CourseEnrollment.objects.get(user=request.user, course=course)
        
        # SYNC ENROLLMENT PROGRESS: Calculate and update enrollment progress
        from core.utils.enrollment import EnrollmentService
        
        # Get all topics for accurate progress calculation
        if request.user.role == 'learner':
            all_course_topics = Topic.objects.filter(
                coursetopic__course=course
            ).exclude(status='draft').exclude(
                restrict_to_learners=True,
                restricted_learners=request.user
            )
        else:
            all_course_topics = Topic.objects.filter(coursetopic__course=course)
        
        total_topics = all_course_topics.count()
        completed_count = TopicProgress.objects.filter(
            user=request.user,
            topic__in=all_course_topics,
            completed=True
        ).count()
        
        # Calculate progress percentage
        calculated_progress = round((completed_count / total_topics) * 100) if total_topics > 0 else 0
        
        # Update enrollment progress
        EnrollmentService.update_enrollment_progress(enrollment, calculated_progress)
        
        # Mark course as incomplete if it was previously completed
        if enrollment.completed and calculated_progress < 100:
            enrollment.completed = False
            enrollment.completion_date = None
            enrollment.save()
            logger.info(f"Course '{course.title}' marked as incomplete for user {request.user.username}")
    except CourseEnrollment.DoesNotExist:
        pass
    
    # Calculate current progress for response
    if request.user.role == 'learner':
        # Apply same restrictions as other views
        all_topics = Topic.objects.filter(
            coursetopic__course=course
        ).exclude(
            status='draft'  # Hide draft topics from learners
        ).exclude(
            restrict_to_learners=True,
            restricted_learners=request.user  # Hide topics where learner is restricted
        )
    else:
        all_topics = Topic.objects.filter(coursetopic__course=course)
    
    total_topics = all_topics.count()
    completed_topics = TopicProgress.objects.filter(
        user=request.user,
        topic__in=all_topics,
        completed=True
    ).count()
    
    # For AJAX requests, return JSON response
    if is_json_request:
        response_data = {
            'success': True,
            'topic_id': topic_id,
            'title': topic.title,
            'completed': False,
            'marked_incomplete_at': timezone.now().isoformat(),
            'progress': completed_topics,
            'total': total_topics
        }
        return JsonResponse(response_data)
    
    # For regular form submissions, add a message and redirect
    messages.success(request, f"Topic '{topic.title}' has been marked as incomplete.")
    return redirect('courses:topic_view', topic_id=topic_id)

def update_audio_progress(request, topic_id):
    """Update progress for audio content"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
    
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check permission
    if not check_course_permission(request.user, course):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Only update progress for audio content type
    if topic.content_type != 'Audio':
        return JsonResponse({'error': 'This topic is not audio content'}, status=400)
    
    try:
        data = json.loads(request.body)
        current_time = data.get('current_time')
        duration = data.get('duration')
        completed = data.get('completed', False)
        
        if current_time is None or duration is None:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Get or create progress
        progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic=topic
        )
        
        # Use the model's method to update audio progress
        progress.update_audio_progress(current_time, duration)
        
        # If explicitly marked as completed, ensure it's completed
        if completed:
            progress.mark_complete('auto')
            progress.save()
        
        return JsonResponse({
            'success': True,
            'progress': progress.audio_progress,
            'completed': progress.completed
        })
    except Exception as e:
        logger.error(f"Error updating audio progress: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

def update_video_progress(request, topic_id):
    """Update progress for video content"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
    
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    logger.info(f"Processing video progress update for topic_id={topic_id}, user={request.user.username}, course={course.title if course else 'None'}")
    
    # Check permission
    if not check_course_permission(request.user, course):
        logger.warning(f"Permission denied for user={request.user.username} on topic_id={topic_id}")
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Only update progress for video content type
    if topic.content_type != 'Video' and topic.content_type != 'EmbedVideo':
        logger.warning(f"Invalid content type for topic_id={topic_id}: {topic.content_type}")
        return JsonResponse({'error': 'This topic is not video content'}, status=400)
    
    try:
        data = json.loads(request.body)
        from core.utils.type_guards import safe_get_float, safe_get_bool
        
        # Type-safe extraction of numeric values
        current_time = safe_get_float(data, 'current_time')
        duration = safe_get_float(data, 'duration') 
        progress = safe_get_float(data, 'progress')
        completed = safe_get_bool(data, 'completed', False)
        
        logger.info(f"Received video progress update: topic_id={topic_id}, current_time={current_time}, "
                    f"duration={duration}, progress={progress}, completed={completed}")
        
        if current_time is None or duration is None:
            logger.warning(f"Missing required fields for topic_id={topic_id}: current_time={current_time}, duration={duration}")
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Convert to numeric values if they're valid
        try:
            current_time = float(current_time)
            duration = float(duration)
            if progress is not None:
                progress = float(progress)
            
            logger.info(f"Converted values: current_time={current_time}, duration={duration}, progress={progress}")
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid numeric values for topic_id={topic_id}: {str(e)}")
            return JsonResponse({'error': 'Invalid numeric values'}, status=400)
            
        # Calculate progress if not provided
        if progress is None and duration > 0:
            progress = (current_time / duration) * 100
            logger.info(f"Calculated progress for topic_id={topic_id}: {progress}%")
        
        # Get or create progress
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic=topic
        )
        
        logger.info(f"TopicProgress record {'created' if created else 'retrieved'}: id={topic_progress.id}")
        
        # Initialize progress_data if it's missing or has invalid structure
        if created or not topic_progress.progress_data or not isinstance(topic_progress.progress_data, dict):
            logger.info(f"Initializing progress_data for TopicProgress id={topic_progress.id}")
            topic_progress.init_progress_data()
        
        # Log the current state before updating
        logger.info(f"Before update - TopicProgress state: completed={topic_progress.completed}, video_progress={topic_progress.video_progress}")
        
        # Update video progress
        topic_progress.mark_video_progress(current_time, duration, progress)
        
        # If explicitly marked as completed or if progress is close to 100%, mark as complete
        should_complete = completed or (progress is not None and progress >= 95)
        
        if should_complete and not topic_progress.completed:
            logger.info(f"Marking topic_id={topic_id} as completed for user={request.user.username}")
            topic_progress.mark_complete('auto')
            
        topic_progress.save()
        
        # Return the updated progress information
        return JsonResponse({
            'success': True,
            'progress': topic_progress.video_progress,
            'completed': topic_progress.completed,
            'current_time': current_time,
            'duration': duration
        })
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error updating video progress: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def like_item(request, topic_id, item_type, item_id):
    """Toggle like status for discussions, comments, and replies"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check permission
    if not check_course_permission(request.user, course):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if item_type == 'discussion':
        item = get_object_or_404(DiscussionModel, id=item_id)
        if request.user in item.likes.all():
            item.likes.remove(request.user)
            liked = False
        else:
            item.likes.add(request.user)
            liked = True
    elif item_type == 'comment':
        item = get_object_or_404(Comment, id=item_id)
        if request.user in item.likes.all():
            item.likes.remove(request.user)
            liked = False
        else:
            item.likes.add(request.user)
            liked = True
    elif item_type == 'reply':
        # Assuming replies are also Comments but with a parent
        item = get_object_or_404(Comment, id=item_id, parent__isnull=False)
        if request.user in item.likes.all():
            item.likes.remove(request.user)
            liked = False
        else:
            item.likes.add(request.user)
            liked = True
    else:
        return JsonResponse({'error': 'Invalid item type'}, status=400)
    
    return JsonResponse({
        'success': True,
        'liked': liked,
        'likes_count': item.likes.count()
    })

@login_required
def delete_comment(request, topic_id, comment_id):
    """Delete a comment from a topic discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Make sure topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get the comment
    comment = get_object_or_404(Comment, id=comment_id, discussion=topic.discussion)
    
    # Check permissions
    if comment.created_by != request.user and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to delete this comment.')
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if request.method == 'POST':
        comment.delete()
        messages.success(request, 'Comment deleted successfully.')
    
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def edit_comment(request, topic_id, comment_id):
    """Edit a comment in a topic discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Make sure topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get the comment
    comment = get_object_or_404(Comment, id=comment_id, discussion=topic.discussion)
    
    # Check permissions
    if comment.created_by != request.user:
        messages.error(request, 'You do not have permission to edit this comment.')
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        
        if content:
            comment.content = content
            comment.save()
            messages.success(request, 'Comment updated successfully.')
        else:
            messages.error(request, 'Please enter a comment.')
    
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def add_reply(request, topic_id, comment_id):
    """Add a reply to a comment in a topic discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Make sure topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get the parent comment
    parent_comment = get_object_or_404(Comment, id=comment_id, discussion=topic.discussion)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        files = request.FILES.getlist('attachments')
        
        if content:
            reply = Comment.objects.create(
                discussion=topic.discussion,
                content=content,
                created_by=request.user,
                parent=parent_comment
            )
            
            # Handle attachments
            for file in files:
                file_type = get_file_type(file.name)
                Attachment.objects.create(
                    comment=reply,
                    file=file,
                    file_type=file_type,
                    uploaded_by=request.user
                )
            
            messages.success(request, 'Reply added successfully.')
        else:
            messages.error(request, 'Please enter a reply.')
    
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def delete_reply(request, topic_id, reply_id):
    """Delete a reply from a topic discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Make sure topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get the reply (comment with a parent)
    reply = get_object_or_404(Comment, id=reply_id, discussion=topic.discussion, parent__isnull=False)
    
    # Check permissions
    if reply.created_by != request.user and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to delete this reply.')
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if request.method == 'POST':
        reply.delete()
        messages.success(request, 'Reply deleted successfully.')
    
    return redirect('courses:topic_view', topic_id=topic_id)

@login_required
def edit_reply(request, topic_id, reply_id):
    """Edit a reply in a topic discussion"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Make sure topic has a discussion
    if not hasattr(topic, 'discussion') or not topic.discussion:
        messages.error(request, "This topic doesn't have an associated discussion.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Get the reply (comment with a parent)
    reply = get_object_or_404(Comment, id=reply_id, discussion=topic.discussion, parent__isnull=False)
    
    # Check permissions
    if reply.created_by != request.user:
        messages.error(request, 'You do not have permission to edit this reply.')
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if request.method == 'POST':
        content = request.POST.get('content')
        
        if content:
            reply.content = content
            reply.save()
            messages.success(request, 'Reply updated successfully.')
        else:
            messages.error(request, 'Please enter a reply.')
    
    return redirect('courses:topic_view', topic_id=topic_id)

def get_file_type(filename):
    """Helper function to determine the type of an uploaded file"""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
    return 'document'

def get_course_topics(request, course_id):
    """API endpoint to get topics for a course"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check permission
    if not check_course_permission(request.user, course):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Filter topics based on user role
    if request.user.role == 'learner':
        # For learners, exclude draft topics and restricted topics
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).exclude(
            status='draft'  # Hide draft topics from learners
        ).exclude(
            restrict_to_learners=True,
            restricted_learners=request.user  # Hide topics where learner is restricted
        ).order_by('coursetopic__order', 'created_at')
    else:
        # Admin, instructors and other roles see all topics
        topics = Topic.objects.filter(
            coursetopic__course=course
        ).order_by('coursetopic__order', 'created_at')
    
    topics_data = []
    for topic in topics:
        topics_data.append({
            'id': topic.id,
            'title': topic.title,
            'order': topic.coursetopic_set.get(course=course).order,
            'content_type': topic.content_type,
            'status': topic.status
        })
    
    return JsonResponse({
        'success': True,
        'topics': topics_data
    })

def reorder_topics(request):
    """Reorder topics within a course"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        section_id = data.get('section_id')
        topic_orders = data.get('topic_orders', [])
        
        logger.info(f"Reordering topics for course {course_id}, section {section_id}")
        logger.info(f"Topic orders: {topic_orders}")
        
        if not course_id or not topic_orders:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        course = get_object_or_404(Course, id=course_id)
        
        # Check permission
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
        
        # Update order for each topic
        with transaction.atomic():
            for item in topic_orders:
                topic_id = item.get('topic_id')
                order = item.get('order')
                item_section_id = item.get('section_id', section_id)
                
                if topic_id is None or order is None:
                    continue
                
                # Get the topic directly
                topic = get_object_or_404(Topic, id=topic_id)
                
                # Make sure the topic is in this course
                course_topic = CourseTopic.objects.filter(course=course, topic=topic).first()
                if not course_topic:
                    logger.warning(f"Topic {topic_id} not found in course {course_id}")
                    continue
                
                # Update order
                topic.order = order
                
                # Update section if provided
                if item_section_id:
                    section = get_object_or_404(Section, id=item_section_id, course=course)
                    topic.section = section
                else:
                    topic.section = None
                
                topic.save()
                
                logger.info(f"Updated topic {topic_id} to order {order} in section {item_section_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Topic order updated successfully'
        })
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error reordering topics: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error reordering topics: {str(e)}")
        logger.exception("Exception details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# Old create_category function removed - use categories app instead

@login_required
def topic_edit(request, topic_id, section_id=None):
    """View for editing a topic"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Get section information if section_id is provided
    section = None
    if section_id:
        section = get_object_or_404(Section, id=section_id, course=course)
    
    # Check if user has permission to edit
    if not course or not check_topic_edit_permission(request.user, topic, course):
        messages.error(request, "You don't have permission to edit this topic.")
        if course:
            return redirect('courses:course_edit', course.id)
        else:
            return redirect('courses:course_list')
    
    # Get filtered content based on user role
    filtered_content = get_user_filtered_content(request.user, course, request)
    
    # Create the form instance with the topic data and filtered content
    form = TopicForm(instance=topic, course=course, filtered_content=filtered_content)
    
    # Handle AJAX requests for fetching topic data
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.method == 'GET':
        # Convert topic data to JSON
        topic_data = {
            'id': topic.id,
            'title': topic.title,
            'description': topic.description,
            'content_type': topic.content_type,
            'status': topic.status,
            'start_date': topic.start_date.strftime('%Y-%m-%dT%H:%M') if topic.start_date else None,
            'end_date': topic.end_date.strftime('%Y-%m-%dT%H:%M') if topic.end_date else None,
            'endless_access': topic.endless_access,
            'order': topic.order
        }
        
        # Add section information if topic has a section
        if hasattr(topic, 'section') and topic.section:
            topic_data['section_id'] = topic.section.id
        
        # Add content-specific information
        if topic.content_type.lower() == 'quiz':
            topic_data['quiz_id'] = topic.quiz_id
        elif topic.content_type.lower() == 'assignment':
            # More robust assignment_id handling
            assignment_id = None
            if hasattr(topic, 'assignment_id') and topic.assignment_id:
                assignment_id = topic.assignment_id
            elif hasattr(topic, 'assignment') and topic.assignment:
                assignment_id = topic.assignment.id
            topic_data['assignment_id'] = assignment_id
            logger.info(f"Topic {topic.id} assignment_id: {assignment_id}")
        elif topic.content_type.lower() == 'conference':
            topic_data['conference_id'] = topic.conference_id
        elif topic.content_type.lower() == 'discussion':
            topic_data['discussion_id'] = topic.discussion_id
        elif topic.content_type.lower() == 'text':
            # For TinyMCE content, send the content directly
            topic_data['text_content'] = topic.text_content or ''
        elif topic.content_type.lower() == 'web':
            topic_data['web_url'] = topic.web_url
        elif topic.content_type.lower() == 'embedvideo':
            topic_data['embed_code'] = topic.embed_code
        
        # Return data as JSON
        return JsonResponse({
            'success': True,
            'topic': topic_data
        })
    
    if request.method == 'POST':
        form_data = request.POST.copy()
        files = request.FILES
        
        # Log warning if someone tries to change content type
        submitted_content_type = form_data.get('content_type', '').lower()
        if submitted_content_type and submitted_content_type != topic.content_type.lower():
            logger.warning(f"Attempt to change content type from {topic.content_type} to {submitted_content_type} rejected for topic {topic_id}")
        
        # Update fields
        topic.title = form_data.get('title')
        topic.description = form_data.get('description')
        topic.status = form_data.get('status')
        
        # Handle dates
        start_date = form_data.get('start_date')
        end_date = form_data.get('end_date')
        endless_access = form_data.get('endless_access') == 'on'
        
        if start_date:
            try:
                # Parse the datetime string and make it timezone-aware
                from datetime import datetime
                from django.utils import timezone
                
                # Parse the datetime string (format: YYYY-MM-DDTHH:MM)
                parsed_date = datetime.strptime(start_date, '%Y-%m-%dT%H:%M')
                
                # Make it timezone-aware using the current timezone
                topic.start_date = timezone.make_aware(parsed_date)
            except ValueError as e:
                messages.error(request, f"Invalid start date format: {str(e)}")
                logger.warning(f"Invalid start date format for course {course.id}: {start_date}")
        else:
            topic.start_date = None
        
        if end_date and not endless_access:
            try:
                # Parse the datetime string and make it timezone-aware
                from datetime import datetime
                from django.utils import timezone
                
                # Parse the datetime string (format: YYYY-MM-DDTHH:MM)
                parsed_date = datetime.strptime(end_date, '%Y-%m-%dT%H:%M')
                
                # Make it timezone-aware using the current timezone
                topic.end_date = timezone.make_aware(parsed_date)
            except ValueError as e:
                messages.error(request, f"Invalid end date format: {str(e)}")
                logger.warning(f"Invalid end date format for course {course.id}: {end_date}")
        else:
            topic.end_date = None
        topic.endless_access = endless_access
        
        # Handle learner restrictions
        restrict_to_learners = form_data.get('restrict_to_learners') == 'on'
        topic.restrict_to_learners = restrict_to_learners
        
        # Handle content based on type - always use the existing content type
        content_type = topic.content_type.lower()
        
        # Process the content based on the existing content type
        if content_type == 'text':
            # Process text content - directly use the content from TinyMCE
            text_content = form_data.get('text_content', '')
            topic.text_content = text_content
            content_file = files['content_file']
            
            # Check file size for all content types - maximum 600MB
            max_size = 600 * 1024 * 1024  # 600MB in bytes
            if content_file.size > max_size:
                error_msg = f" File size limit exceeded! Your file size: {(content_file.size / (1024 * 1024)):.2f}MB. Maximum allowed: 600MB. Please upload a smaller file."
                logger.warning(f"File size exceeded limit: {error_msg}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': error_msg,
                        'details': {'content_file': [error_msg]}
                    }, status=400)
                
                messages.error(request, error_msg)
                if course:
                    return redirect('courses:course_edit', course_id=course.id)
                else:
                    return redirect('courses:course_list')
            
        elif content_type == 'web':
            # Handle web content
            topic.web_url = form_data.get('web_url')
        elif content_type == 'embedvideo':
            # Handle embedded video content
            topic.embed_code = form_data.get('embed_code')
        elif content_type == 'quiz':
            quiz_id = form_data.get('quiz')
            if quiz_id:
                topic.quiz_id = quiz_id
        elif content_type == 'assignment':
            assignment_id = form_data.get('assignment')
            if assignment_id:
                topic.assignment_id = assignment_id
        elif content_type == 'conference':
            conference_id = form_data.get('conference')
            if conference_id:
                topic.conference_id = conference_id
        elif content_type == 'discussion':
            discussion_id = form_data.get('discussion')
            if discussion_id:
                topic.discussion_id = discussion_id
        elif content_type == 'scorm':
            # SCORM packages are typically not replaced after creation
            # But we allow metadata updates (title, description, etc.)
            # File upload is only allowed during creation, not edit
            if 'content_file' in files:
                logger.warning(f"SCORM file upload attempted during edit for topic {topic_id} - ignoring")
                messages.warning(request, "SCORM packages cannot be replaced after creation.")
        
        # Handle section assignment
        new_section_name = form_data.get('new_section_name')
        section_id_from_form = form_data.get('section')
        
        # Use section_id from URL parameter if available, otherwise use form data
        target_section_id = section_id if section_id else section_id_from_form
        
        if new_section_name and new_section_name.strip():
            # Create new section
            try:
                new_section = Section.objects.create(
                    name=new_section_name.strip(),
                    course=course,
                    order=Section.objects.filter(course=course).aggregate(Max('order')).get('order__max', 0) or 0 + 1
                )
                topic.section = new_section
                logger.info(f"Created new section '{new_section_name}' and assigned topic {topic.id} to it")
            except Exception as e:
                logger.error(f"Error creating new section: {str(e)}")
                messages.error(request, f"Error creating new section: {str(e)}")
        elif target_section_id and target_section_id != 'new_section':
            # Assign to existing section
            try:
                target_section = Section.objects.get(id=target_section_id, course=course)
                topic.section = target_section
                logger.info(f"Assigned topic {topic.id} to existing section {target_section.name}")
            except Section.DoesNotExist:
                logger.warning(f"Section {target_section_id} not found for course {course.id}")
                topic.section = None
        else:
            # No section (standalone topic)
            topic.section = None
            logger.info(f"Topic {topic.id} set as standalone (no section)")

        try:
            topic.save()
            
            # Handle restricted learners (many-to-many field must be set after topic is saved)
            if restrict_to_learners:
                restricted_learner_ids = request.POST.getlist('restricted_learners')
                topic.restricted_learners.clear()
                if restricted_learner_ids:
                    for learner_id in restricted_learner_ids:
                        try:
                            learner = CustomUser.objects.get(id=learner_id, role='learner')
                            topic.restricted_learners.add(learner)
                        except CustomUser.DoesNotExist:
                            pass
            else:
                # Clear all restrictions if checkbox is unchecked
                topic.restricted_learners.clear()
            
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if course:
                    return JsonResponse({
                        'success': True,
                        'message': 'Topic updated successfully.',
                        'redirect_url': reverse('courses:course_edit', kwargs={'course_id': course.id})
                    })
                else:
                    return JsonResponse({
                        'success': True,
                        'message': 'Topic updated successfully.',
                        'redirect_url': reverse('courses:course_list')
                    })
            
            # Redirect back to course edit page after successful update
            messages.success(request, 'Topic updated successfully.')
            if course:
                return redirect('courses:course_edit', course_id=course.id)
            else:
                return redirect('courses:course_list')
        except Exception as e:
            logger.error(f"Error updating topic: {str(e)}")
            
            # Return JSON error for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': f'Error updating topic: {str(e)}'
                }, status=500)
                
            messages.error(request, f'Error updating topic: {str(e)}')
            # Redirect back keeping the section information if it exists
            if section:
                return redirect('courses:topic_section_edit', topic_id=topic.id, section_id=section.id)
            else:
                return redirect('courses:topic_edit', topic_id=topic.id)
    
    # Prepare context for GET request
    content_types = [
        ('Text', 'Text'),
        ('Web', 'Web Content'),
        ('EmbedVideo', 'Embedded Video'),
        ('Audio', 'Audio'),
        ('Video', 'Video'),
        ('Document', 'Document'),
        ('Quiz', 'Quiz'),
        ('Assignment', 'Assignment'),
        ('SCORM', 'SCORM Package'),
        ('Conference', 'Conference'),
        ('Discussion', 'Discussion'),
    ]
    
    # Define breadcrumbs for this view
    if course:
            breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
            {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        ]
            
            # Add section to breadcrumbs if it exists
            if section:
                breadcrumbs.append({
                    'label': section.name, 
                    'icon': 'fa-folder'
                })
                
            breadcrumbs.append({'label': f"Edit {topic.title}", 'icon': 'fa-edit'})
    else:
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
            {'label': f"Edit {topic.title}", 'icon': 'fa-edit'}
        ]
    
    # Safely check if the topic has a quiz_id attribute
    has_quiz = hasattr(topic, 'quiz_id') or hasattr(topic, 'quiz')
    quiz_id = getattr(topic, 'quiz_id', None) if has_quiz else None
    
    # Safely check if the topic has assignment_id and conference_id attributes
    has_assignment = hasattr(topic, 'assignment_id') or hasattr(topic, 'assignment')
    assignment_id = None
    
    # Get assignment_id from topic - use multiple methods to ensure we get it
    if has_assignment:
        # First try direct attribute
        if hasattr(topic, 'assignment_id') and topic.assignment_id:
            assignment_id = topic.assignment_id
        # Then try as object reference
        elif hasattr(topic, 'assignment') and topic.assignment:
            assignment_id = topic.assignment.id
            
        # Log for debugging
        logger.debug(f"Topic {topic.id} has assignment_id: {assignment_id}")
    
    has_conference = hasattr(topic, 'conference_id') or hasattr(topic, 'conference')
    conference_id = getattr(topic, 'conference_id', None) if has_conference else None
    
    # Safely check if the topic has discussion_id attribute
    has_discussion = hasattr(topic, 'discussion_id') or hasattr(topic, 'discussion')
    discussion_id = getattr(topic, 'discussion_id', None) if has_discussion else None
    
    # Get forum content type and assessment type for discussions
    forum_content_type = 'text'
    assessment_type = 'discussion'
    if discussion_id:
        try:
            # Use existing DiscussionModel instead of re-importing
            discussion = DiscussionModel.objects.get(id=discussion_id)
            forum_content_type = discussion.content_type
            assessment_type = discussion.assessment_type
        except Exception as e:
            logger.warning(f"Error getting discussion details: {str(e)}")
    
    # Get categories for search dropdown with role-based filtering
    categories = get_user_accessible_categories(request.user)
    
    # Get all sections for this course for the section dropdown
    sections = Section.objects.filter(course=course).order_by('order')
    
    # Determine the correct section_id for the template
    # Priority: URL parameter > topic's current section > None
    current_section_id = None
    if section:
        # Section was provided via URL parameter
        current_section_id = section.id
        logger.debug(f"Using section from URL parameter: {current_section_id}")
    elif topic.section:
        # Use topic's current section if no URL parameter provided
        current_section_id = topic.section.id
        logger.debug(f"Using topic's current section: {current_section_id}")
    else:
        logger.debug("No section found - topic is standalone")
    
    # Create a context with the topic details
    context = {
        'topic': topic,
        'course': course,
        'action': 'Edit',  # Add this line to properly set action to 'Edit' instead of 'Create'
        'content_types': content_types,
        'section_id': current_section_id,
        'sections': sections,  # Add sections for the dropdown
        'has_quiz': has_quiz,
        'quiz_id': quiz_id,
        'has_assignment': has_assignment,
        'assignment_id': assignment_id,
        'has_conference': has_conference,
        'conference_id': conference_id,
        'has_discussion': has_discussion,
        'discussion_id': discussion_id,
        'forum_content_type': forum_content_type,
        'assessment_type': assessment_type,
        'breadcrumbs': breadcrumbs,
        'quizzes': filtered_content['quizzes'],
        'assignments': filtered_content['assignments'],
        'conferences': filtered_content['conferences'],
        'discussions': filtered_content['discussions'],
        'categories': categories,
        'form': form,  # Add the form to the context
    }
    
    # Render the template with the context
    return render(request, 'courses/add_topic.html', context)

@login_required
def topic_delete(request, topic_id):
    """Delete a topic"""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check if user has permission to delete
    if not course or not check_topic_edit_permission(request.user, topic, course, check_for='delete'):
        messages.error(request, "You don't have permission to delete this topic.")
        if course:
            return redirect('courses:course_edit', course.id)
        else:
            return redirect('courses:course_list')
    
    # Store topic title for success message
    topic_title = topic.title
    
    # Delete the topic
    topic.delete()
    
    # Show success message
    messages.success(request, f"Topic '{topic_title}' has been deleted successfully.")
    
    # Redirect back to course edit page
    if course:
        return redirect('courses:course_edit', course.id)
    else:
        return redirect('courses:course_list')

@login_required
def section_create(request, course_id=None):
    """
    Create a new section for a course
    """
    # Handle both URL patterns: with course_id parameter and from POST data
    if course_id is None:
        course_id = request.POST.get('course_id')
        if not course_id:
            return JsonResponse({'success': False, 'error': 'Course ID is required'}, status=400)
    
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user has permission to edit the course
    if not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to add sections to this course.")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': "You don't have permission to add sections to this course."}, status=403)
        return redirect('courses:course_details', course_id=course_id)
    
    if request.method == 'POST':
        name = request.POST.get('name', '')
        description = request.POST.get('description', '')
        
        # Check for return URL in referrer or request parameters
        return_url = request.POST.get('return_url') or request.META.get('HTTP_REFERER')
        from_topic_create = 'topics/create' in str(return_url) if return_url else False
        
        errors = {}
        if name and len(name) > 255:
            errors['name'] = [f"Section name is too long (max 255 characters, got {len(name)})."]
            
        if errors:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False, 
                    'error': "Validation failed",
                    'errors': errors
                }, status=400)
            
            for field, field_errors in errors.items():
                for error in field_errors:
                    messages.error(request, f"{field}: {error}")
            
            # Redirect back to the referer if available
            if from_topic_create:
                return redirect(return_url)
            return redirect('courses:course_edit', course_id=course_id)
        
        try:
            # Get the highest order value and add 1
            highest_order = Section.objects.filter(course=course).aggregate(Max('order')).get('order__max') or 0
            
            # Create the section
            section = Section.objects.create(
                name=name,
                description=description,
                course=course,
                order=highest_order + 1
            )
            
            section_display_name = name if name else f"Section {section.id}"
            messages.success(request, f"Section '{section_display_name}' has been created.")
            
            # If this is an AJAX request (from the topic creation form)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'section_id': section.id,
                    'section_name': section.name or f"Section {section.id}",
                    'return_url': return_url if from_topic_create else None
                })
            
            # For normal requests, redirect to topic create page if that's where we came from
            if from_topic_create:
                # Parse the URL to get the course ID 
                return redirect(return_url)
                
            # Otherwise redirect to course edit page
            return redirect('courses:course_edit', course_id=course_id)
        except Exception as e:
            from role_management.utils import SessionErrorHandler
            error_message = SessionErrorHandler.log_and_sanitize_error(
                e, request, error_type='system', operation='section creation'
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_message
                }, status=500)
            
            messages.error(request, f"Error creating section: {error_message}")
            if from_topic_create:
                return redirect(return_url)
            return redirect('courses:course_edit', course_id=course_id)
    
    # If not POST, redirect based on referrer
    http_referer = request.META.get('HTTP_REFERER', '')
    if 'topics/create' in http_referer or 'topic/create' in http_referer:
        return redirect(http_referer)
    
    # Default redirect to course edit page
    return redirect('courses:course_edit', course_id=course_id)

@login_required
@require_http_methods(["POST"])
def section_update(request, section_id):
    """
    Update a section's name and description
    """
    section = get_object_or_404(Section, id=section_id)
    course = section.course
    
    # Check if user has permission to edit the course
    if not check_course_edit_permission(request.user, course):
        return JsonResponse({
            'success': False, 
            'error': "You don't have permission to update sections in this course."
        }, status=403)
    
    try:
        data = json.loads(request.body)
        name = data.get('name', '')
        description = data.get('description', '')
        
        errors = {}
        if name and len(name) > 255:
            errors['name'] = [f"Section name is too long (max 255 characters, got {len(name)})."]
            
        if errors:
            return JsonResponse({
                'success': False, 
                'error': "Validation failed",
                'errors': errors
            }, status=400)
        
        # Update the section
        section.name = name
        section.description = description
        section.save()
        
        section_display_name = name if name else f"Section {section.id}"
        return JsonResponse({
            'success': True,
            'message': f"Section '{section_display_name}' has been updated.",
            'section': {
                'id': section.id,
                'name': section.name or f"Section {section.id}",
                'description': section.description
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': "Invalid JSON in request body"
        }, status=400)
    except Exception as e:
        from role_management.utils import SessionErrorHandler
        error_message = SessionErrorHandler.log_and_sanitize_error(
            e, request, error_type='system', operation='section update'
        )
        return JsonResponse({
            'success': False,
            'error': error_message
        }, status=500)

@login_required
@require_http_methods(["DELETE"])
def section_delete(request, section_id):
    """
    Delete a section and optionally move its topics
    """
    import logging
    logger = logging.getLogger(__name__)
    
    section = get_object_or_404(Section, id=section_id)
    course = section.course
    
    # Add detailed logging for debugging
    logger.info(f"Section delete request: user {request.user.id} ({request.user.role}) trying to delete section {section_id} from course {course.id}")
    logger.info(f"Course instructor: {course.instructor}")
    logger.info(f"Course branch: {course.branch}")
    logger.info(f"User branch: {request.user.branch}")
    
    # Check if user has permission to edit the course
    has_permission = check_course_edit_permission(request.user, course)
    logger.info(f"Permission check result: {has_permission}")
    
    # Additional fallback permission checks for debugging
    if not has_permission:
        # Check if user is the course instructor directly
        if request.user == course.instructor:
            logger.info("Fallback: User is course instructor - allowing deletion")
            has_permission = True
        # Check if user is superuser or admin
        elif request.user.is_superuser or request.user.role in ['admin', 'superadmin', 'globaladmin']:
            logger.info(f"Fallback: User has elevated role ({request.user.role}) - allowing deletion")
            has_permission = True
        # Check if user is enrolled in the course (for instructors)
        elif request.user.role == 'instructor' and course.enrolled_users.filter(id=request.user.id).exists():
            logger.info("Fallback: User is enrolled instructor - allowing deletion")
            has_permission = True
    
    # Additional permission checks for edge cases
    if not has_permission:
        # Check if user is enrolled in the course with instructor role
        if request.user.role == 'instructor' and course.enrolled_users.filter(id=request.user.id).exists():
            logger.info("User is enrolled instructor - allowing deletion")
            has_permission = True
        # Check if user has any relationship to the course
        elif hasattr(course, 'instructor') and course.instructor and request.user.id == course.instructor.id:
            logger.info("User is course instructor - allowing deletion")
            has_permission = True
        # Check if user has group access with edit permissions
        elif course.accessible_groups.filter(
            memberships__user=request.user,
            memberships__is_active=True,
            memberships__custom_role__can_edit=True
        ).exists():
            logger.info("User has group access with edit permissions - allowing deletion")
            has_permission = True
    
    if not has_permission:
        logger.warning(f"Permission denied for user {request.user.id} to delete section {section_id}")
        logger.warning(f"User role: {request.user.role}, Course instructor: {course.instructor}, User branch: {getattr(request.user, 'branch', 'N/A')}, Course branch: {course.branch}")
        return JsonResponse({
            'success': False, 
            'error': "You don't have permission to delete sections in this course. Please contact your administrator."
        }, status=403)
    
    try:
        # Check if section has topics
        has_topics = Topic.objects.filter(section=section).exists()
        
        if has_topics:
            # Check if a target section was specified for topic migration
            try:
                data = json.loads(request.body or '{}')
                target_section_id = data.get('target_section_id')
                
                if target_section_id:
                    # Move topics to the target section
                    target_section = get_object_or_404(Section, id=target_section_id, course=course)
                    
                    # Get the highest order in target section
                    highest_order = Topic.objects.filter(section=target_section).aggregate(
                        Max('order')).get('order__max') or 0
                    
                    # Update all topics from the section to be deleted
                    topics = Topic.objects.filter(section=section)
                    for i, topic in enumerate(topics):
                        topic.section = target_section
                        topic.order = highest_order + i + 1
                        topic.save()
                        
                    logger.info(f"Moved {topics.count()} topics from section {section_id} to section {target_section_id}")
                else:
                    # Make topics standalone (no section)
                    Topic.objects.filter(section=section).update(section=None)
                    logger.info(f"Made topics from section {section_id} standalone")
            except json.JSONDecodeError:
                # No valid JSON body, make topics standalone
                Topic.objects.filter(section=section).update(section=None)
                logger.info(f"Made topics from section {section_id} standalone (no JSON body)")
        
        # Now delete the section
        section_name = section.name
        section.delete()
        
        return JsonResponse({
            'success': True,
            'message': f"Section '{section_name}' has been deleted."
        })
    except Exception as e:
        from role_management.utils import SessionErrorHandler
        error_message = SessionErrorHandler.log_and_sanitize_error(
            e, request, error_type='system', operation='section deletion'
        )
        return JsonResponse({
            'success': False,
            'error': error_message
        }, status=500)

@login_required
def move_topic_to_section(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    topic_id = request.POST.get('topic_id')
    section_id = request.POST.get('section_id')
    
    if not topic_id:
        return JsonResponse({'success': False, 'error': 'Topic ID is required'})
    
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check if user has permission to edit the course
    if not course or not check_course_edit_permission(request.user, course):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if section_id and section_id.strip():
        # Move to specified section
        section = get_object_or_404(Section, id=section_id)
        
        # Ensure section belongs to the same course
        if section.course != course:
            return JsonResponse({'success': False, 'error': 'Section does not belong to this course'})
        
        # Get highest order in this section
        highest_order = Topic.objects.filter(section=section).aggregate(Max('order')).get('order__max') or 0
        
        # Update topic
        topic.section = section
        topic.order = highest_order + 1
        topic.save()
        
        message = f'Topic moved to section: {section.name}'
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': message})
        else:
            messages.success(request, message)
            return redirect('courses:course_details', course_id=course.id)
    else:
        # Remove from section
        topic.section = None
        topic.save()
        
        message = 'Topic removed from section'
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': message})
        else:
            messages.success(request, message)
            return redirect('courses:course_details', course_id=course.id)

@login_required
@require_POST
def reorder_sections(request):
    """
    API endpoint to reorder sections
    """
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        section_orders = data.get('section_orders', [])
        
        logger.info(f"Reordering sections for course {course_id}")
        logger.info(f"Section orders: {section_orders}")
        
        if not course_id or not section_orders:
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        course = get_object_or_404(Course, id=course_id)
        
        # Check if user has permission to edit the course
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Update order for each section
        with transaction.atomic():
            for item in section_orders:
                section_id = item.get('section_id')
                order = item.get('order')
                
                if section_id is None or order is None:
                    continue
                
                section = get_object_or_404(Section, id=section_id, course=course)
                section.order = order
                section.save()
                
                logger.info(f"Updated section {section_id} to order {order}")
        
        return JsonResponse({
            'success': True,
            'message': 'Section order updated successfully'
        })
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error reordering sections: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error reordering sections: {str(e)}")
        logger.exception("Exception details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["DELETE"])
def delete_section(request, section_id):
    """
    Delete a section, moving all its topics to unsectioned
    """
    try:
        section = get_object_or_404(Section, id=section_id)
        course = section.course
        
        # Check if user has permission to edit the course
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Get all topics in this section
        topics = Topic.objects.filter(section=section)
        
        # Remove the topics from this section
        for topic in topics:
            topic.section = None
            topic.save()
        
        # Delete the section
        section_name = section.name
        section.delete()
        
        return JsonResponse({
            'success': True, 
            'message': f'Section "{section_name}" deleted successfully. All topics have been moved to unsectioned.'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def update_section_name(request, section_id):
    """
    Simple API endpoint to update a section's name
    """
    try:
        # Debug logging
        logger.info(f"Section rename request from user: {request.user.username} (role: {request.user.role}) for section {section_id}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"Content type: {request.content_type}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        # Get new name from request
        if request.content_type == 'application/json':
            import json
            try:
                data = json.loads(request.body)
                new_name = data.get('name', '').strip()
                logger.info(f"JSON data received: {data}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                return JsonResponse({'success': False, 'error': 'Invalid JSON in request body'})
        else:
            new_name = request.POST.get('name', '').strip()
            logger.info(f"Form data received: {dict(request.POST)}")
        
        if not new_name:
            logger.warning("Section name is empty or not provided")
            return JsonResponse({'success': False, 'error': 'Section name is required'})
        
        # Get section and check permissions
        try:
            section = get_object_or_404(Section, id=section_id)
            instructor_username = section.course.instructor.username if section.course.instructor else 'None'
            logger.info(f"Section {section_id} belongs to course: {section.course.title} (instructor: {instructor_username})")
        except Exception as e:
            logger.error(f"Error getting section {section_id}: {e}")
            return JsonResponse({'success': False, 'error': f'Section not found: {str(e)}'})
        
        can_edit = check_course_edit_permission(request.user, section.course)
        logger.info(f"User {request.user.username} can edit course: {can_edit}")
        
        if not can_edit:
            logger.warning(f"Permission denied for user {request.user.username} to edit section {section_id}")
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Update section name
        old_name = section.name
        section.name = new_name
        section.save()
        
        logger.info(f"Section {section_id} renamed from '{old_name}' to '{new_name}'")
        
        return JsonResponse({
            'success': True,
            'message': 'Section renamed successfully',
            'name': section.name
        })
        
    except Exception as e:
        logger.error(f"Unexpected error in update_section_name: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})

@login_required(login_url='/login/')
def course_settings(request, course_id):
    """Display and manage course settings."""
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # Check if the user has permission to edit this course
    if not check_course_edit_permission(user, course):
        messages.error(request, "You don't have permission to edit this course's settings.")
        return redirect('courses:course_details', course_id=course_id)
    
    # Get categories for dropdown with role-based filtering
    categories = get_user_accessible_categories(request.user)
    
    # Get instructors for dropdown with business/branch filtering
    from core.utils.business_filtering import filter_users_by_business
    
    if user.is_superuser or user.role == 'globaladmin':
        # Global admins can see all instructors
        instructors = CustomUser.objects.filter(role='instructor').order_by('first_name', 'last_name')
    elif user.role == 'superadmin':
        # Super admins can see instructors within their assigned businesses
        assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
        if assigned_businesses.exists():
            instructors = CustomUser.objects.filter(
                role='instructor',
                branch__business__in=assigned_businesses
            ).order_by('first_name', 'last_name')
        else:
            instructors = CustomUser.objects.none()
    elif user.role == 'admin':
        # Branch admins can see instructors in their branch
        if user.branch:
            instructors = CustomUser.objects.filter(
                role='instructor',
                branch=user.branch
            ).order_by('first_name', 'last_name')
        else:
            instructors = CustomUser.objects.none()
    elif user.role == 'instructor':
        # Instructors can only select themselves
        instructors = CustomUser.objects.filter(id=user.id, role='instructor')
    else:
        # Other roles (learners) cannot see instructors
        instructors = CustomUser.objects.none()
    
    # Get courses for prerequisites selection - filtered based on user role and permissions
    if user.is_superuser or user.role == 'globaladmin':
        # Global admins can see all courses
        all_courses = Course.objects.exclude(id=course_id).order_by('title')
    elif user.role == 'superadmin':
        # Super admins can see all courses in their businesses
        assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
        if assigned_businesses.exists():
            all_courses = Course.objects.filter(
                branch__business__in=assigned_businesses
            ).exclude(id=course_id).order_by('title')
        else:
            all_courses = Course.objects.none()
    elif user.role == 'admin':
        # Branch admins can see courses in their branch and business
        if user.branch:
            branch_courses = Course.objects.filter(branch=user.branch)
            business_courses = Course.objects.none()
            if user.branch.business:
                business_courses = Course.objects.filter(branch__business=user.branch.business)
            all_courses = (branch_courses | business_courses).distinct().exclude(id=course_id).order_by('title')
        else:
            all_courses = Course.objects.none()
    elif user.role == 'instructor':
        # Instructors can see:
        # 1. Courses they teach
        # 2. Courses they're enrolled in
        # 3. Courses in their branch
        instructor_courses = Course.objects.filter(instructor=user)
        enrolled_courses = Course.objects.filter(enrolled_users=user)
        branch_courses = Course.objects.none()
        if user.branch:
            branch_courses = Course.objects.filter(branch=user.branch)
        all_courses = (instructor_courses | enrolled_courses | branch_courses).distinct().exclude(id=course_id).order_by('title')
    else:
        # Regular users (learners) can only see courses they're enrolled in
        all_courses = Course.objects.filter(enrolled_users=user).exclude(id=course_id).order_by('title')
    
    # Debug: Log available courses
    # Load available courses and current prerequisites
    logger.info(f"Loading prerequisites for course {course_id}, user role: {user.role}")
    
    # Get certificate templates for dropdown - RBAC filtered
    from certificates.models import CertificateTemplate
    
    # Filter certificate templates based on user role
    if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
        # Super admins can see all templates
        certificate_templates = CertificateTemplate.objects.filter(is_active=True)
    elif request.user.role == 'admin' and request.user.branch:
        # Branch admins can see templates from users in their branch
        branch_users = CustomUser.objects.filter(branch=request.user.branch)
        certificate_templates = CertificateTemplate.objects.filter(
            created_by__in=branch_users,
            is_active=True
        )
    else:
        # Other roles (learners, etc.) cannot see certificate templates in course settings
        certificate_templates = CertificateTemplate.objects.none()
    
    # Get available surveys for dropdown - RBAC filtered
    from course_reviews.models import Survey
    
    # Filter surveys based on user role
    if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
        # Super admins can see all surveys
        available_surveys = Survey.objects.filter(is_active=True)
    elif request.user.role in ['admin', 'instructor'] and request.user.branch:
        # Admins and instructors can see surveys from their branch or created by them
        available_surveys = Survey.objects.filter(
            Q(branch=request.user.branch) | Q(created_by=request.user),
            is_active=True
        ).distinct()
    else:
        # Other roles cannot see surveys in course settings
        available_surveys = Survey.objects.none()
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course_id}), 'label': course.title, 'icon': 'fa-graduation-cap'},
        {'label': 'Settings', 'icon': 'fa-cog'}
    ]
    
    # Handle form submission
    if request.method == 'POST':
        # Debug: Log all POST data
        # Process form submission
        
        # Process the form data
        # Course Info tab
        title = request.POST.get('title')
        course_code = request.POST.get('course_code')
        category_id = request.POST.get('category')
        instructor_id = request.POST.get('instructor')
        short_description = request.POST.get('short_description')
        course_image = request.FILES.get('course_image')
        course_video = request.FILES.get('course_video')
        
        # Course Availability tab
        catalog_visibility = request.POST.get('catalog_visibility')
        visibility = request.POST.get('visibility')
        public_enrollment = request.POST.get('public_enrollment') == 'on'
        enrollment_capacity = request.POST.get('enrollment_capacity')
        require_enrollment_approval = request.POST.get('require_enrollment_approval') == 'on'
        
        # Course Schedule tab
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        time_limit = request.POST.get('time_limit')
        retain_access = request.POST.get('retain_access') == 'on'
        prerequisites = request.POST.getlist('prerequisites')
        
        # Debug: Log prerequisites from form
        # Process prerequisites from form
        
        # Course Completion tab
        sequential_progression = request.POST.get('sequential_progression') == 'on'
        completion_criteria = request.POST.get('completion_criteria')
        completion_percentage = request.POST.get('completion_percentage')
        passing_score = request.POST.get('passing_score')
        course_outcomes = request.POST.get('course_outcomes')
        course_rubrics = request.POST.get('course_rubrics')
        
        # Process certificate settings for all users (including instructors)
        issue_certificate = request.POST.get('issue_certificate') == 'on'
        certificate_type = request.POST.get('certificate_type')
        certificate_template_id = request.POST.get('certificate_template')
        
        # Process survey selection (available to admins and instructors)
        survey_id = request.POST.get('survey')
        if survey_id:
            try:
                from course_reviews.models import Survey
                survey = Survey.objects.get(id=survey_id)
                course.survey = survey
            except Survey.DoesNotExist:
                messages.error(request, "Selected survey does not exist.")
        else:
            course.survey = None
        
        # Update course settings
        # Course Info
        if title:
            course.title = title
        if course_code is not None:
            course.course_code = course_code
        if short_description is not None:
            course.short_description = short_description
        if category_id:
            try:
                category = CourseCategory.objects.get(id=category_id)
                course.category = category
            except CourseCategory.DoesNotExist:
                messages.error(request, "Selected category does not exist.")
        if instructor_id:
            try:
                instructor = CustomUser.objects.get(id=instructor_id)
                course.instructor = instructor
            except CustomUser.DoesNotExist:
                messages.error(request, "Selected instructor does not exist.")
        if course_image:
            course.course_image = course_image
        if course_video:
            course.course_video = course_video
            
        # Course Availability
        if catalog_visibility:
            course.catalog_visibility = catalog_visibility
        if visibility:
            course.visibility = visibility
        course.public_enrollment = public_enrollment
        if enrollment_capacity:
            try:
                course.enrollment_capacity = int(enrollment_capacity)
            except ValueError:
                messages.error(request, "Invalid enrollment capacity value. Please enter a valid number.")
        else:
            course.enrollment_capacity = None
        course.require_enrollment_approval = require_enrollment_approval
        
        # Course Schedule
        if start_date:
            try:
                # Parse the datetime string and make it timezone-aware
                from datetime import datetime
                from django.utils import timezone
                
                # Parse the datetime string (format: YYYY-MM-DDTHH:MM)
                parsed_date = datetime.strptime(start_date, '%Y-%m-%dT%H:%M')
                
                # Make it timezone-aware using the current timezone
                course.start_date = timezone.make_aware(parsed_date)
            except ValueError as e:
                messages.error(request, f"Invalid start date format: {str(e)}")
                logger.warning(f"Invalid start date format for course {course.id}: {start_date}")
        else:
            course.start_date = None
        
        if end_date:
            try:
                # Parse the datetime string and make it timezone-aware
                from datetime import datetime
                from django.utils import timezone
                
                # Parse the datetime string (format: YYYY-MM-DDTHH:MM)
                parsed_date = datetime.strptime(end_date, '%Y-%m-%dT%H:%M')
                
                # Make it timezone-aware using the current timezone
                course.end_date = timezone.make_aware(parsed_date)
            except ValueError as e:
                messages.error(request, f"Invalid end date format: {str(e)}")
                logger.warning(f"Invalid end date format for course {course.id}: {end_date}")
        else:
            course.end_date = None
                
        # Set time limit
        if time_limit:
            try:
                course.time_limit_days = int(time_limit)
            except ValueError:
                messages.error(request, "Invalid time limit value. Please enter a valid number.")
        
        course.retain_access_after_completion = retain_access
        
        # Course Completion        
        course.sequential_progression = sequential_progression
        
        # Map completion_criteria to the corresponding model fields
        if completion_criteria == 'all_content':
            course.all_topics_complete = True
            course.minimum_score = False
        elif completion_criteria == 'final_assessment':
            course.all_topics_complete = False
            course.minimum_score = True
        elif completion_criteria == 'custom':
            # For custom criteria, keep both flags false
            course.all_topics_complete = False
            course.minimum_score = False
            
        # Set completion percentage
        if completion_percentage:
            try:
                course.completion_percentage = int(completion_percentage)
            except ValueError:
                messages.error(request, "Invalid completion percentage value. Please enter a valid number.")
        
        # Set passing score
        if passing_score:
            try:
                course.passing_score = int(passing_score)
            except ValueError:
                messages.error(request, "Invalid passing score value. Please enter a valid number.")
        
        # Set TinyMCE fields
        if course_outcomes:
            course.course_outcomes = course_outcomes
        
        if course_rubrics:
            course.course_rubrics = course_rubrics
        
        # Set certificate settings (only for non-instructor users)
        if request.user.role != 'instructor':
            course.issue_certificate = issue_certificate
            if certificate_type:
                course.certificate_type = certificate_type
            
            # Set certificate template
            if certificate_template_id:
                try:
                    certificate_template = CertificateTemplate.objects.get(id=certificate_template_id)
                    course.certificate_template = certificate_template
                except CertificateTemplate.DoesNotExist:
                    messages.error(request, "Selected certificate template does not exist.")
            else:
                course.certificate_template = None
                
        try:
            course.save()
            
            # Handle custom completion requirements if completion criteria is custom
            if completion_criteria == 'custom':
                # Import the model
                from .models import CourseCompletionRequirement
                
                # Get selected topics and their scores
                selected_topics = request.POST.getlist('completion_topics')
                
                # Clear existing requirements
                CourseCompletionRequirement.objects.filter(course=course).delete()
                
                # Create new requirements
                for topic_id in selected_topics:
                    try:
                        topic = Topic.objects.get(id=topic_id)
                        # Get the score for this topic
                        score_field_name = f'topic_score_{topic_id}'
                        required_score = request.POST.get(score_field_name, '0')
                        
                        # Convert to integer, default to 0 if invalid
                        try:
                            required_score = int(required_score)
                            if required_score < 0:
                                required_score = 0
                            elif required_score > 100:
                                required_score = 100
                        except (ValueError, TypeError):
                            required_score = 0
                        
                        # Create the requirement
                        CourseCompletionRequirement.objects.create(
                            course=course,
                            topic=topic,
                            required_score=required_score,
                            is_mandatory=True
                        )
                        
                    except Topic.DoesNotExist:
                        messages.error(request, f"Topic with ID {topic_id} does not exist.")
                    except Exception as e:
                        messages.error(request, f"Error adding completion requirement for topic {topic_id}: {str(e)}")
                
                if selected_topics:
                    messages.success(request, f"Custom completion requirements saved for {len(selected_topics)} topics.")
            
            # Handle prerequisites with auto-enrollment and deselection AFTER course save
            # Get current prerequisites before clearing
            current_prereq_ids = set(course.prerequisites.values_list('id', flat=True))
            new_prereq_ids = set(int(id) for id in prerequisites) if prerequisites else set()
            
            # Debug: Log prerequisite changes
            # Update prerequisites for course
            
            # Clear existing prerequisites and add new ones
            course.prerequisites.clear()
            
            if prerequisites:
                # Add new prerequisites
                for prereq_id in prerequisites:
                    try:
                        prereq_course = Course.objects.get(id=prereq_id)
                        
                        # Check for circular dependencies before adding
                        if course in prereq_course.prerequisites.all():
                            messages.warning(request, f"Cannot add '{prereq_course.title}' as prerequisite - it would create a circular dependency.")
                            continue
                        
                        course.prerequisites.add(prereq_course)
                        # Added prerequisite successfully
                                    
                    except Course.DoesNotExist:
                        messages.error(request, f"Prerequisite course with ID {prereq_id} does not exist.")
                    except Exception as e:
                        messages.error(request, f"Error adding prerequisite {prereq_id}: {str(e)}")
                        logger.error(f"Error adding prerequisite {prereq_id}: {str(e)}")
            
            # Use the utility function to handle auto-enrollment and unenrollment
            from .utils import handle_prerequisite_changes
            enrolled_users_count, unenrolled_users_count = handle_prerequisite_changes(
                course, current_prereq_ids, new_prereq_ids
            )
            
            # Show feedback messages
            if enrolled_users_count > 0:
                messages.success(request, f"Successfully auto-enrolled {enrolled_users_count} users from newly selected prerequisite courses.")
            
            if unenrolled_users_count > 0:
                messages.info(request, f"Auto-unenrolled {unenrolled_users_count} users from deselected prerequisite courses.")
            
            messages.success(request, "Course settings updated successfully.")
            return redirect('courses:course_edit', course_id=course_id)
        except Exception as e:
            messages.error(request, f"Error saving course settings: {str(e)}")
    
    # Set initial values for the form based on course settings
    enrollment_type = 'open'
    if not course.public_enrollment:
        enrollment_type = 'invite'
    elif course.require_enrollment_approval:
        enrollment_type = 'approval'
        
    completion_criteria = 'custom'
    if course.all_topics_complete:
        completion_criteria = 'all_content'
    elif course.minimum_score:
        completion_criteria = 'final_assessment'
        
    context = {
        'course': course,
        'breadcrumbs': breadcrumbs,
        'enrollment_type': enrollment_type,
        'completion_criteria': completion_criteria,
        'categories': categories,
        'instructors': instructors,
        'all_courses': all_courses,
        'certificate_templates': certificate_templates,
        'available_surveys': available_surveys,
    }
    
    return render(request, 'courses/course_settings.html', context)

@login_required
def create_course(request):
    """Create a new course"""
    if not (request.user.role in ['admin', 'superadmin', 'instructor']):
        return HttpResponseForbidden("You don't have permission to create courses")
        
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                # Create the course
                course = form.save(commit=False)
                
                # Set branch based on user's role
                if request.user.role == 'superadmin':
                    # For superadmin, branch should come from the form (optional)
                    # Super admin operates at business level, not branch level
                    course._created_by_superadmin = True
                elif request.user.branch:
                    # For other roles, use their assigned branch
                    course.branch = request.user.branch
                
                # If instructor is creating, assign themselves as instructor
                if request.user.role == 'instructor':
                    course.instructor = request.user
                
                course.save()
                
                # Ensure the course creator is enrolled in the course
                # This is important for branch admins and other non-instructor roles
                CourseEnrollment.objects.get_or_create(
                    course=course,
                    user=request.user,
                    defaults={
                        'enrollment_source': 'manual'
                    }
                )
                
                # Save many-to-many relationships
                form.save_m2m()
                
                # Create initial "Welcome" section
                Section.objects.create(
                    name="Welcome",
                    course=course,
                    order=0
                )
                
                messages.success(request, f"Course '{course.title}' created successfully!")
                return redirect('courses:edit_course', course_id=course.id)
                
            except ValidationError as e:
                messages.error(request, f"Validation error: {str(e)}")
            except PermissionError as e:
                messages.error(request, f"Permission error: {str(e)}")
            except IntegrityError as e:
                messages.error(request, f"Database error: {str(e)}")
            except OSError as e:
                messages.error(request, f"File system error: {str(e)}")
            except Exception as e:
                from role_management.utils import SessionErrorHandler
                logger.error(f"Unexpected error creating course: {str(e)}", exc_info=True)
                
                # Provide more specific error message based on exception type
                error_message = SessionErrorHandler.log_and_sanitize_error(
                    e, request, error_type='system', operation='course creation'
                )
                messages.error(request, error_message)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = CourseForm(user=request.user)
        
    context = {
        'form': form,
        'title': 'Create Course',
        'button_text': 'Create Course',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard'},
            {'url': reverse('courses:course_list'), 'label': 'Courses'},
            {'label': 'Create Course'}
        ]
    }
    return render(request, 'courses/create_course.html', context)

@login_required
def course_create(request):
    # ... existing code ...
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            # Process category_id properly - ensure it's converted to int if exists
            category_id = form.cleaned_data.get('category_id')
            course = form.save(commit=False)
            
            # Ensure category_id is properly converted to integer if needed
            if category_id and isinstance(category_id, str) and category_id.isdigit():
                category_id = int(category_id)
                
            if category_id:
                try:
                    category = CourseCategory.objects.get(id=category_id)
                    course.category = category
                except (CourseCategory.DoesNotExist, ValueError):
                    logger.warning(f"Invalid category ID: {category_id}, ignoring")
            
            # ... rest of existing code ...


@login_required
@require_http_methods(["POST"])
def api_topic_reorder(request):
    """
    Reorder topics within a section - API endpoint
    Consistent API endpoint naming pattern
    """
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        section_id = data.get('section_id')  # Can be None for standalone topics
        topic_orders = data.get('topic_orders', [])
        
        # Validate data
        if not course_id:
            return JsonResponse({
                'success': False,
                'error': 'Course ID is required'
            }, status=400)
            
        # Ensure course_id is integer
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid course ID format'
            }, status=400)
        
        # Get the course
        course = get_object_or_404(Course, id=course_id)
        
        # Check permissions using standard check_course_edit_permission function
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to edit this course'
            }, status=403)
        
        # If section_id is not None, verify it exists
        section = None
        # Handle 'null' string or None values - both mean we're dealing with standalone topics
        if section_id is not None and section_id != 'null' and section_id != '':
            try:
                section_id = int(section_id)
                section = Section.objects.get(id=section_id, course=course)
            except (ValueError, TypeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid section ID format'
                }, status=400)
            except Section.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Section with ID {section_id} not found'
                }, status=404)
        
        # Process the order updates
        for order_item in topic_orders:
            topic_id = order_item.get('topic_id')
            order = order_item.get('order')
            item_section_id = order_item.get('section_id')
            
            # Skip items with missing data
            if not topic_id or not order:
                continue
                
            # Ensure proper type conversion
            try:
                topic_id = int(topic_id)
                order = int(order)
            except (ValueError, TypeError):
                continue
            
            # Handle the case where item_section_id might be different from the main section_id
            # This can happen when topics are moved between sections during drag-and-drop
            target_section = None
            if item_section_id is not None and item_section_id != 'null' and item_section_id != '':
                try:
                    item_section_id = int(item_section_id)
                    target_section = Section.objects.get(id=item_section_id, course=course)
                except (ValueError, TypeError, Section.DoesNotExist):
                    # If there's an issue with the specified section, use the default section
                    target_section = section
            else:
                target_section = section

            # Get the topic and update it
            try:
                # Find the topic using the CourseTopic relationship
                topic = Topic.objects.filter(
                    id=topic_id,
                    coursetopic__course=course
                ).first()
                
                if not topic:
                    logger.warning(f"Topic {topic_id} not found or not associated with course {course.id}")
                    continue
                
                # Update the topic's section and order
                topic.section = target_section
                topic.order = order
                topic.save()
                
                # Also update the CourseTopic relationship order to ensure consistency
                course_topic_relation = CourseTopic.objects.filter(
                    course=course,
                    topic=topic
                ).first()
                
                if course_topic_relation:
                    course_topic_relation.order = order
                    course_topic_relation.save()
                    logger.info(f"Updated CourseTopic relation for topic {topic_id} to order {order}")
                
                section_name = target_section.name if target_section else "standalone"
                logger.info(f"Updated topic {topic_id} to order {order} in section {section_name}")
            except Exception as e:
                logger.warning(f"Error updating topic {topic_id}: {str(e)}")
                continue
        
        return JsonResponse({
            'success': True,
            'message': 'Topic order updated successfully'
        })
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error reordering topics: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error reordering topics: {str(e)}")
        logger.exception("Exception details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def api_section_reorder(request):
    """
    Reorder sections - API endpoint
    """
    try:
        # Parse the JSON data
        data = json.loads(request.body)
        course_id = data.get('course_id')
        section_orders = data.get('section_orders', [])
        
        # Validate required data
        if not course_id or not section_orders:
            return JsonResponse({
                'success': False,
                'error': 'Course ID and section orders are required'
            }, status=400)
            
        # Ensure proper type conversion
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid course ID format'
            }, status=400)
        
        # Get the course
        course = get_object_or_404(Course, id=course_id)
        
        # Check permissions
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to edit this course'
            }, status=403)
            
        # Clean the section order data to prevent duplicates
        seen_section_ids = set()
        cleaned_section_orders = []
        
        for order_item in section_orders:
            section_id = order_item.get('section_id')
            
            # Skip the 'standalone' section entry - it's not a real database section
            if section_id == 'standalone':
                logger.info("Skipping standalone section in reordering")
                continue
                
            # Ensure proper type conversion for real section ids
            try:
                section_id = int(section_id)
            except (ValueError, TypeError):
                continue
                
            if section_id not in seen_section_ids:
                seen_section_ids.add(section_id)
                cleaned_section_orders.append(order_item)
        
        # Use the cleaned list instead
        section_orders = cleaned_section_orders
        
        # Process the order updates
        for order_item in section_orders:
            section_id = order_item.get('section_id')
            order = order_item.get('order')
            
            # Skip items with missing data or standalone sections
            if not section_id or not order or section_id == 'standalone':
                continue
                
            # Ensure proper type conversion
            try:
                section_id = int(section_id)
                order = int(order)
            except (ValueError, TypeError):
                continue
            
            # Get the section and update it
            try:
                section = Section.objects.get(id=section_id, course=course)
                section.order = order
                section.save()
                logger.info(f"Updated section {section_id} to order {order}")
            except Section.DoesNotExist:
                logger.warning(f"Section {section_id} not found during reordering")
                continue
        
        return JsonResponse({
            'success': True,
            'message': 'Section order updated successfully'
        })
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error reordering sections: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error reordering sections: {str(e)}")
        logger.exception("Exception details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def api_topic_move(request):
    """
    Move a topic to a different section - API endpoint
    Consistent API endpoint naming pattern
    """
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        topic_id = data.get('topic_id')
        section_id = data.get('section_id')  # Can be None for standalone topics
        new_order = data.get('new_order')
        
        # Validate required data
        if not course_id or not topic_id or new_order is None:
            return JsonResponse({
                'success': False,
                'error': 'Course ID, topic ID, and new order are required'
            }, status=400)
            
        # Ensure proper type conversion
        try:
            course_id = int(course_id)
            topic_id = int(topic_id)
            new_order = int(new_order)
            if section_id is not None:
                section_id = int(section_id)
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid ID format'
            }, status=400)
        
        # Get the course and topic
        course = get_object_or_404(Course, id=course_id)
        topic = get_object_or_404(Topic, id=topic_id, coursetopic__course=course)
        
        # Check permissions
        if not check_course_edit_permission(request.user, course):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to edit this course'
            }, status=403)
        
        # Store the old section for later reference
        old_section = topic.section
        old_section_id = old_section.id if old_section else None
        
        # Get the target section if specified
        target_section = None
        if section_id is not None:
            target_section = get_object_or_404(Section, id=section_id, course=course)
        
        # Step 1: If moving from one section to another, reorder topics in old section
        if old_section != target_section:
            if old_section:
                # Get all topics from old section except the one being moved
                old_section_topics = list(Topic.objects.filter(section=old_section).exclude(id=topic_id).order_by('order'))
                
                # Reorder topics in old section to close the gap
                for i, t in enumerate(old_section_topics):
                    new_pos = i + 1
                    if t.order != new_pos:
                        t.order = new_pos
                        t.save()
                        
                        # Update CourseTopic relation for consistency
                        course_topic = CourseTopic.objects.filter(course=course, topic=t).first()
                        if course_topic:
                            course_topic.order = new_pos
                            course_topic.save()
            
            # Set the topic's new section
            topic.section = target_section
        
        # Step 2: Handle ordering in the target section
        if target_section:
            # Get all topics in target section (excluding the topic being moved)
            target_section_topics = list(Topic.objects.filter(section=target_section).exclude(id=topic_id).order_by('order'))
            
            # Insert the topic at the new position
            target_section_topics.insert(new_order - 1, topic)
            
            # Update all topic orders
            for i, t in enumerate(target_section_topics):
                new_pos = i + 1
                if t.order != new_pos or t.id == topic_id:
                    t.order = new_pos
                    t.save()
                    
                    # Update CourseTopic relation for consistency
                    course_topic = CourseTopic.objects.filter(course=course, topic=t).first()
                    if course_topic:
                        course_topic.order = new_pos
                        course_topic.save()
        else:
            # Moving to standalone (no section)
            # Get all standalone topics for this course
            standalone_topics = list(Topic.objects.filter(section=None, coursetopic__course=course).exclude(id=topic_id).order_by('order'))
            
            # Insert the topic at the new position
            standalone_topics.insert(new_order - 1, topic)
            
            # Update all topic orders
            for i, t in enumerate(standalone_topics):
                new_pos = i + 1
                if t.order != new_pos or t.id == topic_id:
                    t.order = new_pos
                    t.save()
                    
                    # Update CourseTopic relation for consistency
                    course_topic = CourseTopic.objects.filter(course=course, topic=t).first()
                    if course_topic:
                        course_topic.order = new_pos
                        course_topic.save()
        
        # Save the topic to ensure all changes are persisted
        topic.save()
        
        # Log the move operation
        if old_section_id != section_id:
            logger.info(f"Moved topic {topic_id} from section {old_section_id} to {section_id} with order {new_order}")
        else:
            logger.info(f"Updated topic {topic_id} order to {new_order} in section {section_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Topic moved successfully'
        })
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error moving topic: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error moving topic: {str(e)}")
        logger.exception("Exception details:")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def course_users(request, course_id):
    """View to display and manage users enrolled in a course with proper role categorization"""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to view the course
    if not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to manage users for this course.")
        return redirect('courses:course_list')
    
    # Import the new course permissions utility
    from core.utils.course_permissions import CourseAccessManager
    
    # Use the new CourseAccessManager to properly categorize users
    categorized_users = CourseAccessManager.categorize_course_users(course)
    
    # Extract enrollment objects for backward compatibility with template
    learner_enrollments = [item['enrollment'] for item in categorized_users['learners']]
    instructor_enrollments = [item['enrollment'] for item in categorized_users['instructors']]
    
    # Only show admin enrollments to superusers and admins, not to instructors
    if request.user.is_superuser or request.user.role == 'admin':
        admin_enrollments = [item['enrollment'] for item in categorized_users['admins']]
    else:
        admin_enrollments = []
    
    other_enrollments = [item['enrollment'] for item in categorized_users['others']]
    
    # Add search functionality
    search_query = request.GET.get('q', '')
    if search_query:
        search_filter = Q(user__username__icontains=search_query) | \
                       Q(user__email__icontains=search_query) | \
                       Q(user__first_name__icontains=search_query) | \
                       Q(user__last_name__icontains=search_query)
        
        # Apply search filter to the enrollment QuerySets
        if learner_enrollments:
            learner_enrollments = CourseEnrollment.objects.filter(
                id__in=[e.id for e in learner_enrollments]
            ).filter(search_filter)
        else:
            learner_enrollments = CourseEnrollment.objects.none()
            
        if instructor_enrollments:
            instructor_enrollments = CourseEnrollment.objects.filter(
                id__in=[e.id for e in instructor_enrollments]
            ).filter(search_filter)
        else:
            instructor_enrollments = CourseEnrollment.objects.none()
            
        if admin_enrollments:
            admin_enrollments = CourseEnrollment.objects.filter(
                id__in=[e.id for e in admin_enrollments]
            ).filter(search_filter)
        else:
            admin_enrollments = CourseEnrollment.objects.none()
            
        if other_enrollments:
            other_enrollments = CourseEnrollment.objects.filter(
                id__in=[e.id for e in other_enrollments]
            ).filter(search_filter)
        else:
            other_enrollments = CourseEnrollment.objects.none()
    
    # Combine all enrollments for pagination but maintain categorization
    all_enrollments = list(learner_enrollments) + list(instructor_enrollments) + list(admin_enrollments) + list(other_enrollments)
    enrollments = all_enrollments
    
    # Get user roles from group memberships
    # Import models using get_model to avoid circular imports
    BranchGroup = apps.get_model('groups', 'BranchGroup')
    GroupMembership = apps.get_model('groups', 'GroupMembership')
    
    # Get all course groups for this course
    course_group = None
    try:
        CourseGroup = apps.get_model('groups', 'CourseGroup')
        course_group_relation = CourseGroup.objects.filter(course=course).first()
        course_group = course_group_relation.group if course_group_relation else None
    except:
        pass
    
    # Create a dictionary of user_id -> role information
    user_roles = {}
    if course_group:
        # Get all memberships for the course group
        memberships = GroupMembership.objects.filter(
            group=course_group
        ).select_related('user', 'custom_role')
        
        for membership in memberships:
            if membership.custom_role:
                user_roles[membership.user.id] = {
                    'role_name': membership.custom_role.name,
                    'can_edit': membership.custom_role.can_edit,
                    'can_manage_members': membership.custom_role.can_manage_members,
                    'can_manage_content': membership.custom_role.can_manage_content
                }
    
    # Get available roles for the dropdown
    GroupMemberRole = apps.get_model('groups', 'GroupMemberRole')
    available_roles = GroupMemberRole.objects.filter(group=course_group).order_by('name') if course_group else []
    
    # Pagination
    paginator = Paginator(enrollments, 10)  # Show 10 enrollments per page
    page = request.GET.get('page', 1)
    
    try:
        enrollments_page = paginator.page(page)
    except PageNotAnInteger:
        enrollments_page = paginator.page(1)
    except EmptyPage:
        enrollments_page = paginator.page(paginator.num_pages)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'label': 'Course Users', 'icon': 'fa-users'}
    ]
    
    context = {
        'course': course,
        'enrollments': enrollments_page,
        'paginator': paginator,
        'breadcrumbs': breadcrumbs,
        'search_query': search_query,
        'user_roles': user_roles,
        'available_roles': available_roles,
        'course_group': course_group,
        # Add categorized enrollments for better role-based display
        'learner_enrollments': learner_enrollments,
        'instructor_enrollments': instructor_enrollments,
        'admin_enrollments': admin_enrollments,
        'other_enrollments': other_enrollments,
        'categorized_users': categorized_users,
        'total_learners': len(learner_enrollments) if isinstance(learner_enrollments, list) else learner_enrollments.count(),
        'total_instructors': len(instructor_enrollments) if isinstance(instructor_enrollments, list) else instructor_enrollments.count(),
        'total_admins': len(admin_enrollments) if isinstance(admin_enrollments, list) else admin_enrollments.count(),
        'total_others': len(other_enrollments) if isinstance(other_enrollments, list) else other_enrollments.count()
    }
    
    return render(request, 'courses/course_users.html', context)

@login_required
def course_add_users(request, course_id):
    """View to add users to a course"""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to add users to the course
    if not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to add users to this course.")
        return redirect('courses:course_list')
    
    # Handle form submission (POST request)
    if request.method == 'POST':
        user_ids = request.POST.getlist('user_ids')
        if user_ids:
            from groups.models import BranchGroup, GroupMembership, GroupMemberRole, CourseGroupAccess
            
            for user_id in user_ids:
                try:
                    user_id = int(user_id)
                    user = CustomUser.objects.get(id=user_id)
                    
                    # Create enrollment using the enrollment service
                    from core.utils.enrollment import EnrollmentService
                    enrollment, created, message = EnrollmentService.create_or_get_enrollment(
                        user=user,
                        course=course,
                        source='manual'
                    )
                    
                    # For instructors, just enroll them - no automatic group creation
                    if user.role == 'instructor':
                        
                        if created:
                            messages.success(request, f"Instructor {user.get_full_name()} has been added to this course with editing permissions.")
                        else:
                            messages.info(request, f"Instructor {user.get_full_name()} was already enrolled in this course.")
                    else:
                        # For non-instructors (learners), just enrollment is sufficient
                        if created:
                            messages.success(request, f"{user.get_full_name()} has been enrolled in this course.")
                        else:
                            messages.info(request, f"{user.get_full_name()} was already enrolled in this course.")
                        
                except (ValueError, CustomUser.DoesNotExist):
                    messages.error(request, f"User with ID {user_id} does not exist.")
                except Exception as e:
                    messages.error(request, f"Error enrolling user: {str(e)}")
                    logger.error(f"Error in course_add_users for user {user_id}: {str(e)}")
            
            return redirect('courses:course_users', course_id=course.id)
    
    # Get all active users who are not already enrolled in the course
    enrolled_user_ids = CourseEnrollment.objects.filter(course=course).values_list('user_id', flat=True)
    
    # Get users from the same branch as the course
    if request.user.is_superuser:
        available_users = CustomUser.objects.filter(is_active=True).exclude(id__in=enrolled_user_ids)
    elif request.user.role == 'admin':
        # Admin can add users from their own branch except superadmin users
        available_users = CustomUser.objects.filter(
            is_active=True, 
            branch=request.user.branch
        ).exclude(
            id__in=enrolled_user_ids
        ).exclude(
            role='superadmin'
        ).exclude(
            is_superuser=True
        )
    else:
        # Instructors can add users from their own branch except superadmin and admin users
        available_users = CustomUser.objects.filter(
            is_active=True,
            branch=request.user.branch
        ).exclude(
            id__in=enrolled_user_ids
        ).exclude(
            role='superadmin'
        ).exclude(
            role='admin'
        ).exclude(
            is_superuser=True
        )
    
    # Add filtering for super admin users
    business_filter = request.GET.get('business', '')
    branch_filter = request.GET.get('branch', '')
    
    if request.user.is_superuser:
        if business_filter:
            available_users = available_users.filter(branch__business_id=business_filter)
        if branch_filter:
            available_users = available_users.filter(branch_id=branch_filter)
    
    # Add search functionality
    search_query = request.GET.get('q', '')
    if search_query:
        available_users = available_users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(branch__name__icontains=search_query) |
            Q(branch__business__name__icontains=search_query)
        )
    
    # Select related to avoid N+1 queries when displaying branch/business info
    available_users = available_users.select_related('branch', 'branch__business')
    
    # Order by business, branch, then name for super admin users
    if request.user.is_superuser:
        available_users = available_users.order_by(
            'branch__business__name', 
            'branch__name', 
            'first_name', 
            'last_name'
        )
    else:
        available_users = available_users.order_by('first_name', 'last_name')
    
    # Pagination
    per_page = request.GET.get('per_page', 10)
    try:
        per_page = int(per_page)
        # Limit per_page to reasonable values
        per_page = min(max(per_page, 10), 100)
    except (ValueError, TypeError):
        per_page = 10
        
    paginator = Paginator(available_users, per_page)
    page = request.GET.get('page', 1)
    
    try:
        available_users_page = paginator.page(page)
    except PageNotAnInteger:
        available_users_page = paginator.page(1)
    except EmptyPage:
        available_users_page = paginator.page(paginator.num_pages)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'url': reverse('courses:course_users', kwargs={'course_id': course.id}), 'label': 'Course Users', 'icon': 'fa-users'},
        {'label': 'Add Users', 'icon': 'fa-user-plus'}
    ]
    
    # Get business and branch data for super admin filters
    businesses = []
    branches = []
    if request.user.is_superuser:
        from business.models import Business
        from branches.models import Branch
        businesses = Business.objects.filter(is_active=True).order_by('name')
        branches = Branch.objects.filter(is_active=True).select_related('business').order_by('business__name', 'name')

    context = {
        'course': course,
        'available_users': available_users_page,
        'paginator': paginator,
        'breadcrumbs': breadcrumbs,
        'search_query': search_query,
        'per_page': per_page,
        'businesses': businesses,
        'branches': branches,
        'business_filter': business_filter,
        'branch_filter': branch_filter,
        'is_superuser': request.user.is_superuser
    }
    
    return render(request, 'courses/course_add_users.html', context)

@login_required
def get_course_progress(request, course_id):
    """API endpoint to get the current progress for a course"""
    from django.core.cache import cache
    from django.views.decorators.cache import cache_page
    
    course = get_object_or_404(Course, id=course_id)
    
    # Check permission to access course
    if not check_course_permission(request.user, course):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Check cache first (cache for 5 minutes to reduce DB load)
    cache_key = f"course_progress_{course_id}_{request.user.id}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return JsonResponse(cached_result)
    
    # Get progress information
    try:
        # Get all topics for this course with optimized query
        course_topics = CourseTopic.objects.filter(course=course).select_related('topic').prefetch_related('topic__topicprogress_set')
        topics_data = []
        
        # Get overall course progress
        total_topics = course_topics.count()
        if total_topics == 0:
            result = {
                'success': True,
                'overall_progress': 0,
                'completed_topics': 0,
                'total_topics': 0,
                'topics': []
            }
            cache.set(cache_key, result, 300)  # Cache for 5 minutes
            return JsonResponse(result)
            
        # Get or create enrollment for this user
        enrollment, created, message = EnrollmentService.create_or_get_enrollment(
            user=request.user,
            course=course,
            source='manual'
        )
        
        # Calculate overall progress
        overall_progress = enrollment.get_progress()
        
        # Get progress data for each topic - optimized single query
        topic_ids = [ct.topic.id for ct in course_topics]
        existing_progress = TopicProgress.objects.filter(
            user=request.user,
            topic_id__in=topic_ids
        ).select_related('topic')
        
        # Map of topic ID to progress for efficient lookup
        progress_by_topic_id = {p.topic.id: p for p in existing_progress}
        
        # Batch create missing progress records
        missing_progresses = []
        for course_topic in course_topics:
            topic = course_topic.topic
            
            # Get existing progress
            progress = progress_by_topic_id.get(topic.id)
            if not progress:
                # Add to batch create list
                missing_progresses.append(TopicProgress(
                    user=request.user,
                    topic=topic,
                    completed=False
                ))
        
        # Batch create missing progress records
        if missing_progresses:
            created_progresses = TopicProgress.objects.bulk_create(missing_progresses)
            # Initialize progress data for newly created records
            for progress in created_progresses:
                progress.init_progress_data()
                progress_by_topic_id[progress.topic.id] = progress
        
        # For each topic in the course, get progress data
        completed_topics = 0
        for course_topic in course_topics:
            topic = course_topic.topic
            
            # Get progress (now guaranteed to exist)
            progress = progress_by_topic_id.get(topic.id)
            if not progress:
                continue
                
            # Get progress percentage
            topic_progress = 0
            if progress.completed:
                topic_progress = 100
                completed_topics += 1
            elif topic.content_type in ['Video', 'EmbedVideo', 'Audio'] and progress.progress_data:
                topic_progress = progress.progress_data.get('progress', 0)
                
            # Add to topics data
            topics_data.append({
                'id': topic.id,
                'title': topic.title,
                'progress': topic_progress,
                'completed': progress.completed,
                'content_type': topic.content_type
            })
        
        result = {
            'success': True,
            'overall_progress': round(overall_progress),
            'completed_topics': completed_topics,
            'total_topics': total_topics,
            'topics': topics_data
        }
        
        # Cache the result for 5 minutes
        cache.set(cache_key, result, 300)
        
        return JsonResponse(result)
    except Exception as e:
        import traceback
        logger.error(f"Error getting course progress for course {course_id}: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def course_add_groups(request, course_id):
    """Add groups to a course."""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to edit the course
    if not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to edit this course.")
        return redirect('courses:course_list')
    
    # Get all groups not already associated with this course
    existing_group_ids = CourseGroup.objects.filter(course=course).values_list('group_id', flat=True)
    available_groups = BranchGroup.objects.exclude(id__in=existing_group_ids).order_by('name')
    
    # Pagination logic
    paginator = Paginator(available_groups, 10)
    page = request.GET.get('page', 1)
    
    try:
        available_groups = paginator.page(page)
    except PageNotAnInteger:
        available_groups = paginator.page(1)
    except EmptyPage:
        available_groups = paginator.page(paginator.num_pages)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'url': reverse('groups:group_list') + '?tab=course-groups', 'label': 'Groups', 'icon': 'fa-users'},
        {'label': 'Add Groups', 'icon': 'fa-plus'}
    ]
    
    context = {
        'course': course,
        'available_groups': available_groups,
        'paginator': paginator,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'courses/course_add_groups.html', context)

@login_required
@require_POST
def add_group_to_course(request, course_id, group_id):
    """Add a group to a course."""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to edit the course
    if not check_course_edit_permission(request.user, course):
        return JsonResponse({
            'success': False,
            'error': "You don't have permission to edit this course."
        }, status=403)
    
    # Get the group
    try:
        group = BranchGroup.objects.get(pk=group_id)
    except BranchGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "The selected group does not exist."
        }, status=404)
    
    # Check if the group is already associated with the course
    if CourseGroup.objects.filter(course=course, group=group).exists():
        return JsonResponse({
            'success': False,
            'error': "This group is already associated with the course."
        }, status=400)
    
    # Create the association
    course_group = CourseGroup.objects.create(
        course=course,
        group=group,
        created_by=request.user
    )
    
    return JsonResponse({
        'success': True,
        'message': f"Group '{group.name}' has been added to the course."
    })

@login_required
@require_POST
def remove_group_from_course(request, course_id, group_id):
    """Remove a group from a course."""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to edit the course
    if not check_course_edit_permission(request.user, course):
        return JsonResponse({
            'success': False,
            'error': "You don't have permission to edit this course."
        }, status=403)
    
    # Get the group
    try:
        group = BranchGroup.objects.get(pk=group_id)
    except BranchGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "The selected group does not exist."
        }, status=404)
    
    # Check if the group is associated with the course
    try:
        course_group = CourseGroup.objects.get(course=course, group=group)
        course_group.delete()
        return JsonResponse({
            'success': True,
            'message': f"Group '{group.name}' has been removed from the course."
        })
    except CourseGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': "This group is not associated with the course."
        }, status=400)

def stream_video(request, path):
    """
    Stream video content with proper headers for efficient buffering
    Enhanced for S3 storage with proper error handling and CORS support
    Requires authentication for security
    """
    try:
        # Decode URL-encoded path to handle spaces in filenames
        import urllib.parse
        path = urllib.parse.unquote(path)
        
        # Sanitize path to prevent path traversal attacks
        path = path.replace('..', '').replace('\\', '/').lstrip('/')
        
        # Log video access attempts for security monitoring
        user_info = f"User: {request.user.id if request.user.is_authenticated else 'Anonymous'}"
        ip_address = request.META.get('REMOTE_ADDR', 'Unknown')
        logger.info(f"Video access attempt: {path} by {user_info} from {ip_address}")
        
        # Basic security check - ensure path is within expected video directory
        if not path.startswith('course_videos/'):
            logger.warning(f"Suspicious video path access: {path}")
            return HttpResponseForbidden('Invalid video path')
        
        # For S3 storage, we need to handle this differently
        from django.core.files.storage import default_storage
        import mimetypes
        import re
        from wsgiref.util import FileWrapper
        
        # Skip existence check since MediaS3Storage.exists() always returns False
        # Instead, try to generate the URL directly
        try:
            # Generate S3 URL - this will work if file exists
            file_url = default_storage.url(path)
            if not file_url:
                logger.error(f"Video file not found: {path}")
                return HttpResponseNotFound('Video file not found')
                
        except Exception as open_error:
            error_msg = str(open_error).lower()
            if "403" in error_msg or "forbidden" in error_msg:
                logger.error(f"S3 permission denied for video file: {path}")
                return HttpResponseForbidden('Access denied to video file')
            elif "nosuchkey" in error_msg or "not found" in error_msg:
                logger.error(f"Video file not found: {path}")
                return HttpResponseNotFound('Video file not found')
            else:
                logger.error(f"Error accessing video file {path}: {open_error}")
                return HttpResponseNotFound('Video file not found')
        
        # Get content type based on file extension
        content_type, encoding = mimetypes.guess_type(path)
        if not content_type:
            # Determine content type by file extension
            if path.lower().endswith('.mp4'):
                content_type = 'video/mp4'
            elif path.lower().endswith('.webm'):
                content_type = 'video/webm'
            elif path.lower().endswith('.ogg'):
                content_type = 'video/ogg'
            elif path.lower().endswith('.avi'):
                content_type = 'video/avi'
            elif path.lower().endswith('.mov'):
                content_type = 'video/quicktime'
            else:
                content_type = 'video/mp4'  # Default fallback
        
        # For authenticated video streaming, we'll proxy through Django
        # This ensures authentication is maintained while allowing video playback
        try:
            # Stream the video content directly through Django
            return _stream_video_direct(request, path, content_type)
            
        except Exception as s3_error:
            logger.error(f"Error streaming video {path}: {s3_error}")
            return HttpResponseServerError('Error streaming video')
        
    except Exception as e:
        logger.error(f"Error streaming video {path}: {str(e)}", exc_info=True)
        return HttpResponseServerError('Error streaming video')


def _stream_video_direct(request, path, content_type):
    """
    Fallback method to stream video directly through Django
    Used when S3 redirect fails
    """
    try:
        from django.core.files.storage import default_storage
        
        # Try to open the file from S3
        file_obj = default_storage.open(path)
        
        # Get file size if possible
        try:
            file_size = file_obj.size
        except:
            file_size = None
        
        # Handle range requests for video seeking
        range_header = request.META.get('HTTP_RANGE', '').strip()
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        
        if range_match and file_size:
            first_byte, last_byte = range_match.groups()
            first_byte = int(first_byte) if first_byte else 0
            last_byte = int(last_byte) if last_byte else file_size - 1
            
            if last_byte >= file_size:
                last_byte = file_size - 1
                
            length = last_byte - first_byte + 1
            
            # Seek to the start position
            file_obj.seek(first_byte)
            
            # Create streaming response for partial content
            def file_iterator():
                remaining = length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
                file_obj.close()
            
            response = StreamingHttpResponse(
                file_iterator(),
                status=206,
                content_type=content_type
            )
            
            response['Content-Length'] = str(length)
            response['Content-Range'] = f'bytes {first_byte}-{last_byte}/{file_size}'
        else:
            # Full file streaming
            def file_iterator():
                while True:
                    chunk = file_obj.read(8192)
                    if not chunk:
                        break
                    yield chunk
                file_obj.close()
            
            response = StreamingHttpResponse(
                file_iterator(),
                content_type=content_type
            )
            
            if file_size:
                response['Content-Length'] = str(file_size)
        
        # Add essential headers for video streaming
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'public, max-age=3600'
        
        # Add CORS headers
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Range, Content-Range, Content-Length, Content-Type'
        response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in direct video streaming for {path}: {str(e)}")
        return HttpResponseServerError('Error streaming video')

@login_required
def check_video_status(request, course_id):
    """
    Check if a course video file exists and is accessible
    Enhanced with better S3 error handling and detailed status information
    """
    try:
        course = get_object_or_404(Course, id=course_id)
        
        # Check if user has permission to access this course
        if not check_course_permission(request.user, course):
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to access this course video."
            }, status=403)
        
        # Check if the course has a video
        if not course.course_video:
            return JsonResponse({
                'success': False,
                'error': "No video associated with this course."
            })
        
        # Enhanced file existence check for S3
        file_exists = False
        file_info = {}
        stream_url = None
        error_details = None
        
        try:
            from django.core.files.storage import default_storage
            
            # Try to get the file URL from S3
            try:
                file_url = default_storage.url(course.course_video.name)
                if file_url:
                    file_exists = True
                    file_info = {
                        'exists': True,
                        'url': file_url,
                        'name': str(course.course_video).split('/')[-1] if course.course_video else 'Unknown',
                        'size': getattr(course.course_video, 'size', 'Unknown'),
                        'content_type': getattr(course.course_video, 'content_type', 'video/mp4')
                    }
                    # Generate the stream URL with proper path
                    stream_url = reverse('courses:stream_video', kwargs={'path': course.course_video.name})
                    
                    # Ensure the URL is absolute for proper video loading
                    if not stream_url.startswith('http'):
                        # Use request domain for staging environments to ensure correct URL generation
                        if 'staging.nexsy.io' in request.get_host():
                            stream_url = f"https://staging.nexsy.io{stream_url}"
                        else:
                            # Fallback to Site model for production environments
                            from django.contrib.sites.models import Site
                            try:
                                current_site = Site.objects.get_current()
                                stream_url = f"https://{current_site.domain}{stream_url}"
                            except:
                                # Final fallback to request domain
                                stream_url = f"https://{request.get_host()}{stream_url}"
                    
            except Exception as url_error:
                error_msg = str(url_error).lower()
                if "403" in error_msg or "forbidden" in error_msg:
                    error_details = "Permission denied accessing video file"
                    logger.warning(f"S3 permission denied for video: {course.course_video.name}")
                elif "nosuchkey" in error_msg or "not found" in error_msg:
                    error_details = "Video file not found in storage"
                    logger.warning(f"Video file not found: {course.course_video.name}")
                else:
                    error_details = f"Error accessing video file: {str(url_error)}"
                    logger.error(f"Error accessing video file {course.course_video.name}: {url_error}")
                    
        except Exception as e:
            error_details = f"Storage error: {str(e)}"
            logger.error(f"Storage error for course {course_id}: {str(e)}")
        
        # Return detailed response
        response_data = {
            'success': True,
            'video_exists': file_exists,
            'file_info': file_info,
            'stream_url': stream_url
        }
        
        if error_details:
            response_data['warning'] = error_details
            response_data['video_exists'] = False
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error checking video status for course {course_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f"Error checking video status: {str(e)}"
        }, status=500)

@login_required
def get_user_course_progress(request, course_id, user_id):
    """View to display a user's progress in a specific course"""
    course = get_object_or_404(Course, pk=course_id)
    user = get_object_or_404(CustomUser, pk=user_id)
    
    # Check if the user has permission to view the course
    # For first-time learners, allow viewing their own progress without additional checks
    if user.id == request.user.id:
        # User is viewing their own progress - always allow
        pass
    elif not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to view progress for this course.")
        return redirect('courses:course_list')
    
    # Check if the user is enrolled in the course
    try:
        enrollment = CourseEnrollment.objects.get(user=user, course=course)
    except CourseEnrollment.DoesNotExist:
        messages.error(request, f"The user is not enrolled in this course.")
        return redirect('courses:course_users', course_id=course.id)
    
    # Get all topics in the course
    topics = CourseTopic.objects.filter(course=course).select_related('topic').order_by('order')
    
    # Get progress for each topic
    topic_progress = []
    for topic in topics:
        progress = TopicProgress.objects.filter(user=user, topic=topic.topic).first()
        topic_progress.append({
            'topic': topic,
            'progress': progress,
            'completed': progress.completed if progress else False,
            'score': progress.last_score if progress and progress.last_score else None,
            'last_accessed': progress.last_accessed if progress else None,
            'completion_date': progress.completed_at if progress and progress.completed else None,
        })
    
    # Calculate overall progress
    total_topics = topics.count()
    completed_topics = sum(1 for tp in topic_progress if tp['completed'])
    progress_percentage = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'url': reverse('courses:course_users', kwargs={'course_id': course.id}), 'label': 'Course Users', 'icon': 'fa-users'},
        {'label': f'{user.get_full_name()} Progress', 'icon': 'fa-chart-line'}
    ]
    
    context = {
        'course': course,
        'user_obj': user,
        'enrollment': enrollment,
        'topic_progress': topic_progress,
        'progress_percentage': progress_percentage,
        'completed_topics': completed_topics,
        'total_topics': total_topics,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'courses/user_course_progress.html', context)

@login_required
def api_enrolled_learners(request, course_id):
    """API endpoint to get enrolled learners for a course"""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check permission - Allow users who can create/edit topics in this course
    has_permission = check_course_edit_permission(request.user, course)
    
    # Also allow instructors who are enrolled in the course (invited instructors)
    if not has_permission and request.user.role == 'instructor':
        from courses.models import CourseEnrollment
        is_enrolled_instructor = CourseEnrollment.objects.filter(
            user=request.user, 
            course=course
        ).exists()
        has_permission = is_enrolled_instructor
    
    if not has_permission:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Get topic ID if provided (for edit mode)
    topic_id = request.GET.get('topic_id')
    restricted_learner_ids = []
    
    if topic_id:
        try:
            topic = Topic.objects.get(id=topic_id)
            restricted_learner_ids = list(topic.restricted_learners.values_list('id', flat=True))
        except Topic.DoesNotExist:
            pass
    
    # Get enrolled learners
    enrolled_learners = CourseEnrollment.objects.filter(
        course=course,
        user__role='learner'
    ).select_related('user')
    
    learners_data = []
    for enrollment in enrolled_learners:
        learners_data.append({
            'id': enrollment.user.id,
            'username': enrollment.user.username,
            'full_name': enrollment.user.get_full_name() or enrollment.user.username,
            'email': enrollment.user.email
        })
    
    return JsonResponse({
        'success': True,
        'learners': learners_data,
        'restricted_learners': restricted_learner_ids
    })

@login_required
def course_create_user(request, course_id):
    """Create a new user and automatically enroll them in the specified course"""
    course = get_object_or_404(Course, pk=course_id)
    
    # Check if the user has permission to add users to the course
    if not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to add users to this course.")
        return redirect('courses:course_list')
    
    if request.method == 'POST':
        from users.forms import CustomUserCreationForm
        form = CustomUserCreationForm(request.POST, request=request)
        
        if form.is_valid():
            # Create the user with course auto-enrollment
            user = form.save()
            
            # Ensure the user is enrolled in the current course if not already
            from courses.models import CourseEnrollment
            from django.utils import timezone
            
            enrollment, created = CourseEnrollment.objects.get_or_create(
                user=user,
                course=course,
                defaults={
                    'enrolled_at': timezone.now(),
                    'enrollment_source': 'manual'
                }
            )
            
            if created:
                messages.success(request, f"User '{user.get_full_name()}' has been created and enrolled in '{course.title}' successfully!")
            else:
                messages.success(request, f"User '{user.get_full_name()}' has been created successfully!")
            
            return redirect('courses:course_users', course_id=course.id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        from users.forms import CustomUserCreationForm
        # Pre-select the current course
        initial_data = {'courses': [course]}
        form = CustomUserCreationForm(initial=initial_data, request=request)
        
        # Set branch based on course branch
        if course.branch:
            form.fields['branch'].initial = course.branch
            form.fields['courses'].queryset = Course.objects.filter(branch=course.branch)
        
        # Make course field readonly by pre-selecting it
        form.fields['courses'].widget.attrs['disabled'] = True
        
        # Add CSS classes to form fields
        form.fields['username'].widget.attrs.update({'class': 'form-input'})
        form.fields['email'].widget.attrs.update({'class': 'form-input'})
        form.fields['first_name'].widget.attrs.update({'class': 'form-input'})
        form.fields['last_name'].widget.attrs.update({'class': 'form-input'})
        form.fields['password1'].widget.attrs.update({'class': 'form-input'})
        form.fields['password2'].widget.attrs.update({'class': 'form-input'})
        form.fields['role'].widget.attrs.update({'class': 'form-select'})
        form.fields['branch'].widget.attrs.update({'class': 'form-select'})
        form.fields['timezone'].widget.attrs.update({'class': 'form-select'})
        form.fields['courses'].widget.attrs.update({'class': 'form-select readonly-field'})
        
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
        {'url': reverse('courses:course_users', kwargs={'course_id': course.id}), 'label': 'Course Users', 'icon': 'fa-users'},
        {'label': 'Create New User', 'icon': 'fa-user-plus'}
    ]
    
    context = {
        'form': form,
        'course': course,
        'breadcrumbs': breadcrumbs,
        'page_title': f'Create New User for {course.title}',
    }
    
    return render(request, 'courses/course_create_user.html', context)

@login_required
def course_bulk_enroll(request, course_id):
    from core.utils.enrollment import EnrollmentService
    
    course = get_object_or_404(Course, pk=course_id)

    logger.info(f"Bulk enrollment request for course {course_id}")

    if not check_course_edit_permission(request.user, course):
        logger.warning("Permission denied for bulk enrollment")
        return JsonResponse({
            'success': False,
            'message': "You don't have permission to add users to this course."
        }, status=403)
    
    if request.method == 'POST':
        try:
            # Process request body
            data = json.loads(request.body)
            user_ids = data.get('user_ids', [])
            logger.info(f"Processing {len(user_ids)} user IDs for enrollment")

            if not user_ids:
                logger.warning("No user IDs provided for bulk enrollment")
                return JsonResponse({
                    'success': False,
                    'message': 'No users selected for enrollment.'
                }, status=400)

            # Ensure user_ids are integers
            try:
                user_ids = [int(uid) for uid in user_ids]
            except (ValueError, TypeError) as e:
                 logger.error(f"Invalid user ID format: {e}")
                 return JsonResponse({'success': False, 'message': 'Invalid user ID format.'}, status=400)


            # Get already enrolled users to avoid duplicates
            enrolled_user_ids = CourseEnrollment.objects.filter(
                course=course,
                user_id__in=user_ids
            ).values_list('user_id', flat=True)
            enrolled_user_ids_set = set(enrolled_user_ids)
            
            # Filter out already enrolled users
            new_user_ids = [uid for uid in user_ids if uid not in enrolled_user_ids_set]
            logger.info(f"New users to enroll: {len(new_user_ids)}")

            if not new_user_ids:
                logger.info("All selected users are already enrolled")
                return JsonResponse({
                    'success': False,
                    'message': 'All selected users are already enrolled in this course.'
                }, status=400)

            # Filter users based on permissions and existence
            users_to_enroll_qs = CustomUser.objects.filter(id__in=new_user_ids, is_active=True)

            if not request.user.is_superuser and request.user.role == 'admin':
                users_to_enroll_qs = users_to_enroll_qs.filter(branch=request.user.branch)
                # Filter users by admin's branch
            elif request.user.role == 'instructor':
                users_to_enroll_qs = users_to_enroll_qs.filter(branch=request.user.branch)
                # Filter users by instructor's branch

            users_to_enroll = list(users_to_enroll_qs) # Evaluate the queryset
            found_user_ids = {user.id for user in users_to_enroll}
            logger.info(f"Users found for enrollment: {len(found_user_ids)}")

            if len(users_to_enroll) != len(new_user_ids):
                 missing_ids = set(new_user_ids) - found_user_ids
                 logger.warning(f"Some users not found or inactive: {len(missing_ids)} users")


            if not users_to_enroll:
                logger.warning("No valid users found to enroll")
                return JsonResponse({
                    'success': False,
                    'message': 'No valid users found to enroll (might be inactive or not in branch).'
                }, status=400)


            from groups.models import BranchGroup, GroupMembership, GroupMemberRole, CourseGroupAccess
            
            # Use bulk enrollment service for atomic operations
            # Suppress individual notifications for bulk operations
            try:
                bulk_results = EnrollmentService.bulk_create_enrollments(
                    users=users_to_enroll,
                    course=course,
                    source='bulk'
                )
                
                logger.info(f"Bulk enrollment results: {bulk_results['created']} created, {bulk_results['already_enrolled']} already enrolled")

                if bulk_results['errors']:
                    return JsonResponse({
                        'success': False,
                        'message': f"Bulk enrollment partially failed: {'; '.join(bulk_results['errors'])}"
                    }, status=400)
            except Exception as e:
                logger.error(f"Bulk enrollment service failed: {e}")
                return JsonResponse({
                    'success': False,
                    'message': f"Bulk enrollment failed: {str(e)}"
                }, status=500)
            
            # Handle instructor permissions for users with instructor role
            instructors_to_setup = [user for user in users_to_enroll if user.role == 'instructor']
            
            if instructors_to_setup:
                logger.info(f"Enrolled {len(instructors_to_setup)} instructors - no automatic group creation")

            instructor_count = len(instructors_to_setup)
            learner_count = len(users_to_enroll) - instructor_count
            
            message_parts = []
            if learner_count > 0:
                message_parts.append(f'{learner_count} learners')
            if instructor_count > 0:
                message_parts.append(f'{instructor_count} instructors (with editing permissions)')
            
            message = f"Successfully enrolled {' and '.join(message_parts)} in the course."
            
            return JsonResponse({
                'success': True,
                'message': message
            })
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error: {e}")
            logger.error(traceback.format_exc())
            return JsonResponse({'success': False, 'message': 'Invalid request data.'}, status=400)
        except Exception as e:
            from role_management.utils import SessionErrorHandler
            error_message = SessionErrorHandler.log_and_sanitize_error(
                e, request, error_type='system', operation='course enrollment'
            )
            return JsonResponse({'success': False, 'message': error_message}, status=500)

    logger.warning("Invalid request method for bulk enrollment (Not POST)")
    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

@login_required
def course_progress_view(request, course_id):
    """View to display course progress for all users or redirect to specific user progress"""
    course = get_object_or_404(Course, pk=course_id)
    user_id = request.GET.get('user_id')

    # If user_id is provided, redirect to user-specific progress view
    if user_id:
        try:
            user_id = int(user_id)
            return redirect('reports:user_detail_report', user_id=user_id)
        except (ValueError, TypeError):
            messages.error(request, "Invalid user ID provided.")
            return redirect('courses:course_list')

    # Check if the user is enrolled in the course - enrolled users can view progress
    is_enrolled = CourseEnrollment.objects.filter(course=course, user=request.user).exists()
    
    # Check if the user has permission to view the course
    if not is_enrolled and not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to view progress for this course.")
        return redirect('courses:course_list')

    # Get enrollments for this course - filtered based on user role
    if request.user.role == 'learner':
        # Learners can only see their own progress
        enrollments = CourseEnrollment.objects.filter(course=course, user=request.user).select_related('user')
    else:
        # Other roles can see all enrollments (existing behavior)
        enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
    
    # Calculate progress for each enrollment
    progress_data = []
    for enrollment in enrollments:
        completed_topics = TopicProgress.objects.filter(
            user=enrollment.user,
            topic__coursetopic__course=course,
            completed=True
        ).count()
        
        total_topics = CourseTopic.objects.filter(course=course).count()
        progress_percentage = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        progress_data.append({
            'user': enrollment.user,
            'progress': progress_percentage,
            'completed_topics': completed_topics,
            'total_topics': total_topics,
            'last_accessed': enrollment.last_accessed,
            'completed': enrollment.completed,
            'completion_date': enrollment.completion_date
        })

    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-graduation-cap'},
        {'label': 'Course Progress', 'icon': 'fa-chart-line'}
    ]

    context = {
        'course': course,
        'progress_data': progress_data,
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'courses/course_progress.html', context)

@login_required
def user_course_progress_view(request, course_id, user_id):
    """View to display a specific user's progress in a course"""
    course = get_object_or_404(Course, pk=course_id)
    user = get_object_or_404(CustomUser, pk=user_id)

    # Check if the user has permission to view the course
    # Allow users to view their own progress without additional permission checks
    viewing_own_progress = int(user_id) == request.user.id
    if not viewing_own_progress and not check_course_edit_permission(request.user, course):
        messages.error(request, "You don't have permission to view progress for this course.")
        return redirect('courses:course_list')

    # Check if the user is enrolled in the course
    try:
        enrollment = CourseEnrollment.objects.get(user=user, course=course)
    except CourseEnrollment.DoesNotExist:
        messages.error(request, f"The user is not enrolled in this course.")
        return redirect('courses:course_progress', course_id=course.id)

    # Get all topics in the course
    topics = CourseTopic.objects.filter(course=course).select_related('topic').order_by('order')

    # Get progress for each topic
    topic_progress = []
    for topic in topics:
        progress = TopicProgress.objects.filter(user=user, topic=topic.topic).first()
        topic_progress.append({
            'topic': topic,
            'progress': progress,
            'completed': progress.completed if progress else False,
            'score': progress.last_score if progress and progress.last_score else None,
            'last_accessed': progress.last_accessed if progress else None,
            'completion_date': progress.completed_at if progress and progress.completed else None,
        })

    # Calculate overall progress
    total_topics = topics.count()
    completed_topics = sum(1 for tp in topic_progress if tp['completed'])
    progress_percentage = round((completed_topics / total_topics) * 100) if total_topics > 0 else 0

    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
        {'url': reverse('courses:course_details', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-graduation-cap'},
        {'url': reverse('courses:course_users', kwargs={'course_id': course.id}), 'label': 'Course Users', 'icon': 'fa-users'},
        {'label': f'{user.get_full_name()} Progress', 'icon': 'fa-chart-line'}
    ]

    context = {
        'course': course,
        'user_obj': user,
        'enrollment': enrollment,
        'topic_progress': topic_progress,
        'progress_percentage': progress_percentage,
        'completed_topics': completed_topics,
        'total_topics': total_topics,
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'courses/user_course_progress.html', context)

@login_required
@require_POST
def toggle_topic_status(request, topic_id):
    """Toggle a topic's status between draft and active."""
    topic = get_object_or_404(Topic, id=topic_id)
    course = get_topic_course(topic)
    
    # Check if the user has permission to edit this topic
    if not check_topic_edit_permission(request.user, topic, course):
        return JsonResponse({'success': False, 'error': "You don't have permission to edit this topic."}, status=403)
    
    try:
        # Get the current status and determine the new status
        current_status = topic.status
        new_status = None
        
        # Handle all possible status transitions
        if current_status == 'draft':
            new_status = 'active'
        elif current_status == 'active':
            new_status = 'draft'
        elif current_status == 'inactive':
            new_status = 'active'
        elif current_status == 'archived':
            new_status = 'active'
        else:
            new_status = 'active'  # Default case
        
        # Update the status
        topic.status = new_status
        topic.save()
        
        # Log the status change for debugging
        logger.info(f"Topic {topic.id} status changed from {current_status} to {new_status} by {request.user.username}")
        
        return JsonResponse({
            'success': True, 
            'topic_id': topic_id,
            'new_status': new_status,
            'message': f"Topic '{topic.title}' is now {new_status}."
        })
    except Exception as e:
        logger.error(f"Error toggling topic status: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST

@login_required
def generate_certificate(request, course_id):
    """Generate a certificate for the user who completed the course."""
    if request.method != 'POST':
        return HttpResponseBadRequest("Invalid request method")
    
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # Verify the user has completed the course
    enrollment = get_object_or_404(CourseEnrollment, user=user, course=course, completed=True)
    
    if not course.issue_certificate or not course.certificate_template:
        messages.error(request, "This course is not configured to issue certificates.")
        return redirect('courses:course_details', course_id=course_id)
    
    # Check if certificate already exists
    try:
        from certificates.models import IssuedCertificate
        import uuid
        
        # Check if certificate already exists for this user and course
        existing_cert = IssuedCertificate.objects.filter(
            recipient=user,
            course_name=course.title
        ).first()
        
        if existing_cert:
            messages.success(request, "Certificate already exists.")
            # Instead of redirecting to certificate, redirect back to course details
            return redirect('courses:course_details', course_id=course_id)
        
        # Generate unique certificate number
        certificate_number = f"CERT-{uuid.uuid4().hex[:8].upper()}"
        
        # Get course instructor or superuser as issuer
        issuer = course.instructor
        if not issuer:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            issuer = User.objects.filter(is_superuser=True).first()
        
        # Create certificate
        certificate = IssuedCertificate.objects.create(
            template=course.certificate_template,
            recipient=user,
            issued_by=issuer,
            course_name=course.title,
            certificate_number=certificate_number
        )
        
        messages.success(request, "Certificate generated successfully.")
        # Redirect back to course details page instead of certificate view
        return redirect('courses:course_details', course_id=course_id)
        
    except Exception as e:
        messages.error(request, f"Error generating certificate: {str(e)}")
        return redirect('courses:course_details', course_id=course_id)

@login_required
@require_POST
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
@api_error_handler
@safe_file_operation
def upload_editor_image(request):
    """Handle image uploads from the rich text editor."""
    if request.FILES.get('image'):
        image = request.FILES['image']
        
        # Use enhanced file Session validation
        # is_valid, error_message = FileSessionValidator.validate_file(image, 'image')
        # if not is_valid:
        #     return JsonResponse({'success': False, 'error': error_message})
        
        # Get course ID from the referrer URL or a hidden field
        course_id = None
        referrer = request.META.get('HTTP_REFERER', '')
        
        # Try to extract course ID from referrer URL
        import re
        course_id_match = re.search(r'/courses/(\d+)/', referrer)
        if course_id_match:
            course_id = course_id_match.group(1)
        elif request.POST.get('course_id'):
            course_id = request.POST.get('course_id')
        
        # Use Django's default storage for all cases (works with both local and S3)
        from django.core.files.storage import default_storage
        
        # Generate safe filename
        # safe_filename = FileSessionValidator.generate_safe_filename(
        #     image.name, 
        #     f"course_{course_id}_image"
        # )
        safe_filename = f"course_{course_id}_image_{image.name}"
        
        if not course_id:
            # Fallback to default location if we can't determine course ID
            image_relative_path = f"editor_uploads/{safe_filename}"
        else:
            # Use the same pattern as course featured images
            image_relative_path = f"course_content/{course_id}/{safe_filename}"
        
        # Save file using Django's storage backend (works with S3 and local)
        saved_path = default_storage.save(image_relative_path, image)
        
        # Generate the URL using default storage
        uploaded_file_url = default_storage.url(saved_path)
        
        # Update course model if we can find it and we have a course_id
        if course_id:
            try:
                course = Course.objects.get(id=course_id)
                course.course_image = saved_path
                course.save()
                logger.info(f"Updated course {course_id} image field with: {saved_path}")
            except Course.DoesNotExist:
                logger.warning(f"Course with ID {course_id} not found for image upload")
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=image_relative_path,
                uploaded_by=request.user,
                source_type='editor_upload',
                course=course,
                filename=image.name,
                description=f'Editor image upload for course: {course.title if course else "Unknown"}'
            )
        except Exception as e:
            logger.error(f"Error registering editor image in media database: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'url': uploaded_file_url,
            'filename': filename
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request or missing image file'
    })

@login_required
@require_POST
# @ensure_csrf_cookie  # COMMENTED OUT TO FIX ERRORS
def upload_editor_video(request):
    if request.FILES.get('video'):
        video = request.FILES['video']
        
        # Validate file type
        allowed_types = ['video/mp4', 'video/webm', 'video/ogg', 'video/avi', 'video/mov']
        if video.content_type not in allowed_types:
            return JsonResponse({'success': False, 'error': 'Invalid file type. Only videos allowed.'})
        
        # Validate actual file content using python-magic
        try:
            import magic
            file_signature = magic.from_buffer(video.read(1024), mime=True)
            video.seek(0)  # Reset file pointer
            
            if file_signature not in allowed_types:
                return JsonResponse({'success': False, 'error': 'File content does not match declared type.'})
        except Exception as e:
            logger.error(f"Error validating file signature: {str(e)}")
            return JsonResponse({'success': False, 'error': 'Unable to validate file content.'})
        
        # Validate file size (max 500MB to match frontend validation)
        if video.size > 500 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'File too large. Maximum size is 500MB.'})
        
        # Get course ID from the referrer URL or a hidden field
        course_id = None
        referrer = request.META.get('HTTP_REFERER', '')
        
        # Try to extract course ID from referrer URL
        import re
        course_id_match = re.search(r'/courses/(\d+)/', referrer)
        if course_id_match:
            course_id = course_id_match.group(1)
        elif request.POST.get('course_id'):
            course_id = request.POST.get('course_id')
        
        # Use Django's default storage for all cases (works with both local and S3)
        from django.core.files.storage import default_storage
        
        # Generate filename with timestamp to avoid collisions
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        video_filename = f"{timestamp}_{unique_id}_{video.name}"
        
        if not course_id:
            # Fallback to default location if we can't determine course ID
            video_relative_path = f"editor_uploads/videos/{video_filename}"
        else:
            # Use the same pattern as course featured videos
            video_relative_path = f"course_content/{course_id}/{video_filename}"
        
        # Save file using Django's storage backend (works with S3 and local)
        saved_path = default_storage.save(video_relative_path, video)
        
        # Generate the URL using default storage
        uploaded_file_url = default_storage.url(saved_path)
        filename = video_filename
        
        logger.info(f"Saved editor video to: {saved_path}")
        
        # Try to get the course for registration if we have a course_id
        course = None
        if course_id:
            try:
                course = Course.objects.get(id=course_id)
            except Course.DoesNotExist:
                logger.warning(f"Course with ID {course_id} not found for video upload")
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=video_relative_path,
                uploaded_by=request.user,
                source_type='editor_upload',
                course=course,
                filename=video.name,
                description=f'Editor video upload for course: {course.title if course else "Unknown"}'
            )
        except Exception as e:
            logger.error(f"Error registering editor video in media database: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'url': uploaded_file_url,
            'filename': filename
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request or missing video file'
    })

def certificate_view(request, uuid):
    """
    View for displaying a certificate by its UUID.
    This function allows public access to certificates through a unique identifier.
    """
    try:
        from certificates.models import IssuedCertificate
        from django.core.exceptions import FieldError
        # Try to find by UUID first (if the model is updated later)
        try:
            certificate = IssuedCertificate.objects.get(uuid=uuid)
        except (IssuedCertificate.DoesNotExist, FieldError):
            # If UUID field doesn't exist, try to use the certificate_number instead
            certificate = IssuedCertificate.objects.get(certificate_number=uuid)
        
        return render(request, 'certificates/view_certificate.html', {
            'certificate': certificate,
            'public_view': True,
        })
    except Exception as e:
        logger.error(f"Error viewing certificate: {str(e)}")
        raise Http404("Certificate not found")

@login_required
def get_branch_courses(request, branch_id):
    """API to get courses belonging to a specific branch"""
    try:
        branch = Branch.objects.get(id=branch_id)
        
        # Check permissions - admin/instructor should only see their branch's courses
        if not request.user.is_superuser and request.user.branch != branch:
            return JsonResponse({
                'success': False, 
                'message': 'You do not have permission to view courses for this branch'
            }, status=403)
        
        courses = Course.objects.filter(branch=branch).values('id', 'title')
        
        return JsonResponse({
            'success': True,
            'courses': list(courses)
        })
    except Branch.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Branch not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

# Claude AI proxy endpoint
@login_required
@require_POST
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def claude_ai_proxy(request):
    """Proxy requests to Claude AI API to avoid CORS issues"""
    try:
        # Parse request data
        request_data = json.loads(request.body)
        
        # Get the API key from settings (not from request headers for Session)
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        
        if not api_key:
            return JsonResponse({
                'error': {
                    'message': 'AI service not configured'
                }
            }, status=503)
        
        # Forward request to Claude API
        claude_response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01'
            },
            json=request_data
        )
        
        # Return response from Claude API
        return JsonResponse(claude_response.json(), status=claude_response.status_code)
    
    except Exception as e:
        logging.error(f"Error in Claude AI proxy: {str(e)}")
        return JsonResponse({
            'error': {
                'message': f'Error processing request: {str(e)}'
            }
        }, status=500)

@login_required
def topic_create(request, course_id):
    """Handle topic creation for a course"""
    from django.urls import reverse  # Ensure reverse is available in local scope
    # Log request information for debugging
    logger.info(f"Topic create view accessed - URL: {request.path}, Course ID: {course_id}, Query params: {request.GET}")
    
    # Attempt to get the course
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        logger.error(f"Course with ID {course_id} not found")
        messages.error(request, "Course not found.")
        return redirect('courses:course_list')
        
    # Check user permissions
    # First check if the user is a learner who is enrolled in the course
    is_enrolled_learner = False
    if request.user.role == 'learner' and course.enrolled_users.filter(id=request.user.id).exists():
        is_enrolled_learner = True
        logger.info(f"User {request.user.id} is an enrolled learner in course {course_id}")
    
    # Check if user can modify the course content
    if not course.user_can_modify(request.user) and not is_enrolled_learner:
        logger.warning(f"User {request.user.id} attempted to create topic for course {course_id} without permission")
        messages.error(request, "You don't have permission to create topics for this course.")
        return redirect('courses:course_details', course_id=course_id)
    
    # Get section if specified in query params
    section_id = request.GET.get('section')
    section = None
    if section_id and section_id not in ['new_section', 'standalone']:
        try:
            section = Section.objects.get(id=section_id, course=course)
        except Section.DoesNotExist:
            logger.warning(f"Section with ID {section_id} not found for course {course_id}")
            section = None
            
    # Get all sections for the course
    sections = Section.objects.filter(course=course).order_by('order')
    
    # Handle GET request
    if request.method == 'GET':
        # Get filtered content based on user role
        filtered_content = get_user_filtered_content(request.user, course, request)
        
        # Create empty form with filtered content
        form = TopicForm(course=course, filtered_content=filtered_content)
        
        # Prepare content type choices
        content_types = Topic.TOPIC_TYPE_CHOICES
        
        # Get categories for search dropdown with role-based filtering
        categories = get_user_accessible_categories(request.user)
        
        # Define breadcrumbs for this view
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('courses:course_list'), 'label': 'Course Catalog', 'icon': 'fa-book'},
            {'url': reverse('courses:course_edit', kwargs={'course_id': course.id}), 'label': course.title, 'icon': 'fa-edit'},
            {'label': 'Create Topic', 'icon': 'fa-plus-circle'}
        ]
        
        context = {
            'action': 'Create',
            'course': course,
            'course_id': course_id,
            'sections': sections,
            'content_types': content_types,
            'quizzes': filtered_content['quizzes'],
            'assignments': filtered_content['assignments'],
            'conferences': filtered_content['conferences'],
            'discussions': filtered_content['discussions'],
            'breadcrumbs': breadcrumbs,
            'section_id': section.id if section else None,
            'forum_content_type': request.GET.get('forum_content_type', 'text'),
            'assessment_type': request.GET.get('assessment_type', 'discussion'),
            'categories': categories,
            'form': form,
            'can_create_quiz': course.can_create_quiz(),
            'can_create_assignment': course.can_create_assignment(),
            'quiz_count': course.get_quiz_count(),
            'assignment_count': course.get_assignment_count(),
        }
        
        return render(request, 'courses/add_topic.html', context)
    
    # Handle POST request
    elif request.method == 'POST':
        logger.info(f"Processing topic creation POST request for course {course_id}")
        logger.debug(f"POST data: {request.POST}")
        logger.debug(f"FILES data: {request.FILES}")
        
        # Get filtered content for form validation
        filtered_content = get_user_filtered_content(request.user, course, request)
        
        # Create form with submitted data and filtered content
        form = TopicForm(request.POST, request.FILES, course=course, filtered_content=filtered_content)
        
        # Log the content type and assignment selection for debugging
        content_type = request.POST.get('content_type')
        assignment_id = request.POST.get('assignment')
        logger.info(f"Content type: {content_type}, Assignment ID: {assignment_id}")
        logger.info(f"Files submitted: {list(request.FILES.keys())}")
        logger.info(f"POST keys: {list(request.POST.keys())}")
        
        if form.is_valid():
            # Save the form but don't commit to DB yet
            new_topic = form.save(commit=False)
            
            # Log the text content for text-type topics
            if new_topic.content_type == 'Text':
                logger.info(f"Saving text topic - Content saved length: {len(str(new_topic.text_content or ''))}")
                
            # Set section if specified
            if section:
                new_topic.section = section
            elif request.POST.get('section') and request.POST.get('section') != 'new_section' and request.POST.get('section') != 'standalone':
                try:
                    selected_section = Section.objects.get(id=request.POST.get('section'), course=course)
                    new_topic.section = selected_section
                except Section.DoesNotExist:
                    pass
            
            try:
                # Save the topic to get an ID
                new_topic.save()
                
                # Create the relationship with the course immediately after saving
                CourseTopic.objects.create(
                    course=course,
                    topic=new_topic,
                    order=CourseTopic.objects.filter(course=course).count() + 1
                )
                
            except Exception as e:
                logger.error(f"Error creating topic: {str(e)}")
                messages.error(request, f"Error creating topic: {str(e)}")
                return redirect("courses:course_edit", course_id=course.id)
            
            messages.success(request, f"Topic created successfully!")
            return redirect("courses:course_edit", course_id=course.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
        # If form invalid, rebuild context for error display
        content_types = Topic.TOPIC_TYPE_CHOICES
        categories = get_user_accessible_categories(request.user)
        
        context = {
            'action': 'Create',
            'course': course,
            'course_id': course_id,
            'sections': sections,
            'content_types': content_types,
            'quizzes': filtered_content['quizzes'],
            'assignments': filtered_content['assignments'],
            'conferences': filtered_content['conferences'],
            'discussions': filtered_content['discussions'],
            'section_id': section.id if section else None,
            'categories': categories,
            'form': form,
            'can_create_quiz': course.can_create_quiz(),
            'can_create_assignment': course.can_create_assignment(),
            'quiz_count': course.get_quiz_count(),
            'assignment_count': course.get_assignment_count(),
        }
        
        return render(request, "courses/add_topic.html", context)
                
def get_user_filtered_content(user, course=None, request=None):
    """Filter content (Quiz, Assignment, Conference, Discussion) based on user role
    
    Args:
        user: The user to filter content for
        course: Optional specific course to include content from
        request: Optional request object for admin branch switching support
    """
    from quiz.models import Quiz
    from assignments.models import Assignment
    from conferences.models import Conference
    from discussions.models import Discussion
    from django.db.models import Q
    from core.branch_filters import BranchFilterManager
    from branches.models import Branch

    def get_default_branch():
        """Get the default branch (first active branch) as fallback"""
        try:
            return Branch.objects.filter(is_active=True).first()
        except:
            return None

    if user.role == 'globaladmin':
        # Global admin sees everything
        quizzes = Quiz.objects.all().order_by('title')
        assignments = Assignment.objects.all().order_by('title')
        conferences = Conference.objects.filter(status='published')
        discussions = Discussion.objects.all()
    elif user.role == 'superadmin':
        # Super admin sees content from their assigned businesses
        if hasattr(user, 'business_assignments') and user.business_assignments.filter(is_active=True).exists():
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            quizzes = Quiz.objects.filter(
                Q(course__branch__business__in=assigned_businesses) |
                Q(course=None, creator__branch__business__in=assigned_businesses)
            ).order_by('title')
            assignments = Assignment.objects.filter(
                Q(course__branch__business__in=assigned_businesses) |
                Q(course=None, user__branch__business__in=assigned_businesses)
            ).order_by('title')
            conferences = Conference.objects.filter(
                Q(course__branch__business__in=assigned_businesses, status='published') |
                Q(course=None, created_by__branch__business__in=assigned_businesses, status='published')
            )
            discussions = Discussion.objects.filter(
                Q(course__branch__business__in=assigned_businesses) |
                Q(course=None, created_by__branch__business__in=assigned_businesses)
            )
        else:
            # Fallback: use default branch or show nothing
            default_branch = get_default_branch()
            if default_branch:
                quizzes = Quiz.objects.filter(
                    Q(course__branch=default_branch) |
                    Q(course=None, creator__branch=default_branch) |
                    Q(creator=user)
                ).order_by('title')
                assignments = Assignment.objects.filter(
                    Q(course__branch=default_branch) |
                    Q(course=None, user__branch=default_branch) |
                    Q(user=user)
                ).order_by('title')
                conferences = Conference.objects.filter(
                    Q(course__branch=default_branch, status='published') |
                    Q(course=None, created_by__branch=default_branch, status='published') |
                    Q(created_by=user, status='published')
                )
                discussions = Discussion.objects.filter(
                    Q(course__branch=default_branch) |
                    Q(course=None, created_by__branch=default_branch) |
                    Q(created_by=user)
                )
            else:
                # No business assignments and no default branch, show only own content
                quizzes = Quiz.objects.filter(creator=user).order_by('title')
                assignments = Assignment.objects.filter(user=user).order_by('title')
                conferences = Conference.objects.filter(created_by=user, status='published')
                discussions = Discussion.objects.filter(created_by=user)
    elif user.role == 'admin':
        # Branch admin sees content scoped to their effective branch (supports branch switching)
        effective_branch = BranchFilterManager.get_effective_branch(user, request)
        if not effective_branch:
            effective_branch = get_default_branch()
        
        if effective_branch:
            quizzes = Quiz.objects.filter(
                Q(course__branch=effective_branch) |
                Q(course=None, creator__branch=effective_branch)
            ).order_by('title')
            assignments = Assignment.objects.filter(
                Q(course__branch=effective_branch) |
                Q(course=None, user__branch=effective_branch)
            ).order_by('title')
            conferences = Conference.objects.filter(
                Q(course__branch=effective_branch, status='published') |
                Q(course=None, created_by__branch=effective_branch, status='published')
            )
            discussions = Discussion.objects.filter(
                Q(course__branch=effective_branch) |
                Q(course=None, created_by__branch=effective_branch)
            )
        else:
            # No effective branch, show only own content
            quizzes = Quiz.objects.filter(creator=user).order_by('title')
            assignments = Assignment.objects.filter(user=user).order_by('title')
            conferences = Conference.objects.filter(created_by=user, status='published')
            discussions = Discussion.objects.filter(created_by=user)
    elif user.role == 'instructor':
        # Instructor sees content from their branch (like admins) plus content they created
        user_branch = user.branch if hasattr(user, 'branch') and user.branch else get_default_branch()
        if user_branch:
            quizzes = Quiz.objects.filter(
                Q(course__branch=user_branch) |
                Q(course=None, creator__branch=user_branch) |
                Q(creator=user)  # Include their own content regardless of branch
            ).order_by('title')
            assignments = Assignment.objects.filter(
                Q(course__branch=user_branch) |
                Q(course=None, user__branch=user_branch) |
                Q(user=user)  # Include their own content regardless of branch
            ).order_by('title')
            conferences = Conference.objects.filter(
                Q(course__branch=user_branch, status='published') |
                Q(course=None, created_by__branch=user_branch, status='published') |
                Q(created_by=user, status='published')  # Include their own content regardless of branch
            )
            discussions = Discussion.objects.filter(
                Q(course__branch=user_branch) |
                Q(course=None, created_by__branch=user_branch) |
                Q(created_by=user)  # Include their own content regardless of branch
            )
        else:
            # Fallback: if no branch, only show their own content
            quizzes = Quiz.objects.filter(creator=user).order_by('title')
            assignments = Assignment.objects.filter(user=user).order_by('title')
            conferences = Conference.objects.filter(created_by=user, status='published')
            discussions = Discussion.objects.filter(created_by=user)
    elif user.role == 'learner':
        # Learners see content from their branch or default branch
        user_branch = user.branch if hasattr(user, 'branch') and user.branch else get_default_branch()
        if user_branch:
            quizzes = Quiz.objects.filter(course__branch=user_branch).order_by('title')
            assignments = Assignment.objects.filter(course__branch=user_branch).order_by('title')
            conferences = Conference.objects.filter(course__branch=user_branch, status='published')
            discussions = Discussion.objects.filter(course__branch=user_branch)
        else:
            # No branch available, show nothing
            quizzes = Quiz.objects.none()
            assignments = Assignment.objects.none()
            conferences = Conference.objects.none()
            discussions = Discussion.objects.none()
    else:
        # Other roles see nothing
        quizzes = Quiz.objects.none()
        assignments = Assignment.objects.none()
        conferences = Conference.objects.none()
        discussions = Discussion.objects.none()

    # If course is provided, also include content specific to that course
    if course:
        quizzes = quizzes | Quiz.objects.filter(course=course)
        assignments = assignments | Assignment.objects.filter(course=course)
        conferences = conferences | Conference.objects.filter(course=course, status='published')
        discussions = discussions | Discussion.objects.filter(course=course)

    return {
        'quizzes': quizzes.distinct(),
        'assignments': assignments.distinct(),
        'conferences': conferences.distinct(),
        'discussions': discussions.distinct()
    }


