from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Prefetch, F, ExpressionWrapper, FloatField, Sum, Avg, Max, fields, Case, When, Value, IntegerField, Subquery, OuterRef
from django.urls import reverse
from django.db.models.functions import TruncDate, Cast, ExtractMonth, ExtractYear
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import HttpResponse, JsonResponse, Http404, HttpResponseForbidden
from django.core.serializers.json import DjangoJSONEncoder
from django.urls import reverse
from .models import Report, ReportAttachment, Event
from calendar_app.models import CalendarEvent
from users.models import Branch
from groups.models import BranchGroup
from courses.models import Course, CourseEnrollment, TopicProgress, Topic, CourseTopic
from categories.models import CourseCategory
from core.utils.forms import CustomTinyMCEFormField
from core.utils.business_filtering import filter_queryset_by_business
from core.branch_filters import BranchFilterManager
from django import forms
import os
import uuid
import json
import csv
import xlwt
import logging
from django.conf import settings
from django.views.decorators.http import require_POST
from datetime import timedelta, datetime
from django.core.cache import cache
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import PageNotAnInteger, EmptyPage
from django.contrib import messages
import logging
from functools import wraps
from role_management.models import Role, RoleCapability, UserRole

User = get_user_model()
logger = logging.getLogger(__name__)

@login_required
def activity_report_overview(request, activity_id):
    """
    Display overview report for a specific learning activity/topic.
    """
    try:
        topic = get_object_or_404(Topic, id=activity_id)
        
        # Get topic progress data
        progress_data = TopicProgress.objects.filter(topic=topic).select_related('user')
        
        # Calculate progress statistics
        total_users = progress_data.count()
        completed_users = progress_data.filter(completed=True).count()
        # Users who have accessed but not completed (have first_accessed but not completed)
        in_progress_users = progress_data.filter(completed=False, first_accessed__isnull=False).count()
        # Users who haven't started (no first_accessed or very old first_accessed with no progress)
        not_started_users = progress_data.filter(first_accessed__isnull=True).count()
        
        # Calculate average score
        completed_with_scores = progress_data.filter(completed=True, last_score__isnull=False)
        average_score = None
        
        if completed_with_scores.exists():
            total_score = sum(normalize_score(progress.last_score) for progress in completed_with_scores)
            average_score = total_score / completed_with_scores.count() if completed_with_scores.count() > 0 else None
        
        # Calculate total progress records (attempts field doesn't exist)
        total_attempts = progress_data.count()
        
        # Calculate final average score
        final_average_score = average_score
        
        progress_stats = {
            'total_users': total_users,
            'completed_users': completed_users,
            'in_progress_users': in_progress_users,
            'not_started_users': not_started_users,
            'average_score': final_average_score,
            'total_attempts': total_attempts,
        }
        
        
        context = {
            'activity': topic,  # Use 'activity' to match template expectations
            'topic': topic,  # Keep for backward compatibility
            'progress_data': progress_data,
            'progress_stats': progress_stats,
            'total_enrollments': total_users,
            'completed_count': completed_users,
            'section_title': 'Overview',
            'breadcrumbs': [
                {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
                {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
                {'url': reverse('reports:learning_activities'), 'label': 'Learning Activities', 'icon': 'fa-tasks'},
                {'label': topic.title, 'icon': 'fa-lightbulb'}
            ],
        }
        
        return render(request, 'reports/activity_report_sections/overview.html', context)
    except Exception as e:
        logger.error(f"Error in activity_report_overview: {e}")
        messages.error(request, "Error loading activity report overview.")
        return redirect('reports:dashboard')

def normalize_score(score):
    """
    Normalize score using unified scoring service.
    Ensures consistent score handling across all report pages.
    """
    from core.utils.scoring import ScoreCalculationService
    
    normalized = ScoreCalculationService.normalize_score(score)
    return float(normalized) if normalized is not None else 0.0

def validate_branch_id(branch_id_str):
    """
    Safely validate and convert branch ID string to integer.
    Returns None if invalid to prevent SQL injection.
    """
    if not branch_id_str or branch_id_str == 'all':
        return None
    
    try:
        branch_id = int(branch_id_str)
        if branch_id <= 0:
            logger.warning(f"Invalid branch ID: {branch_id}")
            return None
        return branch_id
    except (ValueError, TypeError):
        logger.warning(f"Invalid branch ID format: {branch_id_str}")
        return None

def parse_date_filter(date_str):
    """
    Safely parse date string in consistent format.
    Returns None if invalid to prevent errors.
    """
    if not date_str:
        return None
    
    # Support multiple date formats for flexibility
    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S']
    
    for date_format in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, date_format)
            return parsed_date.date() if hasattr(parsed_date, 'date') else parsed_date
        except ValueError:
            continue
    
    logger.warning(f"Invalid date format: {date_str}")
    return None

def calculate_progress_percentage(completed_count, total_count):
    """
    Calculate progress percentage with consistent logic.
    Returns 0-100 percentage value.
    """
    if not total_count or total_count <= 0:
        return 0.0
    
    if not completed_count or completed_count <= 0:
        return 0.0
    
    # Ensure we don't exceed 100%
    percentage = min((completed_count / total_count) * 100, 100.0)
    return round(percentage, 1)



def get_enrollment_status(enrollment):
    """
    Get consistent enrollment status based on enrollment data.
    Returns standardized status string.
    """
    if not enrollment:
        return 'not_enrolled'
    
    if enrollment.completed:
        return 'completed'
    
    # Check if course was accessed recently (within 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    if not enrollment.last_accessed:
        return 'not_started'
    
    if enrollment.last_accessed >= thirty_days_ago:
        return 'in_progress'
    else:
        return 'not_passed'  # Inactive for more than 30 days

def check_user_report_access(user):
    """
    Centralized function to check if user has report viewing access.
    Returns True if user has access, False otherwise.
    """
    # Check if user is authenticated first
    if not user.is_authenticated:
        return False
    
    # Superadmins and admins always have access
    if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
        return True
        
    # Check if user has a system role with report access by default
    if user.role in ['admin', 'instructor']:
        return True
        
    # Check primary role capabilities using PermissionManager
    try:
        from role_management.utils import PermissionManager
        
        # Check for view_reports capability through primary role
        if PermissionManager.user_has_capability(user, 'view_reports'):
            return True
            
    except Exception as e:
        logger.error(f"Error checking primary role report access for user {user.id}: {str(e)}")
        
    # Check for report-related capabilities through user roles
    try:
        user_roles = UserRole.objects.filter(user=user)
        if user_roles.exists():
            report_capabilities = [
                'view_reports', 'reports_overview', 'courses_reports',
                'users_reports', 'branches_reports', 'groups_reports',
                'timeline', 'training_matrix', 'custom_reports', 'learning_activities'
            ]
            
            for user_role in user_roles:
                has_report_access = RoleCapability.objects.filter(
                    role=user_role.role,
                    capability__in=report_capabilities
                ).exists()
                
                if has_report_access:
                    return True
    except Exception as e:
        logger.error(f"Error checking user role report access for user {user.id}: {str(e)}")
    
    return False

def superadmin_required(view_func):
    """
    Decorator to restrict access to superadmin users only.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Check authentication first
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect('users:role_based_redirect')
        
        if not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
            messages.error(request, "You don't have permission to access reports. This section is restricted to super administrators only.")
            return redirect('users:role_based_redirect')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def reports_access_required(view_func):
    """
    Decorator to restrict access to users with report viewing capabilities.
    This allows role-based access control to report pages.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        
        # Superadmins and admins always have access
        if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
            return view_func(request, *args, **kwargs)
        
        # Check if user has a system role with report access by default
        if user.role in ['admin', 'instructor']:
            return view_func(request, *args, **kwargs)
        
        # Check primary role capabilities using PermissionManager
        try:
            from role_management.utils import PermissionManager
            
            # Check for view_reports capability through primary role
            if PermissionManager.user_has_capability(user, 'view_reports'):
                return view_func(request, *args, **kwargs)
                
        except Exception as e:
            logger.error(f"Error checking primary role report access for user {user.id}: {str(e)}")
            
        # Check for report-related capabilities through user roles
        try:
            user_roles = UserRole.objects.filter(user=user)
            if user_roles.exists():
                for user_role in user_roles:
                    # Check for any report-related capability
                    report_capabilities = [
                        'view_reports',
                        'reports_overview',
                        'courses_reports',
                        'users_reports',
                        'branches_reports',
                        'groups_reports',
                        'timeline',
                        'training_matrix',
                        'custom_reports',
                        'learning_activities'
                    ]
                    
                    has_report_access = RoleCapability.objects.filter(
                        role=user_role.role,
                        capability__in=report_capabilities
                    ).exists()
                    
                    if has_report_access:
                        return view_func(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error checking user role report access for user {user.id}: {str(e)}")
        
        # If we reach here, user doesn't have access
        messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
        return redirect('users:role_based_redirect')
    return _wrapped_view

class ReportForm(forms.Form):
    content = CustomTinyMCEFormField()

# Enhanced filtering utilities for role-based report access
def get_user_accessible_businesses(user):
    """Get businesses that a user has access to based on their role"""
    from business.models import Business
    
    if user.role == 'globaladmin' or user.is_superuser:
        return Business.objects.all()
    elif user.role == 'superadmin':
        # Super Admin can only see their assigned businesses
        return Business.objects.filter(
            user_assignments__user=user,
            user_assignments__is_active=True
        )
    else:
        # Other roles don't have business-level access
        return Business.objects.none()

def get_user_accessible_branches(user, business_id=None):
    """Get branches that a user has access to based on their role"""
    from branches.models import Branch
    
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin can see all branches
        branches = Branch.objects.all()
        if business_id and business_id != 'all':
            try:
                branches = branches.filter(business_id=int(business_id))
            except (ValueError, TypeError):
                pass
        return branches
    
    elif user.role == 'superadmin':
        # Super Admin can see branches from their assigned businesses
        accessible_businesses = get_user_accessible_businesses(user)
        branches = Branch.objects.filter(business__in=accessible_businesses)
        if business_id and business_id != 'all':
            try:
                branches = branches.filter(business_id=int(business_id))
            except (ValueError, TypeError):
                pass
        return branches
    
    elif user.role in ['admin', 'instructor'] and user.branch:
        # Admin/Instructor can only see their own branch
        return Branch.objects.filter(id=user.branch.id)
    
    else:
        # Learners and others have no branch access
        return Branch.objects.none()

def apply_role_based_filtering(user, queryset, business_id=None, branch_id=None, request=None):
    """
    Apply role-based filtering to any queryset based on user permissions.
    
    Args:
        user: The requesting user
        queryset: The base queryset to filter
        business_id: Optional business filter (for Global Admin)
        branch_id: Optional branch filter (for Global Admin and Super Admin)
        request: Optional request object for admin branch switching support
    
    Returns:
        Filtered queryset based on user role and permissions
    """
    
    # Global Admin - Can see all data with optional business/branch filters
    if user.role == 'globaladmin' or user.is_superuser:
        filtered_qs = queryset
        
        # Apply business filter if provided
        if business_id and business_id != 'all':
            try:
                business_id = int(business_id)
                if hasattr(queryset.model, 'branch'):
                    filtered_qs = filtered_qs.filter(branch__business_id=business_id)
                elif queryset.model.__name__ == 'CustomUser':
                    filtered_qs = filtered_qs.filter(branch__business_id=business_id)
                elif queryset.model.__name__ == 'CourseEnrollment':
                    filtered_qs = filtered_qs.filter(user__branch__business_id=business_id)
                elif queryset.model.__name__ == 'Event':
                    filtered_qs = filtered_qs.filter(user__branch__business_id=business_id)
                elif queryset.model.__name__ == 'Course':
                    filtered_qs = filtered_qs.filter(branch__business_id=business_id)
                elif queryset.model.__name__ == 'TopicProgress':
                    filtered_qs = filtered_qs.filter(user__branch__business_id=business_id)
            except (ValueError, TypeError):
                pass
        
        # Apply branch filter if provided with proper validation
        validated_branch_id = validate_branch_id(branch_id)
        if validated_branch_id is not None:
            if hasattr(queryset.model, 'branch'):
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'CustomUser':
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'CourseEnrollment':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'Event':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'Course':
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'TopicProgress':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
        
        return filtered_qs
    
    # Super Admin - Can see only their business data with optional branch filter
    elif user.role == 'superadmin':
        # Determine the business field path based on queryset model
        if hasattr(queryset.model, 'branch'):
            business_field_path = 'branch__business'
        elif queryset.model.__name__ == 'CustomUser':
            business_field_path = 'branch__business'  
        elif queryset.model.__name__ == 'CourseEnrollment':
            business_field_path = 'user__branch__business'
        elif queryset.model.__name__ == 'Event':
            business_field_path = 'user__branch__business'
        elif queryset.model.__name__ == 'Course':
            business_field_path = 'branch__business'
        elif queryset.model.__name__ == 'TopicProgress':
            business_field_path = 'user__branch__business'
        else:
            # Default fallback
            business_field_path = 'business'
        
        filtered_qs = filter_queryset_by_business(queryset, user, business_field_path)
        
        # Apply branch filter if provided with proper validation
        validated_branch_id = validate_branch_id(branch_id)
        if validated_branch_id is not None:
            if hasattr(queryset.model, 'branch'):
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'CustomUser':
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'CourseEnrollment':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'Event':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'Course':
                filtered_qs = filtered_qs.filter(branch_id=validated_branch_id)
            elif queryset.model.__name__ == 'TopicProgress':
                filtered_qs = filtered_qs.filter(user__branch_id=validated_branch_id)
        
        return filtered_qs
    
    # Instructor/Admin - Can see only their branch data (admin supports branch switching)
    elif user.role in ['admin', 'instructor']:
        # Get the effective branch for the user
        if user.role == 'admin' and request:
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(user, request)
        else:
            effective_branch = user.branch
            
        if effective_branch:
            if queryset.model.__name__ == 'Branch':
                return queryset.filter(id=effective_branch.id)
            elif hasattr(queryset.model, 'branch'):
                return queryset.filter(branch=effective_branch)
            elif queryset.model.__name__ == 'CustomUser':
                return queryset.filter(branch=effective_branch)
            elif queryset.model.__name__ == 'CourseEnrollment':
                if user.role == 'instructor':
                    # For instructors, include enrollments from group-assigned courses
                    group_courses = queryset.model.objects.filter(
                        course__accessible_groups__memberships__user=user,
                        course__accessible_groups__memberships__is_active=True,
                        course__accessible_groups__memberships__custom_role__name__icontains='instructor'
                    ).values_list('course_id', flat=True)
                    return queryset.filter(
                        Q(user__branch=effective_branch) | Q(course_id__in=group_courses)
                    )
                else:
                    return queryset.filter(user__branch=effective_branch)
            elif queryset.model.__name__ == 'Event':
                return queryset.filter(user__branch=effective_branch)
            elif queryset.model.__name__ == 'Course':
                if user.role == 'instructor':
                    # For instructors, include group-assigned courses
                    return queryset.filter(
                        Q(branch=effective_branch) |
                        Q(accessible_groups__memberships__user=user,
                          accessible_groups__memberships__is_active=True,
                          accessible_groups__memberships__custom_role__name__icontains='instructor')
                    ).distinct()
                else:
                    return queryset.filter(branch=effective_branch)
            elif queryset.model.__name__ == 'TopicProgress':
                if user.role == 'instructor':
                    # For instructors, include progress from group-assigned courses
                    group_courses = queryset.model.objects.filter(
                        topic__courses__accessible_groups__memberships__user=user,
                        topic__courses__accessible_groups__memberships__is_active=True,
                        topic__courses__accessible_groups__memberships__custom_role__name__icontains='instructor'
                    ).values_list('topic__courses', flat=True)
                    return queryset.filter(
                        Q(user__branch=effective_branch) |
                        Q(topic__courses__in=group_courses)
                    ).distinct()
                else:
                    return queryset.filter(user__branch=effective_branch)
    
    # Learner - Can see only their own data where they act as learners (Fixed Role Logic)
    elif user.role == 'learner':
        if queryset.model.__name__ == 'CustomUser':
            return queryset.filter(id=user.id)
        elif queryset.model.__name__ == 'CourseEnrollment':
            # Learners can only see their own enrollments
            return queryset.filter(user=user)
        elif queryset.model.__name__ == 'Event':
            return queryset.filter(user=user)
        else:
            # For other models, return empty queryset for learners
            return queryset.none()
    
    # Default fallback
    return queryset

def get_report_filter_context(user, request):
    """
    Get filter context data for report templates based on user role.
    
    Returns a dictionary with:
    - businesses: Available businesses for filtering (Global Admin only)
    - branches: Available branches for filtering (Global Admin and Super Admin)
    - selected_business_id: Currently selected business ID
    - selected_branch_id: Currently selected branch ID
    - show_business_filter: Whether to show business filter
    - show_branch_filter: Whether to show branch filter
    """
    
    context = {
        'businesses': [],
        'branches': [],
        'selected_business_id': None,
        'selected_branch_id': None,
        'show_business_filter': False,
        'show_branch_filter': False,
    }
    
    # Get filter parameters from request
    business_id = request.GET.get('business')
    branch_id = request.GET.get('branch')
    
    context['selected_business_id'] = business_id
    context['selected_branch_id'] = branch_id
    
    # Global Admin gets both business and branch filters
    if user.role == 'globaladmin' or user.is_superuser:
        context['show_business_filter'] = True
        context['show_branch_filter'] = True
        context['businesses'] = get_user_accessible_businesses(user)
        context['branches'] = get_user_accessible_branches(user, business_id)
    
    # Super Admin gets only branch filter (for their accessible branches)
    elif user.role == 'superadmin':
        context['show_branch_filter'] = True
        context['branches'] = get_user_accessible_branches(user, business_id)
    
    # Instructor/Admin/Learner get no filters (data is already restricted by role)
    
    return context

# Use apply_role_based_filtering for filtering

@login_required
@reports_access_required
def reports_view(request):
    """View for displaying the reports list."""
    reports = Report.objects.filter(
        Q(created_by=request.user) | 
        Q(shared_with=request.user)
    ).distinct()
    
    context = {
        'reports': reports,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Reports', 'icon': 'fa-chart-bar'}
        ]
    }
    return render(request, 'reports/reports.html', context)

@login_required
@reports_access_required
def user_reports_list(request):
    """View for displaying the user reports list."""
    from users.models import CustomUser
    from django.core.paginator import Paginator
    from django.db.models import Count, Q, Avg
    from quiz.models import QuizAttempt
    
    # Check if export is requested
    if request.GET.get('export') == 'excel':
        return export_user_reports_to_excel(request)
    
    # Get users based on role permissions
    if request.user.role in ['globaladmin', 'superadmin']:
        users = CustomUser.objects.filter(is_active=True).exclude(role__in=['globaladmin'])
    elif request.user.role in ['admin', 'instructor']:
        # Allow admins and instructors to see users in their branch
        if request.user.branch:
            users = CustomUser.objects.filter(branch=request.user.branch, is_active=True).exclude(role__in=['globaladmin', 'superadmin'])
        else:
            # If no branch, show all non-admin users
            users = CustomUser.objects.filter(is_active=True).exclude(role__in=['globaladmin', 'superadmin', 'admin'])
    else:
        users = CustomUser.objects.none()
    
    # Annotate users with required statistics that templates expect
    users = users.annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        initial_assessment_count=Count('module_quiz_attempts', filter=Q(
            module_quiz_attempts__quiz__is_initial_assessment=True, 
            module_quiz_attempts__is_completed=True
        ), distinct=True)
    ).order_by('username')
    
    # Calculate aggregate statistics for the overview cards
    total_users = users.count()
    if total_users > 0:
        # Get all users data for calculations (evaluate queryset once)
        users_list = list(users)
        
        # Calculate totals
        total_assigned = sum(user.assigned_count for user in users_list)
        total_completed = sum(user.completed_count for user in users_list)
        
        # Calculate in-progress courses (enrolled, not completed, has been accessed)
        courses_in_progress = CourseEnrollment.objects.filter(
            user__in=[user.id for user in users_list],
            completed=False,
            last_accessed__isnull=False
        ).count()
        
        # Calculate not passed courses (enrolled, not completed, has been accessed)
        # Note: CourseEnrollment doesn't have score field, so we count incomplete accessed courses
        courses_not_passed = CourseEnrollment.objects.filter(
            user__in=[user.id for user in users_list],
            completed=False,
            last_accessed__isnull=False
        ).count()
        
        # Calculate not started courses (enrolled but never accessed)
        courses_not_started = CourseEnrollment.objects.filter(
            user__in=[user.id for user in users_list],
            last_accessed__isnull=True
        ).count()
        
        # Calculate completion rate
        completion_rate = round((total_completed / total_assigned * 100) if total_assigned > 0 else 0, 1)
        
        # Get initial assessment statistics
        total_initial_assessments = QuizAttempt.objects.filter(
            user__in=[user.id for user in users_list], 
            quiz__is_initial_assessment=True, 
            is_completed=True
        ).count()
        
        avg_initial_assessment_score = QuizAttempt.objects.filter(
            user__in=[user.id for user in users_list],
            quiz__is_initial_assessment=True,
            is_completed=True
        ).aggregate(avg_score=Avg('score'))['avg_score'] or 0
        
        # Re-create queryset for pagination
        users = users.annotate(
            assigned_count=Count('courseenrollment', distinct=True),
            completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
            initial_assessment_count=Count('module_quiz_attempts', filter=Q(
                module_quiz_attempts__quiz__is_initial_assessment=True, 
                module_quiz_attempts__is_completed=True
            ), distinct=True)
        ).order_by('username')
    else:
        completion_rate = 0
        total_completed = courses_in_progress = courses_not_passed = courses_not_started = 0
        total_initial_assessments = avg_initial_assessment_score = 0
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get filter context for consistency with other report views
    filter_context = get_report_filter_context(request.user, request)
    
    context = {
        'users': page_obj,
        'page_obj': page_obj,
        # Add missing statistical context variables that templates expect
        'completion_rate': completion_rate,
        'completed_courses': total_completed,
        'courses_in_progress': courses_in_progress,
        'courses_not_passed': courses_not_passed,
        'courses_not_started': courses_not_started,
        'total_initial_assessments': total_initial_assessments,
        'avg_initial_assessment_score': round(avg_initial_assessment_score, 1),
        # Add breadcrumbs for consistency
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'User Reports', 'icon': 'fa-users'}
        ]
    }
    
    # Add filter context (business/branch filters)
    context.update(filter_context)
    
    return render(request, 'reports/user_reports.html', context)

class LearningActivitiesView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/learning_activities.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has report viewing capabilities
        user = request.user
        
        # Check if user is authenticated first
        if not user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # Let LoginRequiredMixin handle redirect
        
        # Superadmins and admins always have access
        if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
            return super().dispatch(request, *args, **kwargs)
            
        # Check if user has a system role with report access by default
        if user.role in ['admin', 'instructor']:
            return super().dispatch(request, *args, **kwargs)
        
        # If we reach here, user doesn't have access
        messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
        return redirect('users:role_based_redirect')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get query parameters
        search_query = self.request.GET.get('search', '')
        per_page = int(self.request.GET.get('per_page', 10))
        page = int(self.request.GET.get('page', 1))
        
        # Apply role-based filtering for topics and progress data
        user = self.request.user
        
        # Get filtered topics based on user role and branch access
        if user.role == 'globaladmin' or user.is_superuser:
            # Global Admin can see all topics
            activities = Topic.objects.all()
            progress_base_query = TopicProgress.objects.all()
        elif user.role == 'superadmin':
            # Super Admin can see topics from courses in their assigned businesses
            from core.utils.business_filtering import filter_courses_by_business
            accessible_courses = filter_courses_by_business(user)
            activities = Topic.objects.filter(coursetopic__course__in=accessible_courses).distinct()
            progress_base_query = TopicProgress.objects.filter(
                topic__coursetopic__course__in=accessible_courses
            ).distinct()
        elif user.role == 'admin':
            # Branch Admin can only see topics from their branch
            if user.branch:
                activities = Topic.objects.filter(coursetopic__course__branch=user.branch).distinct()
                progress_base_query = TopicProgress.objects.filter(
                    topic__coursetopic__course__branch=user.branch
                ).distinct()
            else:
                activities = Topic.objects.none()
                progress_base_query = TopicProgress.objects.none()
        elif user.role == 'instructor':
            # Instructor can see topics from courses they teach or from their branch
            if user.branch:
                activities = Topic.objects.filter(
                    Q(coursetopic__course__instructor=user) |
                    Q(coursetopic__course__branch=user.branch)
                ).distinct()
                progress_base_query = TopicProgress.objects.filter(
                    Q(topic__coursetopic__course__instructor=user) |
                    Q(topic__coursetopic__course__branch=user.branch)
                ).distinct()
            else:
                activities = Topic.objects.filter(coursetopic__course__instructor=user).distinct()
                progress_base_query = TopicProgress.objects.filter(
                    topic__coursetopic__course__instructor=user
                ).distinct()
        else:
            # Other roles have no access
            activities = Topic.objects.none()
            progress_base_query = TopicProgress.objects.none()
        
        # Apply search filter if provided
        if search_query:
            activities = activities.filter(title__icontains=search_query)
        
        # Get activity data with progress statistics
        activity_data = []
        for topic in activities:
            topic_progress = progress_base_query.filter(topic=topic)

            # Calculate progress statistics
            total_progress = topic_progress.count()
            completed = topic_progress.filter(completed=True).count()

            in_progress = topic_progress.filter(completed=False, last_score__gt=0).count()
            not_passed = topic_progress.filter(completed=False, last_score=0).count()
            not_attempted = total_progress - completed - in_progress - not_passed

            # Calculate average score with normalization
            scores = topic_progress.exclude(last_score__isnull=True).values_list('last_score', flat=True)
            normalized_scores = []
            for score in scores:
                norm_score = normalize_score(score)
                if norm_score is not None:
                    normalized_scores.append(norm_score)

            average_score = sum(normalized_scores) / len(normalized_scores) if normalized_scores else 0
            
            activity_data.append({
                'topic': topic,
                'completed': completed,
                'in_progress': in_progress,
                'not_passed': not_passed,
                'not_attempted': not_attempted,
                'average_score': round(average_score, 1),
            })
        
        # Pagination
        from django.core.paginator import Paginator
        paginator = Paginator(activity_data, per_page)
        page_obj = paginator.get_page(page)
        
        # Calculate overall statistics
        total_progress = sum(item['completed'] + item['in_progress'] + item['not_passed'] + item['not_attempted'] for item in activity_data)
        completed = sum(item['completed'] for item in activity_data)
        in_progress = sum(item['in_progress'] for item in activity_data)
        not_passed = sum(item['not_passed'] for item in activity_data)
        not_attempted = sum(item['not_attempted'] for item in activity_data)
        
        overall_completion_rate = round((completed / total_progress * 100) if total_progress > 0 else 0, 1)
        
        # Calculate overall average score with proper weighting and normalization
        total_score_sum = 0
        total_activity_count = 0
        
        for item in activity_data:
            if item['average_score'] > 0:  # Only include activities that have scores
                total_score_sum += item['average_score']
                total_activity_count += 1
        
        overall_average_score = round(total_score_sum / total_activity_count, 1) if total_activity_count > 0 else 0
        
        # Add context data
        context.update({
            'activities': page_obj,
            'page_obj': page_obj,
            'search_query': search_query,
            'total_progress': total_progress,
            'completed': completed,
            'in_progress': in_progress,
            'not_passed': not_passed,
            'not_attempted': not_attempted,
            'overall_completion_rate': overall_completion_rate,
            'average_score': overall_average_score,
            'breadcrumbs': [
                {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
                {'label': 'Learning Activities', 'icon': 'fa-tasks'}
            ]
        })
        
        return context

@login_required
@reports_access_required
def new_report(request):
    """View for creating a new report."""
    from branches.models import Branch
    from courses.models import Course
    from groups.models import BranchGroup
    from django.contrib import messages
    
    # Get all branches and their users, filtered by user's branch if applicable
    if request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']:
        branches = Branch.objects.all().prefetch_related('users')
        groups = BranchGroup.objects.all()
        courses = Course.objects.all()
    else:
        # Regular users can only see their own branch
        branches = Branch.objects.filter(id=request.user.branch_id).prefetch_related('users') if request.user.branch else Branch.objects.none()
        groups = BranchGroup.objects.filter(branch=request.user.branch) if request.user.branch else BranchGroup.objects.none()
        courses = Course.objects.filter(branch=request.user.branch) if request.user.branch else Course.objects.none()
    
    # Prepare context data for the template
    context_data = {
        'branches': list(branches.values('id', 'name')),
        'groups': list(groups.values('id', 'name')),
        'courses': list(courses.values('id', 'title')),
    }
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.POST.get('title')
            report_type = request.POST.get('report_type')
            
            # Validate required fields
            if not title:
                messages.error(request, 'Report title is required.')
                return render(request, 'reports/new_report.html', {'context_data': context_data})
            
            if not report_type:
                messages.error(request, 'Report type is required.')
                return render(request, 'reports/new_report.html', {'context_data': context_data})
            
            # Process rules
            rules = {}
            rule_type = request.POST.get('rule')
            if rule_type:
                rule_value = request.POST.get(f'rule_{rule_type}')
                if rule_value:
                    rules[rule_type] = rule_value
            
            # Process output fields
            output_fields = request.POST.getlist('output_fields[]')
            if not output_fields:
                # Default fields if none selected
                output_fields = ['user', 'email', 'user_type', 'registration_date', 'assigned_courses', 'completed_courses', 'initial_assessments_completed']
            
            # Create report with transaction safety
            with transaction.atomic():
                report = Report.objects.create(
                    title=title,
                    description=f"Custom {report_type.replace('_', ' ').title()} Report",
                    report_type=report_type,
                    rules=rules,
                    output_fields=output_fields,
                    created_by=request.user
                )
            
            messages.success(request, 'Report created successfully!')
            return redirect('reports:report_detail', report_id=report.id)
        
        except Exception as e:
            logger.error(f'Error creating report for user {request.user.id}: {str(e)}')
            messages.error(request, f'Error creating report: {str(e)}')
            return render(request, 'reports/new_report.html', {'context_data': context_data})
    
    context = {
        'context_data': context_data,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:reports'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'New Report', 'icon': 'fa-plus'}
        ]
    }
    return render(request, 'reports/new_report.html', context)

@login_required
@reports_access_required
def report_detail(request, report_id):
    """View for displaying a single report with generated data."""
    report = get_object_or_404(
        Report.objects.prefetch_related('attachments'),
        id=report_id
    )
    
    # Enhanced access control check
    has_access = False
    
    # Check if user is the creator
    if report.created_by == request.user:
        has_access = True
    # Check if report is shared with user
    elif request.user in report.shared_with.all():
        has_access = True
    # Check if user has admin privileges and report is from same branch/business
    elif request.user.role in ['globaladmin', 'superadmin'] or request.user.is_superuser:
        has_access = True
    elif request.user.role in ['admin', 'instructor']:
        # Branch-level access for admins/instructors
        if (request.user.branch and report.created_by.branch and 
            request.user.branch == report.created_by.branch):
            has_access = True
    
    if not has_access:
        messages.error(request, "You don't have permission to access this report.")
        return redirect('reports:reports')
    
    # Check if export is requested
    export_format = request.GET.get('export')
    if export_format in ['excel', 'csv']:
        return export_custom_report(request, report, export_format)
    
    # Generate report data
    report_data = generate_report_data(report, request.user)
    
    context = {
        'report': report,
        'report_data': report_data,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:reports'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': report.title, 'icon': 'fa-file-alt'}
        ]
    }
    return render(request, 'reports/report_detail.html', context)

def generate_report_data(report, user):
    """Generate report data based on report configuration."""
    from courses.models import Course, CourseEnrollment
    from branches.models import Branch
    from groups.models import BranchGroup
    from django.db.models import Count, F, Sum, Avg
    
    # Start with all users based on user's permissions (filtered to learners only)
    if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
        users_queryset = User.objects.filter(role='learner')
    else:
        # Regular users can only see their own branch users (learners only)
        if user.branch:
            users_queryset = User.objects.filter(branch=user.branch, role='learner')
        else:
            users_queryset = User.objects.filter(role='learner')
    
    # Apply rules filtering
    if report.rules:
        for rule_type, rule_value in report.rules.items():
            if rule_type == 'branch' and rule_value:
                users_queryset = users_queryset.filter(branch_id=rule_value)
            elif rule_type == 'group' and rule_value:
                users_queryset = users_queryset.filter(groups__id=rule_value)
            elif rule_type == 'course' and rule_value:
                users_queryset = users_queryset.filter(courseenrollment__course_id=rule_value)
    
    # Get the fields to include in the report
    output_fields = report.output_fields or ['user', 'email', 'user_type', 'registration_date']
    
    # Generate the report data
    report_data = []
    
    # Optimize query based on required fields
    select_related = []
    prefetch_related = []
    
    if 'branch' in output_fields:
        select_related.append('branch')
    if 'assigned_courses' in output_fields or 'completed_courses' in output_fields:
        prefetch_related.append('courseenrollment_set__course')
    if 'group' in output_fields:
        prefetch_related.append('groups')
    
    # Apply optimizations
    if select_related:
        users_queryset = users_queryset.select_related(*select_related)
    if prefetch_related:
        users_queryset = users_queryset.prefetch_related(*prefetch_related)
    
    # Sync completion status for all users' enrollments before calculating annotations
    for user_obj in users_queryset:
        CourseEnrollment.sync_user_completions(user_obj)
    
    # Add annotations for calculated fields
    users_queryset = users_queryset.annotate(
        total_courses=Count('courseenrollment', distinct=True),
        completed_courses_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        progress_percentage=Case(
            When(total_courses=0, then=Value(0.0)),
            default=ExpressionWrapper(
                F('completed_courses_count') * 100.0 / F('total_courses'),
                output_field=fields.FloatField()
            ),
            output_field=fields.FloatField()
        )
    )
    
    for user_obj in users_queryset:
        row = {}
        
        # Add data based on selected output fields
        if 'user' in output_fields:
            row['user'] = user_obj.get_full_name() or user_obj.username
        
        if 'email' in output_fields:
            row['email'] = user_obj.email
        
        if 'user_type' in output_fields:
            row['user_type'] = user_obj.get_role_display() if hasattr(user_obj, 'get_role_display') else user_obj.role
        
        if 'registration_date' in output_fields:
            row['registration_date'] = user_obj.date_joined.strftime('%Y-%m-%d') if user_obj.date_joined else 'N/A'
        
        if 'last_login' in output_fields:
            row['last_login'] = user_obj.last_login.strftime('%Y-%m-%d %H:%M') if user_obj.last_login else 'Never'
        
        if 'branch' in output_fields:
            row['branch'] = user_obj.branch.name if user_obj.branch else 'N/A'
        
        if 'group' in output_fields:
            groups = user_obj.groups.all()
            row['group'] = ', '.join([group.name for group in groups]) if groups else 'N/A'
        
        if 'assigned_courses' in output_fields:
            row['assigned_courses'] = user_obj.total_courses or 0
        
        if 'completed_courses' in output_fields:
            row['completed_courses'] = user_obj.completed_courses_count or 0
        
        if 'progress_percentage' in output_fields:
            progress = user_obj.progress_percentage or 0
            row['progress_percentage'] = f"{progress:.1f}%" if progress else "0.0%"
        
        # Initial Assessment fields
        if 'initial_assessments_completed' in output_fields:
            from quiz.models import QuizAttempt
            assessments_count = QuizAttempt.objects.filter(
                user=user_obj,
                quiz__is_initial_assessment=True,
                is_completed=True
            ).count()
            row['initial_assessments_completed'] = assessments_count
        
        if 'latest_assessment_score' in output_fields:
            from quiz.models import QuizAttempt
            latest_attempt = QuizAttempt.objects.filter(
                user=user_obj,
                quiz__is_initial_assessment=True,
                is_completed=True
            ).order_by('-end_time').first()
            row['latest_assessment_score'] = f"{latest_attempt.score:.1f}%" if latest_attempt else "N/A"
        
        if 'avg_assessment_score' in output_fields:
            from quiz.models import QuizAttempt
            from django.db.models import Avg
            avg_score = QuizAttempt.objects.filter(
                user=user_obj,
                quiz__is_initial_assessment=True,
                is_completed=True
            ).aggregate(avg_score=Avg('score'))['avg_score']
            row['avg_assessment_score'] = f"{avg_score:.1f}%" if avg_score else "N/A"
        
        report_data.append(row)
    
    # Prepare summary statistics
    total_users = len(report_data)
    summary = {
        'total_users': total_users,
        'generated_at': timezone.now(),
        'report_type': report.get_report_type_display(),
        'output_fields': output_fields,
        'applied_rules': report.rules
    }
    
    return {
        'data': report_data,
        'summary': summary,
        'headers': [field.replace('_', ' ').title() for field in output_fields]
    }

def export_custom_report(request, report, export_format):
    """Export custom report data to Excel or CSV."""
    import xlwt
    from django.http import HttpResponse
    
    # Generate report data
    report_data = generate_report_data(report, request.user)
    
    if export_format == 'excel':
        # Create Excel workbook
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Report Data')
        
        # Write headers
        for col, header in enumerate(report_data['headers']):
            ws.write(0, col, header)
        
        # Write data
        for row_idx, row_data in enumerate(report_data['data'], 1):
            for col_idx, field in enumerate(report.output_fields):
                value = row_data.get(field, '')
                ws.write(row_idx, col_idx, str(value))
        
        # Create response
        response = HttpResponse(content_type='application/ms-excel')
        response['Content-Disposition'] = f'attachment; filename="{report.title}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xls"'
        wb.save(response)
        return response
    
    elif export_format == 'csv':
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{report.title}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(report_data['headers'])
        
        for row_data in report_data['data']:
            row = [str(row_data.get(field, '')) for field in report.output_fields]
            writer.writerow(row)
        
        return response

@login_required
@reports_access_required
@require_POST
def upload_attachment(request):
    """Handle file uploads for reports with Session validation"""
    try:
        if 'upload' not in request.FILES:
            return JsonResponse({'error': 'No file uploaded'}, status=400)

        upload = request.FILES['upload']
        
        # Check storage permission before upload
        from core.utils.storage_manager import StorageManager
        can_upload, error_message = StorageManager.check_upload_permission(
            request.user, 
            upload.size
        )
        
        if not can_upload:
            return JsonResponse({
                'uploaded': 0,
                'error': {
                    'message': error_message
                },
                'storage_limit_exceeded': True
            }, status=403)
        
        # Session validation: File size limit (10MB)
        max_file_size = 10 * 1024 * 1024  # 10MB
        if upload.size > max_file_size:
            return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)
        
        # Session validation: Allowed file extensions
        allowed_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.png', '.jpg', '.jpeg', '.gif'}
        ext = os.path.splitext(upload.name)[1].lower()
        
        if ext not in allowed_extensions:
            return JsonResponse({'error': f'File type {ext} not allowed'}, status=400)
        
        # Session validation: Sanitize filename to prevent path traversal
        original_name = os.path.basename(upload.name)
        # More restrictive filename sanitization - only allow alphanumeric, hyphens, underscores, and single dots
        safe_name = "".join(c for c in original_name if c.isalnum() or c in ('-', '_', '.'))
        # Remove any multiple dots that could be used for path traversal
        while '..' in safe_name:
            safe_name = safe_name.replace('..', '.')
        # Ensure filename is not empty and doesn't start with a dot (hidden files)
        if not safe_name or safe_name.startswith('.'):
            safe_name = f"upload_{uuid.uuid4().hex[:8]}"
        
        # Generate a unique filename with safe extension
        filename = f"{uuid.uuid4()}_{safe_name}"
        
        # Use Django's default storage (works with both local and S3)
        from django.core.files.storage import default_storage
        
        # Save file using default storage
        file_path = f"report_attachments/{filename}"
        saved_path = default_storage.save(file_path, upload)
        
        # Register file in media database for tracking
        try:
            from lms_media.utils import register_media_file
            register_media_file(
                file_path=saved_path,
                uploaded_by=request.user,
                source_type='report_attachment',
                filename=upload.name,
                description=f'Report attachment uploaded on {timezone.now().date()}'
            )
        except Exception as e:
            logger.error(f"Error registering report attachment in media database: {str(e)}")
        
        # Register file in storage tracking system
        try:
            StorageManager.register_file_upload(
                user=request.user,
                file_path=saved_path,
                original_filename=upload.name,
                file_size_bytes=upload.size,
                content_type=upload.content_type,
                source_app='reports',
                source_model='Report',
            )
        except Exception as e:
            logger.error(f"Error registering file in storage tracking: {str(e)}")
            # Continue with upload even if registration fails
        
        # Return the URL for the uploaded file using default storage
        file_url = default_storage.url(saved_path)
        return JsonResponse({
            'uploaded': 1,
            'fileName': filename,
            'url': file_url
        })
        
    except Exception as e:
        return JsonResponse({
            'uploaded': 0,
            'error': {
                'message': str(e)
            }
        }, status=500)

# Add branch parameter handler
def handle_branch_parameter(request, queryset):
    """
    Handle the branch parameter from request.GET
    """
    branch_id = request.GET.get('branch')
    
    # Skip if branch parameter not present or user is not superadmin
    if not branch_id or not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin']):
        return queryset
        
    # If "all" is specified, return all data
    if branch_id == 'all':
        return queryset
        
    # Safely validate and filter by branch ID
    validated_branch_id = validate_branch_id(branch_id)
    if validated_branch_id is not None:
        if hasattr(queryset.model, 'branch'):
            return queryset.filter(branch_id=validated_branch_id)
        elif queryset.model.__name__ == 'CustomUser':
            return queryset.filter(branch_id=validated_branch_id)
        elif queryset.model.__name__ == 'CourseEnrollment':
            return queryset.filter(user__branch_id=validated_branch_id)
        
    return queryset

@login_required
@reports_access_required
def overview(request):
    """View for displaying the overview dashboard."""
    # Get filter parameters
    business_id = request.GET.get('business')
    branch_id = request.GET.get('branch')
    
    # Get filter context for the template
    filter_context = get_report_filter_context(request.user, request)
    
    # Get user statistics with role-based filtering
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Apply role-based filtering to users
    users_queryset = User.objects.all()
    users_queryset = apply_role_based_filtering(request.user, users_queryset, business_id, branch_id, request)
    
    # Include ALL user roles including custom roles - no role filtering for activity data
    # users_queryset = users_queryset.filter(role='learner')  # REMOVED - include all roles
    
    active_users = users_queryset.filter(last_login__gte=thirty_days_ago).count()
    never_logged_in = users_queryset.filter(last_login__isnull=True).count()
    
    # Apply role-based filtering to courses
    courses_queryset = Course.objects.all()
    courses_queryset = apply_role_based_filtering(request.user, courses_queryset, business_id, branch_id, request)
    
    # Optimize course queries
    course_stats = courses_queryset.aggregate(
        assigned_count=Count('id', filter=Q(instructor__isnull=False)),
        total_count=Count('id')
    )
    
    # Apply role-based filtering to enrollments
    enrollments_queryset = CourseEnrollment.objects.all()
    enrollments_queryset = apply_role_based_filtering(request.user, enrollments_queryset, business_id, branch_id, request)
    
    # For completion rate calculations, only include learner role users
    enrollments_queryset = enrollments_queryset.filter(user__role='learner')
    
    completed_courses = enrollments_queryset.filter(completed=True).distinct().count()
    
    # Get initial assessment statistics
    from quiz.models import Quiz, QuizAttempt
    initial_assessments_queryset = QuizAttempt.objects.filter(
        quiz__is_initial_assessment=True,
        is_completed=True
    )
    
    # Apply role-based filtering to the users, then filter quiz attempts by those users
    filtered_users = apply_role_based_filtering(request.user, User.objects.all(), business_id, branch_id, request)
    
    # Apply the same role-specific filtering as used for users_queryset - MODIFIED TO SHOW ONLY LEARNER USERS
    # All users regardless of role will only see learner role users in reports
    filtered_users = filtered_users.filter(role='learner')
    
    initial_assessments_queryset = initial_assessments_queryset.filter(user__in=filtered_users)
    
    total_initial_assessments = initial_assessments_queryset.count()
    avg_initial_assessment_score = initial_assessments_queryset.aggregate(
        avg_score=Avg('score')
    )['avg_score'] or 0
    
    # Count users with completed initial assessments
    users_with_assessments = initial_assessments_queryset.values('user').distinct().count()
    
    # Calculate learning structure statistics with role-based filtering
    accessible_branches = get_user_accessible_branches(request.user, business_id)
    
    if request.user.role in ['globaladmin'] or request.user.is_superuser:
        # Global Admin sees all data (filtered by current filters)
        total_branches = accessible_branches.count()
        total_categories = CourseCategory.objects.filter(
            courses__in=courses_queryset
        ).distinct().count()
        total_groups = BranchGroup.objects.filter(
            branch__in=accessible_branches
        ).count()
    elif request.user.role == 'superadmin':
        # Super Admin sees business-scoped data
        total_branches = accessible_branches.count()
        total_categories = CourseCategory.objects.filter(
            courses__in=courses_queryset
        ).distinct().count()
        total_groups = BranchGroup.objects.filter(
            branch__in=accessible_branches
        ).count()
    else:
        # For regular users, only show their branch data
        total_branches = 1 if request.user.branch else 0
        total_categories = CourseCategory.objects.filter(
            courses__in=courses_queryset
        ).distinct().count()
        total_groups = BranchGroup.objects.filter(
            branch=request.user.branch
        ).count() if request.user.branch else 0
    
    structure_stats = {
        'total_courses': course_stats['total_count'],
        'total_categories': total_categories,
        'total_branches': total_branches,
        'total_groups': total_groups
    }
    
    # Get activity data with role-based filtering applied
    try:
        # Use dashboard cache method but apply role-based filtering for consistency
        from core.utils.dashboard_cache import DashboardCache
        from django.db.models.functions import ExtractHour
        from core.timezone_utils import TimezoneManager
        
        # Calculate activity data with proper role-based filtering for current month
        import calendar
        now = timezone.now()
        
        # Get user timezone information
        timezone_info = TimezoneManager.get_timezone_info(request.user)
        
        # Convert to user timezone for proper date calculation
        user_now = TimezoneManager.convert_to_user_timezone(now, request.user)
        
        # Get first day of current month in user timezone
        month_start = user_now.replace(day=1).date()
        
        # Get number of days in current month
        days_in_month = calendar.monthrange(user_now.year, user_now.month)[1]
        
        # Generate date range for current month only up to today (in user timezone)
        date_range = []
        for day_num in range(1, days_in_month + 1):
            day_date = month_start.replace(day=day_num)
            if day_date <= user_now.date():  # Only include days up to today
                date_range.append(day_date)
            else:
                break
        
        start_date = date_range[0] if date_range else user_now.date()
        end_date = date_range[-1] if date_range else user_now.date()
        
        # Initialize data structures with day numbers (1, 2, 3...)
        activity_dates = [date.strftime('%d') for date in date_range]
        login_counts = [0] * len(date_range)
        completion_counts = [0] * len(date_range)
        
        # Get login data in batch with role-based filtering applied
        login_query = users_queryset.filter(
            last_login__date__gte=start_date,
            last_login__date__lte=end_date
        )
        
        # Get completion data in batch with role-based filtering applied  
        completion_query = enrollments_queryset.filter(
            completed=True,
            completion_date__date__gte=start_date,
            completion_date__date__lte=end_date
        )
        
        # Aggregate login data efficiently
        logins = login_query.values('last_login__date').annotate(count=Count('id'))
        for login in logins:
            if login['last_login__date']:
                day_index = (login['last_login__date'] - start_date).days
                if 0 <= day_index < len(date_range):
                    login_counts[day_index] = login['count']
        
        # Aggregate completion data efficiently
        completions = completion_query.values('completion_date__date').annotate(count=Count('id'))
        for completion in completions:
            if completion['completion_date__date']:
                day_index = (completion['completion_date__date'] - start_date).days
                if 0 <= day_index < len(date_range):
                    completion_counts[day_index] = completion['count']
        
        # Debug logging to help troubleshoot
        logger.info(f"Reports overview initial data: {len(activity_dates)} data points")
        logger.info(f"Activity dates: {activity_dates[:5]}...")  # Show first 5 labels  
        logger.info(f"Initial login totals: {sum(login_counts)}, completion totals: {sum(completion_counts)}")
                    
    except Exception as e:
        # Fallback to empty data if chart generation fails
        logger.error(f"Error generating chart data: {str(e)}")
        activity_dates = []
        login_counts = []
        completion_counts = []
        # Add fallback for timezone_info to prevent UnboundLocalError
        timezone_info = None
    
    # Calculate course progress percentages for the doughnut chart (matching instructor dashboard)
    try:
        total_enrollments = enrollments_queryset.count()
        
        if total_enrollments > 0:
            completed_count = enrollments_queryset.filter(completed=True).count()
            in_progress_count = enrollments_queryset.filter(
                completed=False,
                last_accessed__isnull=False
            ).count()
            not_started_count = enrollments_queryset.filter(
                completed=False,
                last_accessed__isnull=True
            ).count()
            
            # Calculate percentages (matching instructor dashboard approach)
            completed_percentage = round((completed_count / total_enrollments) * 100)
            in_progress_percentage = round((in_progress_count / total_enrollments) * 100)
            not_started_percentage = round((not_started_count / total_enrollments) * 100)
            not_passed_percentage = max(0, 100 - completed_percentage - in_progress_percentage - not_started_percentage)
            
            course_progress = {
                'total_courses': total_enrollments,
                'completed_count': completed_count,
                'in_progress_count': in_progress_count,
                'not_started_count': not_started_count,
                'not_passed_count': 0,  # Placeholder for failed courses
                'completed_percentage': completed_percentage,
                'in_progress_percentage': in_progress_percentage,
                'not_started_percentage': not_started_percentage,
                'not_passed_percentage': not_passed_percentage,
            }
        else:
            course_progress = {
                'total_courses': 0,
                'completed_count': 0,
                'in_progress_count': 0,
                'not_started_count': 0,
                'not_passed_count': 0,
                'completed_percentage': 0,
                'in_progress_percentage': 0,
                'not_started_percentage': 0,
                'not_passed_percentage': 0,
            }

    except Exception as e:
        logger.error(f"Error calculating course progress: {str(e)}")
        course_progress = {
            'total_courses': 0,
            'completed_count': 0,
            'in_progress_count': 0,
            'not_started_count': 0,
            'not_passed_count': 0,
            'completed_percentage': 0,
            'in_progress_percentage': 0,
            'not_started_percentage': 0,
            'not_passed_percentage': 0,
        }
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Reports', 'icon': 'fa-chart-bar'}
    ]
    
    # Ensure all chart data has safe defaults
    activity_dates = activity_dates or []
    login_counts = login_counts or []
    completion_counts = completion_counts or []
    
    # Build context with filter context and report data
    context = {
        'active_users': active_users or 0,
        'never_logged_in': never_logged_in or 0,
        'assigned_courses': course_stats.get('assigned_count', 0) or 0,
        'completed_courses': completed_courses or 0,
        'total_initial_assessments': total_initial_assessments or 0,
        'avg_initial_assessment_score': round(avg_initial_assessment_score, 1) if avg_initial_assessment_score else 0,
        'users_with_assessments': users_with_assessments or 0,
        'breadcrumbs': breadcrumbs,
        # Chart data with safe JSON encoding
        'activity_dates': json.dumps(activity_dates),
        'login_counts': json.dumps(login_counts),
        'completion_counts': json.dumps(completion_counts),
        'timezone_info': timezone_info,
        # Use the new course_progress data structure (matching instructor dashboard)
        'course_progress': course_progress,
        **structure_stats,
        **filter_context  # Add filter context (businesses, branches, show_*_filter flags)
    }
    
    return render(request, 'reports/overview.html', context)


@login_required
@reports_access_required
def training_matrix(request):
    """View for displaying the training matrix."""
    search_query = request.GET.get('search', '')
    
    # Get all users, filtering by branch for non-superadmins
    users_queryset = User.objects.select_related('branch').order_by('username')
    
    # Apply branch filtering for non-superadmins
    users_queryset = BranchFilterManager.filter_queryset_by_branch(request.user, users_queryset)
    
    # Handle branch parameter if present
    users_queryset = handle_branch_parameter(request, users_queryset)
    
    if search_query:
        users_queryset = users_queryset.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Get all courses, with potential business/branch filtering
    courses_queryset = Course.objects.all().order_by('title')
    
    # Apply business filtering for Super Admin users
    if request.user.role == 'superadmin':
        courses_queryset = filter_queryset_by_business(courses_queryset, request.user, 'branch__business')
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser and request.user.branch:
        # For branch-level users, only show courses with enrollments from their branch
        courses_queryset = courses_queryset.filter(
            courseenrollment__user__branch=request.user.branch
        ).distinct()
    
    # Optimize queries with proper prefetch and select_related
    users_queryset = users_queryset.select_related('branch').prefetch_related(
        Prefetch('courseenrollment_set',
                queryset=CourseEnrollment.objects.filter(course__in=courses_queryset).select_related('course'))
    )
    
    # Get all users as a list and organize enrollments efficiently
    user_list = list(users_queryset)
    for user in user_list:
        # Create enrollment lookup from prefetched data (no additional queries)
        user.course_enrollments = {
            enrollment.course_id: enrollment 
            for enrollment in user.courseenrollment_set.all()
        }
    
    # Get filter parameters with safety limits to prevent memory issues
    per_page = min(int(request.GET.get('per_page', 20)), 100)  # Cap at 100 per page
    export_to_excel = request.GET.get('export') == 'excel'
    
    # Memory protection: limit total dataset size for exports
    if export_to_excel and user_list:
        max_export_size = 10000  # Maximum 10k records for export
        if len(user_list) > max_export_size:
            messages.warning(request, f"Export limited to first {max_export_size} records due to size constraints.")
            user_list = user_list[:max_export_size]
    
    # Get view options and filters
    view_options = request.GET.getlist('view_option')
    focus = request.GET.get('focus', 'all')
    status_filters = request.GET.getlist('status')
    branch_filters = request.GET.getlist('branch')
    group_filters = request.GET.getlist('group')

    # Filter to show only learners in training matrix
    user_list = [user for user in user_list if user.role == 'learner']
    
    # Get course IDs for not_enrolled filter
    course_ids = list(courses_queryset.values_list('id', flat=True))
    
    # Apply focus filter to users
    filtered_users = []
    for user in user_list:
        if focus == 'all':
            filtered_users.append(user)
        else:
            # Check if user has enrollments matching the focus criteria
            has_matching_enrollment = False
            
            for course_id, enrollment in user.course_enrollments.items():
                if focus == 'completed' and enrollment.completed:
                    has_matching_enrollment = True
                    break
                elif focus == 'not_passed' and not enrollment.completed and enrollment.last_accessed:
                    has_matching_enrollment = True
                    break
                elif focus == 'in_progress' and not enrollment.completed and enrollment.last_accessed:
                    has_matching_enrollment = True
                    break
                elif focus == 'not_started' and not enrollment.last_accessed:
                    has_matching_enrollment = True
                    break
            
            # For 'not_enrolled', check if user has no enrollments in any of the courses
            if focus == 'not_enrolled':
                user_enrolled_courses = set(user.course_enrollments.keys())
                all_course_ids = set(course_ids)
                if all_course_ids - user_enrolled_courses:  # User has courses they're not enrolled in
                    has_matching_enrollment = True
            
            if has_matching_enrollment:
                filtered_users.append(user)
    paginator = Paginator(filtered_users, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get branches for the branch filter based on role requirements
    branches = Branch.objects.none()  # Default to no branches
    
    if request.user.role == 'globaladmin':
        # Global Admin: Show all branches
        branches = Branch.objects.all()
    elif request.user.role == 'superadmin':
        # Super Admin: Show only branches under their assigned businesses
        if hasattr(request.user, 'business_assignments'):
            assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            if assigned_businesses:
                branches = Branch.objects.filter(business__in=assigned_businesses)
    # Admin and learner roles don't need branch filter - branches remains empty
    
    # Get branches and groups for filter dropdowns - apply business filtering for SuperAdmin
    if request.user.role == 'superadmin':
        from core.utils.business_filtering import filter_branches_by_business
        filtered_branches = filter_branches_by_business(request.user)
        branch_names = filtered_branches.order_by('name').values_list('name', flat=True)
    else:
        branch_names = Branch.objects.all().order_by('name').values_list('name', flat=True)
    from groups.models import BranchGroup
    group_names = BranchGroup.objects.all().order_by('name').values_list('name', flat=True)
    
    context = {
        'courses': courses_queryset,
        'users': page_obj,
        'search_query': search_query,
        'per_page': per_page,
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'branches': branches,
        'user_branch_id': request.user.branch_id,
        'status_filters': status_filters,
        'branch_filters': branch_filters,
        'group_filters': group_filters,
        'groups': group_names,
        'view_options': view_options,
        'focus': focus,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'Training Matrix', 'icon': 'fa-table'}
        ]
    }
    # Export to Excel if requested
    if export_to_excel:
        return export_training_matrix_to_excel(request, filtered_users, courses_queryset, search_query)
    
    return render(request, 'reports/training_matrix.html', context)

def export_training_matrix_to_excel(request, users, courses, search_query):
    """Export training matrix data to Excel with memory optimization"""
    import xlwt
    from django.http import HttpResponse
    
    # Memory protection: limit export size
    max_export_users = 5000
    max_export_courses = 100
    
    if len(users) > max_export_users:
        messages.warning(request, f"Export limited to first {max_export_users} users due to memory constraints.")
        users = users[:max_export_users]
    
    if len(courses) > max_export_courses:
        messages.warning(request, f"Export limited to first {max_export_courses} courses due to memory constraints.")
        courses = courses[:max_export_courses]
    
    # Get filter parameters for filename
    status_filters = request.GET.getlist('status')
    branch_filters = request.GET.getlist('branch')
    group_filters = request.GET.getlist('group')
    
    # Create a new workbook and add a worksheet
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Training Matrix')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    date_style = xlwt.easyxf('font: bold off; align: wrap on, vert centre, horiz center', num_format_str='DD/MM/YYYY')
    completed_style = xlwt.easyxf('pattern: pattern solid, fore_colour light_green; font: color black; align: horiz center, vert centre')
    in_progress_style = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; font: color black; align: horiz center, vert centre')
    not_started_style = xlwt.easyxf('pattern: pattern solid, fore_colour gray25; font: color black; align: horiz center, vert centre')
    
    # Write headers
    ws.write(0, 0, 'User', header_style)
    for col, course in enumerate(courses, start=1):
        ws.write(0, col, course.title, header_style)
        ws.col(col).width = 4000  # Set column width
    
    # Write data rows
    for row, user in enumerate(users, start=1):
        # Write user name
        user_name = user.get_full_name() or user.username
        ws.write(row, 0, user_name)
        
        # Write course completion statuses
        for col, course in enumerate(courses, start=1):
            enrollment = user.course_enrollments.get(course.id)
            if enrollment:
                if enrollment.completed:
                    ws.write(row, col, 'Completed', completed_style)
                elif enrollment.last_accessed:
                    ws.write(row, col, f"{enrollment.get_progress():.0f}%", in_progress_style)
                else:
                    ws.write(row, col, 'Not Started', not_started_style)
            else:
                ws.write(row, col, 'Not Started', not_started_style)
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename_parts = ['training_matrix']
    
    if search_query:
        filename_parts.append(search_query)
    
    if status_filters:
        filename_parts.append('_'.join(status_filters))
    
    if branch_filters:
        filename_parts.append('_'.join(branch_filters))
    
    if group_filters:
        filename_parts.append('_'.join(group_filters))
    
    filename_parts.append(timestamp)
    filename = '_'.join(filename_parts) + '.xls'
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

def export_user_reports_to_excel(request):
    """Export user reports to Excel"""
    import xlwt
    from users.models import CustomUser
    from django.db.models import Count, Q, Avg
    from quiz.models import QuizAttempt
    
    # Get users based on role permissions
    if request.user.role in ['globaladmin', 'superadmin']:
        users = CustomUser.objects.filter(is_active=True).exclude(role__in=['globaladmin'])
    elif request.user.role in ['admin', 'instructor']:
        if request.user.branch:
            users = CustomUser.objects.filter(branch=request.user.branch, is_active=True).exclude(role__in=['globaladmin', 'superadmin'])
        else:
            users = CustomUser.objects.filter(is_active=True).exclude(role__in=['globaladmin', 'superadmin', 'admin'])
    else:
        users = CustomUser.objects.none()
    
    # Annotate users with statistics
    users = users.annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        initial_assessment_count=Count('module_quiz_attempts', filter=Q(
            module_quiz_attempts__quiz__is_initial_assessment=True, 
            module_quiz_attempts__is_completed=True
        ), distinct=True)
    ).order_by('username')
    
    # Create workbook
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('User Reports')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    
    # Write headers
    headers = ['User', 'User Type', 'Last Login', 'Assigned Courses', 'Completed Courses', 'Initial Assessments']
    for col, header in enumerate(headers):
        ws.write(0, col, header, header_style)
        ws.col(col).width = 5000
    
    # Write data rows
    for row, user in enumerate(users, start=1):
        ws.write(row, 0, user.get_full_name() or user.username)
        ws.write(row, 1, user.get_user_type_display() if hasattr(user, 'get_user_type_display') else user.role)
        ws.write(row, 2, user.last_login.strftime('%d/%m/%Y') if user.last_login else 'Never')
        ws.write(row, 3, user.assigned_count)
        ws.write(row, 4, user.completed_count)
        ws.write(row, 5, user.initial_assessment_count)
    
    # Prepare response
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'user_reports_{timestamp}.xls'
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response

def export_courses_report_to_excel(request):
    """Export courses report to Excel"""
    import xlwt
    
    # Get courses (reuse logic from courses_report view)
    courses = Course.objects.all()
    
    # Apply business/branch filtering based on user permissions
    enrollment_filter = Q()
    if request.user.role == 'superadmin':
        courses = filter_queryset_by_business(courses, request.user, 'branch__business')
        from core.utils.business_filtering import get_superadmin_business_filter
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses:
            enrollment_filter = Q(courseenrollment__user__branch__business__in=assigned_businesses)
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser:
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                courses = courses.filter(courseenrollment__user__branch=effective_branch).distinct()
                enrollment_filter = Q(courseenrollment__user__branch=effective_branch)
        elif request.user.branch:
            courses = courses.filter(courseenrollment__user__branch=request.user.branch).distinct()
            enrollment_filter = Q(courseenrollment__user__branch=request.user.branch)
    
    # Add learner filter
    learner_filter = Q(courseenrollment__user__role='learner')
    enrollment_filter = enrollment_filter & learner_filter
    
    # Annotate courses with statistics
    courses = courses.annotate(
        enrolled_count=Count('courseenrollment', filter=enrollment_filter, distinct=True),
        completed_count=Count('courseenrollment', filter=enrollment_filter & Q(courseenrollment__completed=True), distinct=True),
        completion_rate=ExpressionWrapper(
            Case(
                When(enrolled_count=0, then=Value(0, output_field=FloatField())),
                default=Cast(F('completed_count'), FloatField()) / Cast(F('enrolled_count'), FloatField()) * 100
            ),
            output_field=FloatField()
        )
    )
    
    # Create workbook
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Course Reports')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center')
    
    # Write headers
    headers = ['Course', 'Category', 'Enrolled', 'Completed', 'Completion Rate (%)']
    for col, header in enumerate(headers):
        ws.write(0, col, header, header_style)
        ws.col(col).width = 6000
    
    # Write data rows
    for row, course in enumerate(courses, start=1):
        ws.write(row, 0, course.title)
        ws.write(row, 1, course.category.name if course.category else 'N/A')
        ws.write(row, 2, course.enrolled_count)
        ws.write(row, 3, course.completed_count)
        ws.write(row, 4, f'{course.completion_rate:.1f}%')
    
    # Prepare response
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'course_reports_{timestamp}.xls'
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response

@login_required
@reports_access_required
def timeline(request):
    """View for displaying the learning timeline."""
    # Get filter parameters
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    event_type = request.GET.get('event_type')
    user_id = request.GET.get('user')
    course_id = request.GET.get('course')
    per_page = int(request.GET.get('per_page', 10))
    page_number = int(request.GET.get('page', 1))

    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'label': 'Timeline', 'icon': 'fa-clock'}
    ]

    # Base query
    events = Event.objects.select_related('user', 'course')
    
    # Apply branch filtering based on user permissions
    events = BranchFilterManager.filter_queryset_by_branch(request.user, events)

    # Apply filters
    # Use consistent date parsing
    parsed_from_date = parse_date_filter(from_date)
    if parsed_from_date:
        events = events.filter(created_at__date__gte=parsed_from_date)

    parsed_to_date = parse_date_filter(to_date)
    if parsed_to_date:
        events = events.filter(created_at__date__lte=parsed_to_date)

    if event_type:
        events = events.filter(type=event_type)

    if user_id:
        events = events.filter(user_id=user_id)

    if course_id:
        events = events.filter(course_id=course_id)

    # Order the queryset to avoid pagination warnings
    events = events.order_by('-created_at')

    # Handle pagination
    paginator = Paginator(events, per_page)
    page_obj = paginator.get_page(page_number)

    # Get data for filters - apply business/branch filtering
    all_users = BranchFilterManager.filter_queryset_by_branch(request.user, User.objects.all()).order_by('first_name', 'last_name')
    
    # Filter to show only learner role users in the user dropdown
    all_users = all_users.filter(role='learner')
    
    all_courses = Course.objects.all().order_by('title')
    
    # Apply business filtering for Super Admin users, branch filtering for others
    if request.user.role == 'superadmin':
        all_courses = filter_queryset_by_business(all_courses, request.user, 'branch__business')
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser and request.user.branch:
        # Filter courses that have enrollments from user's branch
        all_courses = all_courses.filter(courseenrollment__user__branch=request.user.branch).distinct()

    # If no dates are set, default to last 30 days
    if not from_date:
        from_date = timezone.now().date() - timedelta(days=30)
    if not to_date:
        to_date = timezone.now().date()

    context = {
        'events': page_obj,
        'event_types': Event.EVENT_TYPES,
        'all_users': all_users,
        'all_courses': all_courses,
        'from_date': from_date,
        'to_date': to_date,
        'selected_event_type': event_type,
        'selected_user_id': int(user_id) if user_id else None,
        'selected_course_id': int(course_id) if course_id else None,
        'per_page': per_page,
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_previous': page_obj.has_previous(),
        'has_next': page_obj.has_next(),
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'reports/timeline.html', context)

@login_required
@reports_access_required
def subgroup_report(request):
    """View for displaying subgroup reports - only course groups."""
    # Get search parameters
    search_query = request.GET.get('search', '')
    per_page = int(request.GET.get('per_page', 10))

    # Get only course groups with their basic statistics
    subgroups = BranchGroup.objects.filter(
        Q(course_access__isnull=False) | Q(group_type='course')
    ).distinct().annotate(
        assigned_users=Count('memberships', filter=Q(memberships__user__role='learner'), distinct=True),
        total_courses=Count('accessible_courses', distinct=True)
    ).prefetch_related('accessible_courses', 'memberships__user')

    # Apply search filter if provided
    if search_query:
        subgroups = subgroups.filter(name__icontains=search_query)
    
    # Order the queryset to avoid pagination warnings
    subgroups = subgroups.order_by('name')

    # Calculate overall statistics with proper branch filtering
    enrollments = CourseEnrollment.objects.all()
    enrollments = apply_role_based_filtering(request.user, enrollments, request=request)
    
    # Filter enrollments to only include learner users
    enrollments = enrollments.filter(user__role='learner')
    
    total_enrollments = enrollments.count()
    completed_courses = enrollments.filter(completed=True).count()
    courses_in_progress = enrollments.filter(
        completed=False,
        last_accessed__isnull=False
    ).count()
    courses_not_passed = enrollments.filter(
        completed=False,
        last_accessed__lt=timezone.now() - timedelta(days=30)
    ).count()
    courses_not_started = enrollments.filter(
        completed=False,
        last_accessed__isnull=True
    ).count()

    # Calculate completion rate
    completion_rate = calculate_progress_percentage(completed_courses, total_enrollments)

    # Calculate total training time with proper branch filtering
    topic_progress = TopicProgress.objects.all()
    topic_progress = apply_role_based_filtering(request.user, topic_progress, request=request)
    
    # Filter topic progress to only include learner users
    topic_progress = topic_progress.filter(user__role='learner')
    
    total_time = topic_progress.aggregate(
        total=Sum('total_time_spent', default=0)
    )['total'] or 0
    
    # Convert seconds to days and hours
    total_seconds = total_time
    days = total_seconds // (24 * 3600)
    remaining_seconds = total_seconds % (24 * 3600)
    hours = remaining_seconds // 3600
    training_time = f"{days}d {hours}h"

    # Calculate completion rate for each subgroup
    # Fixed: Calculate completed courses separately for each subgroup instead of using F() expression
    for subgroup in subgroups:
        # Get all courses accessible to this subgroup
        accessible_course_ids = subgroup.accessible_courses.values_list('id', flat=True)
        
        # Get learner users in this subgroup
        learner_user_ids = subgroup.memberships.filter(
            user__role='learner', 
            is_active=True
        ).values_list('user_id', flat=True)
        
        # Count completed courses for learners in this subgroup for accessible courses
        subgroup.completed_courses = CourseEnrollment.objects.filter(
            user_id__in=learner_user_ids,
            course_id__in=accessible_course_ids,
            completed=True
        ).count()
        
        # Calculate completion rate
        total_possible = subgroup.assigned_users * subgroup.total_courses
        if total_possible > 0:
            subgroup.completion_rate = round((subgroup.completed_courses / total_possible) * 100, 1)
        else:
            subgroup.completion_rate = 0

    # Pagination
    paginator = Paginator(subgroups, per_page)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'label': 'Course Groups Reports', 'icon': 'fa-users-cog'}
    ]

    context = {
        'subgroups': page_obj,
        'completion_rate': completion_rate,
        'completed_courses': completed_courses,
        'courses_in_progress': courses_in_progress,
        'courses_not_passed': courses_not_passed,
        'courses_not_started': courses_not_started,
        'training_time': training_time,
        'search_query': search_query,
        'per_page': per_page,
        'page_obj': page_obj,
        'paginator': paginator,
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'reports/subgroup_report.html', context)

@login_required
@reports_access_required
def subgroup_detail(request, subgroup_id):
    """View for displaying detailed subgroup report similar to course dashboard."""
    # Get the subgroup
    subgroup = get_object_or_404(BranchGroup, id=subgroup_id)
    
    # Apply role-based access control
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        if request.user.branch != subgroup.branch:
            return HttpResponseForbidden("You don't have permission to view this subgroup.")
    
    # Get tab parameter
    active_tab = request.GET.get('tab', 'overview')
    
    # Get subgroup members
    members = subgroup.memberships.select_related('user').all()
    
    # Get accessible courses for this subgroup
    accessible_courses = subgroup.accessible_courses.all()
    
    # Calculate subgroup statistics
    total_members = members.count()
    total_courses = accessible_courses.count()
    
    # Get enrollments for subgroup members in accessible courses
    member_user_ids = [m.user.id for m in members]
    enrollments = CourseEnrollment.objects.filter(
        user_id__in=member_user_ids,
        course__in=accessible_courses,
        user__role='learner'  # Only include learner users
    )
    
    total_enrollments = enrollments.count()
    completed_enrollments = enrollments.filter(completed=True).count()
    in_progress_enrollments = enrollments.filter(
        completed=False,
        last_accessed__isnull=False,
        last_accessed__gte=timezone.now() - timedelta(days=30)
    ).count()
    not_passed_enrollments = enrollments.filter(
        completed=False,
        last_accessed__isnull=False,
        last_accessed__lt=timezone.now() - timedelta(days=30)
    ).count()
    not_started_enrollments = enrollments.filter(
        completed=False,
        last_accessed__isnull=True
    ).count()
    
    # Calculate completion rate
    completion_rate = round((completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 1)
    
    # Get training time for subgroup members
    topic_progresses = TopicProgress.objects.filter(
        user_id__in=member_user_ids,
        user__role='learner'  # Only include learner users
    )
    total_time_seconds = topic_progresses.aggregate(Sum('total_time_spent'))['total_time_spent__sum'] or 0
    training_hours = int(total_time_seconds / 3600)
    training_minutes = int((total_time_seconds % 3600) / 60)
    training_time = f"{training_hours}h {training_minutes}m"
    
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Get login activity (using last_accessed from enrollments as proxy)
    login_activity = enrollments.filter(
        last_accessed__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('last_accessed')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Get course completions in last 30 days
    completion_activity = enrollments.filter(
        completed=True,
        completion_date__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('completion_date')
    ).values('date').annotate(
        count=Count('id')
    ).order_by('date')
    
    # Prepare chart data
    chart_data = {
        'dates': [],
        'logins': [],
        'completions': []
    }
    
    # Create date range for last 30 days
    current_date = thirty_days_ago.date()
    end_date = timezone.now().date()
    
    while current_date <= end_date:
        chart_data['dates'].append(current_date.strftime('%d/%m'))
        
        # Find login count for this date
        login_count = next((item['count'] for item in login_activity if item['date'] == current_date), 0)
        chart_data['logins'].append(login_count)
        
        # Find completion count for this date
        completion_count = next((item['count'] for item in completion_activity if item['date'] == current_date), 0)
        chart_data['completions'].append(completion_count)
        
        current_date += timedelta(days=1)
    
    # Get timeline events for the timeline tab
    timeline_events = []
    if active_tab == 'timeline' and member_user_ids:
        # Get events for subgroup members in the last 30 days
        events = Event.objects.filter(
            user_id__in=member_user_ids,
            created_at__gte=thirty_days_ago,
            user__role='learner'  # Only include learner users
        ).select_related('user', 'course').order_by('-created_at')
        
        # Apply course filter if events are related to courses in accessible_courses
        if accessible_courses.exists():
            accessible_course_ids = list(accessible_courses.values_list('id', flat=True))
            events = events.filter(
                Q(course_id__in=accessible_course_ids) | Q(course__isnull=True)
            )
        
        timeline_events = events[:50]  # Limit to last 50 events
    
    # Get courses with completion rates
    courses_with_stats = []
    for course in accessible_courses:
        course_enrollments = enrollments.filter(course=course)
        course_total = course_enrollments.count()
        course_completed = course_enrollments.filter(completed=True).count()
        course_completion_rate = round((course_completed / course_total * 100) if course_total > 0 else 0, 1)
        
        courses_with_stats.append({
            'course': course,
            'total_enrollments': course_total,
            'completed_enrollments': course_completed,
            'completion_rate': course_completion_rate
        })
    
    # Sort courses by completion rate (highest first)
    courses_with_stats.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    # Get top performing courses (top 5)
    top_courses = courses_with_stats[:5]
    
    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'url': reverse('reports:subgroup_report'), 'label': 'Course Groups Reports', 'icon': 'fa-users-cog'},
        {'label': subgroup.name, 'icon': 'fa-users'}
    ]
    
    context = {
        'subgroup': subgroup,
        'active_tab': active_tab,
        'total_members': total_members,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'completed_enrollments': completed_enrollments,
        'in_progress_enrollments': in_progress_enrollments,
        'not_passed_enrollments': not_passed_enrollments,
        'not_started_enrollments': not_started_enrollments,
        'completion_rate': completion_rate,
        'training_time': training_time,
        'chart_data': chart_data,
        'courses_with_stats': courses_with_stats,
        'top_courses': top_courses,
        'members': members,
        'accessible_courses': accessible_courses,
        'timeline_events': timeline_events,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'reports/subgroup_detail.html', context)

@login_required
@reports_access_required
def subgroup_detail_excel(request, subgroup_id):
    """Export subgroup detail report to Excel"""
    import xlwt
    from django.http import HttpResponse
    
    # Get the subgroup
    subgroup = get_object_or_404(BranchGroup, id=subgroup_id)
    
    # Apply role-based access control
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        if request.user.branch != subgroup.branch:
            return HttpResponseForbidden("You don't have permission to view this subgroup.")
    
    # Get subgroup data (similar to subgroup_detail view)
    members = subgroup.memberships.select_related('user').all()
    accessible_courses = subgroup.accessible_courses.all()
    total_members = members.count()
    total_courses = accessible_courses.count()
    
    # Get enrollments for subgroup members in accessible courses
    member_user_ids = [m.user.id for m in members]
    enrollments = CourseEnrollment.objects.filter(
        user_id__in=member_user_ids,
        course__in=accessible_courses,
        user__role='learner'  # Only include learner users
    )
    
    total_enrollments = enrollments.count()
    completed_enrollments = enrollments.filter(completed=True).count()
    in_progress_enrollments = enrollments.filter(
        completed=False,
        last_accessed__isnull=False
    ).count()
    not_started_enrollments = enrollments.filter(
        completed=False,
        last_accessed__isnull=True
    ).count()
    
    # Calculate completion rate
    completion_rate = round((completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 1)
    
    # Get training time for subgroup members
    topic_progresses = TopicProgress.objects.filter(
        user_id__in=member_user_ids,
        user__role='learner'  # Only include learner users
    )
    total_time_seconds = topic_progresses.aggregate(Sum('total_time_spent'))['total_time_spent__sum'] or 0
    training_hours = int(total_time_seconds / 3600)
    training_minutes = int((total_time_seconds % 3600) / 60)
    training_time = f"{training_hours}h {training_minutes}m"
    
    # Get courses with completion rates
    courses_with_stats = []
    for course in accessible_courses:
        course_enrollments = enrollments.filter(course=course)
        course_total = course_enrollments.count()
        course_completed = course_enrollments.filter(completed=True).count()
        course_completion_rate = round((course_completed / course_total * 100) if course_total > 0 else 0, 1)
        
        courses_with_stats.append({
            'course': course,
            'total_enrollments': course_total,
            'completed_enrollments': course_completed,
            'completion_rate': course_completion_rate
        })
    
    # Create Excel workbook
    wb = xlwt.Workbook(encoding='utf-8')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    title_style = xlwt.easyxf('font: bold on, height 320; align: wrap on, vert centre, horiz left')
    date_style = xlwt.easyxf('font: bold off; align: wrap on, vert centre, horiz center', num_format_str='DD/MM/YYYY HH:MM')
    
    # Overview Sheet
    overview_sheet = wb.add_sheet('Overview')
    
    overview_sheet.write(0, 0, f'{subgroup.name} - Course Group Report', title_style)
    overview_sheet.write(1, 0, 'Generated on:', xlwt.easyxf('font: bold on'))
    overview_sheet.write(1, 1, timezone.now().strftime('%d/%m/%Y %H:%M'))
    
    # Overview statistics
    overview_sheet.write(3, 0, 'GROUP STATISTICS', header_style)
    overview_sheet.write(4, 0, 'Group Name:')
    overview_sheet.write(4, 1, subgroup.name)
    overview_sheet.write(5, 0, 'Total Members:')
    overview_sheet.write(5, 1, total_members)
    overview_sheet.write(6, 0, 'Total Courses:')
    overview_sheet.write(6, 1, total_courses)
    overview_sheet.write(7, 0, 'Completion Rate:')
    overview_sheet.write(7, 1, f"{completion_rate}%")
    overview_sheet.write(8, 0, 'Completed Enrollments:')
    overview_sheet.write(8, 1, completed_enrollments)
    overview_sheet.write(9, 0, 'In Progress Enrollments:')
    overview_sheet.write(9, 1, in_progress_enrollments)
    overview_sheet.write(10, 0, 'Not Started Enrollments:')
    overview_sheet.write(10, 1, not_started_enrollments)
    overview_sheet.write(11, 0, 'Total Training Time:')
    overview_sheet.write(11, 1, training_time)
    
    # Members Sheet
    members_sheet = wb.add_sheet('Members')
    
    # Members headers
    member_headers = ['Name', 'Email', 'Role', 'Joined Date']
    for col, header in enumerate(member_headers):
        members_sheet.write(0, col, header, header_style)
        members_sheet.col(col).width = 4000
    
    # Members data
    for row, membership in enumerate(members, start=1):
        members_sheet.write(row, 0, membership.user.get_full_name() or membership.user.username)
        members_sheet.write(row, 1, membership.user.email)
        members_sheet.write(row, 2, membership.user.role.title() if membership.user.role else 'N/A')
        members_sheet.write(row, 3, membership.joined_at.strftime('%d/%m/%Y') if membership.joined_at else 'N/A', date_style)
    
    # Courses Sheet
    courses_sheet = wb.add_sheet('Courses')
    
    # Courses headers
    course_headers = ['Course Name', 'Description', 'Total Enrollments', 'Completed', 'Completion Rate']
    for col, header in enumerate(course_headers):
        courses_sheet.write(0, col, header, header_style)
        courses_sheet.col(col).width = 6000
    
    # Courses data
    for row, course_stat in enumerate(courses_with_stats, start=1):
        courses_sheet.write(row, 0, course_stat['course'].title)
        courses_sheet.write(row, 1, course_stat['course'].description or 'N/A')
        courses_sheet.write(row, 2, course_stat['total_enrollments'])
        courses_sheet.write(row, 3, course_stat['completed_enrollments'])
        courses_sheet.write(row, 4, f"{course_stat['completion_rate']}%")
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    subgroup_name = ''.join(c for c in subgroup.name if c.isalnum() or c == ' ').replace(' ', '_')
    filename = f"subgroup_report_{subgroup_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

@login_required
@reports_access_required
def courses_report(request):
    """View for displaying course reports."""
    
    # Check if export is requested
    if request.GET.get('export') == 'excel':
        return export_courses_report_to_excel(request)
    
    # Start with basic course queryset
    courses = Course.objects.all()
    
    # Apply business/branch filtering based on user permissions first
    enrollment_filter = Q()
    if request.user.role == 'superadmin':
        # Filter courses by Super Admin's assigned businesses
        courses = filter_queryset_by_business(courses, request.user, 'branch__business')
        # Add enrollment filter for Super Admin's business
        from core.utils.business_filtering import get_superadmin_business_filter
        assigned_businesses = get_superadmin_business_filter(request.user)
        if assigned_businesses:
            enrollment_filter = Q(courseenrollment__user__branch__business__in=assigned_businesses)
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser:
        # Filter courses by enrollments from the user's effective branch (supports branch switching for admin)
        if request.user.role == 'admin':
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            if effective_branch:
                courses = courses.filter(courseenrollment__user__branch=effective_branch).distinct()
                enrollment_filter = Q(courseenrollment__user__branch=effective_branch)
        elif request.user.branch:
            # For other roles (instructor, etc.), use their assigned branch
            if request.user.role == 'instructor':
                # For instructors, include both branch-based and group-assigned courses
                branch_courses = Q(courseenrollment__user__branch=request.user.branch)
                group_courses = Q(accessible_groups__memberships__user=request.user,
                                accessible_groups__memberships__is_active=True,
                                accessible_groups__memberships__custom_role__name__icontains='instructor')
                courses = courses.filter(branch_courses | group_courses).distinct()
                enrollment_filter = Q(courseenrollment__user__branch=request.user.branch) | Q(courseenrollment__course__accessible_groups__memberships__user=request.user,
                                                                                             courseenrollment__course__accessible_groups__memberships__is_active=True,
                                                                                             courseenrollment__course__accessible_groups__memberships__custom_role__name__icontains='instructor')
            else:
                courses = courses.filter(courseenrollment__user__branch=request.user.branch).distinct()
                enrollment_filter = Q(courseenrollment__user__branch=request.user.branch)
    
    # Handle branch parameter if present
    branch_id = request.GET.get('branch')
    if branch_id and branch_id != 'all':
        try:
            branch_id = int(branch_id)
            courses = courses.filter(courseenrollment__user__branch_id=branch_id).distinct()
            enrollment_filter = Q(courseenrollment__user__branch_id=branch_id)
        except (ValueError, TypeError):
            pass
    
    # Add learner filter to the enrollment filter
    learner_filter = Q(courseenrollment__user__role='learner')
    enrollment_filter = enrollment_filter & learner_filter
    
    # Now annotate courses with filtered enrollment counts
    courses = courses.annotate(
        enrolled_count=Count('courseenrollment', filter=enrollment_filter, distinct=True),
        completed_count=Count('courseenrollment', filter=enrollment_filter & Q(courseenrollment__completed=True), distinct=True),
        in_progress_count=Count('courseenrollment', filter=enrollment_filter & Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False
        ), distinct=True),
        completion_rate=ExpressionWrapper(
            Case(
                When(enrolled_count=0, then=Value(0, output_field=FloatField())),
                default=Cast(F('completed_count'), FloatField()) / Cast(F('enrolled_count'), FloatField()) * 100
            ),
            output_field=FloatField()
        )
    )
    
    # Get branches for filter dropdown - apply proper business filtering
    from core.utils.business_filtering import filter_branches_by_business
    
    if request.user.is_superuser or request.user.role == 'globaladmin':
        # Global Admin can see all branches
        branches = Branch.objects.all()
    elif request.user.role == 'superadmin':
        # Super Admin can only see branches from their assigned businesses
        branches = filter_branches_by_business(request.user)
    else:
        # Regular users can only see their own branch
        branches = Branch.objects.filter(id=request.user.branch_id) if request.user.branch else Branch.objects.none()
    
    # Calculate overall statistics
    enrollments = CourseEnrollment.objects.all()
    
    # Apply business/branch filtering to enrollments
    if request.user.role == 'superadmin':
        # Filter enrollments by Super Admin's assigned businesses
        enrollments = filter_queryset_by_business(enrollments, request.user, 'user__branch__business')
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser and request.user.branch:
        enrollments = enrollments.filter(user__branch=request.user.branch)
    
    # Filter enrollments to only include learner users
    enrollments = enrollments.filter(user__role='learner')
    
    # Apply branch parameter to enrollments if present
    if branch_id and branch_id != 'all':
        try:
            branch_id = int(branch_id)
            enrollments = enrollments.filter(user__branch_id=branch_id)
        except (ValueError, TypeError):
            pass
    
    total_enrollments = enrollments.count()
    completed_learners = enrollments.filter(completed=True).count()
    learners_in_progress = enrollments.filter(
        completed=False,
        last_accessed__isnull=False
    ).count()
    learners_not_passed = enrollments.filter(
        completed=False,
        last_accessed__isnull=False,
    ).count()
    learners_not_started = enrollments.filter(
        last_accessed__isnull=True
    ).count()
    
    # Calculate completion rate
    completion_rate = round((completed_learners / total_enrollments * 100) if total_enrollments > 0 else 0, 1)
    
    # Calculate total training time
    topic_progresses = TopicProgress.objects.all()
    
    # Apply business/branch filtering to topic progresses
    if request.user.role == 'superadmin':
        # Filter topic progresses by Super Admin's assigned businesses
        topic_progresses = filter_queryset_by_business(topic_progresses, request.user, 'user__branch__business')
    elif request.user.role not in ['globaladmin'] and not request.user.is_superuser and request.user.branch:
        topic_progresses = topic_progresses.filter(user__branch=request.user.branch)
    
    # Apply branch parameter to topic progresses if present
    if branch_id and branch_id != 'all':
        try:
            branch_id = int(branch_id)
            topic_progresses = topic_progresses.filter(user__branch_id=branch_id)
        except (ValueError, TypeError):
            pass
    
    training_time_seconds = topic_progresses.aggregate(Sum('total_time_spent'))['total_time_spent__sum'] or 0
    training_hours = int(training_time_seconds / 3600)
    training_minutes = int((training_time_seconds % 3600) / 60)
    training_time = f"{training_hours}h {training_minutes}m"
    
    # Prepare the context
    context = {
        'courses': courses,
        'completion_rate': completion_rate,
        'completed_learners': completed_learners,
        'learners_in_progress': learners_in_progress,
        'learners_not_passed': learners_not_passed,
        'learners_not_started': learners_not_started,
        'training_time': training_time,
        'branches': branches,
        'user_branch_id': request.user.branch_id,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'Course Reports', 'icon': 'fa-book'}
        ]
    }
    
    return render(request, 'reports/courses_report.html', context)

def export_user_report_to_excel(request, user):
    """Export user report data to Excel"""
    import xlwt
    from django.http import HttpResponse
    from courses.models import CourseEnrollment, TopicProgress
    from django.contrib.auth import get_user_model
    from django.db.models import Count, Sum, Avg
    from django.utils import timezone
    from datetime import timedelta
    
    User = get_user_model()
    
    # Create a new workbook and add worksheets
    wb = xlwt.Workbook(encoding='utf-8')
    overview_sheet = wb.add_sheet('Overview')
    courses_sheet = wb.add_sheet('Courses')
    activities_sheet = wb.add_sheet('Learning Activities')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    date_style = xlwt.easyxf('font: bold off; align: wrap on, vert centre, horiz center', num_format_str='DD/MM/YYYY')
    completed_style = xlwt.easyxf('pattern: pattern solid, fore_colour light_green; font: color black; align: horiz center, vert centre')
    in_progress_style = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; font: color black; align: horiz center, vert centre')
    not_started_style = xlwt.easyxf('pattern: pattern solid, fore_colour gray25; font: color black; align: horiz center, vert centre')
    not_passed_style = xlwt.easyxf('pattern: pattern solid, fore_colour rose; font: color black; align: horiz center, vert centre')
    
    # Overview Sheet - User Information
    overview_sheet.write(0, 0, 'USER REPORT', header_style)
    overview_sheet.write(1, 0, 'Generated on:', xlwt.easyxf('font: bold on'))
    overview_sheet.write(1, 1, timezone.now().strftime('%d/%m/%Y %H:%M'))
    
    overview_sheet.write(3, 0, 'User:', xlwt.easyxf('font: bold on'))
    overview_sheet.write(3, 1, user.get_full_name() or user.username)
    overview_sheet.write(4, 0, 'Email:', xlwt.easyxf('font: bold on'))
    overview_sheet.write(4, 1, user.email)
    
    # Get enrolled courses first (needed for accurate time calculation)
    user_courses = CourseEnrollment.objects.filter(user=user).select_related('course')
    enrolled_course_ids = list(user_courses.values_list('course_id', flat=True))
    
    # Get user statistics
    user_stats = User.objects.filter(id=user.id).annotate(
        assigned_count=Count('courseenrollment'),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True)),
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False
        )),
        not_passed_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__lt=timezone.now() - timedelta(days=30)
        )),
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        )),
        # Calculate total time spent only for enrolled courses
        # Filter by course field first (new records), then fallback to topic relationship (legacy records)
        total_time_spent=Sum('topic_progress__total_time_spent', 
            filter=Q(topic_progress__course_id__in=enrolled_course_ids) | 
                   Q(topic_progress__course__isnull=True, topic_progress__topic__coursetopic__course_id__in=enrolled_course_ids),
            default=0
        )
    ).first()
    
    # Handle case when user has no stats
    if not user_stats:
        user_stats = User.objects.get(id=user.id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Calculate completion rate
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Format training time
    total_seconds = user_stats.total_time_spent or 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    training_time = f"{hours}h {minutes}m {seconds}s"
    
    # Write overview statistics
    overview_sheet.write(6, 0, 'COURSE STATISTICS', header_style)
    overview_sheet.write(7, 0, 'Completion rate:')
    overview_sheet.write(7, 1, f"{completion_rate}%")
    overview_sheet.write(8, 0, 'Completed courses:')
    overview_sheet.write(8, 1, user_stats.completed_count)
    overview_sheet.write(9, 0, 'Courses in progress:')
    overview_sheet.write(9, 1, user_stats.in_progress_count)
    overview_sheet.write(10, 0, 'Courses not passed:')
    overview_sheet.write(10, 1, user_stats.not_passed_count)
    overview_sheet.write(11, 0, 'Courses not started:')
    overview_sheet.write(11, 1, user_stats.not_started_count)
    overview_sheet.write(12, 0, 'Total training time:')
    overview_sheet.write(12, 1, training_time)
    
    # Courses sheet
    user_courses = CourseEnrollment.objects.filter(user=user).select_related('course').order_by('-enrolled_at')
    
    # Write courses headers
    course_headers = ['Course Name', 'Enrolled Date', 'Last Access', 'Status', 'Progress', 'Time Spent']
    for col, header in enumerate(course_headers):
        courses_sheet.write(0, col, header, header_style)
        courses_sheet.col(col).width = 4000
    
    # Write courses data
    for row, enrollment in enumerate(user_courses, start=1):
        courses_sheet.write(row, 0, enrollment.course.title)
        courses_sheet.write(row, 1, enrollment.enrolled_at.strftime('%d/%m/%Y') if enrollment.enrolled_at else 'N/A', date_style)
        courses_sheet.write(row, 2, enrollment.last_accessed.strftime('%d/%m/%Y') if enrollment.last_accessed else 'N/A', date_style)
        
        # Determine status and style
        if enrollment.completed:
            status = 'Completed'
            style = completed_style
        elif enrollment.last_accessed and enrollment.last_accessed < (timezone.now() - timedelta(days=30)):
            status = 'Not Passed'
            style = not_passed_style
        elif enrollment.last_accessed:
            status = 'In Progress'
            style = in_progress_style
        else:
            status = 'Not Started'
            style = not_started_style
        
        courses_sheet.write(row, 3, status, style)
        progress = f"{enrollment.get_progress():.0f}%" if hasattr(enrollment, 'get_progress') and callable(enrollment.get_progress) else "N/A"
        courses_sheet.write(row, 4, progress)
        
        # Format time spent
        time_spent = "N/A"
        if hasattr(enrollment, 'get_time_spent') and callable(enrollment.get_time_spent):
            total_seconds = enrollment.get_time_spent()
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            time_spent = f"{hours}h {minutes}m {seconds}s"
        
        courses_sheet.write(row, 5, time_spent)
    
    # Learning Activities sheet
    try:
        topic_progress = TopicProgress.objects.filter(user=user).select_related('topic').order_by('-last_accessed')
        
        # Write activities headers
        activity_headers = ['Activity Name', 'Type', 'Course', 'Last Access', 'Status', 'Score', 'Time Spent', 'Attempts']
        for col, header in enumerate(activity_headers):
            activities_sheet.write(0, col, header, header_style)
            activities_sheet.col(col).width = 4000
        
        # Write activities data
        for row, progress in enumerate(topic_progress, start=1):
            try:
                activities_sheet.write(row, 0, progress.topic.title if hasattr(progress.topic, 'title') else 'N/A')
                activities_sheet.write(row, 1, progress.topic.get_content_type_display() if hasattr(progress.topic, 'get_content_type_display') else 'N/A')
                
                # Get course for this topic
                course_name = "N/A"
                if hasattr(progress.topic, 'coursetopic_set') and progress.topic.coursetopic_set.exists():
                    course_name = progress.topic.coursetopic_set.first().course.title
                activities_sheet.write(row, 2, course_name)
                
                # Last accessed
                activities_sheet.write(row, 3, progress.last_accessed.strftime('%d/%m/%Y') if progress.last_accessed else 'N/A', date_style)
                
                # Status
                if progress.completed:
                    status = 'Completed'
                    style = completed_style
                elif progress.attempts > 0:
                    status = 'In Progress'
                    style = in_progress_style
                else:
                    status = 'Not Started'
                    style = not_started_style
                
                activities_sheet.write(row, 4, status, style)
                
                # Score
                score = f"{progress.last_score:.0f}%" if progress.last_score is not None else "N/A"
                activities_sheet.write(row, 5, score)
                
                # Time spent
                total_secs = progress.total_time_spent or 0
                hours = total_secs // 3600
                minutes = (total_secs % 3600) // 60
                secs = total_secs % 60
                time_spent = f"{hours}h {minutes}m {secs}s"
                activities_sheet.write(row, 6, time_spent)
                
                # Attempts
                activities_sheet.write(row, 7, progress.attempts)
            except Exception as e:
                print(f"Error processing activity {progress.id}: {str(e)}")
                # Write error row
                activities_sheet.write(row, 0, "Error processing activity")
    except Exception as e:
        print(f"Error processing activities: {str(e)}")
        activities_sheet.write(1, 0, "Error fetching activities data")
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    user_name = user.get_full_name() or user.username
    user_name = ''.join(c for c in user_name if c.isalnum() or c == ' ').replace(' ', '_')  # Clean up filename
    filename = f"user_report_{user_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

@login_required
def my_report(request):
    """View for displaying the user's personal report."""
    # Redirect to the overview section instead of using tabs
    return redirect('reports:my_report_overview')

@login_required
@reports_access_required
def reports_dashboard(request):
    """View for displaying the reports dashboard."""
    context = {
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Reports Dashboard', 'icon': 'fa-chart-bar'}
        ]
    }
    return render(request, 'reports/dashboard.html', context)


    def dispatch(self, request, *args, **kwargs):
        # Use centralized permission checking function
        if not check_user_report_access(request.user):
            messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
            return redirect('users:role_based_redirect')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get filter parameters with safety limits
        search_query = self.request.GET.get('search', '')
        per_page = min(int(self.request.GET.get('per_page', 10)), 50)  # Cap at 50 per page
        page = int(self.request.GET.get('page', 1))
        business_id = self.request.GET.get('business')
        branch_id = self.request.GET.get('branch')

        # Get filter context for the template
        filter_context = get_report_filter_context(user, self.request)
        
        # Apply role-based filtering for users
        users = User.objects.select_related('branch')
        users = apply_role_based_filtering(user, users, business_id, branch_id, self.request)
        
        # Apply role-specific user filtering for reports - MODIFIED TO SHOW ONLY LEARNER USERS
        # All users regardless of role will only see learner role users in reports
        users = users.filter(role='learner')
        
        # Apply search filter if provided (MOVED EARLIER)
        if search_query:
            users = users.filter(
                Q(username__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )
        
        # Order the queryset to avoid pagination warnings
        users = users.order_by('first_name', 'last_name')
        
        # Get all users with their course statistics and initial assessment data
        from quiz.models import Quiz, QuizAttempt
        users = users.annotate(
            assigned_count=Count('courseenrollment', distinct=True),
            completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
            initial_assessment_count=Count('module_quiz_attempts', 
                filter=Q(module_quiz_attempts__quiz__is_initial_assessment=True, 
                         module_quiz_attempts__is_completed=True), 
                distinct=True)
        )
        
        # Calculate overall statistics based on filtered users
        total_enrollments = CourseEnrollment.objects.filter(user__in=users).count()
        completed_courses = CourseEnrollment.objects.filter(user__in=users, completed=True).count()
        
        # Calculate initial assessment statistics
        total_initial_assessments = QuizAttempt.objects.filter(
            user__in=users,
            quiz__is_initial_assessment=True,
            is_completed=True
        ).count()
        
        # Calculate average initial assessment score
        avg_initial_assessment_score = QuizAttempt.objects.filter(
            user__in=users,
            quiz__is_initial_assessment=True,
            is_completed=True
        ).aggregate(avg_score=Avg('score'))['avg_score'] or 0
        
        # Calculate completion rate
        if total_enrollments > 0:
            completion_rate = (completed_courses / total_enrollments) * 100
        else:
            completion_rate = 0
        
        # Pagination
        paginator = Paginator(users, per_page)
        page_obj = paginator.get_page(page)
        
        # Define breadcrumbs
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'User Reports', 'icon': 'fa-users'}
        ]
        
        # Calculate course status statistics (mutually exclusive categories)
        courses_in_progress = CourseEnrollment.objects.filter(
            user__in=users,
            completed=False,
            last_accessed__isnull=False
        ).count()
        
        courses_not_started = CourseEnrollment.objects.filter(
            user__in=users,
            completed=False,
            last_accessed__isnull=True
        ).count()
        
        # For "not passed", we'll use courses that haven't been accessed recently (>30 days)
        # This is a subset of "in progress" courses
        thirty_days_ago = timezone.now() - timedelta(days=30)
        courses_not_passed = CourseEnrollment.objects.filter(
            user__in=users,
            completed=False,
            last_accessed__isnull=False,
            last_accessed__lt=thirty_days_ago
        ).count()
        
        # Adjust courses_in_progress to exclude the "not passed" ones for better categorization
        courses_in_progress_recent = CourseEnrollment.objects.filter(
            user__in=users,
            completed=False,
            last_accessed__isnull=False,
            last_accessed__gte=thirty_days_ago
        ).count()

        context.update({
            'users': page_obj,
            'total_users': users.count(),
            'total_enrollments': total_enrollments,
            'completed_courses': completed_courses,
            'completion_rate': round(completion_rate, 1),
            'courses_in_progress': courses_in_progress_recent,  # Only recently accessed
            'courses_not_passed': courses_not_passed,  # Not accessed in 30 days
            'courses_not_started': courses_not_started,
            'training_time': "0h 0m",  # Placeholder
            'total_initial_assessments': total_initial_assessments,
            'avg_initial_assessment_score': round(avg_initial_assessment_score, 1),
            'page_obj': page_obj,
            'search_query': search_query,
            'per_page': per_page,
            'breadcrumbs': breadcrumbs,
            **filter_context  # Add filter context (businesses, branches, show_*_filter flags)
        })
        
        return context

class GroupReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/group_report.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Use centralized permission checking function
        if not check_user_report_access(request.user):
            messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
            return redirect('users:role_based_redirect')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get query parameters
        search_query = self.request.GET.get('search', '')
        per_page = int(self.request.GET.get('per_page', 10))
        page = int(self.request.GET.get('page', 1))
        
        # Get all groups with their statistics
        groups = BranchGroup.objects.annotate(
            assigned_users=Count('memberships__user', filter=Q(memberships__user__role='learner'), distinct=True),
            completed_courses=Count(
                'memberships__user__courseenrollment',
                filter=Q(memberships__user__courseenrollment__completed=True)
            ),
            total_courses=Count('memberships__user__courseenrollment'),
        ).annotate(
            completion_rate=Case(
                When(total_courses=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    (F('completed_courses') * 100.0) / F('total_courses'),
                    output_field=fields.FloatField()
                )
            )
        )

        # Apply search filter if provided
        if search_query:
            groups = groups.filter(name__icontains=search_query)
        
        # Order the queryset to avoid pagination warnings
        groups = groups.order_by('name')

        # Calculate overall statistics
        enrollments = CourseEnrollment.objects.all()
        total_courses = enrollments.count()
        completed = enrollments.filter(completed=True).count()
        in_progress = enrollments.filter(completed=False, last_accessed__isnull=False).count()
        not_passed = enrollments.filter(completed=False, last_accessed__isnull=False).count()
        not_started = enrollments.filter(last_accessed__isnull=True).count()
        
        # Calculate overall completion rate
        if total_courses > 0:
            overall_completion_rate = (completed / total_courses) * 100
        else:
            overall_completion_rate = 0
        
        # Round completion rates to avoid floating point precision issues
        for group in groups:
            if group.completion_rate is not None:
                group.completion_rate = round(group.completion_rate, 1)
        
        # Pagination
        paginator = Paginator(groups, per_page)
        page_obj = paginator.get_page(page)
        
        # Define breadcrumbs
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'Group Reports', 'icon': 'fa-users'}
        ]
        
        context.update({
            'groups': page_obj,
            'total_groups': groups.count(),
            'total_courses': total_courses,
            'completed_courses': completed,
            'courses_in_progress': in_progress,
            'courses_not_passed': not_passed,
            'courses_not_started': not_started,
            'completion_rate': round(overall_completion_rate, 1),
            'overall_completion_rate': round(overall_completion_rate, 1),
            'page_obj': page_obj,
            'search_query': search_query,
            'breadcrumbs': breadcrumbs,
        })
        
        return context

class CustomReportsView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/custom_reports.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Use centralized permission checking function
        if not check_user_report_access(request.user):
            messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
            return redirect('users:role_based_redirect')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get query parameters
        search_query = self.request.GET.get('search', '')
        per_page = int(self.request.GET.get('per_page', 10))
        page = int(self.request.GET.get('page', 1))
        
        # Get all custom reports
        reports = Report.objects.filter(
            Q(created_by=self.request.user) | 
            Q(shared_with=self.request.user)
        ).distinct().order_by('-created_at')

        # Apply search filter if provided
        if search_query:
            reports = reports.filter(title__icontains=search_query)

        # Pagination
        paginator = Paginator(reports, per_page)
        page_obj = paginator.get_page(page)

        # Define breadcrumbs
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'Custom Reports', 'icon': 'fa-file-alt'}
        ]

        context.update({
            'reports': page_obj,
            'page_obj': page_obj,
            'search_query': search_query,
            'per_page': per_page,
            'breadcrumbs': breadcrumbs,
        })
        
        return context

@login_required
@reports_access_required
def delete_report(request, report_id):
    """Delete a report with confirmation."""
    report = get_object_or_404(Report, id=report_id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:reports'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'url': reverse('reports:report_detail', kwargs={'report_id': report_id}), 'label': report.title, 'icon': 'fa-file-alt'},
        {'label': 'Delete', 'icon': 'fa-trash'}
    ]
    
    # Check if user has permission to delete this report
    is_admin = request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor'] or request.user.is_superuser
    is_creator = report.created_by == request.user
    
    if not (is_admin or is_creator):
        messages.error(request, 'You do not have permission to delete this report.')
        return redirect('reports:report_detail', report_id=report.id)
    
    # For branch-level admins/instructors, ensure they can only delete reports from their branch
    if request.user.role in ['admin', 'instructor'] and not request.user.is_superuser:
        if (request.user.branch and report.created_by.branch and 
            request.user.branch != report.created_by.branch):
            messages.error(request, 'You can only delete reports created by users in your branch.')
            return redirect('reports:report_detail', report_id=report.id)
    
    if request.method == 'POST':
        # Store report title for success message
        report_title = report.title
        report.delete()
        messages.success(request, f'Report "{report_title}" has been deleted successfully.')
        return redirect('reports:reports')
    
    return render(request, 'reports/delete_report.html', {
        'report': report,
        'title': f'Delete: {report.title}',
        'description': 'Delete report',
        'breadcrumbs': breadcrumbs
    })

@login_required
@reports_access_required
def edit_report(request, report_id):
    """Edit an existing report."""
    report = get_object_or_404(Report, id=report_id)
    
    # Check if user has permission to edit this report
    is_admin = request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor'] or request.user.is_superuser
    is_creator = report.created_by == request.user
    
    if not (is_admin or is_creator):
        messages.error(request, 'You do not have permission to edit this report.')
        return redirect('reports:report_detail', report_id=report.id)
    
    # For branch-level admins/instructors, ensure they can only edit reports from their branch
    if request.user.role in ['admin', 'instructor'] and not request.user.is_superuser:
        if (request.user.branch and report.created_by.branch and 
            request.user.branch != report.created_by.branch):
            messages.error(request, 'You can only edit reports created by users in your branch.')
            return redirect('reports:report_detail', report_id=report.id)
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:reports'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'url': reverse('reports:report_detail', kwargs={'report_id': report_id}), 'label': report.title, 'icon': 'fa-file-alt'},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]
    
    if request.method == 'POST':
        try:
            # Update basic fields
            report.title = request.POST.get('title', report.title).strip()
            report.description = request.POST.get('description', report.description)
            report.report_type = request.POST.get('report_type', report.report_type)
            report.status = request.POST.get('status', report.status)
            
            # Handle rules and output_fields (JSON fields)
            rules_data = request.POST.get('rules', '{}')
            if rules_data:
                try:
                    report.rules = json.loads(rules_data) if isinstance(rules_data, str) else rules_data
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid rules format. Please check your JSON syntax.')
                    return render(request, 'reports/edit_report.html', {
                        'report': report,
                        'breadcrumbs': breadcrumbs
                    })
            
            output_fields_data = request.POST.get('output_fields', '[]')
            if output_fields_data:
                try:
                    report.output_fields = json.loads(output_fields_data) if isinstance(output_fields_data, str) else output_fields_data
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid output fields format. Please check your JSON syntax.')
                    return render(request, 'reports/edit_report.html', {
                        'report': report,
                        'breadcrumbs': breadcrumbs
                    })
            
            report.save()
            messages.success(request, f'Report "{report.title}" has been updated successfully.')
            return redirect('reports:report_detail', report_id=report.id)
            
        except Exception as e:
            logger.error(f"Error updating report {report_id}: {str(e)}")
            messages.error(request, f'Error updating report: {str(e)}')
    
    return render(request, 'reports/edit_report.html', {
        'report': report,
        'breadcrumbs': breadcrumbs,
        'report_types': Report._meta.get_field('report_type').choices,
        'status_choices': Report._meta.get_field('status').choices,
    })

def user_detail_report_access_required(view_func):
    """
    Custom decorator for user_detail_report that allows learners to view their own reports
    while maintaining Session for viewing other users' reports.
    """
    @wraps(view_func)
    def _wrapped_view(request, user_id, *args, **kwargs):
        user = request.user
        
        # Check if user is authenticated first
        if not user.is_authenticated:
            messages.error(request, "You must be logged in to access this page.")
            return redirect('users:role_based_redirect')
        
        # If learner is viewing their own report, allow access
        if user.role == 'learner' and user.id == int(user_id):
            return view_func(request, user_id, *args, **kwargs)
        
        # For all other cases, apply standard reports access check
        return reports_access_required(view_func)(request, user_id, *args, **kwargs)
    
    return _wrapped_view

@login_required
@user_detail_report_access_required
def user_detail_report(request, user_id):
    """View for displaying details of a specific user."""
    logger.info(f"Starting user_detail_report for user_id {user_id}")
    
    try:
        user = get_object_or_404(User, id=user_id)
        logger.info(f"Found user: {user.username}")
        
        # Check if the user has access to view this user's data
        if request.user.role == 'learner':
            # Learners can only view their own profile report
            if request.user.id != user_id:
                messages.error(request, "You can only view your own profile report")
                return redirect('reports:user_reports')
        elif not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin'] or 
                request.user.role == 'admin'):
            # Other roles must be in same branch
            if not (request.user.branch and user.branch and request.user.branch.id == user.branch.id):
                messages.error(request, "You don't have permission to view this user's data")
                return redirect('reports:user_reports')
    except Http404:
        logger.warning(f"User with ID {user_id} not found")
        messages.error(request, f"User with ID {user_id} not found")
        return redirect('reports:user_reports')
    
    # Check if export request
    if request.GET.get('export') == 'excel':
        return export_user_report_to_excel(request, user)
    
    # Get user course statistics with improved logic
    # Use UTC for consistent date calculations
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Get user enrolled courses first (needed for accurate time calculation)
    user_courses = CourseEnrollment.objects.filter(user=user).select_related('course').order_by('-enrolled_at')
    enrolled_course_ids = list(user_courses.values_list('course_id', flat=True))
    
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, but has been accessed at some point
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        # Calculate total time spent only for enrolled courses
        # Filter by course field first (new records), then fallback to topic relationship (legacy records)
        total_time_spent=Sum('topic_progress__total_time_spent', 
            filter=Q(topic_progress__course_id__in=enrolled_course_ids) | 
                   Q(topic_progress__course__isnull=True, topic_progress__topic__coursetopic__course_id__in=enrolled_course_ids),
            default=0
        )
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Calculate completion rate
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Format training time with proper null handling
    total_seconds = user_stats.total_time_spent if user_stats.total_time_spent is not None else 0
    # Ensure non-negative values and handle potential data corruption
    total_seconds = max(0, total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    training_time = f"{hours}h {minutes}m {seconds}s"
    
    # Add calculated fields for each enrollment
    for enrollment in user_courses:
        # Ensure completion status is accurate
        enrollment.sync_completion_status()
        
        # Calculate progress percentage
        enrollment.calculated_progress = enrollment.progress_percentage
        
        # Calculate average score from completed topics
        completed_topic_progress = TopicProgress.objects.filter(
            user=user,
            topic__courses=enrollment.course,
            completed=True,
            last_score__isnull=False
        )
        if completed_topic_progress.exists():
            enrollment.calculated_score = round(completed_topic_progress.aggregate(
                avg_score=Avg('last_score')
            )['avg_score'] or 0)
        else:
            enrollment.calculated_score = None
            
        # Format time spent
        enrollment.formatted_time_spent = enrollment.total_time_spent
    
    # Get Learning Activities data (TopicProgress) with data consistency checks
    # Note: CourseEnrollment, TopicProgress, Topic, CourseTopic are already imported at top of file
    
    # Ensure data consistency: create missing TopicProgress records for enrolled courses only
    # Optimize with bulk operations to avoid N+1 queries
    enrolled_courses = CourseEnrollment.objects.filter(user=user).select_related('course')
    
    # Get all topics for enrolled courses in one query
    from courses.models import CourseTopic
    course_ids = [enrollment.course_id for enrollment in enrolled_courses]
    
    # Recalculate user stats after syncing completion status
    thirty_days_ago = timezone.now() - timedelta(days=30)
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, accessed recently (within 30 days)
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__gte=thirty_days_ago
        ), distinct=True),
        
        # Not passed: enrolled, not completed, but hasn't been accessed recently (>30 days)
        not_passed_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__lt=thirty_days_ago
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        # Calculate total time spent only for enrolled courses
        # Filter by course field first (new records), then fallback to topic relationship (legacy records)
        total_time_spent=Sum('topic_progress__total_time_spent', 
            filter=Q(topic_progress__course_id__in=course_ids) | 
                   Q(topic_progress__course__isnull=True, topic_progress__topic__coursetopic__course_id__in=course_ids),
            default=0
        )
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Recalculate completion rate with updated data
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    course_topics = CourseTopic.objects.filter(course_id__in=course_ids).select_related('topic')
    
    # Get existing topic progress records for enrolled courses only
    existing_progress = set(
        TopicProgress.objects.filter(
            user=user,
            topic__in=[ct.topic for ct in course_topics]
        ).values_list('topic_id', flat=True)
    )
    
    # Create missing progress records in bulk for enrolled courses only
    missing_progress = []
    for course_topic in course_topics:
        if course_topic.topic_id not in existing_progress:
            missing_progress.append(
                TopicProgress(
                    user=user,
                    topic=course_topic.topic,
                    completed=False,
                    attempts=0
                )
            )
    
    # Use transaction for data consistency
    if missing_progress:
        try:
            with transaction.atomic():
                TopicProgress.objects.bulk_create(missing_progress, ignore_conflicts=True)
                logger.info(f"Created {len(missing_progress)} missing TopicProgress records for user {user.id}")
        except Exception as e:
            logger.error(f"Error creating TopicProgress records for user {user.id}: {str(e)}")
            # Continue processing even if some records fail
    
    # Get topic progress only for courses the user is enrolled in
    # Include course information for each topic
    enrolled_course_ids = CourseEnrollment.objects.filter(user=user).values_list('course_id', flat=True)
    # Filter by course field directly to avoid duplicates from many-to-many join
    # Also handle legacy records where course might be null
    # Get the latest progress ID for each topic to avoid duplicates
    latest_progress_ids = TopicProgress.objects.filter(
        user=user
    ).filter(
        Q(course__in=enrolled_course_ids) |
        Q(course__isnull=True, topic__coursetopic__course__in=enrolled_course_ids)
    ).values('topic_id').annotate(
        latest_id=Max('id')
    ).values_list('latest_id', flat=True)
    
    topic_progress = TopicProgress.objects.filter(
        id__in=latest_progress_ids
    ).select_related('topic', 'course').annotate(
        course_title=Case(
            When(course__isnull=False, then=F('course__title')),
            default=Subquery(
                CourseTopic.objects.filter(
                    topic=OuterRef('topic'),
                    course__in=enrolled_course_ids
                ).values('course__title')[:1]
            )
        )
    ).order_by('-last_accessed')
    
    
    # Calculate learning activities statistics with improved logic
    total_activities = topic_progress.count()
    completed_activities = topic_progress.filter(completed=True).count()
    
    # In progress: not completed but engaged (first_accessed or time or score)
    activities_in_progress = topic_progress.filter(
        completed=False
    ).filter(
        Q(first_accessed__isnull=False) | Q(total_time_spent__gt=0) | Q(last_score__gt=0)
    ).count()
    
    # Not started: not completed and no engagement signals
    activities_not_started = topic_progress.filter(
        completed=False,
        first_accessed__isnull=True,
        total_time_spent=0,
        last_score__isnull=True
    ).count()
    
    # Calculate average activity score with robust handling
    from core.utils.scoring import ScoreCalculationService
    
    scored_progress = topic_progress.filter(last_score__isnull=False, last_score__gte=0)
    scored_activities_count = scored_progress.count()
    
    if scored_activities_count > 0:
        # Calculate properly normalized scores
        normalized_scores = []
        for progress in scored_progress:
            normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
            if normalized_score is not None:
                normalized_scores.append(float(normalized_score))
        
        avg_activity_score = round(sum(normalized_scores) / len(normalized_scores)) if normalized_scores else 0
    else:
        avg_activity_score = 0
    
    # Add formatted time to topic progress objects
    for progress in topic_progress:
        if progress.total_time_spent:
            hours = progress.total_time_spent // 3600
            minutes = (progress.total_time_spent % 3600) // 60
            seconds = progress.total_time_spent % 60
            progress.formatted_time = f"{hours}h {minutes}m {seconds}s"
        else:
            progress.formatted_time = "0h 0m 0s"
    
    # Get user timeline activities (Event model for proper learning activities tracking)
    user_activities = Event.objects.filter(user=user).select_related('course').order_by('-created_at')[:20]
    
    # Get initial assessment quiz results
    from quiz.models import Quiz, QuizAttempt
    initial_assessment_data = []
    
    if user.branch:
        # Find all Initial Assessment quizzes for the user's branch
        initial_assessment_quizzes = Quiz.objects.filter(
            Q(creator__branch=user.branch) | Q(course__branch=user.branch),
            is_initial_assessment=True,
            is_active=True
        ).distinct().order_by('title')
        
        # Get user's latest attempts for each Initial Assessment quiz
        for quiz in initial_assessment_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=user,
                is_completed=True
            ).select_related('quiz', 'user').prefetch_related(
                'quiz__questions',  # Prefetch questions for initial assessment classification
                'user_answers__question'  # Prefetch user answers with their questions for classification
            ).order_by('-end_time').first()
            
            if latest_attempt:
                # Get assessment classification if available
                classification_data = latest_attempt.calculate_assessment_classification()
                
                initial_assessment_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'completion_date': latest_attempt.end_time,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=user,
                        is_completed=True
                    ).count(),
                    'classification': classification_data
                })
    
    # Use Event model to track actual user login activity
    # Using TruncDate instead of .extra() for Session
    user_login_events_by_date = Event.objects.filter(
        user=user,
        type='LOGIN',
        created_at__gte=thirty_days_ago
    ).annotate(
        event_date=TruncDate('created_at')
    ).values('event_date').annotate(
        count=Count('id')
    ).order_by('event_date')
    
    # Create a dictionary for quick lookup
    login_by_date = {entry['event_date']: entry['count'] for entry in user_login_events_by_date}
    
    # Generate recent login data for the last 30 days
    # Fix timezone issue by ensuring we work with UTC dates consistently
    recent_logins = []
    for i in range(30):
        # Calculate date in UTC to match TruncDate behavior
        date = (thirty_days_ago + timedelta(days=i)).date()
        login_count = login_by_date.get(date, 0)
        recent_logins.append({
            'date': thirty_days_ago + timedelta(days=i),  # Keep datetime for template
            'count': min(login_count, 10)  # Cap at 10 for chart readability
        })
    
    course_completion_events = Event.objects.filter(
        user=user,
        type='COURSE_COMPLETE',
        created_at__gte=thirty_days_ago
    ).annotate(
        event_date=TruncDate('created_at')
    ).values('event_date').annotate(
        count=Count('id')
    ).order_by('event_date')
    
    # Create completion data for chart
    completion_by_date = {entry['event_date']: entry['count'] for entry in course_completion_events}
    
    course_completions = []
    for i in range(30):
        # Calculate date in UTC to match TruncDate behavior
        date = (thirty_days_ago + timedelta(days=i)).date()
        completion_count = completion_by_date.get(date, 0)
        if completion_count > 0:  # Only add dates with actual completions for cleaner data
            course_completions.append({
                'date': thirty_days_ago + timedelta(days=i),  # Keep datetime for template
                'count': completion_count
            })
    
    # Branch filter not needed for single user detail view
    
    # Import the IssuedCertificate model from certificates app
    from certificates.models import IssuedCertificate
    
    # Get user certificates
    user_certificates = IssuedCertificate.objects.filter(recipient=user).order_by('-issue_date')
    total_certificates = user_certificates.count()
    
    # Gamification data removed
    total_badges = 0
    total_points = 0
    user_level = 0
    
    context = {
        'user': user,
        'completion_rate': completion_rate,
        'completed_courses': user_stats.completed_count,
        'courses_in_progress': user_stats.in_progress_count,
        'courses_not_passed': user_stats.not_passed_count,
        'courses_not_started': user_stats.not_started_count,
        'total_courses': user_stats.assigned_count,
        'training_time': training_time,
        'user_courses': user_courses,
        # Learning Activities data
        'topic_progress': topic_progress,
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'activities_in_progress': activities_in_progress,
        'activities_not_started': activities_not_started,
        'avg_activity_score': avg_activity_score,
        'scored_activities_count': scored_activities_count,
        # Timeline data
        'user_activities': user_activities,
        'recent_logins': recent_logins,
        'course_completions': course_completions,
        # Initial Assessment data
        'initial_assessment_data': initial_assessment_data,
        'total_initial_assessments': len(initial_assessment_data),
        # Other data
        'user_certificates': user_certificates,
        'total_certificates': total_certificates,
        'total_badges': total_badges,
        'total_points': total_points,
        'user_level': user_level,
        'total_courses': user_stats.assigned_count,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'label': user.get_full_name() or user.username, 'icon': 'fa-user'}
        ]
    }
    
    # Redirect to overview page instead of showing tabs
    return redirect('reports:user_report_overview', user_id=user_id)


def _get_user_report_data(request, user_id):
    """
    Helper function to get all user report data.
    This avoids code duplication between the main report and section views.
    """
    try:
        user = get_object_or_404(User, id=user_id)
        logger.info(f"Found user: {user.username}")
        
        # Check if the user has access to view this user's data
        if request.user.role == 'learner':
            # Learners can only view their own profile report
            if request.user.id != user_id:
                messages.error(request, "You can only view your own profile report")
                return None
        elif not (request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin'] or 
                request.user.role == 'admin'):
            # Other roles must be in same branch
            if not (request.user.branch and user.branch and request.user.branch.id == user.branch.id):
                messages.error(request, "You don't have permission to view this user's data")
                return None
    except Http404:
        logger.warning(f"User with ID {user_id} not found")
        messages.error(request, f"User with ID {user_id} not found")
        return None
    
    # Get user course statistics with improved logic
    # Use UTC for consistent date calculations
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Get user enrolled courses first (needed for accurate time calculation)
    user_courses = CourseEnrollment.objects.filter(user=user).select_related('course').order_by('-enrolled_at')
    enrolled_course_ids = list(user_courses.values_list('course_id', flat=True))
    
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, but has been accessed at some point
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        # Calculate total time spent only for enrolled courses
        # Filter by course field first (new records), then fallback to topic relationship (legacy records)
        total_time_spent=Sum('topic_progress__total_time_spent', 
            filter=Q(topic_progress__course_id__in=enrolled_course_ids) | 
                   Q(topic_progress__course__isnull=True, topic_progress__topic__coursetopic__course_id__in=enrolled_course_ids),
            default=0
        )
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Calculate completion rate
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Add calculated fields for each enrollment
    for enrollment in user_courses:
        # Ensure completion status is accurate
        enrollment.sync_completion_status()
        
        # Calculate progress percentage
        enrollment.calculated_progress = enrollment.progress_percentage
        
        # Get all topic progress for this course (using course-aware filtering)
        course_topic_progress = TopicProgress.objects.filter(
            user=user,
            course=enrollment.course
        )
        
        # Fallback: include legacy records without course field
        if not course_topic_progress.exists():
            course_topic_progress = TopicProgress.objects.filter(
                user=user,
                topic__coursetopic__course=enrollment.course,
                course__isnull=True
            )
        
        # Calculate average score from completed topics
        completed_topic_progress = course_topic_progress.filter(
            completed=True,
            last_score__isnull=False
        )
        if completed_topic_progress.exists():
            enrollment.calculated_score = round(completed_topic_progress.aggregate(
                avg_score=Avg('last_score')
            )['avg_score'] or 0)
        else:
            enrollment.calculated_score = None
        
        # Calculate total time spent on course (sum of all topic time)
        course_stats = course_topic_progress.aggregate(
            total_time=Sum('total_time_spent', default=0),
            total_attempts=Sum('attempts', default=0)
        )
        
        enrollment.course_time_spent = course_stats['total_time'] or 0
        enrollment.course_attempts = course_stats['total_attempts'] or 0
        
        # Format time spent for display
        total_seconds = enrollment.course_time_spent
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        enrollment.formatted_time_spent = f"{hours}h {minutes}m {seconds}s"
    
    # Recalculate user stats after syncing completion status
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Get list of course IDs the user is enrolled in
    enrolled_course_ids = list(user_courses.values_list('course_id', flat=True))
    
    user_stats = User.objects.filter(id=user_id).annotate(
        assigned_count=Count('courseenrollment', distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True), distinct=True),
        
        # In progress: enrolled, not completed, accessed recently (within 30 days)
        in_progress_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__gte=thirty_days_ago
        ), distinct=True),
        
        # Not passed: enrolled, not completed, but hasn't been accessed recently (>30 days)
        not_passed_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=False,
            courseenrollment__last_accessed__lt=thirty_days_ago
        ), distinct=True),
        
        # Not started: enrolled but never accessed
        not_started_count=Count('courseenrollment', filter=Q(
            courseenrollment__completed=False,
            courseenrollment__last_accessed__isnull=True
        ), distinct=True),
        
        # Calculate total time spent only for enrolled courses
        # Filter by course field first (new records), then fallback to topic relationship (legacy records)
        total_time_spent=Sum('topic_progress__total_time_spent', 
            filter=Q(topic_progress__course_id__in=enrolled_course_ids) | 
                   Q(topic_progress__course__isnull=True, topic_progress__topic__coursetopic__course_id__in=enrolled_course_ids),
            default=0
        )
    ).first()
    
    # Handle user with no stats
    if not user_stats:
        user_stats = User.objects.get(id=user_id)
        user_stats.assigned_count = 0
        user_stats.completed_count = 0
        user_stats.in_progress_count = 0
        user_stats.not_passed_count = 0
        user_stats.not_started_count = 0
        user_stats.total_time_spent = 0
    
    # Recalculate completion rate with updated data
    if user_stats.assigned_count > 0:
        completion_rate = round((user_stats.completed_count / user_stats.assigned_count) * 100, 1)
    else:
        completion_rate = 0.0
    
    # Format training time with proper null handling
    total_seconds = user_stats.total_time_spent if user_stats.total_time_spent is not None else 0
    # Ensure non-negative values and handle potential data corruption
    total_seconds = max(0, total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    training_time = f"{hours}h {minutes}m {seconds}s"
        
    # Get Learning Activities data (TopicProgress) with data consistency checks
    # Ensure data consistency: create missing TopicProgress records for enrolled courses only
    # Get all topics for enrolled courses in one query
    from courses.models import CourseTopic
    course_ids = [enrollment.course_id for enrollment in user_courses]
    course_topics = CourseTopic.objects.filter(course_id__in=course_ids).select_related('topic')
    
    # Get existing topic progress records for enrolled courses only
    existing_progress = set(
        TopicProgress.objects.filter(
            user=user,
            topic__in=[ct.topic for ct in course_topics]
        ).values_list('topic_id', flat=True)
    )
    
    # Create missing progress records in bulk for enrolled courses only
    missing_progress = []
    for course_topic in course_topics:
        if course_topic.topic_id not in existing_progress:
            missing_progress.append(
                TopicProgress(
                    user=user,
                    topic=course_topic.topic,
                    completed=False,
                    attempts=0
                )
            )
    
    # Use transaction for data consistency
    if missing_progress:
        try:
            with transaction.atomic():
                TopicProgress.objects.bulk_create(missing_progress, ignore_conflicts=True)
                logger.info(f"Created {len(missing_progress)} missing TopicProgress records for user {user.id}")
        except Exception as e:
            logger.error(f"Error creating TopicProgress records for user {user.id}: {str(e)}")
    
    # Get topic progress only for courses the user is enrolled in
    enrolled_course_ids = CourseEnrollment.objects.filter(user=user).values_list('course_id', flat=True)
    # Filter by course field directly to avoid duplicates from many-to-many join
    # Also handle legacy records where course might be null
    # Get the latest progress ID for each topic to avoid duplicates
    latest_progress_ids = TopicProgress.objects.filter(
        user=user
    ).filter(
        Q(course__in=enrolled_course_ids) |
        Q(course__isnull=True, topic__coursetopic__course__in=enrolled_course_ids)
    ).values('topic_id').annotate(
        latest_id=Max('id')
    ).values_list('latest_id', flat=True)
    
    topic_progress = TopicProgress.objects.filter(
        id__in=latest_progress_ids
    ).select_related('topic', 'course', 'topic__quiz').annotate(
        course_title=Case(
            When(course__isnull=False, then=F('course__title')),
            default=Subquery(
                CourseTopic.objects.filter(
                    topic=OuterRef('topic'),
                    course__in=enrolled_course_ids
                ).values('course__title')[:1]
            )
        )
    ).order_by('-last_accessed')
    
    # Calculate learning activities statistics
    total_activities = topic_progress.count()
    completed_activities = topic_progress.filter(completed=True).count()
    activities_in_progress = topic_progress.filter(
        completed=False
    ).filter(
        Q(first_accessed__isnull=False) | Q(total_time_spent__gt=0) | Q(last_score__gt=0)
    ).count()
    activities_not_started = topic_progress.filter(
        completed=False,
        first_accessed__isnull=True,
        total_time_spent=0,
        last_score__isnull=True
    ).count()
    
    # Calculate average activity score with proper handling
    from core.utils.scoring import ScoreCalculationService
    
    scored_progress = topic_progress.filter(last_score__isnull=False, last_score__gte=0)
    scored_activities_count = scored_progress.count()
    
    if scored_activities_count > 0:
        # Calculate properly normalized scores
        normalized_scores = []
        for progress in scored_progress:
            normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
            if normalized_score is not None:
                normalized_scores.append(float(normalized_score))
        
        avg_activity_score = round(sum(normalized_scores) / len(normalized_scores)) if normalized_scores else 0
    else:
        avg_activity_score = 0
    
    # Add formatted time to topic progress objects
    for progress in topic_progress:
        if progress.total_time_spent:
            hours = progress.total_time_spent // 3600
            minutes = (progress.total_time_spent % 3600) // 60
            seconds = progress.total_time_spent % 60
            progress.formatted_time = f"{hours}h {minutes}m {seconds}s"
        else:
            progress.formatted_time = "0h 0m 0s"
    
    # Get user timeline activities
    user_activities = Event.objects.filter(user=user).select_related('course').order_by('-created_at')[:20]
    
    # Get initial assessment quiz results
    from quiz.models import Quiz, QuizAttempt
    initial_assessment_data = []
    
    if user.branch:
        initial_assessment_quizzes = Quiz.objects.filter(
            Q(creator__branch=user.branch) | Q(course__branch=user.branch),
            is_initial_assessment=True,
            is_active=True
        ).distinct().order_by('title')
        
        for quiz in initial_assessment_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=user,
                is_completed=True
            ).select_related('quiz', 'user').prefetch_related(
                'quiz__questions',  # Prefetch questions for initial assessment classification
                'user_answers__question'  # Prefetch user answers with their questions for classification
            ).order_by('-end_time').first()
            
            if latest_attempt:
                classification_data = latest_attempt.calculate_assessment_classification()
                
                initial_assessment_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'completion_date': latest_attempt.end_time,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=user,
                        is_completed=True
                    ).count(),
                    'classification': classification_data
                })
    
    user_login_events_by_date = Event.objects.filter(
        user=user,
        type='LOGIN',
        created_at__gte=thirty_days_ago
    ).annotate(
        event_date=TruncDate('created_at')
    ).values('event_date').annotate(
        count=Count('id')
    ).order_by('event_date')
    
    login_by_date = {entry['event_date']: entry['count'] for entry in user_login_events_by_date}
    
    recent_logins = []
    for i in range(30):
        date = (thirty_days_ago + timedelta(days=i)).date()
        login_count = login_by_date.get(date, 0)
        recent_logins.append({
            'date': thirty_days_ago + timedelta(days=i),
            'count': min(login_count, 10)
        })
    
    # Get course completion data
    course_completion_events = Event.objects.filter(
        user=user,
        type='COURSE_COMPLETE',
        created_at__gte=thirty_days_ago
    ).annotate(
        event_date=TruncDate('created_at')
    ).values('event_date').annotate(
        count=Count('id')
    ).order_by('event_date')
    
    completion_by_date = {entry['event_date']: entry['count'] for entry in course_completion_events}
    
    course_completions = []
    for i in range(30):
        date = (thirty_days_ago + timedelta(days=i)).date()
        completion_count = completion_by_date.get(date, 0)
        if completion_count > 0:
            course_completions.append({
                'date': thirty_days_ago + timedelta(days=i),
                'count': completion_count
            })
    
    # Get user certificates
    from certificates.models import IssuedCertificate
    user_certificates = IssuedCertificate.objects.filter(recipient=user).order_by('-issue_date')
    total_certificates = user_certificates.count()
    
    # Gamification data removed
    total_badges = 0
    total_points = 0
    user_level = 0
        
    return {
        'user': user,
        'completion_rate': completion_rate,
        'completed_courses': user_stats.completed_count,
        'courses_in_progress': user_stats.in_progress_count,
        'courses_not_passed': user_stats.not_passed_count,
        'courses_not_started': user_stats.not_started_count,
        'total_courses': user_stats.assigned_count,
        'training_time': training_time,
        'user_courses': user_courses,
        # Learning Activities data
        'topic_progress': topic_progress,
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'activities_in_progress': activities_in_progress,
        'activities_not_started': activities_not_started,
        'avg_activity_score': avg_activity_score,
        'scored_activities_count': scored_activities_count,
        # Timeline data
        'user_activities': user_activities,
        'recent_logins': recent_logins,
        'course_completions': course_completions,
        # Initial Assessment data
        'initial_assessment_data': initial_assessment_data,
        'total_initial_assessments': len(initial_assessment_data),
        # Other data
        'user_certificates': user_certificates,
        'total_certificates': total_certificates,
        'total_badges': total_badges,
        'total_points': total_points,
        'user_level': user_level,
        'user_stats': user_stats,
    }


# Individual section views
@login_required
@user_detail_report_access_required
def user_report_overview(request, user_id):
    """Overview section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'overview',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Overview', 'icon': 'fa-chart-line'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/overview.html', data)


@login_required
@user_detail_report_access_required
def user_report_courses(request, user_id):
    """Courses section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'courses',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Courses', 'icon': 'fa-book'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/courses.html', data)


@login_required
@user_detail_report_access_required
def user_report_activities(request, user_id):
    """Learning Activities section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'learning-activities',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Learning Activities', 'icon': 'fa-tasks'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/learning_activities.html', data)


@login_required
@user_detail_report_access_required
def user_report_assessments(request, user_id):
    """Initial Assessments section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'initial-assessments',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Initial Assessments', 'icon': 'fa-clipboard-check'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/assessments.html', data)


@login_required
@user_detail_report_access_required
def user_report_certificates(request, user_id):
    """Certificates section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'certificates',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Certificates', 'icon': 'fa-certificate'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/certificates.html', data)


@login_required
@user_detail_report_access_required
def user_report_timeline(request, user_id):
    """Timeline section as separate page"""
    data = _get_user_report_data(request, user_id)
    if data is None:
        return redirect('reports:user_reports')
        
    # Add navigation context
    data.update({
        'current_section': 'timeline',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:user_reports'), 'label': 'User Reports', 'icon': 'fa-users'},
            {'url': reverse('reports:user_detail_report', kwargs={'user_id': user_id}), 'label': data['user'].get_full_name() or data['user'].username, 'icon': 'fa-user'},
            {'label': 'Timeline', 'icon': 'fa-clock'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/timeline.html', data)


# My learning report section views (for learners accessing their own reports)
@login_required
def my_report_overview(request):
    """My learning report - Overview section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'overview',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Overview', 'icon': 'fa-chart-line'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/overview.html', data)


@login_required
def my_report_courses(request):
    """My learning report - Courses section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
    
    # Note: Initial Assessments are now included in time spent calculation
    # Previously excluded, but now included per user request
    
    # Recalculate course-level statistics for each enrollment (including Initial Assessments)
    user_courses = data.get('user_courses', [])
    for enrollment in user_courses:
        # Get topic progress for this course (including Initial Assessments)
        course_topic_progress = TopicProgress.objects.filter(
            user=request.user,
            course=enrollment.course
        )
        
        # Fallback: include legacy records without course field
        if not course_topic_progress.exists():
            course_topic_progress = TopicProgress.objects.filter(
                user=request.user,
                topic__coursetopic__course=enrollment.course,
                course__isnull=True
            )
        
        # Recalculate average score from completed topics (including Initial Assessments)
        completed_topic_progress = course_topic_progress.filter(
            completed=True,
            last_score__isnull=False
        )
        if completed_topic_progress.exists():
            enrollment.calculated_score = round(completed_topic_progress.aggregate(
                avg_score=Avg('last_score')
            )['avg_score'] or 0)
        else:
            enrollment.calculated_score = None
        
        # Recalculate total time spent on course (sum of all topic time, including Initial Assessments)
        course_stats = course_topic_progress.aggregate(
            total_time=Sum('total_time_spent', default=0),
            total_attempts=Sum('attempts', default=0)
        )
        
        enrollment.course_time_spent = course_stats['total_time'] or 0
        enrollment.course_attempts = course_stats['total_attempts'] or 0
        
        # Format time spent for display
        total_seconds = enrollment.course_time_spent
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        enrollment.formatted_time_spent = f"{hours}h {minutes}m {seconds}s"
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'courses',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Courses', 'icon': 'fa-book'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/courses.html', data)


@login_required
def my_report_activities(request):
    """My learning report - Learning Activities section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
    
    # Filter out Initial Assessments related topics from topic_progress
    # Exclude topics where the quiz is an initial assessment
    if 'topic_progress' in data:
        data['topic_progress'] = data['topic_progress'].exclude(
            Q(topic__quiz__is_initial_assessment=True)
        )
        
        # Recalculate learning activities statistics excluding Initial Assessments
        topic_progress = data['topic_progress']
        data['total_activities'] = topic_progress.count()
        data['completed_activities'] = topic_progress.filter(completed=True).count()
        data['activities_in_progress'] = topic_progress.filter(
            completed=False
        ).filter(
            Q(first_accessed__isnull=False) | Q(total_time_spent__gt=0) | Q(last_score__gt=0)
        ).count()
        data['activities_not_started'] = topic_progress.filter(
            completed=False,
            first_accessed__isnull=True,
            total_time_spent=0,
            last_score__isnull=True
        ).count()
        
        # Recalculate average activity score excluding Initial Assessments
        from core.utils.scoring import ScoreCalculationService
        
        scored_progress = topic_progress.filter(last_score__isnull=False, last_score__gte=0)
        scored_activities_count = scored_progress.count()
        
        if scored_activities_count > 0:
            # Calculate properly normalized scores
            normalized_scores = []
            for progress in scored_progress:
                normalized_score = ScoreCalculationService.normalize_score(progress.last_score)
                if normalized_score is not None:
                    normalized_scores.append(float(normalized_score))
            
            data['avg_activity_score'] = round(sum(normalized_scores) / len(normalized_scores)) if normalized_scores else 0
            data['scored_activities_count'] = scored_activities_count
        else:
            data['avg_activity_score'] = 0
            data['scored_activities_count'] = 0
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'learning-activities',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Activities', 'icon': 'fa-tasks'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/learning_activities.html', data)


@login_required
def my_report_assessments(request):
    """My learning report - Initial Assessments section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'initial-assessments',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Assessments', 'icon': 'fa-clipboard-check'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/assessments.html', data)


@login_required
def my_report_certificates(request):
    """My learning report - Certificates section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'certificates',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Certificates', 'icon': 'fa-certificate'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/certificates.html', data)


@login_required
def my_report_timeline(request):
    """My learning report - Timeline section"""
    data = _get_user_report_data(request, request.user.id)
    if data is None:
        return redirect('users:dashboard')
        
    # Add navigation context for my reports
    data.update({
        'current_section': 'timeline',
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'My Learning Report - Timeline', 'icon': 'fa-clock'}
        ]
    })
    
    return render(request, 'reports/user_report_sections/timeline.html', data)


@login_required
@user_detail_report_access_required
def load_more_activities(request, user_id):
    """AJAX endpoint to load more user activities for timeline"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        user = get_object_or_404(User, id=user_id)
        
        # Session check: Ensure user has access to view this user's activities
        current_user = request.user
        if current_user.role == 'learner':
            # Learners can only view their own activities
            if current_user.id != int(user_id):
                return JsonResponse({'error': 'Access denied'}, status=403)
        elif not (current_user.is_superuser or current_user.role in ['globaladmin', 'superadmin', 'admin']):
            # Other roles must have same branch or report access permission
            if not (current_user.branch and user.branch and current_user.branch.id == user.branch.id):
                return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Get offset parameter for pagination
        offset = int(request.GET.get('offset', 20))  # Default offset is 20 (initial load)
        limit = 20  # Load 20 more items at a time
        
        # Get activities with offset and limit
        activities = Event.objects.filter(user=user).select_related('course').order_by('-created_at')[offset:offset+limit]
        
        # Prepare activity data for JSON response
        activities_data = []
        for activity in activities:
            activities_data.append({
                'type': activity.type,
                'type_display': activity.get_type_display(),
                'course_title': activity.course.title if activity.course else None,
                'description': activity.description,
                'created_at': activity.created_at.strftime('%d/%m/%Y %H:%M'),
                'icon_class': get_activity_icon_class(activity.type)
            })
        
        return JsonResponse({
            'activities': activities_data,
            'has_more': Event.objects.filter(user=user).count() > (offset + limit)
        })
        
    except Exception as e:
        logger.error(f"Error loading more activities for user {user_id}: {str(e)}")
        return JsonResponse({'error': 'Failed to load activities'}, status=500)




@login_required
@reports_access_required
def group_detail(request, group_id):
    """View for displaying detailed statistics for a specific group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    
    # Session check: Check permissions for group access
    if request.user.role == 'learner':
        messages.error(request, "You don't have permission to access group detail reports.")
        return redirect('reports:overview')
    
    # Get group members and their statistics
    members = User.objects.filter(
        group_memberships__group=group,
        group_memberships__is_active=True
    ).select_related('branch').prefetch_related('courseenrollment_set')
    
    # Calculate group statistics
    total_members = members.count()
    active_members = members.filter(is_active=True).count()
    
    # Get course enrollment statistics for group members
    enrollments = CourseEnrollment.objects.filter(user__in=members)
    total_enrollments = enrollments.count()
    completed_enrollments = enrollments.filter(completed=True).count()
    completion_rate = (completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0
    
    # Get courses with enrollment statistics for group members
    member_ids = list(members.values_list('id', flat=True))
    group_courses = Course.objects.filter(
        courseenrollment__user_id__in=member_ids
    ).distinct().annotate(
        enrollments_count=Count('courseenrollment', filter=Q(courseenrollment__user_id__in=member_ids), distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user_id__in=member_ids), distinct=True)
    ).annotate(
        completion_rate=Case(
            When(enrollments_count=0, then=Value(0.0)),
            default=ExpressionWrapper(
                (F('completed_count') * 100.0) / F('enrollments_count'),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).order_by('title')
    
    # Get timeline events for group members (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    timeline_events = Event.objects.filter(
        user_id__in=member_ids,
        created_at__gte=thirty_days_ago
    ).select_related('user', 'course').order_by('-created_at')[:50]
    
    context = {
        'group': group,
        'members': members,
        'total_members': total_members,
        'active_members': active_members,
        'total_enrollments': total_enrollments,
        'completed_enrollments': completed_enrollments,
        'completion_rate': round(completion_rate, 2),
        'group_courses': group_courses,
        'timeline_events': timeline_events,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:group_report'), 'label': 'Group Report', 'icon': 'fa-users'},
            {'label': f'Group: {group.name}', 'icon': 'fa-users'}
        ]
    }
    
    return render(request, 'reports/group_detail.html', context)


@login_required
@reports_access_required
def branch_detail(request, branch_id):
    """View for displaying detailed statistics for a specific branch."""
    branch = get_object_or_404(Branch, id=branch_id)
    
    # Session check: Learners cannot access branch detail reports
    if request.user.role == 'learner':
        return HttpResponseForbidden("Learners do not have access to branch detail reports.")
    
    # Get branch statistics - filter for learner users only
    branch_stats = Branch.objects.filter(id=branch_id).annotate(
        assigned_users=Count('users', filter=Q(users__role='learner')),
        total_enrollments=Count('users__courseenrollment', filter=Q(users__role='learner'), distinct=True),
        completed_courses=Count('users__courseenrollment', filter=Q(users__courseenrollment__completed=True, users__role='learner'), distinct=True),
        courses_in_progress=Count('users__courseenrollment', filter=Q(users__courseenrollment__completed=False, users__courseenrollment__last_accessed__isnull=False, users__role='learner'), distinct=True),
        courses_not_passed=Count('users__courseenrollment', filter=Q(users__courseenrollment__completed=False, users__courseenrollment__last_accessed__isnull=False, users__role='learner'), distinct=True),
        courses_not_started=Count('users__courseenrollment', filter=Q(users__courseenrollment__last_accessed__isnull=True, users__role='learner'), distinct=True),
        training_time=Sum('users__topic_progress__total_time_spent', filter=Q(users__role='learner'))
    ).annotate(
        completion_rate=Case(
            When(total_enrollments=0, then=Value(0.0)),
            default=ExpressionWrapper(
                (F('completed_courses') * 100.0) / F('total_enrollments'),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).first()
    
    # Get courses assigned to this branch with enrollment statistics - filter for learner users only
    branch_courses = Course.objects.filter(branch=branch).annotate(
        enrollments_count=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'), distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user__role='learner'), distinct=True)
    ).annotate(
        completion_rate=Case(
            When(enrollments_count=0, then=Value(0.0)),
            default=ExpressionWrapper(
                (F('completed_count') * 100.0) / F('enrollments_count'),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).order_by('title')
    
    # Get user-level statistics with course enrollment data - filter for learner users only
    users = branch.users.filter(role='learner').annotate(
        total_enrollments=Count('courseenrollment', distinct=True),
        completed_courses=Count('courseenrollment', filter=Q(courseenrollment__completed=True)),
        courses_in_progress=Count('courseenrollment', filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False)),
        courses_not_passed=Count('courseenrollment', filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False)),
        courses_not_started=Count('courseenrollment', filter=Q(courseenrollment__last_accessed__isnull=True)),
        training_time=Count('courseenrollment')
    ).order_by('first_name', 'last_name')
    
    # Format training time for display
    if branch_stats and branch_stats.training_time:
        hours = branch_stats.training_time // 3600 if branch_stats.training_time else 0
        minutes = (branch_stats.training_time % 3600) // 60 if branch_stats.training_time else 0
        seconds = branch_stats.training_time % 60 if branch_stats.training_time else 0
        branch_stats.training_time = f"{hours}h {minutes}m {seconds}s"
    else:
        if branch_stats:
            branch_stats.training_time = "0h 0m 0s"
    
    # Get top courses with highest completion rates
    top_courses = branch_courses.filter(enrollments_count__gt=0).order_by('-completion_rate')[:4]
    
    # Get timeline data for branch activities (last 30 days) - filter for learner users only
    thirty_days_ago = timezone.now() - timedelta(days=30)
    branch_user_ids = list(branch.users.filter(role='learner').values_list('id', flat=True))
    
    # Get recent events from Event model
    timeline_events = Event.objects.filter(
        user_id__in=branch_user_ids,
        created_at__gte=thirty_days_ago
    ).select_related('user', 'course').order_by('-created_at')[:50]
    
    # Month view - last 30 days (every 2 days)
    for i in range(0, 30, 2):
        date = timezone.now() - timedelta(days=29-i)
        
        # Count logins for this date
        login_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='LOGIN',
            created_at__date=date.date()
        ).count()
        
        # Count course completions for this date
        completion_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='COURSE_COMPLETE',
            created_at__date=date.date()
        ).count()
    
    # Week view - last 7 days
    for i in range(7):
        date = timezone.now() - timedelta(days=6-i)
        day_name = date.strftime('%a')
        
        login_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='LOGIN',
            created_at__date=date.date()
        ).count()
        
        completion_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='COURSE_COMPLETE',
            created_at__date=date.date()
        ).count()
    
    # Day view - last 24 hours (every 2 hours)
    for i in range(0, 24, 2):
        hour = (timezone.now() - timedelta(hours=23-i)).hour
        
        # For hourly data, we'll show a simplified version
        start_time = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        login_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='LOGIN',
            created_at__gte=start_time,
            created_at__lt=end_time
        ).count()
        
        completion_count = Event.objects.filter(
            user_id__in=branch_user_ids,
            type='COURSE_COMPLETE',
            created_at__gte=start_time,
            created_at__lt=end_time
        ).count()
    
    context = {
        'branch': branch,
        'branch_stats': branch_stats,
        'branch_courses': branch_courses,
        'top_courses': top_courses,
        'users': users,
        'timeline_events': timeline_events,
        'global_breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'url': reverse('reports:branch_report'), 'label': 'Branch Reports', 'icon': 'fa-code-branch'},
            {'label': branch.name, 'icon': 'fa-building'}
        ]
    }
    return render(request, 'reports/branch_detail.html', context)

@login_required
@reports_access_required
def branch_detail_excel(request, branch_id):
    """Export branch detail report to Excel"""
    import xlwt
    from django.http import HttpResponse
    from django.utils import timezone
    
    # Get the branch
    branch = get_object_or_404(Branch, id=branch_id)
    
    # Session check: Learners cannot access branch detail reports
    if request.user.role == 'learner':
        return HttpResponseForbidden("Learners do not have access to branch detail reports.")
    
    # Get branch statistics - filter for learner users only
    branch_stats = Branch.objects.filter(id=branch_id).annotate(
        assigned_users=Count('users', filter=Q(users__role='learner')),
        total_enrollments=Count('users__courseenrollment', filter=Q(users__role='learner'), distinct=True),
        completed_courses=Count('users__courseenrollment', filter=Q(users__courseenrollment__completed=True, users__role='learner'), distinct=True),
        training_time=Sum('users__topic_progress__total_time_spent', filter=Q(users__role='learner'))
    ).annotate(
        completion_rate=Case(
            When(total_enrollments=0, then=Value(0.0)),
            default=ExpressionWrapper(
                (F('completed_courses') * 100.0) / F('total_enrollments'),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).first()
    
    # Get courses assigned to this branch - filter for learner users only
    branch_courses = Course.objects.filter(branch=branch).annotate(
        enrollments_count=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'), distinct=True),
        completed_count=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user__role='learner'), distinct=True)
    ).annotate(
        completion_rate=Case(
            When(enrollments_count=0, then=Value(0.0)),
            default=ExpressionWrapper(
                (F('completed_count') * 100.0) / F('enrollments_count'),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )
    ).order_by('title')
    
    # Get user-level statistics - filter for learner users only
    users = branch.users.filter(role='learner').annotate(
        total_enrollments=Count('courseenrollment', distinct=True),
        completed_courses=Count('courseenrollment', filter=Q(courseenrollment__completed=True)),
        courses_in_progress=Count('courseenrollment', filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False)),
        courses_not_started=Count('courseenrollment', filter=Q(courseenrollment__last_accessed__isnull=True)),
    ).order_by('first_name', 'last_name')
    
    # Create Excel workbook
    wb = xlwt.Workbook(encoding='utf-8')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    title_style = xlwt.easyxf('font: bold on, height 320; align: wrap on, vert centre, horiz left')
    
    # Create Overview Sheet
    overview_sheet = wb.add_sheet('Branch Overview')
    overview_sheet.write(0, 0, f'{branch.name} - Branch Report', title_style)
    overview_sheet.write(2, 0, 'Branch Statistics', header_style)
    
    if branch_stats:
        overview_sheet.write(3, 0, 'Metric', header_style)
        overview_sheet.write(3, 1, 'Value', header_style)
        
        overview_sheet.write(4, 0, 'Total Learners')
        overview_sheet.write(4, 1, branch_stats.assigned_users or 0)
        
        overview_sheet.write(5, 0, 'Total Enrollments')
        overview_sheet.write(5, 1, branch_stats.total_enrollments or 0)
        
        overview_sheet.write(6, 0, 'Completed Courses')
        overview_sheet.write(6, 1, branch_stats.completed_courses or 0)
        
        overview_sheet.write(7, 0, 'Completion Rate')
        overview_sheet.write(7, 1, f"{branch_stats.completion_rate:.1f}%" if branch_stats.completion_rate else "0.0%")
    
    # Create Courses Sheet
    courses_sheet = wb.add_sheet('Courses')
    courses_sheet.write(0, 0, 'Course Title', header_style)
    courses_sheet.write(0, 1, 'Total Enrollments', header_style)
    courses_sheet.write(0, 2, 'Completed', header_style)
    courses_sheet.write(0, 3, 'Completion Rate', header_style)
    
    for row, course in enumerate(branch_courses, start=1):
        courses_sheet.write(row, 0, course.title)
        courses_sheet.write(row, 1, course.enrollments_count or 0)
        courses_sheet.write(row, 2, course.completed_count or 0)
        courses_sheet.write(row, 3, f"{course.completion_rate:.1f}%" if course.completion_rate else "0.0%")
    
    # Create Users Sheet
    users_sheet = wb.add_sheet('Users')
    users_sheet.write(0, 0, 'Name', header_style)
    users_sheet.write(0, 1, 'Email', header_style)
    users_sheet.write(0, 2, 'Total Enrollments', header_style)
    users_sheet.write(0, 3, 'Completed Courses', header_style)
    users_sheet.write(0, 4, 'In Progress', header_style)
    users_sheet.write(0, 5, 'Not Started', header_style)
    
    for row, user in enumerate(users, start=1):
        users_sheet.write(row, 0, user.get_full_name() or user.username)
        users_sheet.write(row, 1, user.email)
        users_sheet.write(row, 2, user.total_enrollments or 0)
        users_sheet.write(row, 3, user.completed_courses or 0)
        users_sheet.write(row, 4, user.courses_in_progress or 0)
        users_sheet.write(row, 5, user.courses_not_started or 0)
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    branch_name = ''.join(c for c in branch.name if c.isalnum() or c == ' ').replace(' ', '_')
    filename = f"branch_report_{branch_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

@login_required
@reports_access_required
def course_detail(request, course_id):
    """View for displaying detailed statistics for a specific course."""
    course = get_object_or_404(Course, id=course_id)
    
    # Session check: Ensure user has access to this course data
    current_user = request.user
    user_is_learner = current_user.role == 'learner'
    
    # If user is a learner, they can only see their own data and only if enrolled in the course
    if user_is_learner:
        # Check if the learner is enrolled in this course
        user_enrollment = CourseEnrollment.objects.filter(course=course, user=current_user).first()
        if not user_enrollment:
            return HttpResponseForbidden("You don't have access to this course report.")
    
    # For learners: filter data to show only their own information
    # For other roles: show all data (existing behavior)
    if user_is_learner:
        # Course statistics - only show current user's data
        course_stats = Course.objects.filter(id=course_id).annotate(
            assigned_learners=Count('courseenrollment', filter=Q(courseenrollment__user=current_user), distinct=True),
            completed_learners=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user=current_user), distinct=True),
            learners_in_progress=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user=current_user), 
                distinct=True
            ),
            learners_not_started=Count('courseenrollment', 
                filter=Q(courseenrollment__last_accessed__isnull=True, courseenrollment__user=current_user), 
                distinct=True
            ),
            learners_not_passed=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user=current_user), 
                distinct=True
            ),
            # Calculate total training time (in hours)
            total_training_time=Count('courseenrollment', filter=Q(courseenrollment__user=current_user))
        ).first()
        
        # Learner-level statistics - only show current user's data
        learners = User.objects.filter(
            courseenrollment__course=course, 
            id=current_user.id  # Only show current user's data
        ).annotate(
            completion_date=F('courseenrollment__completion_date'),
            last_accessed=F('courseenrollment__last_accessed'),
            enrolled_date=F('courseenrollment__enrolled_at'),
            status=Case(
                When(courseenrollment__completed=True, then=Value('Completed')),
                When(courseenrollment__last_accessed__isnull=False, then=Value('In Progress')),
                default=Value('Not Started')
            )
        ).select_related('branch')
    else:
        # For non-learner users: show all data (existing behavior)
        # Get course statistics - filter for learner users only
        course_stats = Course.objects.filter(id=course_id).annotate(
            assigned_learners=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'), distinct=True),
            completed_learners=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user__role='learner'), distinct=True),
            learners_in_progress=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            learners_not_started=Count('courseenrollment', 
                filter=Q(courseenrollment__last_accessed__isnull=True, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            learners_not_passed=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            # Calculate total training time (in hours)
            total_training_time=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'))
        ).first()
        
        # Get learner-level statistics with role information and scores - filter for actual learner role users only
        # Using fixed role logic: only show users who are enrolled as learners (role='learner')
        learners = User.objects.filter(
            courseenrollment__course=course, 
            role='learner'  # This ensures we only get actual learner role users
        ).annotate(
            completion_date=F('courseenrollment__completion_date'),
            last_accessed=F('courseenrollment__last_accessed'),
            enrolled_date=F('courseenrollment__enrolled_at'),
            status=Case(
                When(courseenrollment__completed=True, then=Value('Completed')),
                When(courseenrollment__last_accessed__isnull=False, then=Value('In Progress')),
                default=Value('Not Started')
            )
        ).select_related('branch')
    
    # Add time spent and progress data by getting the enrollment object for each learner
    learners_with_progress = []
    for learner in learners:
        enrollment = CourseEnrollment.objects.filter(course=course, user=learner).first()
        if enrollment:
            learner.progress_percentage = enrollment.progress_percentage if hasattr(enrollment, 'progress_percentage') else 0
            
            # Get all topic progress for this course (using course-aware filtering)
            course_topic_progress = TopicProgress.objects.filter(
                user=learner,
                course=course
            )
            
            # Fallback: include legacy records without course field
            if not course_topic_progress.exists():
                course_topic_progress = TopicProgress.objects.filter(
                    user=learner,
                    topic__coursetopic__course=course,
                    course__isnull=True
                )
            
            # Calculate total time spent on course (sum of all topic time)
            time_stats = course_topic_progress.aggregate(
                total_time=Sum('total_time_spent', default=0)
            )
            
            # Format time spent for display
            total_seconds = time_stats['total_time'] or 0
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            learner.time_spent_formatted = f"{hours}h {minutes}m {seconds}s"
            
            raw_score = getattr(enrollment, 'score', None)
            # Use normalized score to handle both percentage and basis points formats
            learner.score = normalize_score(raw_score)
        else:
            learner.progress_percentage = 0
            learner.time_spent_formatted = "0h 0m 0s"
            learner.score = None
        learners_with_progress.append(learner)
    
    # Get topic progress statistics for learning activities
    if user_is_learner:
        # For learners: only show their own progress data
        topics = Topic.objects.filter(coursetopic__course=course).annotate(
            completed_count=Count('user_progress', filter=Q(user_progress__completed=True, user_progress__user=current_user)),
            in_progress_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__user=current_user)
            ),
            not_started_count=Count('user_progress', filter=Q(user_progress__first_accessed__isnull=True, user_progress__user=current_user)),
            not_passed_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__last_score__lt=70, user_progress__user=current_user)
            ),
            average_score=Avg('user_progress__last_score', filter=Q(user_progress__user=current_user)),
            # Get total enrollments count for this topic (just for current user)
            total_enrollments=Count('user_progress', filter=Q(user_progress__user=current_user), distinct=True)
        ).order_by('order', 'coursetopic__order', 'created_at')
    else:
        # For non-learners: show all data (existing behavior)
        topics = Topic.objects.filter(coursetopic__course=course).annotate(
            completed_count=Count('user_progress', filter=Q(user_progress__completed=True)),
            in_progress_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False)
            ),
            not_started_count=Count('user_progress', filter=Q(user_progress__first_accessed__isnull=True)),
            not_passed_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__last_score__lt=70)
            ),
            average_score=Avg('user_progress__last_score'),
            # Get total enrollments count for this topic
            total_enrollments=Count('user_progress', distinct=True)
        ).order_by('order', 'coursetopic__order', 'created_at')
    
    # Normalize average scores to handle basis points properly
    for topic in topics:
        if topic.average_score:
            topic.average_score = normalize_score(topic.average_score)
    
    # Prepare unit matrix data - a matrix of learners vs topics with their progress status
    matrix_data = []
    
    # Get all enrolled learners for the matrix
    if learners_with_progress and topics:
        for learner in learners_with_progress:
            learner_row = {
                'learner': learner,
                'topics_progress': []
            }
            
            # For each topic, get the learner's progress
            for topic in topics:
                progress = TopicProgress.objects.filter(
                    user=learner,
                    topic=topic
                ).first()
                
                if progress:
                    if progress.completed:
                        status = 'completed'
                        score = normalize_score(progress.last_score)
                    elif progress.first_accessed:
                        status = 'in_progress'
                        score = normalize_score(progress.last_score)
                    else:
                        status = 'not_started'
                        score = None
                else:
                    status = 'not_started'
                    score = None
                
                learner_row['topics_progress'].append({
                    'topic': topic,
                    'status': status,
                    'score': score
                })
            
            matrix_data.append(learner_row)
    
    # Get course timeline events
    if user_is_learner:
        # For learners: only show their own events
        course_events = Event.objects.filter(course=course, user=current_user).select_related('user').order_by('-created_at')[:20]
    else:
        # For non-learners: show all events (existing behavior)
        course_events = Event.objects.filter(course=course).select_related('user').order_by('-created_at')[:20]
    
    # Calculate completion rate and other metrics
    total_learners = course_stats.assigned_learners if course_stats else 0
    completion_rate = 0
    if total_learners > 0 and course_stats:
        completion_rate = round((course_stats.completed_learners / total_learners) * 100, 1)
    
    # Calculate training time
    training_time_display = "3d 21h"
    
    # Calculate pass/fail counts and total attempts
    if course_stats:
        passed_count = course_stats.completed_learners
        not_passed_count = course_stats.learners_not_passed
    else:
        passed_count = 0
        not_passed_count = 0
    
    # Calculate total enrollments (CourseEnrollment doesn't have attempts field)
    total_attempts = CourseEnrollment.objects.filter(
        course=course, 
        user__role='learner'
    ).count()
    
    now = timezone.now()
    start_date = (now - timedelta(days=29)).date()
    end_date = now.date()
    date_range = [start_date + timedelta(days=i) for i in range(30)]
    date_labels = [date.strftime('%m/%d') for date in date_range]
    
    # Initialize counts
    login_counts = [0] * len(date_range)
    completion_counts = [0] * len(date_range)
    
    try:
        if user_is_learner:
            # For learners: only show their own login and completion data
            logins = User.objects.filter(
                id=current_user.id,
                last_login__date__gte=start_date,
                last_login__date__lte=end_date
            ).values('last_login__date').annotate(count=Count('id'))
            
            # Map login data to dates
            for login in logins:
                if login['last_login__date']:
                    try:
                        day_index = (login['last_login__date'] - start_date).days
                        if 0 <= day_index < len(date_range):
                            login_counts[day_index] = login['count']
                    except (TypeError, AttributeError):
                        continue
            
            # Get completion data - only for current user
            completions = CourseEnrollment.objects.filter(
                course=course,
                user=current_user,
                completed=True,
                completion_date__date__gte=start_date,
                completion_date__date__lte=end_date
            ).values('completion_date__date').annotate(count=Count('id'))
        else:
            # For non-learners: show all data (existing behavior)
            # Get login data for course-enrolled users
            enrolled_users = User.objects.filter(
                courseenrollment__course=course,
                role='learner'
            )
            
            logins = enrolled_users.filter(
                last_login__date__gte=start_date,
                last_login__date__lte=end_date
            ).values('last_login__date').annotate(count=Count('id'))
            
            # Map login data to dates
            for login in logins:
                if login['last_login__date']:
                    try:
                        day_index = (login['last_login__date'] - start_date).days
                        if 0 <= day_index < len(date_range):
                            login_counts[day_index] = login['count']
                    except (TypeError, AttributeError):
                        continue
            
            # Get completion data
            completions = CourseEnrollment.objects.filter(
                course=course,
                completed=True,
                completion_date__date__gte=start_date,
                completion_date__date__lte=end_date,
                user__role='learner'
            ).values('completion_date__date').annotate(count=Count('id'))
        
        # Map completion data to dates
        for completion in completions:
            if completion['completion_date__date']:
                try:
                    day_index = (completion['completion_date__date'] - start_date).days
                    if 0 <= day_index < len(date_range):
                        completion_counts[day_index] = completion['count']
                except (TypeError, AttributeError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error getting initial activity data for course {course_id}: {str(e)}")
        # Fallback to empty data
        pass
    
    # Add breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'url': reverse('reports:courses_report'), 'label': 'Courses', 'icon': 'fa-book'},
        {'label': course.title, 'icon': 'fa-book-open'}
    ]
    
    context = {
        'course': course,
        'course_stats': course_stats,
        'learners': learners_with_progress,
        'topics': topics,
        'course_events': course_events,
        'completion_rate': completion_rate,
        'activity_dates': date_labels,
        'login_counts': login_counts,
        'completion_counts': completion_counts,
        'breadcrumbs': breadcrumbs,
        'training_time_display': training_time_display,
        'passed_count': passed_count,
        'not_passed_count': not_passed_count,
        'total_attempts': total_attempts,
        'matrix_data': matrix_data,
    }
    # Redirect to the overview section for the new page-based navigation
    from django.shortcuts import redirect
    return redirect('reports:course_report_overview', course_id=course_id)

def _get_course_report_data(request, course_id):
    """Helper function to get course report data - shared across all course section views"""
    from courses.models import TopicProgress
    
    course = get_object_or_404(Course, id=course_id)
    
    # Session check: Ensure user has access to this course data
    current_user = request.user
    user_is_learner = current_user.role == 'learner'
    
    # If user is a learner, they can only see their own data and only if enrolled in the course
    if user_is_learner:
        # Check if the learner is enrolled in this course
        user_enrollment = CourseEnrollment.objects.filter(course=course, user=current_user).first()
        if not user_enrollment:
            return None
    
    # For learners: filter data to show only their own information
    # For other roles: show all data (existing behavior)
    if user_is_learner:
        # Course statistics - only show current user's data
        course_stats = Course.objects.filter(id=course_id).annotate(
            assigned_learners=Count('courseenrollment', filter=Q(courseenrollment__user=current_user), distinct=True),
            completed_learners=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user=current_user), distinct=True),
            learners_in_progress=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user=current_user), 
                distinct=True
            ),
            learners_not_started=Count('courseenrollment', 
                filter=Q(courseenrollment__last_accessed__isnull=True, courseenrollment__user=current_user), 
                distinct=True
            ),
            learners_not_passed=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user=current_user), 
                distinct=True
            ),
            # Calculate total training time (in hours)
            total_training_time=Count('courseenrollment', filter=Q(courseenrollment__user=current_user))
        ).first()
        
        # Learner-level statistics - only show current user's data
        learners = User.objects.filter(
            courseenrollment__course=course, 
            id=current_user.id  # Only show current user's data
        ).annotate(
            completion_date=F('courseenrollment__completion_date'),
            last_accessed=F('courseenrollment__last_accessed'),
            enrolled_date=F('courseenrollment__enrolled_at'),
            status=Case(
                When(courseenrollment__completed=True, then=Value('Completed')),
                When(courseenrollment__last_accessed__isnull=False, then=Value('In Progress')),
                default=Value('Not Started')
            )
        ).select_related('branch')
    else:
        # For non-learner users: show all data (existing behavior)
        # Get course statistics - filter for learner users only
        course_stats = Course.objects.filter(id=course_id).annotate(
            assigned_learners=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'), distinct=True),
            completed_learners=Count('courseenrollment', filter=Q(courseenrollment__completed=True, courseenrollment__user__role='learner'), distinct=True),
            learners_in_progress=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            learners_not_started=Count('courseenrollment', 
                filter=Q(courseenrollment__last_accessed__isnull=True, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            learners_not_passed=Count('courseenrollment', 
                filter=Q(courseenrollment__completed=False, courseenrollment__last_accessed__isnull=False, courseenrollment__user__role='learner'), 
                distinct=True
            ),
            # Calculate total training time (in hours)
            total_training_time=Count('courseenrollment', filter=Q(courseenrollment__user__role='learner'))
        ).first()
        
        # Get learner-level statistics with role information and scores - filter for actual learner role users only
        # Using fixed role logic: only show users who are enrolled as learners (role='learner')
        learners = User.objects.filter(
            courseenrollment__course=course, 
            role='learner'  # This ensures we only get actual learner role users
        ).annotate(
            completion_date=F('courseenrollment__completion_date'),
            last_accessed=F('courseenrollment__last_accessed'),
            enrolled_date=F('courseenrollment__enrolled_at'),
            status=Case(
                When(courseenrollment__completed=True, then=Value('Completed')),
                When(courseenrollment__last_accessed__isnull=False, then=Value('In Progress')),
                default=Value('Not Started')
            )
        ).select_related('branch')
    
    # Add time spent and progress data by getting the enrollment object for each learner
    learners_with_progress = []
    for learner in learners:
        enrollment = CourseEnrollment.objects.filter(course=course, user=learner).first()
        if enrollment:
            learner.progress_percentage = enrollment.progress_percentage if hasattr(enrollment, 'progress_percentage') else 0
            
            # Get all topic progress for this course (using course-aware filtering)
            course_topic_progress = TopicProgress.objects.filter(
                user=learner,
                course=course
            )
            
            # Fallback: include legacy records without course field
            if not course_topic_progress.exists():
                course_topic_progress = TopicProgress.objects.filter(
                    user=learner,
                    topic__coursetopic__course=course,
                    course__isnull=True
                )
            
            # Calculate total time spent on course (sum of all topic time)
            time_stats = course_topic_progress.aggregate(
                total_time=Sum('total_time_spent', default=0)
            )
            
            # Format time spent for display
            total_seconds = time_stats['total_time'] or 0
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            learner.time_spent_formatted = f"{hours}h {minutes}m {seconds}s"
            
            raw_score = getattr(enrollment, 'score', None)
            # Use normalized score to handle both percentage and basis points formats
            learner.score = normalize_score(raw_score)
        else:
            learner.progress_percentage = 0
            learner.time_spent_formatted = "0h 0m 0s"
            learner.score = None
        learners_with_progress.append(learner)
    
    # Get topic progress statistics for learning activities
    if user_is_learner:
        # For learners: only show their own progress data
        topics = Topic.objects.filter(coursetopic__course=course).annotate(
            completed_count=Count('user_progress', filter=Q(user_progress__completed=True, user_progress__user=current_user)),
            in_progress_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__user=current_user)
            ),
            not_started_count=Count('user_progress', filter=Q(user_progress__first_accessed__isnull=True, user_progress__user=current_user)),
            not_passed_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__last_score__lt=70, user_progress__user=current_user)
            ),
            average_score=Avg('user_progress__last_score', filter=Q(user_progress__user=current_user)),
            # Get total enrollments count for this topic (just for current user)
            total_enrollments=Count('user_progress', filter=Q(user_progress__user=current_user), distinct=True)
        ).order_by('order', 'coursetopic__order', 'created_at')
    else:
        # For non-learners: show all data (existing behavior)
        topics = Topic.objects.filter(coursetopic__course=course).annotate(
            completed_count=Count('user_progress', filter=Q(user_progress__completed=True)),
            in_progress_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False)
            ),
            not_started_count=Count('user_progress', filter=Q(user_progress__first_accessed__isnull=True)),
            not_passed_count=Count('user_progress', 
                filter=Q(user_progress__completed=False, user_progress__first_accessed__isnull=False, user_progress__last_score__lt=70)
            ),
            average_score=Avg('user_progress__last_score'),
            # Get total enrollments count for this topic
            total_enrollments=Count('user_progress', distinct=True)
        ).order_by('order', 'coursetopic__order', 'created_at')
    
    # Normalize average scores to handle basis points properly
    for topic in topics:
        if topic.average_score:
            topic.average_score = normalize_score(topic.average_score)
    
    # Prepare unit matrix data - a matrix of learners vs topics with their progress status
    matrix_data = []
    
    # Get all enrolled learners for the matrix
    if learners_with_progress and topics:
        for learner in learners_with_progress:
            learner_row = {
                'learner': learner,
                'topics_progress': []
            }
            
            # For each topic, get the learner's progress
            for topic in topics:
                progress = TopicProgress.objects.filter(
                    user=learner,
                    topic=topic
                ).first()
                
                if progress:
                    if progress.completed:
                        status = 'completed'
                        score = normalize_score(progress.last_score)
                    elif progress.first_accessed:
                        status = 'in_progress'
                        score = normalize_score(progress.last_score)
                    else:
                        status = 'not_started'
                        score = None
                else:
                    status = 'not_started'
                    score = None
                
                learner_row['topics_progress'].append({
                    'topic': topic,
                    'status': status,
                    'score': score
                })
            
            matrix_data.append(learner_row)
    
    # Get course timeline events
    if user_is_learner:
        # For learners: only show their own events
        course_events = Event.objects.filter(course=course, user=current_user).select_related('user').order_by('-created_at')[:20]
    else:
        # For non-learners: show all events (existing behavior)
        course_events = Event.objects.filter(course=course).select_related('user').order_by('-created_at')[:20]
    
    # Calculate completion rate and other metrics
    total_learners = course_stats.assigned_learners if course_stats else 0
    completion_rate = 0
    if total_learners > 0 and course_stats:
        completion_rate = round((course_stats.completed_learners / total_learners) * 100, 1)
    
    # Calculate training time
    training_time_display = "3d 21h"
    
    # Calculate pass/fail counts and total attempts
    if course_stats:
        passed_count = course_stats.completed_learners
        not_passed_count = course_stats.learners_not_passed
    else:
        passed_count = 0
        not_passed_count = 0
    
    # Calculate total enrollments (CourseEnrollment doesn't have attempts field)
    total_attempts = CourseEnrollment.objects.filter(
        course=course, 
        user__role='learner'
    ).count()
    
    now = timezone.now()
    start_date = (now - timedelta(days=29)).date()
    end_date = now.date()
    date_range = [start_date + timedelta(days=i) for i in range(30)]
    date_labels = [date.strftime('%m/%d') for date in date_range]
    
    # Initialize counts
    login_counts = [0] * len(date_range)
    completion_counts = [0] * len(date_range)
    
    try:
        if user_is_learner:
            # For learners: only show their own login and completion data
            logins = User.objects.filter(
                id=current_user.id,
                last_login__date__gte=start_date,
                last_login__date__lte=end_date
            ).values('last_login__date').annotate(count=Count('id'))
            
            # Map login data to dates
            for login in logins:
                if login['last_login__date']:
                    try:
                        day_index = (login['last_login__date'] - start_date).days
                        if 0 <= day_index < len(date_range):
                            login_counts[day_index] = login['count']
                    except (TypeError, AttributeError):
                        continue
            
            # Get completion data - only for current user
            completions = CourseEnrollment.objects.filter(
                course=course,
                user=current_user,
                completed=True,
                completion_date__date__gte=start_date,
                completion_date__date__lte=end_date
            ).values('completion_date__date').annotate(count=Count('id'))
            
        else:
            # For non-learners: show all login data (existing behavior)
            logins = User.objects.filter(
                role='learner',
                last_login__date__gte=start_date,
                last_login__date__lte=end_date
            ).values('last_login__date').annotate(count=Count('id'))
            
            # Map login data to dates
            for login in logins:
                if login['last_login__date']:
                    try:
                        day_index = (login['last_login__date'] - start_date).days
                        if 0 <= day_index < len(date_range):
                            login_counts[day_index] = login['count']
                    except (TypeError, AttributeError):
                        continue
            
            # Get completion data
            completions = CourseEnrollment.objects.filter(
                course=course,
                completed=True,
                completion_date__date__gte=start_date,
                completion_date__date__lte=end_date,
                user__role='learner'
            ).values('completion_date__date').annotate(count=Count('id'))
        
        # Map completion data to dates
        for completion in completions:
            if completion['completion_date__date']:
                try:
                    day_index = (completion['completion_date__date'] - start_date).days
                    if 0 <= day_index < len(date_range):
                        completion_counts[day_index] = completion['count']
                except (TypeError, AttributeError):
                    continue
                    
    except Exception as e:
        logger.error(f"Error getting initial activity data for course {course_id}: {str(e)}")
        # Fallback to empty data
        pass
    
    # Add breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
        {'url': reverse('reports:courses_report'), 'label': 'Courses', 'icon': 'fa-book'},
        {'label': course.title, 'icon': 'fa-book-open'}
    ]
    
    
    return {
        'course': course,
        'course_stats': course_stats,
        'learners': learners_with_progress,
        'topics': topics,
        'course_events': course_events,
        'completion_rate': completion_rate,
        'activity_dates': date_labels,
        'login_counts': login_counts,
        'completion_counts': completion_counts,
        'breadcrumbs': breadcrumbs,
        'training_time_display': training_time_display,
        'passed_count': passed_count,
        'not_passed_count': not_passed_count,
        'total_attempts': total_attempts,
        'matrix_data': matrix_data,
    }

@login_required
@reports_access_required
def course_report_overview(request, course_id):
    """Overview section as separate page"""
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    data.update({
        'current_section': 'overview',
        'section_title': 'Overview'
    })
    return render(request, 'reports/course_report_sections/overview.html', data)


@login_required
@reports_access_required
def course_report_users(request, course_id):
    """Users section as separate page"""
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    data.update({
        'current_section': 'users',
        'section_title': 'Users'
    })
    return render(request, 'reports/course_report_sections/users.html', data)

@login_required
@reports_access_required
def course_report_activities(request, course_id):
    """Learning Activities section as separate page"""
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    data.update({
        'current_section': 'learning-activities',
        'section_title': 'Learning Activities'
    })
    return render(request, 'reports/course_report_sections/learning_activities.html', data)

@login_required
@reports_access_required
def course_report_matrix(request, course_id):
    """Unit Matrix section as separate page"""
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    data.update({
        'current_section': 'unit-matrix',
        'section_title': 'Unit Matrix'
    })
    return render(request, 'reports/course_report_sections/unit_matrix.html', data)

@login_required
@reports_access_required
def course_report_timeline(request, course_id):
    """Timeline section as separate page"""
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    data.update({
        'current_section': 'timeline',
        'section_title': 'Timeline'
    })
    return render(request, 'reports/course_report_sections/timeline.html', data)

@login_required
@reports_access_required
def course_timeline_excel(request, course_id):
    """Export course timeline data to Excel"""
    import xlwt
    from django.http import HttpResponse
    from django.utils import timezone
    from courses.models import Course, CourseEnrollment, TopicProgress
    from django.contrib.auth import get_user_model
    from lms_notifications.models import UserNotification
    
    # Get the course
    course = get_object_or_404(Course, id=course_id)
    
    # Check access permissions (same as course_report_timeline)
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    # Get timeline events data
    User = get_user_model()
    timeline_events = []
    
    # Get course enrollments and related progress events
    enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
    
    for enrollment in enrollments:
        user = enrollment.user
        
        # Get topic progress for this user in this course
        topic_progresses = TopicProgress.objects.filter(
            user=user,
            topic__course=course
        ).select_related('topic').order_by('-updated_at')
        
        for progress in topic_progresses:
            event_type = "Assessment Progress"
            if progress.status == 'completed':
                if hasattr(progress, 'score') and progress.score is not None:
                    if progress.score >= 70:  # Assuming 70% is pass threshold
                        description = f"{user.get_full_name() or user.username} completed {progress.topic.title} (score: {progress.score}%)"
                    else:
                        description = f"{user.get_full_name() or user.username} did not pass the {progress.topic.title} (score: {progress.score}%)"
                else:
                    description = f"{user.get_full_name() or user.username} completed {progress.topic.title}"
            elif progress.status == 'in_progress':
                description = f"{user.get_full_name() or user.username} started {progress.topic.title}"
            else:
                description = f"{user.get_full_name() or user.username} accessed {progress.topic.title}"
            
            timeline_events.append({
                'date': progress.updated_at,
                'user': user.get_full_name() or user.username,
                'event_type': event_type,
                'description': description,
                'topic': progress.topic.title,
                'score': getattr(progress, 'score', None),
                'status': progress.status
            })
    
    # Get course update notifications
    course_notifications = UserNotification.objects.filter(
        message__icontains=course.title
    ).order_by('-created_at')[:50]  # Limit to recent 50 notifications
    
    for notification in course_notifications:
        if 'updated' in notification.message.lower():
            timeline_events.append({
                'date': notification.created_at,
                'user': notification.user.get_full_name() or notification.user.username if notification.user else 'System',
                'event_type': 'Course Update',
                'description': notification.message,
                'topic': '',
                'score': None,
                'status': 'update'
            })
    
    # Sort events by date (most recent first)
    timeline_events.sort(key=lambda x: x['date'], reverse=True)
    
    # Create Excel workbook
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Course Timeline')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    date_style = xlwt.easyxf('num_format_str: DD/MM/YYYY HH:MM')
    
    # Write headers
    headers = ['Date', 'Time', 'User', 'Event Type', 'Description', 'Topic/Unit', 'Score', 'Status']
    for col, header in enumerate(headers):
        ws.write(0, col, header, header_style)
    
    # Set column widths
    ws.col(0).width = 3000  # Date
    ws.col(1).width = 2500  # Time
    ws.col(2).width = 4000  # User
    ws.col(3).width = 4000  # Event Type
    ws.col(4).width = 8000  # Description
    ws.col(5).width = 4000  # Topic/Unit
    ws.col(6).width = 2000  # Score
    ws.col(7).width = 3000  # Status
    
    # Write data rows
    for row, event in enumerate(timeline_events, start=1):
        ws.write(row, 0, event['date'].strftime('%d/%m/%Y'), date_style)
        ws.write(row, 1, event['date'].strftime('%H:%M'))
        ws.write(row, 2, event['user'])
        ws.write(row, 3, event['event_type'])
        ws.write(row, 4, event['description'])
        ws.write(row, 5, event['topic'])
        ws.write(row, 6, f"{event['score']}%" if event['score'] is not None else '-')
        ws.write(row, 7, event['status'].title())
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    course_name = ''.join(c for c in course.title if c.isalnum() or c == ' ').replace(' ', '_')
    filename = f"course_timeline_{course_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

@login_required
@reports_access_required
def course_overview_excel(request, course_id):
    """Export course overview data to Excel"""
    import xlwt
    from django.http import HttpResponse
    from django.utils import timezone
    from courses.models import Course
    
    # Get the course
    course = get_object_or_404(Course, id=course_id)
    
    # Check access permissions
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    # Create Excel workbook
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Course Overview')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    bold_style = xlwt.easyxf('font: bold on')
    
    # Write course information
    ws.write(0, 0, 'Course:', bold_style)
    ws.write(0, 1, course.title)
    ws.write(1, 0, 'Course Code:', bold_style)
    ws.write(1, 1, course.code if hasattr(course, 'code') else '-')
    
    # Write overview statistics
    ws.write(3, 0, 'Overview Statistics', header_style)
    ws.write(4, 0, 'Metric', header_style)
    ws.write(4, 1, 'Value', header_style)
    
    course_stats = data.get('course_stats')
    completion_rate = data.get('completion_rate', 0)
    
    stats = [
        ('Completion Rate', f"{completion_rate}%"),
        ('Assigned Learners', course_stats.assigned_learners if course_stats else 0),
        ('Completed Learners', course_stats.completed_learners if course_stats else 0),
        ('Learners In Progress', course_stats.learners_in_progress if course_stats else 0),
        ('Learners Not Started', course_stats.learners_not_started if course_stats else 0),
        ('Learners Not Passed', course_stats.learners_not_passed if course_stats else 0),
    ]
    
    for i, (metric, value) in enumerate(stats, start=5):
        ws.write(i, 0, metric)
        ws.write(i, 1, value)
    
    # Set column widths
    ws.col(0).width = 6000
    ws.col(1).width = 4000
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    course_name = ''.join(c for c in course.title if c.isalnum() or c == ' ').replace(' ', '_')
    filename = f"course_overview_{course_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

@login_required
@reports_access_required
def course_users_excel(request, course_id):
    """Export course users data to Excel"""
    import xlwt
    from django.http import HttpResponse
    from django.utils import timezone
    from courses.models import Course
    
    # Get the course
    course = get_object_or_404(Course, id=course_id)
    
    # Check access permissions
    data = _get_course_report_data(request, course_id)
    if data is None:
        return HttpResponseForbidden("You don't have access to this course report.")
    
    # Get learners data
    learners = data.get('learners', [])
    
    # Create Excel workbook
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Course Users')
    
    # Define styles
    header_style = xlwt.easyxf('font: bold on; align: wrap on, vert centre, horiz center; pattern: pattern solid, fore_colour gray25')
    date_style = xlwt.easyxf('num_format_str: DD/MM/YYYY')
    
    # Write headers
    headers = ['User', 'Email', 'Role', 'Branch', 'Progress Status', 'Progress %', 'Score', 'Time Spent', 'Enrolled Date', 'Last Accessed', 'Completion Date']
    for col, header in enumerate(headers):
        ws.write(0, col, header, header_style)
    
    # Set column widths
    ws.col(0).width = 5000  # User
    ws.col(1).width = 6000  # Email
    ws.col(2).width = 3000  # Role
    ws.col(3).width = 4000  # Branch
    ws.col(4).width = 4000  # Progress Status
    ws.col(5).width = 3000  # Progress %
    ws.col(6).width = 2500  # Score
    ws.col(7).width = 3000  # Time Spent
    ws.col(8).width = 3500  # Enrolled Date
    ws.col(9).width = 3500  # Last Accessed
    ws.col(10).width = 3500  # Completion Date
    
    # Write data rows
    for row, learner in enumerate(learners, start=1):
        ws.write(row, 0, learner.get_full_name() if hasattr(learner, 'get_full_name') else learner.username)
        ws.write(row, 1, learner.email if hasattr(learner, 'email') else '-')
        ws.write(row, 2, learner.role.title() if hasattr(learner, 'role') else '-')
        ws.write(row, 3, learner.branch.name if hasattr(learner, 'branch') and learner.branch else '-')
        ws.write(row, 4, getattr(learner, 'status', '-'))
        ws.write(row, 5, f"{getattr(learner, 'progress_percentage', 0)}%")
        ws.write(row, 6, str(getattr(learner, 'score', '-')) if getattr(learner, 'score', None) is not None else '-')
        ws.write(row, 7, getattr(learner, 'time_spent_formatted', '-'))
        
        # Enrolled date
        if hasattr(learner, 'enrolled_date') and learner.enrolled_date:
            ws.write(row, 8, learner.enrolled_date.strftime('%d/%m/%Y'), date_style)
        else:
            ws.write(row, 8, '-')
        
        # Last accessed
        if hasattr(learner, 'last_accessed') and learner.last_accessed:
            ws.write(row, 9, learner.last_accessed.strftime('%d/%m/%Y'), date_style)
        else:
            ws.write(row, 9, '-')
        
        # Completion date
        if hasattr(learner, 'completion_date') and learner.completion_date:
            ws.write(row, 10, learner.completion_date.strftime('%d/%m/%Y'), date_style)
        else:
            ws.write(row, 10, '-')
    
    # Set response headers for Excel download
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    course_name = ''.join(c for c in course.title if c.isalnum() or c == ' ').replace(' ', '_')
    filename = f"course_users_{course_name}_{timestamp}.xls"
    
    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Save workbook to response
    wb.save(response)
    return response

class BranchReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/branch_report.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has view_reports capability
        user = request.user
        
        # Check if user is authenticated first
        if not user.is_authenticated:
            return redirect('login')
            
        if not (user.is_superuser or user.role in ['globaladmin', 'superadmin']):
            # Check if user has a system role with report access by default
            if user.role in ['admin', 'instructor']:
                return super().dispatch(request, *args, **kwargs)
                
            try:
                user_roles = UserRole.objects.filter(user=user)
                has_view_reports = False
                for user_role in user_roles:
                    has_view_reports = has_view_reports or RoleCapability.objects.filter(
                        role=user_role.role,
                        capability='view_reports'
                    ).exists()
                if not has_view_reports:
                    messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
                    return redirect('users:role_based_redirect')
            except Exception as e:
                messages.error(request, f"Error checking permissions: {str(e)}")
                return redirect('users:role_based_redirect')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get filter parameters
        search_query = self.request.GET.get('search', '')
        business_id = self.request.GET.get('business')
        branch_id = self.request.GET.get('branch')
        page = self.request.GET.get('page', 1)

        # Get filter context for the template
        filter_context = get_report_filter_context(user, self.request)
        
        # Get branches the user has access to using role-based filtering
        branches = Branch.objects.all()
        branches = apply_role_based_filtering(user, branches, business_id, branch_id, self.request)
        
        # Apply search filter if provided
        if search_query:
            branches = branches.filter(Q(name__icontains=search_query) | 
                                    Q(description__icontains=search_query))
        
        # Order the queryset to avoid pagination warnings
        branches = branches.order_by('name')
        
        # Annotate branches with statistics
        branches = branches.annotate(
            users_count=Count('users', filter=Q(users__role='learner'), distinct=True),
            courses_count=Count('courses', distinct=True),
            enrollments_count=Count('users__courseenrollment', distinct=True),
            completed_enrollments=Count('users__courseenrollment', 
                                      filter=Q(users__courseenrollment__completed=True), 
                                      distinct=True)
        ).annotate(
            completion_rate=Case(
                When(enrollments_count=0, then=Value(0.0)),
                default=ExpressionWrapper(
                    (F('completed_enrollments') * 100.0) / F('enrollments_count'),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )
        )
        
        # Calculate overall statistics
        total_enrollments = CourseEnrollment.objects.filter(
            user__branch__in=branches
        ).count()
        completed_courses = CourseEnrollment.objects.filter(
            user__branch__in=branches,
            completed=True
        ).count()
        
        completion_rate = (completed_courses / total_enrollments * 100) if total_enrollments > 0 else 0
        
        # Paginate results
        paginator = Paginator(branches, 10)  # Show 10 branches per page
        try:
            branches_page = paginator.page(page)
        except PageNotAnInteger:
            branches_page = paginator.page(1)
        except EmptyPage:
            branches_page = paginator.page(paginator.num_pages)
        
        # Define breadcrumbs
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('reports:overview'), 'label': 'Reports', 'icon': 'fa-chart-bar'},
            {'label': 'Branch Reports', 'icon': 'fa-code-branch'}
        ]
        
        # Note: filter_context includes 'branches' for the filter dropdown
        # We'll use 'report_branches' for the actual data being reported on
        context.update({
            'report_branches': branches_page,
            'search_query': search_query,
            'completion_rate': round(completion_rate, 1),
            'completed_courses': completed_courses,
            'courses_in_progress': CourseEnrollment.objects.filter(
                user__branch__in=branches,
                completed=False, 
                last_accessed__isnull=False,
                last_accessed__gte=timezone.now() - timedelta(days=30)
            ).count(),
            'courses_not_passed': CourseEnrollment.objects.filter(
                user__branch__in=branches,
                completed=False,
                last_accessed__isnull=False,
                last_accessed__lt=timezone.now() - timedelta(days=30)
            ).count(),
            'courses_not_started': CourseEnrollment.objects.filter(
                user__branch__in=branches,
                completed=False,
                last_accessed__isnull=True
            ).count(),
            'training_time': "0h 0m",  # Placeholder
            'breadcrumbs': breadcrumbs,
            **filter_context  # Add filter context (businesses, branches for filter, show_*_filter flags)
        })
        return context

class CourseReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/course_report.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has view_reports capability
        user = request.user
        
        # Check if user is authenticated first
        if not user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # Let LoginRequiredMixin handle redirect
        
        if not (user.is_superuser or user.role in ['globaladmin', 'superadmin']):
            # Check if user has a system role with report access by default
            if user.role in ['admin', 'instructor']:
                return super().dispatch(request, *args, **kwargs)
                
            try:
                user_roles = UserRole.objects.filter(user=user)
                has_view_reports = False
                for user_role in user_roles:
                    has_view_reports = has_view_reports or RoleCapability.objects.filter(
                        role=user_role.role,
                        capability='view_reports'
                    ).exists()
                if not has_view_reports:
                    messages.error(request, "You don't have permission to access reports. This section is restricted to users with report viewing permissions.")
                    return redirect('users:role_based_redirect')
            except Exception as e:
                messages.error(request, f"Error checking permissions: {str(e)}")
                return redirect('users:role_based_redirect')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get courses the user has access to
        courses = Course.objects.all()
        courses = BranchFilterManager.filter_queryset_by_branch(user, courses)
        
        # Get pagination parameters
        page = self.request.GET.get('page', 1)
        per_page = min(int(self.request.GET.get('per_page', 10)), 50)  # Cap at 50 per page
        
        # Apply filters if provided
        search_query = self.request.GET.get('search', '')
        category_id = self.request.GET.get('category', '')
        
        if search_query:
            courses = courses.filter(Q(title__icontains=search_query) | 
                                    Q(description__icontains=search_query))
        
        if category_id:
            try:
                category_id = int(category_id)
                courses = courses.filter(categories__id=category_id)
            except (ValueError, TypeError):
                pass
        
        # Order the queryset to avoid pagination warnings
        courses = courses.order_by('title')
        
        # Get categories for filter dropdown
        categories = CourseCategory.objects.all()
        
        # Paginate results
        paginator = Paginator(courses, per_page)
        try:
            courses_page = paginator.page(page)
        except PageNotAnInteger:
            courses_page = paginator.page(1)
        except EmptyPage:
            courses_page = paginator.page(paginator.num_pages)
        
        context.update({
            'courses': courses_page,
            'categories': categories,
            'search_query': search_query,
            'selected_category': category_id,
            'per_page': per_page,
            'page_obj': courses_page,
        })
        return context

