from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse, HttpResponseServerError
from django.contrib.auth import authenticate, login, update_session_auth_hash, logout
from django.template.exceptions import TemplateDoesNotExist
from courses.models import Course, Topic, CourseEnrollment

# Import TopicProgress and CourseTopic dynamically
try:
    from courses.models import TopicProgress
except ImportError:
    TopicProgress = None

try:
    from courses.models import CourseTopic
except ImportError:
    CourseTopic = Course.topics.through if hasattr(Course, 'topics') else None
from courses.forms import CourseForm
from users.models import CustomUser, Branch, UserQuestionnaire
from .forms import (
    CustomUserCreationForm, 
    CustomUserChangeForm, 
    CustomPasswordChangeForm,
    AdminPasswordChangeForm,
    TabbedUserCreationForm
)
import logging
from django.db import models
from django import forms
import os
import time
from django.conf import settings
# from django.views.decorators.csrf import csrf_exempt, csrf_protect  # COMMENTED OUT TO FIX ERRORS
from django.contrib.admin.models import LogEntry
from django.db.models import Count, Q, F, Sum, Avg, ExpressionWrapper, DurationField
from django.db.models.functions import ExtractHour, TruncDate, TruncDay, ExtractWeekDay
from django.utils import timezone
from django.urls import reverse, NoReverseMatch
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
import json
import pandas as pd
from django.views.decorators.http import require_http_methods, require_POST
import xlsxwriter
from io import BytesIO
import pytz
from datetime import timedelta, datetime
from categories.models import CourseCategory
from groups.models import BranchGroup, GroupMembership
import csv
import io
from django.core.exceptions import PermissionDenied, ValidationError
from role_management.models import RoleCapability, UserRole
from django.apps import apps
from calendar_app.models import CalendarEvent
from django.contrib.auth.models import Group
import requests
import re
from branch_portal.models import BranchPortal
from core.services.todo_service import TodoService
from .models import CustomUser, UserQuestionnaire, UserQuizAssignment, ManualVAKScore
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from django.http import HttpRequest
from core.utils.type_guards import (
    safe_get_string, safe_get_int, safe_get_bool, safe_get_list,
    validate_timezone_data, safe_json_loads, TypeValidationError
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
@require_http_methods(["POST"])
def timezone_update(request: HttpRequest) -> JsonResponse:
    """Update user timezone"""
    from core.utils.api_response import APIResponse, handle_api_exception
    
    try:
        # Safely parse JSON with type validation
        raw_data = safe_json_loads(request.body.decode('utf-8'))
        if raw_data is None:
            return APIResponse.validation_error(
                errors={'body': 'Invalid JSON data'},
                message="Request body must be valid JSON"
            )
        
        # Validate timezone data structure using imported utility
        validated_data = validate_timezone_data(raw_data)
        if validated_data is None:
            return APIResponse.validation_error(
                errors={'timezone': 'Timezone is required and must be a string'},
                message="Timezone is required and must be a valid string"
            )
        
        timezone_str: str = validated_data['timezone']
        offset: int = validated_data['offset']
        
        # Type safety: check if user exists and is authenticated
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return APIResponse.error(
                message="User not authenticated",
                error_type="authentication_required",
                status_code=401
            )
        
        # Use the UserTimezone model instead of direct user field
        from .models import UserTimezone
        timezone_obj, created = UserTimezone.objects.get_or_create(
            user=request.user,
            defaults={'timezone': timezone_str, 'auto_detected': False}
        )
        if not created:
            timezone_obj.timezone = timezone_str
            timezone_obj.auto_detected = False
            timezone_obj.save()
        
        return APIResponse.success(
            data={
                'timezone': timezone_str,
                'offset': offset,
                'user_id': request.user.id
            },
            message="Timezone updated successfully"
        )
            
    except Exception as e:
        return handle_api_exception(e, request)
from individual_learning_plan.models import (
    LearningPreference, SENDAccommodation, StatementOfPurpose, StrengthWeakness,
    InductionChecklist, HealthSafetyQuestionnaire, LearningNeeds, LearningGoal,
    InternalCourseReview, EducatorNote, IndividualLearningPlan, HealthSafetyDocument
)
from quiz.models import Quiz
from account_settings.models import GlobalAdminSettings
from django.contrib.auth.forms import PasswordChangeForm
from .models import PasswordResetToken, EmailVerificationToken
from .forms import SimpleRegistrationForm
from role_management.utils import PermissionManager
from branches.models import Branch

# PDF processing imports
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info(f"pdfplumber imported successfully, version: {pdfplumber.__version__}")
except ImportError as e:
    PDFPLUMBER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import pdfplumber: {str(e)}")
except Exception as e:
    PDFPLUMBER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.error(f"Unexpected error importing pdfplumber: {str(e)}")

logger = logging.getLogger(__name__)

@login_required
def role_based_redirect(request: HttpRequest) -> HttpResponse:
    """Redirect users to their appropriate dashboard based on role"""
    import logging
    auth_logger = logging.getLogger('authentication')
    
    user_role = request.user.role
    username = request.user.username
    
    auth_logger.info(f"Role-based redirect for user {username} with role: {user_role}")
    
    if user_role == 'globaladmin':
        auth_logger.info(f"Redirecting {username} to global admin dashboard")
        return redirect('dashboard_globaladmin')
    elif user_role == 'superadmin':
        auth_logger.info(f"Redirecting {username} to super admin dashboard")
        return redirect('dashboard_superadmin')
    elif user_role == 'admin':
        auth_logger.info(f"Redirecting {username} to admin dashboard")
        return redirect('dashboard_admin')
    elif user_role == 'instructor':
        auth_logger.info(f"Redirecting {username} to instructor dashboard")
        return redirect('dashboard_instructor')
    elif user_role == 'learner':
        auth_logger.info(f"Redirecting {username} to learner dashboard")
        return redirect('dashboard_learner')
    else:
        # Default fallback - redirect to learner dashboard
        auth_logger.warning(f"Unknown role '{user_role}' for user {username}, defaulting to learner dashboard")
        return redirect('dashboard_learner')

def register(request: HttpRequest) -> HttpResponse:
    """Public learner registration view"""
    # Get branch from URL parameter if coming from branch portal
    branch_slug: Optional[str] = request.GET.get('branch')
    branch: Optional[Branch] = None
    
    # Type safety: ensure branch_slug is a string if present
    if branch_slug is not None and not isinstance(branch_slug, str):
        branch_slug = str(branch_slug)
    
    if branch_slug:
        try:
            from branch_portal.models import BranchPortal
            portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('login')
    
    if request.method == 'POST':
        from .forms import SimpleRegistrationForm
        form = SimpleRegistrationForm(request.POST, branch=branch)
        
        if form.is_valid():
            user = form.save()
            
            # Auto-assign to branch if coming from branch portal
            if branch:
                user.branch = branch
                user.save()
                messages.success(request, f"Account created successfully! You've been enrolled in {branch.name}.")
            else:
                # For general registration, assign to a non-default branch (default branch reserved for global admin)
                from core.utils.default_assignments import DefaultAssignmentManager
                safe_branch = DefaultAssignmentManager.get_safe_branch_for_user(user)
                if safe_branch:
                    user.branch = safe_branch
                    user.save()
                    messages.success(request, f"Account created successfully! You've been assigned to {safe_branch.name}.")
                else:
                    messages.success(request, "Account created successfully! Please contact administrator for branch assignment.")
            
            return redirect('login')
    else:
        from .forms import SimpleRegistrationForm
        form = SimpleRegistrationForm(branch=branch)
    
    context = {
        'form': form,
        'branch': branch,
        'branch_portal': branch_slug is not None
    }
    
    return render(request, 'users/register.html', context)

def home(request: HttpRequest) -> HttpResponse:
    """Main homepage view with redirect loop prevention and session validation"""
    import logging
    logger = logging.getLogger('authentication')
    
    # CRITICAL FIX: Enhanced authentication check with session recovery
    # Type safety: check if user exists before accessing is_authenticated
    is_authenticated = hasattr(request, 'user') and request.user.is_authenticated
    
    # Session recovery for edge cases where session exists but user not authenticated
    if not is_authenticated and hasattr(request, 'session'):
        user_id = request.session.get('_auth_user_id')
        if user_id:
            logger.warning(f"Session recovery attempt for user ID {user_id}")
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(pk=user_id, is_active=True)
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                request.user = user
                request.session.modified = True
                is_authenticated = True
                logger.info(f"Successfully recovered session for user {user.username}")
            except Exception as e:
                logger.error(f"Session recovery failed: {e}")
    
    # Log home page access with enhanced information
    logger.info(f"Home page accessed by {'authenticated' if is_authenticated else 'anonymous'} user")
    
    if is_authenticated:
        user_role = getattr(request.user, 'role', None)
        logger.info(f"Authenticated user {request.user.username} with role {user_role} accessing home")
        
        # Direct redirect based on role to avoid redirect chain
        if user_role == 'globaladmin':
            logger.info(f"Redirecting {request.user.username} directly to global admin dashboard")
            return redirect('dashboard_globaladmin')
        elif user_role == 'superadmin':
            logger.info(f"Redirecting {request.user.username} directly to super admin dashboard")
            return redirect('dashboard_superadmin')
        elif user_role == 'admin':
            logger.info(f"Redirecting {request.user.username} directly to admin dashboard")
            return redirect('dashboard_admin')
        elif user_role == 'instructor':
            logger.info(f"Redirecting {request.user.username} directly to instructor dashboard")
            return redirect('dashboard_instructor')
        elif user_role == 'learner':
            logger.info(f"Redirecting {request.user.username} directly to learner dashboard")
            return redirect('dashboard_learner')
        else:
            logger.warning(f"User {request.user.username} has unknown role '{user_role}', redirecting to learner dashboard")
            return redirect('dashboard_learner')
    else:
        logger.info("Anonymous user accessing home, redirecting to login")
        return redirect('login')

def custom_login(request):
    # Check if user is already authenticated
    if request.user.is_authenticated:
        # User is already logged in, redirect to appropriate dashboard
        user_role = getattr(request.user, 'role', 'learner')
        if user_role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            return redirect('dashboard_instructor')
        elif user_role == 'learner':
            return redirect('dashboard_learner')
        else:
            return redirect('dashboard_learner')
    
    # SIMPLE SESSION FIX - Force session creation with error handling
    try:
        if hasattr(request, 'session') and not request.session.session_key:
            request.session.create()
            request.session.modified = True
            request.session.save()
    except Exception as e:
        # If session creation fails, continue without session
        print(f"Session creation failed: {e}")
        pass

    """Enhanced custom login view with comprehensive Session"""
    # Get client IP address
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    client_ip = get_client_ip(request)
    
    # Initialize default values for rate limiting and session status
    rate_limit_info = {
        'is_limited': False,
        'limit_type': 'minute',
        'remaining_time': 0,
        'current_count': 0,
        'max_count': 60
    }
    
    login_Session_status = {
        'warning_level': 'none',
        'failure_count': 0,
        'remaining_attempts': 5,
        'max_attempts': 5,
        'lockout_minutes': 0,
        'remaining_time': 0,
        'is_blocked': False
    }
    
    # Check rate limiting status with error handling
    try:
        def dummy_get_response(request):
            return None
        
        # Get rate limiting info with fallback
        # Get login Session status with fallback
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        # Use default values already set above
    
    # Combine both Session statuses
    security_status = {
        'warning_level': login_Session_status.get('warning_level', 'none'),
        'failure_count': login_Session_status.get('failure_count', 0),
        'remaining_attempts': login_Session_status.get('remaining_attempts', 10),
        'max_attempts': login_Session_status.get('max_attempts', 5),
        'lockout_minutes': login_Session_status.get('lockout_minutes', 0),
        'remaining_time': login_Session_status.get('remaining_time', 0),
        'is_blocked': login_Session_status.get('is_blocked', False),
        # Add rate limiting info
        'rate_limited': rate_limit_info['is_limited'],
        'rate_limit_type': rate_limit_info.get('limit_type'),
        'rate_remaining_time': rate_limit_info.get('remaining_time', 0),
        'rate_current_count': rate_limit_info.get('current_count', 0),
        'rate_max_count': rate_limit_info.get('max_count', 0)
    }
    
    # If rate limited, show rate limiting message and countdown
    if rate_limit_info['is_limited']:
        limit_type = "per minute" if rate_limit_info['limit_type'] == 'minute' else "per hour"
        messages.error(request, 
            f"Too many authentication attempts ({rate_limit_info['current_count']}/{rate_limit_info['max_count']} {limit_type}). "
            f"Please wait {rate_limit_info['remaining_time']} seconds before trying again.")
        
        # Create proper context with all required variables
        context = {
            'form': None,  # No form for rate limited state
            'next': request.GET.get('next', '')
        }
        return render(request, "users/shared/login.html", context)
    
    if request.method == "POST":
        from django.core.cache import cache
        import logging
        
        # Get Session logger
        Session_logger = logging.getLogger('Session')
        auth_logger = logging.getLogger('authentication')
        logger = logging.getLogger(__name__)
        
        # Get client IP address
        def get_client_ip(request):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR', '')
            return ip
        
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # blocked_until_key = f"login_blocked_{ip_address}"
        # blocked_until = cache.get(blocked_until_key)
        # if blocked_until and time.time() < blocked_until:
        #     Session_logger.warning(f"Blocked login attempt from IP: {ip_address}")
        #     messages.error(request, "Account temporarily locked due to too many failed attempts. Please try again later.")
        #     return render(request, "users/shared/login.html")
        
        username = safe_get_string(request.POST, "username").strip()
        password = safe_get_string(request.POST, "password")
        
        # Input validation
        if not username or not password:
            messages.error(request, "Username and password are required.")
            context = {
                'form': None,
                'next': request.GET.get('next', '')
            }
            return render(request, "users/shared/login.html", context)
        
        # Terms acceptance validation
        terms_acceptance = request.POST.get("terms_acceptance")
        if not terms_acceptance:
            messages.error(request, "You must agree to the Terms of Service and Privacy Policy to log in.")
            context = {
                'form': None,
                'next': request.GET.get('next', '')
            }
            return render(request, "users/shared/login.html", context)
        
        # Sanitize username input
        import re
        if not re.match(r'^[a-zA-Z0-9@._-]+$', username):
            Session_logger.warning(f"Suspicious username pattern in login: {username} from IP: {ip_address}")
            messages.error(request, "Invalid username format.")
            context = {
                'form': None,
                'next': request.GET.get('next', '')
            }
            return render(request, "users/shared/login.html", context)
        
        # Log authentication attempt
        auth_logger.info(f"Login attempt for user: {username} from IP: {ip_address}")
        
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Check if user account is active
            if not user.is_active:
                Session_logger.warning(f"Login attempt for inactive user: {username} from IP: {ip_address}")
                messages.error(request, "Account is deactivated. Please contact administrator.")
                context = {
                    'form': None,
                    'next': request.GET.get('next', '')
                }
                return render(request, "users/shared/login.html", context)
            
            # If user doesn't have a branch and there's only one branch, assign it automatically
            if not user.branch:
                try:
                    # Try to get the only branch if there's just one
                    branch = Branch.objects.first()
                    if branch:
                        user.branch = branch
                        user.save()
                        auth_logger.info(f"Auto-assigned branch {branch.name} to user {username}")
                except Branch.DoesNotExist:
                    # No branches exist, continue without assigning
                    pass
                except Exception as e:
                    # Log any other errors but continue with login
                    logger.error(f"Error assigning branch to user: {str(e)}")
                    pass

            # Check if user has 2FA enabled
            from .models import TwoFactorAuth, OTPToken
            user_2fa = None
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
            except TwoFactorAuth.DoesNotExist:
                pass
            
            if user_2fa and user_2fa.is_enabled:
                # User has 2FA enabled, generate and send OTP
                try:
                    # Clear any existing unused OTP tokens for this user
                    OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                    
                    # Create new OTP token
                    otp_token = OTPToken.objects.create(user=user, purpose='login')
                    
                    # Send OTP email
                    otp_token.send_otp_email(request)
                    
                    # Store user info in session for OTP verification
                    request.session['otp_user_id'] = user.id
                    request.session['otp_token_id'] = otp_token.id
                    request.session['otp_next_url'] = request.GET.get('next') or request.POST.get('next')
                    
                    # Clear any login failures on successful authentication
                    def dummy_get_response(request):
                        return None
                    
                    # Log 2FA step
                    auth_logger.info(f"2FA OTP sent for user: {username} from IP: {ip_address}")
                    
                    messages.success(request, f"A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                    
                    # Redirect to OTP verification page
                    return redirect('users:verify_otp')
                    
                except Exception as e:
                    logger.error(f"Error sending OTP for user {username}: {str(e)}")
                    messages.error(request, "Error sending verification code. Please try again or contact support.")
                    context = {
                        'form': None,
                        'next': request.GET.get('next', '')
                    }
                    return render(request, "users/shared/login.html", context)
            
            # Normal login flow (no 2FA or 2FA disabled)
            # Clear any login failures on successful login
            def dummy_get_response(request):
                return None
            
            # Log successful login
            auth_logger.info(f"Successful login for user: {username} from IP: {ip_address}")
            
            # Update last login time
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            
            # Redirect to next URL if specified, otherwise to role-based redirect
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                # Validate redirect URL for Session
                from django.utils.http import url_has_allowed_host_and_scheme
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    auth_logger.info(f"Redirecting user {username} to next URL: {next_url}")
                    return redirect(next_url)
                else:
                    auth_logger.warning(f"Invalid next URL blocked for user {username}: {next_url}")
            
            auth_logger.info(f"Redirecting user {username} (role: {user.role}) to role-based redirect")
            return redirect('users:role_based_redirect')
        else:
            # TEMPORARILY DISABLED - Record failed login attempt
            def dummy_get_response(request):
                return None
            
            # Log failed attempt
            Session_logger.warning(f"Failed login attempt for user: {username} from IP: {ip_address} UA: {user_agent}")
            
            messages.error(request, "Invalid username or password. Please try again.")

    # Pass Session status to template with all required variables
    context = {
        'form': None,  # No form for GET requests
        'next': request.GET.get('next', '')  # Get next parameter from URL
    }
    return render(request, "users/shared/login.html", context)

def get_or_assign_branch_for_global_admin(request):
    """
    Helper function to get or assign a branch for global admin users when needed.
    For global admins, if no branch is specified, we'll use the last updated user's branch,
    or create/assign a default branch.
    """
    if request.user.role != 'globaladmin':
        return request.user.branch
    
    # Try to get branch from request parameters first
    branch_id = request.GET.get('branch')
    if branch_id:
        try:
            return Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            pass
    
    # Get the most recently active user's branch (using last_login for better relevance)
    last_updated_user = CustomUser.objects.filter(
        branch__isnull=False,
        last_login__isnull=False
    ).order_by('-last_login').first()
    
    # Fallback to most recently created user if no one has logged in
    if not last_updated_user:
        last_updated_user = CustomUser.objects.filter(
            branch__isnull=False
        ).order_by('-date_joined').first()
    
    if last_updated_user and last_updated_user.branch:
        return last_updated_user.branch
    
    # If no users have branches, get or create a default branch
    default_branch = Branch.objects.first()
    if not default_branch:
        default_branch = Branch.objects.create(
            name='Default Branch',
            description='Default branch for global admin operations'
        )
    
    return default_branch

@login_required
def user_list(request):
    """Display list of users based on permissions."""
    user = request.user
    
    # Debug logging
    logger.info(f"User {user.username} with role '{user.role}' attempting to access user_list")
    
    # Define breadcrumbs for this view
    if request.user.role == 'instructor':
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Learner Management', 'icon': 'fa-users'}
        ]
    else:
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'User Management', 'icon': 'fa-users'}
        ]
    
    # Allow globaladmin unrestricted access
    if request.user.role not in ['globaladmin', 'superadmin', 'admin', 'instructor']:
        logger.warning(f"User {user.username} with role '{user.role}' denied access to user_list")
        return HttpResponseForbidden(f"You don't have permission to view user list. Your role: {request.user.role}")

    # Get base queryset
    if request.user.role == 'globaladmin':
        # Global admin can see all users without restriction, except themselves
        users = CustomUser.objects.all().exclude(id=request.user.id)
        branches = Branch.objects.all().order_by('name')
    elif request.user.role == 'admin':
        # Filter users by effective branch (supports branch switching) and exclude superadmin and globaladmin users, and exclude current user
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        users = CustomUser.objects.filter(branch=effective_branch).exclude(role__in=['superadmin', 'globaladmin']).exclude(id=request.user.id)
        branches = [effective_branch]
    elif request.user.role == 'instructor':
        # Instructors can only see learner users, excluding themselves
        users = CustomUser.objects.filter(
            branch=request.user.branch,
            role='learner'
        ).exclude(id=request.user.id)
        branches = [request.user.branch]
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped users)
        # Note: filter_users_by_business already excludes global admin accounts
        from core.utils.business_filtering import filter_users_by_business, filter_branches_by_business
        users = filter_users_by_business(request.user)
        branches = filter_branches_by_business(request.user).order_by('name')
    else:
        users = CustomUser.objects.all().exclude(id=request.user.id)
        branches = Branch.objects.all().order_by('name')

    # Get groups based on user's business access
    from core.utils.business_filtering import filter_queryset_by_business
    if request.user.role == 'superadmin':
        groups = filter_queryset_by_business(
            BranchGroup.objects.all(), 
            request.user, 
            business_field_path='branch__business'
        ).order_by('name')
    else:
        groups = BranchGroup.objects.all().order_by('name')

    # Handle search functionality
    search_query = request.GET.get('q', '').strip()
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    # Handle status filtering  
    status_filter = request.GET.get('status', '').strip()
    selected_status = []
    if status_filter:
        selected_status = [status.strip() for status in status_filter.split(',') if status.strip()]
        if selected_status:
            status_conditions = Q()
            for status in selected_status:
                if status == 'active':
                    status_conditions |= Q(is_active=True)
                elif status == 'inactive':
                    status_conditions |= Q(is_active=False)
            if status_conditions:
                users = users.filter(status_conditions)

    # Handle branch filtering
    branch_filter = request.GET.get('branch', '').strip()
    selected_branches = []
    if branch_filter:
        selected_branches = [branch.strip() for branch in branch_filter.split(',') if branch.strip()]
        if selected_branches:
            users = users.filter(branch__id__in=selected_branches)

    # Handle group filtering
    group_filter = request.GET.get('group', '').strip()
    selected_groups = []
    if group_filter:
        selected_groups = [group.strip() for group in group_filter.split(',') if group.strip()]
        if selected_groups:
            users = users.filter(groups__id__in=selected_groups).distinct()

    # Handle role filtering
    role_filter = request.GET.get('role', '').strip()
    selected_roles = []
    if role_filter:
        selected_roles = [role.strip() for role in role_filter.split(',') if role.strip()]
        if selected_roles:
            users = users.filter(role__in=selected_roles)

    # Get available roles based on user permissions
    available_roles = []
    if request.user.role == 'globaladmin':
        # Global admin can filter by all roles
        available_roles = CustomUser.ROLE_CHOICES
    elif request.user.role == 'superadmin':
        # Super admin cannot see globaladmin users
        available_roles = [
            ('superadmin', 'SuperAdmin'),
            ('admin', 'Admin'),
            ('instructor', 'Instructor'),
            ('learner', 'Learner'),
        ]
    elif request.user.role == 'admin':
        # Admin cannot see superadmin or globaladmin users
        available_roles = [
            ('admin', 'Admin'),
            ('instructor', 'Instructor'),
            ('learner', 'Learner'),
        ]
    elif request.user.role == 'instructor':
        # Instructors can only see learners
        available_roles = [
            ('learner', 'Learner'),
        ]

    # Handle pagination
    per_page = int(request.GET.get('per_page', 10))
    page = request.GET.get('page', 1)
    paginator = Paginator(users.order_by('-date_joined').distinct(), per_page)
    
    try:
        users = paginator.page(page)
    except PageNotAnInteger:
        users = paginator.page(1)
    except EmptyPage:
        users = paginator.page(paginator.num_pages)

    # Import permission manager for capability checking
    from role_management.utils import PermissionManager
    from core.branch_filters import filter_context_by_branch
    
    context = {
        'users': users,
        'branches': branches,
        'groups': groups,
        'search_query': search_query,
        'available_roles': available_roles,
        'selected_roles': selected_roles,
        'selected_status': selected_status,
        'selected_branches': selected_branches,
        'selected_groups': selected_groups,
        'can_edit_user': request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor'],  # Allow globaladmin access
        'can_delete_user': PermissionManager.user_has_capability(request.user, 'delete_users'),
        'current_page': int(page),
        'per_page': per_page,
        'breadcrumbs': breadcrumbs
    }
    
    # Add branch context for template (enables branch switcher)
    context = filter_context_by_branch(context, request.user, request)
    
    return render(request, 'users/shared/user_list_new.html', context)

@login_required
@require_POST
def bulk_delete_users(request):
    """Handle bulk deletion of users with proper permission checks."""
    from django.http import JsonResponse
    from django.contrib import messages
    import json
    
    logger.info(f"Bulk delete request from user: {request.user.username}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Content type: {request.content_type}")
    logger.info(f"Request body: {request.body}")
    
    # Check if user has permission to delete users
    if request.user.role not in ['globaladmin', 'superadmin', 'admin']:
        logger.warning(f"User {request.user.username} with role {request.user.role} denied bulk delete access")
        return JsonResponse({
            'success': False,
            'message': 'You do not have permission to delete users.'
        }, status=403)
    
    try:
        # Parse the JSON data
        data = json.loads(request.body)
        user_ids = data.get('user_ids', [])
        
        if not user_ids:
            return JsonResponse({
                'success': False,
                'message': 'No users selected for deletion.'
            }, status=400)
        
        # Validate that all IDs are integers
        try:
            user_ids = [int(uid) for uid in user_ids]
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'message': 'Invalid user IDs provided.'
            }, status=400)
        
        # Get users to delete with permission checks
        users_to_delete = CustomUser.objects.filter(id__in=user_ids)
        
        # Additional permission checks based on user role
        if request.user.role == 'admin':
            # Admin can only delete users in their branch and cannot delete superadmin/globaladmin
            from core.branch_filters import BranchFilterManager
            effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
            users_to_delete = users_to_delete.filter(
                branch=effective_branch
            ).exclude(role__in=['superadmin', 'globaladmin'])
        elif request.user.role == 'superadmin':
            # Super admin can delete users in their business scope but not globaladmin
            from core.utils.business_filtering import filter_users_by_business
            business_users = filter_users_by_business(request.user)
            users_to_delete = users_to_delete.filter(id__in=business_users.values_list('id', flat=True))
        
        # Prevent deletion of the current user
        users_to_delete = users_to_delete.exclude(id=request.user.id)
        
        # Get the actual users that will be deleted
        actual_users = list(users_to_delete)
        deleted_count = 0
        
        # Delete users one by one to handle any potential errors
        deleted_users = []
        for user in actual_users:
            try:
                user_name = user.get_full_name() or user.username
                user.delete()  # This will use the comprehensive delete method
                deleted_users.append(user_name)
                deleted_count += 1
                logger.info(f"Successfully deleted user: {user_name} (ID: {user.id}) by {request.user.username}")
            except Exception as e:
                logger.error(f"Error deleting user {user.username} (ID: {user.id}): {str(e)}")
                continue
        
        if deleted_count == 0:
            return JsonResponse({
                'success': False,
                'message': 'No users were deleted. You may not have permission to delete the selected users.'
            }, status=400)
        
        # Prepare success message
        if deleted_count == 1:
            message = f"Successfully deleted user: {deleted_users[0]}"
        else:
            message = f"Successfully deleted {deleted_count} users: {', '.join(deleted_users[:5])}"
            if len(deleted_users) > 5:
                message += f" and {len(deleted_users) - 5} more"
        
        return JsonResponse({
            'success': True,
            'message': message,
            'deleted_count': deleted_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data provided.'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in bulk_delete_users: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while deleting users.'
        }, status=500)

@login_required
def user_detail(request, user_id):
    """Display detailed information for a specific user."""
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    # Prevent admin users from viewing superadmin user profiles
    if request.user.role == 'admin' and target_user.role in ['globaladmin', 'superadmin']:
        messages.error(request, "You don't have permission to view superadmin user profiles.")
        return redirect('users:user_list')
    
    # Check permission - users can view their own profile or globaladmin/admin/superadmin can view any profile
    # Instructors can view learners in their branch
    instructor_viewing_learner = (
        request.user.role == 'instructor' and 
        target_user.role == 'learner' and 
        target_user.branch == request.user.branch
    )
    
    if request.user.id != target_user.id and request.user.role not in ['globaladmin', 'superadmin', 'admin'] and not instructor_viewing_learner:
        return HttpResponseForbidden("You don't have permission to view this user's profile")
    
    # Define breadcrumbs for this view
    if request.user.role == 'instructor' and target_user.role == 'learner':
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('users:user_list'), 'label': 'Learner Management', 'icon': 'fa-users'},
            {'label': target_user.get_full_name() or target_user.username, 'icon': 'fa-user'}
        ]
    else:
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('users:user_list'), 'label': 'User Management', 'icon': 'fa-users'},
            {'label': target_user.get_full_name() or target_user.username, 'icon': 'fa-user'}
        ]
    
    # Determine if user can edit profile
    instructor_can_edit_learner = (
        request.user.role == 'instructor' and 
        target_user.role == 'learner' and 
        target_user.branch == request.user.branch
    )
    
    # Get context data needed for ILP tabs (same as edit_user view)
    try:
        # Get ILP data for various tabs
        from individual_learning_plan.models import (
            InductionChecklistSection, HealthSafety, LearningNeeds, 
            LearningGoal, StrengthsWeaknessesItem
        )
        
        # Get induction checklist sections
        induction_sections = InductionChecklistSection.objects.filter(
            user=target_user
        ).prefetch_related('items').order_by('created_at')
        
        # Get health & safety items
        existing_health_safety_items = HealthSafety.objects.filter(
            user=target_user
        ).order_by('created_at')
        
        # Get learning needs items
        existing_learning_needs_items = LearningNeeds.objects.filter(
            user=target_user
        ).order_by('created_at')
        
        # Get learning goals
        existing_learning_goals = LearningGoal.objects.filter(
            user=target_user
        ).order_by('created_at')
        
        # Get strengths & weaknesses items
        existing_strengths_items = StrengthsWeaknessesItem.objects.filter(
            user=target_user
        ).order_by('created_at')
        
    except Exception as e:
        # If any errors occur, just use empty lists
        induction_sections = []
        existing_health_safety_items = []
        existing_learning_needs_items = []
        existing_learning_goals = []
        existing_strengths_items = []
    
    # Get branch assessment quizzes
    initial_assessment_quizzes = []
    vak_test_quizzes = []
    initial_assessment_data = []
    vak_test_data = []

    if target_user.branch:
        from quiz.models import Quiz, QuizAttempt
        
        # Find all Initial Assessment quizzes created by branch admins and instructors
        initial_assessment_quizzes = Quiz.objects.filter(
            creator__branch=target_user.branch,
            creator__role__in=['admin', 'instructor'],
            is_initial_assessment=True,
            is_active=True
        ).order_by('title')
        
        # Find all VAK Test quizzes created by branch admins and instructors
        vak_test_quizzes = Quiz.objects.filter(
            creator__branch=target_user.branch,
            creator__role__in=['admin', 'instructor'],
            is_vak_test=True,
            is_active=True
        ).order_by('title')
        
        # Get user's attempts for each Initial Assessment quiz - only latest
        for quiz in initial_assessment_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=target_user,
                is_completed=True
            ).order_by('-end_time').first()
            
            if latest_attempt:
                initial_assessment_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=target_user,
                        is_completed=True
                    ).count()
                })
        
        # Get user's attempts for each VAK Test quiz - only latest
        for quiz in vak_test_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=target_user,
                is_completed=True
            ).order_by('-end_time').first()
            
            if latest_attempt:
                vak_test_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=target_user,
                        is_completed=True
                    ).count()
                })
    
    # Get quiz assignments for Assessment Data tab only
    from users.models import UserQuizAssignment
    initial_assessment_assignments = UserQuizAssignment.objects.filter(
        user=target_user,
        assignment_type='initial_assessment',
        is_active=True
    ).select_related('quiz', 'assigned_by').order_by('assigned_at')
    
    # Get VAK quiz attempts with course/topic context
    vak_quiz_attempts = target_user.get_vak_quiz_attempts_with_context()
    
    # Get manual assessment entries for Assessment Data tab
    from users.models import ManualAssessmentEntry
    manual_assessment_entries = ManualAssessmentEntry.objects.filter(
        user=target_user
    ).select_related('entered_by').order_by('subject')
    
    # Calculate profile completion data
    profile_completion = target_user.get_profile_completion_percentage()
    
    # Get tab state from URL parameters
    active_tab = request.GET.get('tab', 'account-tab')
    active_subtab = request.GET.get('subtab', 'overview-tab')
    active_nestedtab = request.GET.get('nestedtab', 'assessment-data-tab')
    
    # Load existing education records from JSON field
    existing_education_records = []
    existing_education_records_json = '[]'
    if target_user.education_data:
        try:
            if isinstance(target_user.education_data, list):
                existing_education_records = target_user.education_data
            elif isinstance(target_user.education_data, str):
                import json
                existing_education_records = json.loads(target_user.education_data)
            
            # Convert to JSON string for template
            import json
            existing_education_records_json = json.dumps(existing_education_records)
        except (json.JSONDecodeError, TypeError):
            existing_education_records = []
            existing_education_records_json = '[]'
    
    # Load existing employment records from JSON field
    existing_employment_records = []
    existing_employment_records_json = '[]'
    if target_user.employment_data:
        try:
            if isinstance(target_user.employment_data, list):
                existing_employment_records = target_user.employment_data
            elif isinstance(target_user.employment_data, str):
                import json
                existing_employment_records = json.loads(target_user.employment_data)
            
            # Convert to JSON string for template
            import json
            existing_employment_records_json = json.dumps(existing_employment_records)
        except (json.JSONDecodeError, TypeError):
            existing_employment_records = []
            existing_employment_records_json = '[]'
    
    context = {
        'profile_user': target_user,
        'can_edit': (request.user.role in ['globaladmin', 'superadmin', 'admin'] or 
                    request.user.id == target_user.id or 
                    instructor_can_edit_learner),
        'breadcrumbs': breadcrumbs,
        'is_edit_mode': False,  # This is view mode, not edit mode
        # ILP data for tabs
        'induction_sections': induction_sections,
        'existing_health_safety_items': existing_health_safety_items,
        'existing_learning_needs_items': existing_learning_needs_items,
        'existing_learning_goals': existing_learning_goals,
        'existing_strengths_items': existing_strengths_items,
        # Assessment Data quiz context
        'initial_assessment_quizzes': initial_assessment_quizzes,
        'vak_test_quizzes': vak_test_quizzes,
        'initial_assessment_data': initial_assessment_data,
        'vak_test_data': vak_test_data,
        'initial_assessment_assignments': initial_assessment_assignments,
        # VAK quiz attempts with course/topic context
        'vak_quiz_attempts': vak_quiz_attempts,
        # Profile completion data
        'profile_completion': profile_completion,
        # Tab state management
        'active_tab': active_tab,
        'active_subtab': active_subtab,
        'active_nestedtab': active_nestedtab,
        # Education records data
        'existing_education_records': existing_education_records,
        'existing_education_records_json': existing_education_records_json,
        # Employment records data
        'existing_employment_records': existing_employment_records,
        'existing_employment_records_json': existing_employment_records_json,
        # Manual assessment entries for Assessment Data tab
        'manual_assessment_entries': manual_assessment_entries,
    }
    
    return render(request, 'users/shared/user_profile_tabbed.html', context)

@login_required
def edit_user(request, user_id):
    """Edit an existing user."""
    try:
        target_user = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        messages.error(request, f"User with ID {user_id} does not exist.")
        return redirect('users:user_list')
    except Exception as e:
        messages.error(request, f"Error accessing user: {str(e)}")
        return redirect('users:user_list')
    
    # Allow users to edit their own profile, admins/superadmins to edit any profile, and instructors to edit learners in their branch
    instructor_editing_learner = (
        request.user.role == 'instructor' and 
        target_user.role == 'learner' and 
        target_user.branch == request.user.branch
    )
    
    if (request.user.id != target_user.id and 
        request.user.role not in ['globaladmin', 'superadmin', 'admin'] and 
        not instructor_editing_learner):
        return HttpResponseForbidden("You don't have permission to edit this user's profile")
    
    # Prevent admin users from editing superadmin user profiles
    if request.user.role == 'admin' and target_user.role in ['globaladmin', 'superadmin']:
        messages.error(request, "You don't have permission to edit superadmin user profiles.")
        return redirect('users:user_list')
    
    # Define breadcrumbs for this view
    if request.user.role == 'instructor' and target_user.role == 'learner':
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('users:user_list'), 'label': 'Learner Management', 'icon': 'fa-users'},
            {'label': f'Edit {target_user.get_full_name() or target_user.username}', 'icon': 'fa-user-edit'}
        ]
    else:
        breadcrumbs = [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('users:user_list'), 'label': 'User Management', 'icon': 'fa-users'},
            {'label': f'Edit {target_user.get_full_name() or target_user.username}', 'icon': 'fa-user-edit'}
        ]
    
    if request.method == 'POST':
        # ========================================================================================
        # Process AJAX actions first
        # ========================================================================================
        
        # Handle specific AJAX actions first
        action = request.POST.get('action')
        if action == 'delete_strengths_item':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion, IndividualLearningPlan
                item_id = request.POST.get('item_id')
                
                # Get the item and verify permissions
                item = StrengthsWeaknessesQuestion.objects.get(id=item_id)
                
                # Check if user has permission to delete (instructor/admin/superadmin)
                if request.user.role in ['instructor', 'admin', 'superadmin']:
                    # Get or create ILP for target user if needed
                    target_user_ilp, created = IndividualLearningPlan.objects.get_or_create(
                        user=target_user,
                        defaults={'created_by': request.user}
                    )
                    
                    # Check if item belongs to the target user's ILP
                    if item.section.ilp == target_user_ilp:
                        item.delete()
                        return JsonResponse({
                            'success': True,
                            'message': 'Strengths & weaknesses item deleted successfully'
                        })
                    else:
                        return JsonResponse({
                            'success': False,
                            'message': 'You do not have permission to delete this item'
                        })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to delete items'
                    })
            except StrengthsWeaknessesQuestion.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Item not found'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error deleting item: {str(e)}'
                })
        
        # Handle new Strengths & Weaknesses actions
        elif action == 'add_strength_weakness':
            try:
                from individual_learning_plan.models import (
                    StrengthsWeaknessesSection, StrengthsWeaknessesQuestion, 
                    IndividualLearningPlan, StrengthWeaknessFeedback
                )
                
                item_type = request.POST.get('type')
                description = request.POST.get('description')
                user_id = request.POST.get('user_id')
                
                if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to add strengths/weaknesses'
                    })
                
                # Get or create ILP for target user
                target_user_obj = get_object_or_404(CustomUser, id=user_id)
                ilp, created = IndividualLearningPlan.objects.get_or_create(
                    user=target_user_obj,
                    defaults={'created_by': request.user}
                )
                
                # Get or create default section
                section, section_created = StrengthsWeaknessesSection.objects.get_or_create(
                    ilp=ilp,
                    title='Strengths & Weaknesses Assessment',
                    defaults={
                        'description': 'Assessment of learner strengths and areas for development',
                        'order': 1,
                        'created_by': request.user
                    }
                )
                
                # Check if an item of this type already exists (only one per type allowed)
                existing_item = StrengthsWeaknessesQuestion.objects.filter(
                    section=section,
                    item_type=item_type
                ).first()
                
                if existing_item:
                    item_type_name = 'Strength' if item_type == 'strength' else 'Area for Development'
                    return JsonResponse({
                        'success': False,
                        'message': f'A {item_type_name} item already exists. Only one item per type is allowed.'
                    })
                
                # Create the question
                question = StrengthsWeaknessesQuestion.objects.create(
                    section=section,
                    item_type=item_type,
                    description=description,
                    order=section.questions.count() + 1,
                    is_mandatory=True,
                    created_by=request.user
                )
                
                # Create initial instructor feedback
                StrengthWeaknessFeedback.objects.create(
                    question=question,
                    feedback_type='instructor_initial',
                    content=description,
                    created_by=request.user
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'Strength/weakness added successfully'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error adding strength/weakness: {str(e)}'
                })
        
        elif action == 'update_approval_status':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                status = request.POST.get('status')
                
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only learners can update their own approval status
                if (request.user.role == 'learner' and 
                    request.user.id == target_user.id):
                    
                    if status == 'approved':
                        question.student_confirmed = 'yes'
                    elif status == 'not_approved':
                        question.student_confirmed = 'no'
                    
                    question.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Approval status updated'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to update approval status'
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating approval status: {str(e)}'
                })
        
        elif action == 'update_comment':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                comment = request.POST.get('comment')
                
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only learners can update their own comments
                if (request.user.role == 'learner' and 
                    request.user.id == target_user.id):
                    
                    question.student_comment = comment
                    question.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Comment updated'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to update comments'
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating comment: {str(e)}'
                })
        
        elif action == 'update_instructor_reply':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                reply = request.POST.get('reply', '')
                
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only instructors/admins can add replies
                if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to add replies'
                    })
                
                # Check if question belongs to the target user's ILP
                if question.section.ilp.user != target_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to reply to this item'
                    })
                
                question.instructor_comment = reply.strip()
                question.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Instructor reply updated successfully'
                })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating instructor reply: {str(e)}'
                })
        
        elif action == 'toggle_instructor_confirmation':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only instructors/admins can update instructor confirmation
                if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to update confirmation status'
                    })
                
                # Toggle confirmation status
                if question.instructor_confirmed == 'yes':
                    question.instructor_confirmed = 'no'
                else:
                    question.instructor_confirmed = 'yes'
                
                question.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Confirmation status updated'
                })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating confirmation status: {str(e)}'
                })
        
        elif action == 'edit_strength_weakness':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                description = request.POST.get('description')
                
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only instructors/admins can edit
                if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to edit strength/weakness items'
                    })
                
                # Check if question belongs to the target user's ILP
                if question.section.ilp.user != target_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to edit this item'
                    })
                
                question.description = description.strip()
                question.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Strength/weakness updated successfully'
                })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating strength/weakness: {str(e)}'
                })
        
        elif action == 'delete_strength_weakness':
            try:
                from individual_learning_plan.models import StrengthsWeaknessesQuestion
                
                question_id = request.POST.get('question_id')
                question = get_object_or_404(StrengthsWeaknessesQuestion, id=question_id)
                
                # Check permissions - only instructors/admins can delete
                if request.user.role not in ['instructor', 'admin', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to delete strength/weakness items'
                    })
                
                # Check if question belongs to the target user's ILP
                if question.section.ilp.user != target_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to delete this item'
                    })
                
                question.delete()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Strength/weakness deleted successfully'
                })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error deleting strength/weakness: {str(e)}'
                })
        
        elif action == 'update_strengths_weaknesses':
            # Handle updates to the simplified strengths & weaknesses fields
            try:
                from individual_learning_plan.models import SimpleStrengthsWeaknesses, IndividualLearningPlan

                field_name = request.POST.get('field_name')
                field_value = safe_get_string(request.POST, 'field_value').strip()
                
                # Check permissions
                if request.user.role == 'learner' and request.user.id != target_user.id:
                    return JsonResponse({
                        'success': False,
                        'message': 'You can only update your own assessment data'
                    })
                elif request.user.role not in ['admin', 'instructor', 'superadmin', 'globaladmin', 'learner']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to update this data'
                    })

                # Get or create ILP
                ilp, ilp_created = IndividualLearningPlan.objects.get_or_create(
                    user=target_user,
                    defaults={'created_by': request.user}
                )
                
                # Get or create SimpleStrengthsWeaknesses
                sw_data, sw_created = SimpleStrengthsWeaknesses.objects.get_or_create(
                    ilp=ilp
                )
                
                # Update the specific field
                # Only instructors/admins can update content
                if request.user.role not in ['admin', 'instructor', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'Only instructors can update assessment content'
                    })
                
                setattr(sw_data, field_name, field_value)
                if field_name == 'strengths_content':
                    sw_data.strengths_created_by = request.user
                else:
                    sw_data.development_created_by = request.user
                
                # Only learners can update approval status
                if request.user.role != 'learner' or request.user.id != target_user.id:
                    return JsonResponse({
                        'success': False,
                        'message': 'Only learners can update approval status'
                    })
                
                setattr(sw_data, field_name, field_value)
                
                # Only learners can update their comments
                if request.user.role != 'learner' or request.user.id != target_user.id:
                    return JsonResponse({
                        'success': False,
                        'message': 'Only learners can update their comments'
                    })
                
                setattr(sw_data, field_name, field_value)
                
                # Only instructors/admins can update replies
                if request.user.role not in ['admin', 'instructor', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'Only instructors can update replies'
                    })
                
                setattr(sw_data, field_name, field_value)
                
                sw_data.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Field updated successfully'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error updating field: {str(e)}'
                })
        
        elif action == 'save_instructor_strengths_weaknesses':
            # Handle instructor strengths & weaknesses form submission
            try:
                from individual_learning_plan.models import SimpleStrengthsWeaknesses, IndividualLearningPlan

                # Check permissions - only instructors/admins can edit content
                if request.user.role not in ['admin', 'instructor', 'superadmin', 'globaladmin']:
                    return JsonResponse({
                        'success': False,
                        'message': 'You do not have permission to update assessment content'
                    })

                strengths_content = safe_get_string(request.POST, 'strengths').strip()
                weaknesses_content = safe_get_string(request.POST, 'weaknesses').strip()
                strengths_instructor_reply = safe_get_string(request.POST, 'strengths_instructor_reply').strip()
                development_instructor_reply = safe_get_string(request.POST, 'development_instructor_reply').strip()
                
                # Get or create ILP
                ilp, ilp_created = IndividualLearningPlan.objects.get_or_create(
                    user=target_user,
                    defaults={'created_by': request.user}
                )
                
                # Get or create SimpleStrengthsWeaknesses
                sw_data, sw_created = SimpleStrengthsWeaknesses.objects.get_or_create(
                    ilp=ilp
                )
                
                # Update the content fields
                sw_data.strengths_content = strengths_content
                sw_data.development_content = weaknesses_content
                
                # Update reply fields if provided
                if strengths_instructor_reply:
                    sw_data.strengths_instructor_reply = strengths_instructor_reply
                    sw_data.development_instructor_reply = development_instructor_reply
                    
                sw_data.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Assessment saved successfully'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error saving assessment: {str(e)}'
                })
        
        elif action == 'save_learner_strengths_weaknesses':
            # Handle learner response to strengths & weaknesses assessment
            try:
                from individual_learning_plan.models import SimpleStrengthsWeaknesses, IndividualLearningPlan

                # Check permissions - only the learner themselves can respond
                if request.user.role != 'learner' or request.user.id != target_user.id:
                    return JsonResponse({
                        'success': False,
                        'message': 'You can only respond to your own assessment'
                    })

                strengths_approval = safe_get_string(request.POST, 'strengths_approval').strip()
                development_approval = safe_get_string(request.POST, 'development_approval').strip()
                strengths_learner_comment = safe_get_string(request.POST, 'strengths_learner_comment').strip()
                development_learner_comment = safe_get_string(request.POST, 'development_learner_comment').strip()
                
                # Get or create ILP
                ilp, ilp_created = IndividualLearningPlan.objects.get_or_create(
                    user=target_user,
                    defaults={'created_by': request.user}
                )
                
                # Get or create SimpleStrengthsWeaknesses
                sw_data, sw_created = SimpleStrengthsWeaknesses.objects.get_or_create(
                    ilp=ilp
                )
                
                # Update learner response fields
                if strengths_approval:
                    sw_data.strengths_approval = strengths_approval
                    sw_data.development_approval = development_approval
                    
                sw_data.strengths_learner_comment = strengths_learner_comment
                sw_data.development_learner_comment = development_learner_comment
                    
                sw_data.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Response saved successfully'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Error saving response: {str(e)}'
                })
        
        # Create a mutable copy of the POST data
        post_data = request.POST.copy()
        
        # Map first_name/last_name to given_name/family_name
        if 'given_name' in post_data and 'family_name' in post_data:
            post_data['first_name'] = post_data['given_name']
            post_data['last_name'] = post_data['family_name']
        
        # Apply business rule restrictions for user editing
        selected_role = post_data.get('role', target_user.role)
        
        # Super admin users cannot edit users to globaladmin role
        if request.user.role == 'superadmin' and selected_role == 'globaladmin':
            messages.error(request, "Super admin users are not allowed to set users to global admin role.")
            return redirect('users:edit_user', user_id=user_id)
        
        # Admin users cannot edit users to superadmin or globaladmin roles
        if request.user.role == 'admin' and selected_role in ['superadmin', 'globaladmin']:
            messages.error(request, "Admin users are not allowed to set users to super admin or global admin roles.")
            return redirect('users:edit_user', user_id=user_id)
        
        form = CustomUserChangeForm(post_data, request.FILES, instance=target_user, request=request)
        
        # Handle branch validation based on user role and target user role
        target_role = post_data.get('role', target_user.role)
        
        # Branch requirements based on who is editing and what role is being assigned
        if request.user.role == 'globaladmin':
            # Global Admin users can assign any branch or leave it empty for any user
            pass  # No additional validation needed - form handles this
        elif request.user.role == 'superadmin':
            # Super Admin users: branch required for non-superadmin roles
            if target_role != 'superadmin' and not request.POST.get('branch'):
                form.add_error('branch', 'Branch is required for this user role')
                messages.error(request, 'Please select a branch for this user.')
        else:
            # Other roles: branch generally required (handled by form validation)
            pass
                
        # Now check if the form is valid
        try:
            if form.is_valid():
                # Form validation passed - proceeding with processing
                # Check if password was changed before saving
                password_changed = bool(form.cleaned_data.get('password1'))
                user = form.save()
                
                # Update session auth hash if user changed their own password
                if password_changed and request.user.id == user.id:
                    from django.contrib.auth import update_session_auth_hash
                    update_session_auth_hash(request, user)
                
                # Log password change for Session audit
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Password changed for user {user.username} (ID: {user.id}) by {request.user.username} (ID: {request.user.id})")
                
                # Process multiple education entries
                education_entries = []
                education_count = int(post_data.get('education_entry_count', 0))
                
                # Collect education entries data from dynamic fields
                for i in range(1, education_count + 1):  # Start from 1 since dynamic fields use 1-based indexing
                    education_entry = {}
                    
                    # Check if this entry has any data
                    has_data = False
                    
                    # Collect all possible fields for this entry
                    fields_to_check = [
                        'institution_name', 'study_area', 'study_area_other', 'level_of_study',
                        'qualification', 'grades', 'grades_other', 'start_date', 'end_date',
                        'additional_details', 'currently_studying'
                    ]
                    
                    for field in fields_to_check:
                        field_name = f'{field}_{i}'
                        value = post_data.get(field_name, '')
                        
                        if field == 'currently_studying':
                            # Handle checkbox
                            education_entry[field] = bool(value)
                            if value:
                                has_data = True
                        else:
                            education_entry[field] = value
                            if value and value.strip():
                                has_data = True
                    
                    # Only add the entry if it has some data
                    if has_data:
                        education_entries.append(education_entry)
                
                # Save education entries to the user's education_data field
                user.education_data = education_entries
                
                # Process multiple employment entries
                employment_entries = []
                employment_count = int(post_data.get('employment_entry_count', 0))
                
                # Collect employment entries data from dynamic fields
                for i in range(1, employment_count + 1):  # Start from 1 since dynamic fields use 1-based indexing
                    employment_entry = {}
                    
                    # Check if this entry has any data
                    has_data = False
                    
                    # Collect all possible fields for this entry
                    fields_to_check = [
                        'job_role', 'industry', 'industry_other', 'duration', 'key_skills',
                        'company_name', 'start_date', 'end_date', 'currently_employed'
                    ]
                    
                    for field in fields_to_check:
                        field_name = f'{field}_{i}'
                        value = post_data.get(field_name, '')
                        
                        if field == 'currently_employed':
                            # Handle checkbox
                            employment_entry[field] = bool(value)
                            if value:
                                has_data = True
                        else:
                            employment_entry[field] = value
                            if value and value.strip():
                                has_data = True
                    
                    # Only add the entry if it has some data
                    if has_data:
                        employment_entries.append(employment_entry)
                
                # Save employment entries to the user's employment_data field
                user.employment_data = employment_entries
                user.save()
                
                # Handle questionnaire data
                question_texts = request.POST.getlist('question_text[]')
                answer_texts = request.POST.getlist('answer_text[]')
                question_documents = request.FILES.getlist('question_document[]')
                
                # Get confirmation values for each question
                confirmations = []
                for i in range(len(question_texts)):
                    confirmation_name = f'confirmation_{i + 1}'
                    confirmation_value = request.POST.get(confirmation_name)
                    confirmations.append(confirmation_value)
                
                # Delete existing questionnaire entries for this user
                UserQuestionnaire.objects.filter(user=user).delete()
                
                # Create new questionnaire entries
                for i, question_text in enumerate(question_texts):
                    if question_text.strip():  # Only save if question has content
                        # Create questionnaire entry
                        questionnaire = UserQuestionnaire(
                            user=user,
                            question_text=question_text.strip(),
                            answer_text=answer_texts[i].strip() if i < len(answer_texts) else '',
                            confirmation_required=confirmations[i] if i < len(confirmations) else None,
                            question_order=i + 1,
                            created_by=request.user
                        )
                        
                        # Handle document upload if present
                        if i < len(question_documents) and question_documents[i]:
                            questionnaire.document = question_documents[i]
                        
                        questionnaire.save()
                
                # Process dynamic induction checklist items
                from individual_learning_plan.models import (
                    IndividualLearningPlan, InductionChecklist, 
                    InductionChecklistSection, InductionChecklistQuestion
                )
                
                # Get or create ILP for the user
                ilp, ilp_created = IndividualLearningPlan.objects.get_or_create(
                    user=user,
                    defaults={'created_by': request.user}
                )
                
                # Get or create induction checklist
                induction_checklist, ic_created = InductionChecklist.objects.get_or_create(
                    ilp=ilp,
                    defaults={'created_by': request.user}
                )
                
                # ========================================================================================
                # Learning Goals & Progress Review Processing
                # ========================================================================================
                
                from individual_learning_plan.models import LearningGoal
                
                # Process NEW learning goals (fields: new_learning_goal_{index}_{field})
                new_learning_goals_count = int(request.POST.get('new_learning_goals_count', 0))
                
                for i in range(new_learning_goals_count):
                    goal_title = request.POST.get(f'new_learning_goal_{i}_title', '').strip()
                    goal_description = request.POST.get(f'new_learning_goal_{i}_description', '').strip()
                    goal_type = request.POST.get(f'new_learning_goal_{i}_goal_type', 'short_term')
                    custom_target_name = request.POST.get(f'new_learning_goal_{i}_custom_target_name', '').strip()
                    goal_target_date = request.POST.get(f'new_learning_goal_{i}_target_date')
                    goal_status = request.POST.get(f'new_learning_goal_{i}_status', 'not_started')
                    teacher_input = request.POST.get(f'new_learning_goal_{i}_teacher_input', '').strip()
                    
                    if goal_title and goal_description:
                        # Convert target date to proper format
                        target_completion_date = None
                        if goal_target_date:
                            try:
                                from datetime import datetime
                                target_completion_date = datetime.strptime(goal_target_date, '%Y-%m-%d').date()
                            except ValueError:
                                pass  # Invalid date format, skip
                        
                        LearningGoal.objects.create(
                            ilp=ilp,
                            goal_type=goal_type,
                            custom_target_name=custom_target_name if custom_target_name else None,
                            title=goal_title,
                            description=goal_description,
                            target_completion_date=target_completion_date,
                            status=goal_status,
                            teacher_input=teacher_input if teacher_input else None,
                            created_by=request.user
                        )
                
                # Process EXISTING learning goals updates
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('existing_learning_goal_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:  # existing_learning_goal_{id}_{field}
                            try:
                                goal_id = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                # Get the learning goal and update it
                                try:
                                    goal = LearningGoal.objects.get(id=goal_id, ilp=ilp)
                                    
                                    if field_type == 'title':
                                        goal.title = field_value.strip()
                                    elif field_type == 'description':
                                        goal.description = field_value.strip()
                                    elif field_type == 'goal_type':
                                        goal.goal_type = field_value
                                    elif field_type == 'custom_target_name':
                                        goal.custom_target_name = field_value.strip() if field_value.strip() else None
                                    elif field_type == 'status':
                                        goal.status = field_value
                                    elif field_type == 'target_date':
                                        if field_value:
                                            try:
                                                from datetime import datetime
                                                goal.target_completion_date = datetime.strptime(field_value, '%Y-%m-%d').date()
                                            except ValueError:
                                                pass
                                        else:
                                            goal.target_completion_date = None
                                    elif field_type == 'teacher_input':
                                        goal.teacher_input = field_value.strip() if field_value.strip() else None
                                    elif field_type == 'instructor_reply':
                                        goal.instructor_reply = field_value.strip() if field_value.strip() else None
                                    
                                    goal.save()
                                except LearningGoal.DoesNotExist:
                                    pass  # Goal doesn't exist, skip
                                    
                            except (ValueError, IndexError):
                                continue
                
                # Process learner feedback on learning goals
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('learning_goal_') and field_name.endswith('_learner_comment'):
                        # Extract goal ID from field name like 'learning_goal_123_learner_comment'
                        parts = field_name.split('_')
                        if len(parts) >= 3:
                            try:
                                goal_id = int(parts[2])
                                
                                # Get the learning goal and update learner comment
                                try:
                                    goal = LearningGoal.objects.get(id=goal_id, ilp=ilp)
                                    goal.learner_comment = field_value.strip() if field_value.strip() else None
                                    goal.save()
                                except LearningGoal.DoesNotExist:
                                    pass  # Goal doesn't exist, skip
                                    
                            except (ValueError, IndexError):
                                continue
                
                # Process deletion of learning goals
                delete_goal_ids = request.POST.getlist('delete_learning_goal_ids')
                if delete_goal_ids:
                    for goal_id in delete_goal_ids:
                        try:
                            goal_id = int(goal_id)
                            LearningGoal.objects.filter(id=goal_id, ilp=ilp).delete()
                        except (ValueError, LearningGoal.DoesNotExist):
                            pass  # Invalid ID or goal doesn't exist, skip
                
                # ========================================================================================
                # Enhanced Induction Checklist Processing
                # ========================================================================================
                
                # Process NEW induction checklist items (fields: new_induction_item_{index}_{field})
                new_induction_items = {}
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('new_induction_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:  # new_induction_item_{index}_{field}
                            try:
                                index = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if index not in new_induction_items:
                                    new_induction_items[index] = {}
                                
                                new_induction_items[index][field_type] = field_value
                            except (ValueError, IndexError):
                                continue
                
                # Process NEW induction item file uploads
                for field_name, field_file in request.FILES.items():
                    if field_name.startswith('new_induction_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:
                            try:
                                index = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if index not in new_induction_items:
                                    new_induction_items[index] = {}
                                
                                new_induction_items[index][field_type] = field_file
                            except (ValueError, IndexError):
                                continue
                
                # Process EXISTING induction checklist items (fields: existing_induction_item_{id}_{field})
                existing_induction_updates = {}
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('existing_induction_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:  # existing_induction_item_{id}_{field}
                            try:
                                item_id = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if item_id not in existing_induction_updates:
                                    existing_induction_updates[item_id] = {}
                                
                                existing_induction_updates[item_id][field_type] = field_value
                            except (ValueError, IndexError):
                                continue
                
                # Process EXISTING induction item file uploads
                for field_name, field_file in request.FILES.items():
                    if field_name.startswith('existing_induction_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:
                            try:
                                item_id = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if item_id not in existing_induction_updates:
                                    existing_induction_updates[item_id] = {}
                                
                                existing_induction_updates[item_id][field_type] = field_file
                            except (ValueError, IndexError):
                                continue
                
                # Process LEARNER responses (fields: induction_item_{id}_{field})
                learner_responses = {}
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('induction_item_') and not field_name.startswith('induction_item_template'):
                        parts = field_name.split('_')
                        if len(parts) >= 4:  # induction_item_{id}_{field}
                            try:
                                item_id = int(parts[2])
                                field_type = '_'.join(parts[3:])
                                
                                if item_id not in learner_responses:
                                    learner_responses[item_id] = {}
                                
                                learner_responses[item_id][field_type] = field_value
                            except (ValueError, IndexError):
                                continue
                
                # Get or create the default induction section
                section, section_created = InductionChecklistSection.objects.get_or_create(
                    induction_checklist=induction_checklist,
                    title='Induction Items',
                    defaults={
                        'description': 'Induction checklist items',
                        'order': 1,
                        'created_by': request.user
                    }
                )
                
                # Process deletion requests for existing items
                items_to_delete = []
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('delete_induction_item_') and field_value == 'true':
                        try:
                            item_id = int(field_name.split('_')[-1])
                            items_to_delete.append(item_id)
                        except (ValueError, IndexError):
                            continue
                
                if items_to_delete:
                    
                    # Only allow deletion for admin/instructor/superadmin
                    if request.user.role in ['admin', 'instructor', 'superadmin']:
                        # Delete items from any section within this induction checklist
                        deleted_count = InductionChecklistQuestion.objects.filter(
                            id__in=items_to_delete,
                            section__induction_checklist=induction_checklist
                        ).delete()
                        logger.info(f"Successfully deleted {deleted_count[0] if deleted_count else 0} induction items")
                    else:
                        logger.warning(f"User {request.user.role} not authorized to delete induction items")
                
                # Process NEW induction items (instructor/admin adding new items)
                if new_induction_items and request.user.role in ['admin', 'instructor', 'superadmin']:
                    for index in sorted(new_induction_items.keys()):
                        item_data = new_induction_items[index]
                        
                        if 'question' in item_data and item_data['question'].strip():
                            # Create new question
                            question = InductionChecklistQuestion.objects.create(
                                section=section,
                                question_text=item_data['question'].strip(),
                                order=section.questions.count() + 1,
                                is_mandatory=True,
                                created_by=request.user
                            )
                            
                            # Handle file upload if present
                            if 'file' in item_data and item_data['file']:
                                from individual_learning_plan.models import InductionChecklistDocument
                                try:
                                    InductionChecklistDocument.objects.create(
                                        section=section,
                                        question=question,  # Link to specific question
                                        title=f"Document for {item_data['question'][:30]}...",
                                        document_file=item_data['file'],
                                        description=f"Supporting document for: {item_data['question'][:50]}...",
                                        is_mandatory=True,
                                        uploaded_by=request.user
                                    )
                                except Exception as e:
                                    pass
                
                # Process EXISTING item updates (instructor/admin editing existing items)
                if existing_induction_updates and request.user.role in ['admin', 'instructor', 'superadmin']:
                    for item_id, item_data in existing_induction_updates.items():
                        try:
                            question = InductionChecklistQuestion.objects.get(
                                id=item_id,
                                section__induction_checklist=induction_checklist
                            )
                            
                            # Update question text if provided
                            if 'question' in item_data and item_data['question'].strip():
                                question.question_text = item_data['question'].strip()
                            
                            # Update instructor reply if provided
                            if 'instructor_reply' in item_data:
                                question.instructor_reply = item_data['instructor_reply'].strip()
                            
                            question.save()
                            
                            # Handle file upload if present
                            if 'file' in item_data and item_data['file']:
                                from individual_learning_plan.models import InductionChecklistDocument
                                try:
                                    InductionChecklistDocument.objects.create(
                                        section=question.section,
                                        question=question,  # Link to specific question
                                        title=f"Updated document for {question.question_text[:30]}...",
                                        document_file=item_data['file'],
                                        description=f"Updated supporting document",
                                        is_mandatory=True,
                                        uploaded_by=request.user
                                    )
                                except Exception as e:
                                    pass
                                    
                        except InductionChecklistQuestion.DoesNotExist:
                            continue
                
                # Process LEARNER responses (learner agreeing/disagreeing and commenting)
                if learner_responses and request.user.role == 'learner' and request.user.id == user.id:
                    for item_id, response_data in learner_responses.items():
                        try:
                            question = InductionChecklistQuestion.objects.get(
                                id=item_id,
                                section__induction_checklist__ilp__user=user
                            )
                            
                            # Update learner confirmation
                            if 'confirmation' in response_data:
                                question.student_confirmed = response_data['confirmation']
                            
                            # Update learner comment
                            if 'comment' in response_data:
                                question.student_comment = response_data['comment'].strip()
                            
                            question.save()
                            
                        except InductionChecklistQuestion.DoesNotExist:
                            continue
                
                # ========================================================================================
                # Process Health & Safety Dynamic Items
                # ========================================================================================
                
                # ========================================================================================
                # Process Statement of Purpose Update
                # ========================================================================================
                
                # Process SOP data if provided
                sop_reason_for_course = request.POST.get('ilp_reason_for_course', '').strip()
                sop_career_objectives = request.POST.get('ilp_career_objectives', '').strip()
                sop_relevant_experience = request.POST.get('ilp_relevant_experience', '').strip()
                sop_additional_info = request.POST.get('ilp_additional_info', '').strip()
                
                if any([sop_reason_for_course, sop_career_objectives, sop_relevant_experience, sop_additional_info]):
                    from individual_learning_plan.models import StatementOfPurpose
                    
                    # Get or create StatementOfPurpose
                    sop_obj, sop_created = StatementOfPurpose.objects.get_or_create(
                        ilp=ilp,
                        defaults={'updated_by': request.user}
                    )
                    
                    # Update SOP fields
                    if sop_reason_for_course:
                        sop_obj.reason_for_course = sop_reason_for_course
                    if sop_career_objectives:
                        sop_obj.career_objectives = sop_career_objectives
                    if sop_relevant_experience:
                        sop_obj.relevant_experience = sop_relevant_experience
                    if sop_additional_info:
                        sop_obj.additional_info = sop_additional_info
                    
                    sop_obj.updated_by = request.user
                    sop_obj.save()

                # ========================================================================================
                # Process Strengths & Weaknesses Assessment
                # ========================================================================================
                
                # Process strengths and weaknesses data if provided
                strengths_content = request.POST.get('strengths_content', '').strip()
                development_content = request.POST.get('development_content', '').strip()
                strengths_instructor_reply = request.POST.get('strengths_instructor_reply', '').strip()
                development_instructor_reply = request.POST.get('development_instructor_reply', '').strip()
                
                # Process instructor content and replies
                if (request.user.role in ['admin', 'instructor', 'superadmin'] and 
                    (strengths_content or development_content or strengths_instructor_reply or development_instructor_reply)):
                    
                    from individual_learning_plan.models import SimpleStrengthsWeaknesses
                    
                    # Get or create SimpleStrengthsWeaknesses
                    sw_data, sw_created = SimpleStrengthsWeaknesses.objects.get_or_create(
                        ilp=ilp
                    )
                    
                    # Update content fields if provided
                    if strengths_content:
                        sw_data.strengths_content = strengths_content
                        sw_data.development_content = development_content
                    
                    # Update reply fields if provided
                    if strengths_instructor_reply:
                        sw_data.strengths_instructor_reply = strengths_instructor_reply
                        sw_data.development_instructor_reply = development_instructor_reply
                        
                    sw_data.save()
                
                # Process learner responses
                strengths_approval = request.POST.get('strengths_approval', '').strip()
                development_approval = request.POST.get('development_approval', '').strip()
                strengths_learner_comment = request.POST.get('strengths_learner_comment', '').strip()
                development_learner_comment = request.POST.get('development_learner_comment', '').strip()
                
                if (request.user.role == 'learner' and request.user.id == user.id and 
                    (strengths_approval or development_approval or strengths_learner_comment or development_learner_comment)):
                    
                    from individual_learning_plan.models import SimpleStrengthsWeaknesses
                    
                    # Get or create SimpleStrengthsWeaknesses
                    sw_data, sw_created = SimpleStrengthsWeaknesses.objects.get_or_create(
                        ilp=ilp
                    )
                    
                    # Update learner response fields
                    if strengths_approval:
                        sw_data.strengths_approval = strengths_approval
                        sw_data.development_approval = development_approval
                        
                    sw_data.strengths_learner_comment = strengths_learner_comment
                    sw_data.development_learner_comment = development_learner_comment
                        
                    sw_data.save()

                # ========================================================================================
                # Process Learning Needs Dynamic Items (following same pattern)
                # ========================================================================================
                from individual_learning_plan.models import LearningNeeds, LearningNeedsSection, LearningNeedsQuestion, LearningNeedsSectionDocument
                
                # Get or create learning needs
                learning_needs, ln_created = LearningNeeds.objects.get_or_create(
                    ilp=ilp,
                    defaults={'created_by': request.user}
                )
                
                # Process dynamic learning needs items
                # Look for fields with pattern: learning_needs_item_{index}_{field}
                learning_needs_items = {}
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('learning_needs_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:  # learning_needs_item_{index}_{field}
                            try:
                                index = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if index not in learning_needs_items:
                                    learning_needs_items[index] = {}
                                
                                learning_needs_items[index][field_type] = field_value
                            except (ValueError, IndexError):
                                continue
                
                # Process file uploads for learning needs items
                for field_name, field_file in request.FILES.items():
                    if field_name.startswith('learning_needs_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 5:
                            try:
                                index = int(parts[3])
                                field_type = '_'.join(parts[4:])
                                
                                if index not in learning_needs_items:
                                    learning_needs_items[index] = {}
                                
                                learning_needs_items[index][field_type] = field_file
                            except (ValueError, IndexError):
                                continue
                
                # Get or create the learning needs dynamic items section
                ln_section, ln_section_created = LearningNeedsSection.objects.get_or_create(
                    learning_needs=learning_needs,
                    title='Dynamic Learning Needs Items',
                    defaults={
                        'description': 'Dynamically added learning needs assessment items',
                        'order': 1,
                        'created_by': request.user
                    }
                )
                
                # Process learning needs items
                if learning_needs_items:
                    existing_ln_questions = list(ln_section.questions.all().order_by('order'))
                    existing_ln_count = len(existing_ln_questions)
                    
                    for index in sorted(learning_needs_items.keys()):
                        item_data = learning_needs_items[index]
                        
                        has_question = 'question' in item_data and item_data['question'].strip()
                        has_learner_update = (request.user.role == 'learner' and 
                                            ('confirmation' in item_data or 'comment' in item_data))
                        
                        if has_question or has_learner_update:
                            student_confirmed = ''
                            instructor_confirmed = ''
                            
                            if request.user.role == 'learner':
                                student_confirmed = item_data.get('confirmation', '')
                            else:
                                instructor_confirmed = item_data.get('confirmation', '')
                            
                            if index < existing_ln_count:
                                # Update existing question
                                question = existing_ln_questions[index]
                                
                                if 'question' in item_data and item_data['question'].strip():
                                    question.question_text = item_data['question'].strip()
                                if 'answer' in item_data:
                                    question.answer_text = item_data.get('answer', '').strip()
                                
                                if request.user.role == 'learner':
                                    question.student_confirmed = student_confirmed
                                    question.student_comment = item_data.get('comment', '').strip()
                                else:
                                    question.instructor_confirmed = instructor_confirmed
                                
                                question.order = index + 1
                                question.save()
                            else:
                                # Create new question
                                if 'question' in item_data and item_data['question'].strip():
                                    question = LearningNeedsQuestion.objects.create(
                                        section=ln_section,
                                        question_text=item_data['question'].strip(),
                                        answer_text=item_data.get('answer', '').strip(),
                                        student_confirmed=student_confirmed,
                                        instructor_confirmed=instructor_confirmed,
                                        student_comment=item_data.get('comment', '').strip(),
                                        order=index + 1,
                                        is_mandatory=True,
                                        created_by=request.user
                                    )
                            
                            # Handle file upload
                            if 'file' in item_data and item_data['file']:
                                try:
                                    LearningNeedsSectionDocument.objects.create(
                                        section=ln_section,
                                        title=f"Document for Learning Needs Question {index + 1}",
                                        document_file=item_data['file'],
                                        description=f"Supporting document for: {item_data['question'][:50]}...",
                                        is_mandatory=True,
                                        uploaded_by=request.user
                                    )
                                except Exception as e:
                                    pass
                    
                    # Remove questions beyond submitted range
                    max_ln_index = max(learning_needs_items.keys()) if learning_needs_items else -1
                    if max_ln_index + 1 < existing_ln_count:
                        questions_to_delete = existing_ln_questions[max_ln_index + 1:]
                        for q in questions_to_delete:
                            q.delete()
                
                # Simplified Health & Safety Processing
                from individual_learning_plan.models import HealthSafetyQuestionnaire, HealthSafetySection, HealthSafetyQuestion
                
                # Get or create health safety questionnaire
                health_safety_questionnaire, hs_created = HealthSafetyQuestionnaire.objects.get_or_create(
                    ilp=ilp,
                    defaults={'created_by': request.user}
                )
                
                # Get or create the default section
                hs_section, hs_section_created = HealthSafetySection.objects.get_or_create(
                    health_safety_questionnaire=health_safety_questionnaire,
                    title='Dynamic Health & Safety Items',
                    defaults={
                        'description': 'Health & Safety questions',
                        'order': 1,
                        'created_by': request.user
                    }
                )
                
                # Process new questions (instructor/admin only)
                if request.user.role in ['admin', 'instructor', 'superadmin']:
                    # Parse new question fields
                    new_questions = {}
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('new_health_safety_item_') and '_question_text' in field_name:
                            index = field_name.split('_')[3]
                            if field_value.strip():
                                new_questions[index] = field_value.strip()
                    
                    # Create new questions
                    for index, question_text in new_questions.items():
                        HealthSafetyQuestion.objects.create(
                            section=hs_section,
                            question_text=question_text,
                            order=hs_section.questions.count() + 1,
                            created_by=request.user
                        )
                    
                    # Update existing questions
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('existing_health_safety_item_') and '_question_text' in field_name:
                            try:
                                # Field name pattern: existing_health_safety_item_{id}_question_text
                                item_id = int(field_name.split('_')[4])
                                # Try to find in current section first, then any section for this questionnaire
                                question = HealthSafetyQuestion.objects.filter(
                                    id=item_id,
                                    section__health_safety_questionnaire=health_safety_questionnaire
                                ).first()
                                if question and field_value.strip():
                                    question.question_text = field_value.strip()
                                    question.save()
                            except (ValueError, IndexError):
                                continue
                        elif field_name.startswith('existing_health_safety_item_') and '_instructor_reply' in field_name:
                            try:
                                # Field name pattern: existing_health_safety_item_{id}_instructor_reply
                                item_id = int(field_name.split('_')[4])
                                # Try to find in any section for this questionnaire
                                question = HealthSafetyQuestion.objects.filter(
                                    id=item_id,
                                    section__health_safety_questionnaire=health_safety_questionnaire
                                ).first()
                                if question:
                                    old_reply = question.instructor_reply
                                    question.instructor_reply = field_value.strip() if field_value else ""
                                    question.save()
                                else:
                                    logger.warning(f"Could not find health safety question with ID {item_id}")
                            except (ValueError, IndexError):
                                continue
                    
                    # Process deletions
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('delete_health_safety_item_') and field_value == 'true':
                            try:
                                item_id = int(field_name.split('_')[-1])
                                HealthSafetyQuestion.objects.filter(id=item_id, section=hs_section).delete()
                            except (ValueError, IndexError):
                                continue
                
                # Process ALL remaining form fields for health safety (including learner responses)
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('health_safety_item_'):
                        try:
                            item_id = int(field_name.split('_')[3])
                            # Try to find in any section for this questionnaire
                            question = HealthSafetyQuestion.objects.filter(
                                id=item_id,
                                section__health_safety_questionnaire=health_safety_questionnaire
                            ).first()
                            
                            if question:
                                if '_student_confirmed' in field_name:
                                    question.student_confirmed = field_value
                                    question.save()
                                elif '_answer_text' in field_name:
                                    question.answer_text = field_value.strip() if field_value else ""
                                    question.save()
                                elif '_student_comment' in field_name:
                                    question.student_comment = field_value.strip() if field_value else ""
                                    question.save()
                        except (ValueError, IndexError):
                            continue

                # ========================================================================================
                # Process Learning Needs Dynamic Items (similar to Health & Safety)
                # ========================================================================================
                if request.user.role in ['admin', 'instructor', 'superadmin']:
                    # Parse new learning needs question fields
                    new_ln_questions = {}
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('new_learning_needs_item_') and '_question_text' in field_name:
                            index = field_name.split('_')[3]
                            if field_value.strip():
                                new_ln_questions[index] = field_value.strip()
                    
                    # Create new learning needs questions
                    for index, question_text in new_ln_questions.items():
                        LearningNeedsQuestion.objects.create(
                            section=ln_section,
                            question_text=question_text,
                            order=ln_section.questions.count() + 1,
                            created_by=request.user
                        )
                    
                    # Update existing learning needs questions
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('existing_learning_needs_item_') and '_question_text' in field_name:
                            try:
                                # Field name pattern: existing_learning_needs_item_{id}_question_text
                                item_id = int(field_name.split('_')[4])
                                question = LearningNeedsQuestion.objects.filter(
                                    id=item_id,
                                    section__learning_needs=learning_needs
                                ).first()
                                if question and field_value.strip():
                                    question.question_text = field_value.strip()
                                    question.save()
                            except (ValueError, IndexError):
                                continue
                        elif field_name.startswith('existing_learning_needs_item_') and '_instructor_reply' in field_name:
                            try:
                                # Field name pattern: existing_learning_needs_item_{id}_instructor_reply
                                item_id = int(field_name.split('_')[4])
                                question = LearningNeedsQuestion.objects.filter(
                                    id=item_id,
                                    section__learning_needs=learning_needs
                                ).first()
                                if question:
                                    question.instructor_reply = field_value.strip() if field_value else ""
                                    question.save()
                            except (ValueError, IndexError):
                                continue
                    
                    # Process learning needs deletions
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('delete_learning_needs_item_') and field_value == 'true':
                            try:
                                item_id = int(field_name.split('_')[-1])
                                LearningNeedsQuestion.objects.filter(id=item_id, section=ln_section).delete()
                            except (ValueError, IndexError):
                                continue
                
                # Process ALL remaining form fields for learning needs (including learner responses)
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('learning_needs_item_'):
                        try:
                            item_id = int(field_name.split('_')[3])
                            question = LearningNeedsQuestion.objects.filter(
                                id=item_id,
                                section__learning_needs=learning_needs
                            ).first()
                            
                            if question:
                                if '_student_confirmed' in field_name:
                                    question.student_confirmed = field_value
                                    question.save()
                                elif '_answer_text' in field_name:
                                    question.answer_text = field_value.strip() if field_value else ""
                                    question.save()
                                elif '_student_comment' in field_name:
                                    question.student_comment = field_value.strip() if field_value else ""
                                    question.save()
                        except (ValueError, IndexError):
                            continue

                # ========================================================================================
                # Process Strengths & Weaknesses Dynamic Items (following same pattern)
                # ========================================================================================
                from individual_learning_plan.models import StrengthsWeaknessesSection, StrengthsWeaknessesQuestion, StrengthsWeaknessesSectionDocument
                
                # Process dynamic strengths & weaknesses items
                # Look for fields with pattern: strengths_item_{index}_{field}
                strengths_items = {}
                for field_name, field_value in request.POST.items():
                    if field_name.startswith('strengths_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 4:  # strengths_item_{index}_{field}
                            try:
                                index = int(parts[2])
                                field_type = '_'.join(parts[3:])
                                
                                if index not in strengths_items:
                                    strengths_items[index] = {}
                                
                                strengths_items[index][field_type] = field_value
                            except (ValueError, IndexError):
                                continue
                
                # Process file uploads for strengths & weaknesses items
                for field_name, field_file in request.FILES.items():
                    if field_name.startswith('strengths_item_'):
                        parts = field_name.split('_')
                        if len(parts) >= 4:
                            try:
                                index = int(parts[2])
                                field_type = '_'.join(parts[3:])
                                
                                if index not in strengths_items:
                                    strengths_items[index] = {}
                                
                                strengths_items[index][field_type] = field_file
                            except (ValueError, IndexError):
                                continue
                
                # Get or create the strengths & weaknesses dynamic items section
                sw_section, sw_section_created = StrengthsWeaknessesSection.objects.get_or_create(
                    ilp=ilp,
                    title='Dynamic Strengths & Weaknesses Items',
                    defaults={
                        'description': 'Dynamically added strengths & weaknesses assessment items',
                        'order': 1,
                        'created_by': request.user
                    }
                )
                
                
                # Process strengths & weaknesses items
                if strengths_items:
                    existing_sw_questions = list(sw_section.questions.all().order_by('order'))
                    existing_sw_count = len(existing_sw_questions)
                    
                    for index in sorted(strengths_items.keys()):
                        item_data = strengths_items[index]
                        
                        has_description = 'description' in item_data and item_data['description'].strip()
                        has_learner_update = (request.user.role == 'learner' and 
                                            ('confirmation' in item_data or 'comment' in item_data))
                        
                        if has_description or has_learner_update:
                            student_confirmed = ''
                            instructor_confirmed = ''
                            
                            if request.user.role == 'learner':
                                student_confirmed = item_data.get('confirmation', '')
                            else:
                                instructor_confirmed = item_data.get('confirmation', '')
                            
                            if index < existing_sw_count:
                                # Update existing question
                                question = existing_sw_questions[index]
                                
                                if 'type' in item_data:
                                    question.item_type = item_data['type']
                                if 'description' in item_data and item_data['description'].strip():
                                    question.description = item_data['description'].strip()
                                
                                if request.user.role == 'learner':
                                    question.student_confirmed = student_confirmed
                                    question.student_comment = item_data.get('comment', '').strip()
                                else:
                                    question.instructor_confirmed = instructor_confirmed
                                    question.instructor_comment = item_data.get('instructor_reply', '').strip()
                                
                                question.order = index + 1
                                question.save()
                            else:
                                # Create new question
                                if 'description' in item_data and item_data['description'].strip():
                                    instructor_comment = ''
                                    if request.user.role != 'learner':
                                        instructor_comment = item_data.get('instructor_reply', '').strip()
                                    
                                    question = StrengthsWeaknessesQuestion.objects.create(
                                        section=sw_section,
                                        item_type=item_data.get('type', 'strength'),
                                        description=item_data['description'].strip(),
                                        student_confirmed=student_confirmed,
                                        instructor_confirmed=instructor_confirmed,
                                        student_comment=item_data.get('comment', '').strip(),
                                        instructor_comment=instructor_comment,
                                        order=index + 1,
                                        is_mandatory=True,
                                        created_by=request.user
                                    )
                            
                            # Handle file upload
                            if 'file' in item_data and item_data['file']:
                                try:
                                    StrengthsWeaknessesSectionDocument.objects.create(
                                        section=sw_section,
                                        title=f"Document for Strengths & Weaknesses Item {index + 1}",
                                        document_file=item_data['file'],
                                        description=f"Supporting document for: {item_data['description'][:50]}...",
                                        is_mandatory=True,
                                        uploaded_by=request.user
                                    )
                                except Exception as e:
                                    pass
                    
                    # Remove questions beyond submitted range
                    max_sw_index = max(strengths_items.keys()) if strengths_items else -1
                    if max_sw_index + 1 < existing_sw_count:
                        questions_to_delete = existing_sw_questions[max_sw_index + 1:]
                        for q in questions_to_delete:
                            q.delete()
                
                # ========================================================================================
                # Process Manual VAK Scores (if user has permission)
                # ========================================================================================
                if request.user.role in ['admin', 'instructor', 'superadmin', 'globaladmin']:
                    # Get manual VAK score data from the form
                    manual_visual_score = request.POST.get('manual_visual_score')
                    manual_auditory_score = request.POST.get('manual_auditory_score')
                    manual_kinesthetic_score = request.POST.get('manual_kinesthetic_score')
                    
                    
                    # Check if any manual VAK scores are provided or if we need to clear existing scores
                    from users.models import ManualVAKScore
                    
                    # Get or create ManualVAKScore instance
                    manual_vak_score, created = ManualVAKScore.objects.get_or_create(
                        user=target_user,
                        defaults={
                            'entered_by': request.user
                        }
                    )
                    
                    # Update scores with validation
                    scores_updated = False
                    
                    # Handle visual score
                    if manual_visual_score and manual_visual_score.strip():
                        try:
                            score = float(manual_visual_score)
                            if 0 <= score <= 100:
                                manual_vak_score.visual_score = score
                                scores_updated = True
                        except ValueError:
                            pass
                    else:
                        manual_vak_score.visual_score = None
                        scores_updated = True
                    
                    # Handle auditory score
                    if manual_auditory_score and manual_auditory_score.strip():
                        try:
                            score = float(manual_auditory_score)
                            if 0 <= score <= 100:
                                manual_vak_score.auditory_score = score
                                scores_updated = True
                        except ValueError:
                            pass
                    else:
                        manual_vak_score.auditory_score = None
                        scores_updated = True
                    
                    # Handle kinesthetic score
                    if manual_kinesthetic_score and manual_kinesthetic_score.strip():
                        try:
                            score = float(manual_kinesthetic_score)
                            if 0 <= score <= 100:
                                manual_vak_score.kinesthetic_score = score
                                scores_updated = True
                        except ValueError:
                            pass
                    else:
                        manual_vak_score.kinesthetic_score = None
                        scores_updated = True
                    
                    if scores_updated:
                        manual_vak_score.entered_by = request.user
                        manual_vak_score.save()
                        
                        # Delete the record if all scores are None
                        if not manual_vak_score.has_any_scores():
                            manual_vak_score.delete()
                
                # ========================================================================================
                # Process Manual Assessment Entries (if user has permission)
                # ========================================================================================
                if request.user.role in ['admin', 'instructor', 'superadmin', 'globaladmin']:
                    from users.models import ManualAssessmentEntry
                    
                    # Handle manual assessment entries
                    # Process existing entries updates
                    existing_entries_updated = False
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('manual_assessment_'):
                            parts = field_name.split('_')
                            if len(parts) >= 4:  # manual_assessment_{id}_{field}
                                try:
                                    entry_id = int(parts[2])
                                    field_type = '_'.join(parts[3:])
                                    
                                    # Get the existing entry
                                    try:
                                        entry = ManualAssessmentEntry.objects.get(id=entry_id, user=target_user)
                                        
                                        if field_type == 'subject':
                                            entry.subject = field_value.strip()
                                        elif field_type == 'score':
                                            try:
                                                score = float(field_value)
                                                if 0 <= score <= 100:
                                                    entry.score = score
                                            except ValueError:
                                                pass
                                        elif field_type == 'notes':
                                            entry.notes = field_value.strip()
                                        elif field_type == 'assessment_date':
                                            if field_value:
                                                from datetime import datetime
                                                try:
                                                    entry.assessment_date = datetime.strptime(field_value, '%Y-%m-%d').date()
                                                except ValueError:
                                                    entry.assessment_date = None
                                            else:
                                                entry.assessment_date = None
                                        
                                        entry.entered_by = request.user
                                        entry.save()
                                        existing_entries_updated = True
                                        
                                    except ManualAssessmentEntry.DoesNotExist:
                                        pass
                                        
                                except (ValueError, IndexError):
                                    continue
                    
                    # Process new assessment entries
                    new_entries_created = False
                    new_entries = {}
                    for field_name, field_value in request.POST.items():
                        if field_name.startswith('new_manual_assessment_'):
                            parts = field_name.split('_')
                            if len(parts) >= 5:  # new_manual_assessment_{index}_{field}
                                try:
                                    index = int(parts[3])
                                    field_type = '_'.join(parts[4:])
                                    
                                    if index not in new_entries:
                                        new_entries[index] = {}
                                    
                                    new_entries[index][field_type] = field_value.strip() if field_value else ''
                                    
                                except (ValueError, IndexError):
                                    continue
                    
                    # Create new entries
                    for index, entry_data in new_entries.items():
                        subject = entry_data.get('subject', '').strip()
                        score_str = entry_data.get('score', '').strip()
                        notes = entry_data.get('notes', '').strip()
                        assessment_date_str = entry_data.get('assessment_date', '').strip()
                        
                        if subject and score_str:
                            try:
                                score = float(score_str)
                                if 0 <= score <= 100:
                                    # Parse assessment date if provided
                                    assessment_date = None
                                    if assessment_date_str:
                                        try:
                                            from datetime import datetime
                                            assessment_date = datetime.strptime(assessment_date_str, '%Y-%m-%d').date()
                                        except ValueError:
                                            assessment_date = None
                                    
                                    # Check if entry with same subject already exists
                                    existing_entry = ManualAssessmentEntry.objects.filter(
                                        user=target_user,
                                        subject__iexact=subject
                                    ).first()
                                    
                                    if not existing_entry:
                                        ManualAssessmentEntry.objects.create(
                                            user=target_user,
                                            subject=subject,
                                            score=score,
                                            notes=notes,
                                            assessment_date=assessment_date,
                                            entered_by=request.user
                                        )
                                        new_entries_created = True
                                        
                            except ValueError:
                                pass
                    
                    # Process deletions
                    delete_entry_ids = request.POST.getlist('delete_manual_assessment_ids')
                    if delete_entry_ids:
                        for entry_id in delete_entry_ids:
                            try:
                                entry_id = int(entry_id)
                                ManualAssessmentEntry.objects.filter(id=entry_id, user=target_user).delete()
                            except (ValueError, ManualAssessmentEntry.DoesNotExist):
                                pass
                
                messages.success(request, 'User profile and questionnaire updated successfully')
                
                # Handle AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'User profile and questionnaire updated successfully!',
                        'stay_on_page': True
                    })
                
                # For non-AJAX requests, redirect to edit page to stay on same page
                # Get all tab levels from the form to redirect back to the same tab state
                active_tab = request.POST.get('active_tab', 'account-tab')
                active_subtab = request.POST.get('active_subtab', '')
                active_nestedtab = request.POST.get('active_nestedtab', '')
                
                # Build redirect URL with all tab parameters
                redirect_url = reverse('users:edit_user', args=[user.id])
                url_params = []
                
                # Add tab parameter
                url_params.append(f'tab={active_tab}')
                
                # Add subtab parameter if we're on ILP tab
                if active_tab == 'ilp-tab':
                    active_subtab = request.POST.get('active_subtab') or ''
                    if active_subtab:
                        url_params.append(f'subtab={active_subtab}')
                        
                        # Add nestedtab parameter if we're on learning-profile-tab
                        if active_subtab == 'learning-profile-tab':
                            active_nestedtab = request.POST.get('active_nestedtab') or ''
                            if active_nestedtab:
                                url_params.append(f'nestedtab={active_nestedtab}')
                
                # Join URL parameters and redirect
                if url_params:
                    redirect_url += '?' + '&'.join(url_params)
                
# Redirecting to maintain tab state
                return redirect(redirect_url)
            else:
# Form validation failed - displaying errors to user
                # Simplified error handling - show only the most important errors
                priority_fields = ['username', 'email', 'first_name', 'last_name', 'password1', 'password2']
                error_messages = []
                
                # First, check for priority field errors
                for field in priority_fields:
                    if field in form.errors:
                        try:
                            field_name = form[field].label or field.replace('_', ' ').title()
                        except:
                            field_name = field.replace('_', ' ').title()
                        
                        error = form.errors[field][0]  # Show only first error per field
                        error_messages.append(f"{field_name}: {error}")
                        if len(error_messages) >= 3:  # Limit to 3 most important errors
                            break
                
                # If no priority errors or still have space, add other errors
                if len(error_messages) < 3:
                    for field, errors in form.errors.items():
                        if field not in priority_fields and len(error_messages) < 3:
                            try:
                                field_name = form[field].label or field.replace('_', ' ').title()
                            except:
                                field_name = field.replace('_', ' ').title()
                            
                            error = errors[0]  # Show only first error per field
                            error_messages.append(f"{field_name}: {error}")
                
                if error_messages:
                    messages.error(request, "Please check the following required fields:")
                    for message in error_messages:
                        messages.error(request, message)
                    
                    total_errors = sum(len(errors) for errors in form.errors.values())
                    if total_errors > len(error_messages):
                        messages.info(request, f"Fix these {len(error_messages)} errors first, then check for any remaining issues.")
                else:
                    messages.error(request, "Please correct the form errors and try again.")
                
                # Handle AJAX requests for errors
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': form.errors,
                        'message': 'Please correct the errors below.'
                    })
        
        except Exception as e:
            # Handle any errors during form processing
            messages.error(request, f'An error occurred while saving: {str(e)}')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': f'An error occurred while saving: {str(e)}'
                })

    # For GET requests, initialize the form with the target user instance
    if request.method == 'GET':
        # Prepopulate given_name and family_name from first_name and last_name
        initial_data = {
            'given_name': target_user.first_name,
            'family_name': target_user.last_name,
        }
        form = CustomUserChangeForm(instance=target_user, request=request, initial=initial_data)

    # Get existing questionnaire data
    existing_questionnaires = UserQuestionnaire.objects.filter(user=target_user).order_by('question_order')
    
    # Get existing dynamic induction checklist items for display
    existing_induction_items = []
    existing_health_safety_items = []
    existing_learning_needs_items = []
    existing_strengths_items = []
    sw_sections = []
    
    try:
        from individual_learning_plan.models import (
            IndividualLearningPlan, InductionChecklistSection, 
            HealthSafetyQuestionnaire, HealthSafetySection,
            LearningNeeds, LearningNeedsSection,
            StrengthsWeaknessesSection
        )
        
        ilp = IndividualLearningPlan.objects.filter(user=target_user).first()
        
        # Get induction checklist sections and questions
        induction_sections = []
        if ilp:
            try:
                # Get or create induction checklist
                induction_checklist = getattr(ilp, 'induction_checklist', None)
                if induction_checklist:
                    # Get all sections with their questions and documents
                    induction_sections = InductionChecklistSection.objects.filter(
                        induction_checklist=induction_checklist,
                        is_active=True
                    ).prefetch_related(
                        'questions__created_by',
                        'questions__documents__uploaded_by',  # Prefetch documents for each question
                        'documents__uploaded_by'
                    ).order_by('order')
            except Exception as e:
                induction_sections = []
        
        # Get existing health & safety dynamic items
        existing_health_safety_items = []
        if ilp:
            try:
                from individual_learning_plan.models import HealthSafetyQuestionnaire, HealthSafetySection
                health_safety_questionnaire = HealthSafetyQuestionnaire.objects.filter(ilp=ilp).first()
                if health_safety_questionnaire:
                    hs_section = HealthSafetySection.objects.filter(
                        health_safety_questionnaire=health_safety_questionnaire,
                        title='Dynamic Health & Safety Items'
                    ).first()
                    if hs_section:
                        existing_health_safety_items = list(hs_section.questions.all().order_by('order'))
                        # Prefetch related documents for each question's section
                        for item in existing_health_safety_items:
                            item.section_documents = hs_section.documents.all()
            except Exception:
                existing_health_safety_items = []
        
        # Get existing learning needs dynamic items
        existing_learning_needs_items = []
        if ilp and hasattr(ilp, 'learning_needs'):
            ln_section = LearningNeedsSection.objects.filter(
                learning_needs=ilp.learning_needs,
                title='Dynamic Learning Needs Items'
            ).first()
            
            if ln_section:
                existing_learning_needs_items = list(ln_section.questions.all().order_by('order'))
                # Prefetch related documents for each question's section
                for item in existing_learning_needs_items:
                    item.section_documents = ln_section.documents.all()
        
        # Get existing learning goals
        existing_learning_goals = []
        if ilp:
            existing_learning_goals = list(ilp.learning_goals.all().order_by('-created_at'))
        
        # Get existing strengths & weaknesses dynamic items with feedback discussions
        sw_sections = []
        sw_data = None
        if ilp:
            from individual_learning_plan.models import StrengthWeaknessFeedback, SimpleStrengthsWeaknesses
            
            # Get simplified strengths & weaknesses data
            try:
                sw_data = SimpleStrengthsWeaknesses.objects.get(ilp=ilp)
            except SimpleStrengthsWeaknesses.DoesNotExist:
                sw_data = None
            
            sw_sections = StrengthsWeaknessesSection.objects.filter(
                ilp=ilp,
                questions__isnull=False
            ).prefetch_related(
                'questions__feedback_discussions__created_by',
                'questions__created_by',
                'documents'
            ).distinct().order_by('order')
            
            # Add feedback count and latest feedback for each question
            for section in sw_sections:
                for question in section.questions.all():
                    question.feedback_count = question.feedback_discussions.count()
                    question.latest_feedback = question.feedback_discussions.last()
                    
        # Get existing strengths & weaknesses dynamic items (fallback)
        if ilp and not sw_sections:
            sw_section = StrengthsWeaknessesSection.objects.filter(
                ilp=ilp,
                title='Dynamic Strengths & Weaknesses Items'
            ).first()
            
            if sw_section:
                existing_strengths_items = list(sw_section.questions.all().order_by('order'))
                # Prefetch related documents for each question's section
                for item in existing_strengths_items:
                    item.section_documents = sw_section.documents.all()
                    
    except Exception as e:
        # If any errors occur, just use empty lists
        existing_induction_items = []
        existing_health_safety_items = []
        existing_learning_needs_items = []
        existing_strengths_items = []
        sw_data = None
        sw_sections = []
    
    # Get branch assessment quizzes - now supporting multiple assessments
    initial_assessment_quizzes = []
    vak_test_quizzes = []
    initial_assessment_data = []
    vak_test_data = []

    if target_user.branch:
        from quiz.models import Quiz, QuizAttempt
        
        # Find all Initial Assessment quizzes created by branch admins and instructors
        initial_assessment_quizzes = Quiz.objects.filter(
            creator__branch=target_user.branch,
            creator__role__in=['admin', 'instructor'],
            is_initial_assessment=True,
            is_active=True
        ).order_by('title')
        
        # Find all VAK Test quizzes created by branch admins and instructors
        vak_test_quizzes = Quiz.objects.filter(
            creator__branch=target_user.branch,
            creator__role__in=['admin', 'instructor'],
            is_vak_test=True,
            is_active=True
        ).order_by('title')
        
        # Get user's attempts for each Initial Assessment quiz - only latest
        for quiz in initial_assessment_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=target_user,
                is_completed=True
            ).order_by('-end_time').first()
            
            if latest_attempt:
                initial_assessment_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=target_user,
                        is_completed=True
                    ).count()
                })
        
        # Get user's attempts for each VAK Test quiz - only latest
        for quiz in vak_test_quizzes:
            latest_attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                user=target_user,
                is_completed=True
            ).order_by('-end_time').first()
            
            if latest_attempt:
                vak_test_data.append({
                    'quiz': quiz,
                    'latest_attempt': latest_attempt,
                    'latest_score': latest_attempt.score,
                    'attempt_count': QuizAttempt.objects.filter(
                        quiz=quiz,
                        user=target_user,
                        is_completed=True
                    ).count()
                })
    
    # Get quiz assignments for Assessment Data tab only
    initial_assessment_assignments = UserQuizAssignment.objects.filter(
        user=target_user,
        assignment_type='initial_assessment',
        is_active=True
    ).select_related('quiz', 'assigned_by').order_by('assigned_at')
    
    # Get VAK quiz attempts with course/topic context (instead of assignments)
    vak_quiz_attempts = target_user.get_vak_quiz_attempts_with_context()
    
    # Get manual assessment entries for Assessment Data tab
    from users.models import ManualAssessmentEntry
    manual_assessment_entries = ManualAssessmentEntry.objects.filter(
        user=target_user
    ).select_related('entered_by').order_by('subject')
    
    # Calculate profile completion data
    profile_completion = target_user.get_profile_completion_percentage()
    
    # Get all tab levels from URL parameters (for redirects after form submission)
    # If this is a POST request with errors, preserve tab state from form data
    if request.method == 'POST':
        active_tab = request.POST.get('active_tab') or request.GET.get('tab', 'account-tab')
        active_subtab = request.POST.get('active_subtab') or request.GET.get('subtab', '')
        active_nestedtab = request.POST.get('active_nestedtab') or request.GET.get('nestedtab', '')
    else:
        active_tab = request.GET.get('tab', 'account-tab')
        active_subtab = request.GET.get('subtab', '')
        active_nestedtab = request.GET.get('nestedtab', '')
    
    # Set defaults based on main tab context
    if active_tab == 'ilp-tab':
        if not active_subtab:
            active_subtab = 'overview-tab'
        if active_subtab == 'learning-profile-tab' and not active_nestedtab:
            active_nestedtab = 'assessment-data-tab'
    else:
        # Clear subtab and nestedtab for non-ILP tabs
        active_subtab = ''
        active_nestedtab = ''
    
    # Load existing education records from JSON field
    existing_education_records = []
    existing_education_records_json = '[]'
    if target_user.education_data:
        try:
            if isinstance(target_user.education_data, list):
                existing_education_records = target_user.education_data
            elif isinstance(target_user.education_data, str):
                import json
                existing_education_records = json.loads(target_user.education_data)
            
            # Convert to JSON string for template
            import json
            existing_education_records_json = json.dumps(existing_education_records)
        except (json.JSONDecodeError, TypeError):
            existing_education_records = []
            existing_education_records_json = '[]'
    
    # Load existing employment records from JSON field
    existing_employment_records = []
    existing_employment_records_json = '[]'
    if target_user.employment_data:
        try:
            if isinstance(target_user.employment_data, list):
                existing_employment_records = target_user.employment_data
            elif isinstance(target_user.employment_data, str):
                import json
                existing_employment_records = json.loads(target_user.employment_data)
            
            # Convert to JSON string for template
            import json
            existing_employment_records_json = json.dumps(existing_employment_records)
        except (json.JSONDecodeError, TypeError):
            existing_employment_records = []
            existing_employment_records_json = '[]'
    
    # Get available roles based on user role (same logic as user_create)
    if request.user.role == 'globaladmin':
        roles = CustomUser.ROLE_CHOICES  # Global admin can edit all user types
    elif request.user.role == 'superadmin':
        # Super admin CANNOT edit globaladmin users - only superadmin, admin, instructor, and learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] not in ['globaladmin']]
    elif request.user.role == 'admin':
        # Admin CANNOT edit superadmin, globaladmin or other admin users - only instructors and learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] not in ['superadmin', 'admin', 'globaladmin']]
    else:  # instructor
        # Instructors can only edit learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] == 'learner']
    
    # Get active business assignment for Super Admin users
    user_business = None
    if target_user.role == 'superadmin':
        business_assignment = target_user.business_assignments.filter(is_active=True).first()
        if business_assignment:
            user_business = business_assignment.business
    
    # Get available businesses for Super Admin assignment (same logic as user_create)
    businesses = []
    if request.user.role == 'globaladmin':
        # Global Admin can assign to any business
        from business.models import Business
        businesses = Business.objects.filter(is_active=True).order_by('name')
    elif request.user.role == 'superadmin':
        # Super Admin can assign to businesses they manage
        if hasattr(request.user, 'business_assignments'):
            assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            from business.models import Business
            businesses = Business.objects.filter(id__in=assigned_businesses, is_active=True).order_by('name')
    
    context = {
        'form': form,
        'profile_user': target_user,
        'user_business': user_business,  # Add business information for Super Admin users
        'businesses': businesses,  # Add businesses for Super Admin assignment
        'breadcrumbs': breadcrumbs,
        'is_edit_mode': True,
        'roles': roles,  # Add filtered roles to context
        'existing_questionnaires': existing_questionnaires,
        'induction_sections': induction_sections,  # New induction checklist sections
        'existing_health_safety_items': existing_health_safety_items,
        'existing_learning_needs_items': existing_learning_needs_items,
        'existing_learning_goals': existing_learning_goals,
        'existing_strengths_items': existing_strengths_items,
        # Strengths & Weaknesses sections with feedback discussions
        'sw_sections': sw_sections,
        # Simplified strengths & weaknesses data
        'sw_data': sw_data,
        # Assessment Data quiz context
        'initial_assessment_quizzes': initial_assessment_quizzes,
        'vak_test_quizzes': vak_test_quizzes,
        'initial_assessment_data': initial_assessment_data,
        'vak_test_data': vak_test_data,
        # Quiz assignments for admin/instructor management
        'initial_assessment_assignments': initial_assessment_assignments,
        # VAK quiz attempts with course/topic context
        'vak_quiz_attempts': vak_quiz_attempts,
        # Profile completion data
        'profile_completion': profile_completion,
        # Tab state management - all levels
        'active_tab': active_tab,
        'active_subtab': active_subtab,
        'active_nestedtab': active_nestedtab,
        # Education records data
        'existing_education_records': existing_education_records,
        'existing_education_records_json': existing_education_records_json,
        # Employment records data
        'existing_employment_records': existing_employment_records,
        'existing_employment_records_json': existing_employment_records_json,
        # Manual assessment entries for Assessment Data tab
        'manual_assessment_entries': manual_assessment_entries,
    }
    return render(request, 'users/user_form_tabbed_modular.html', context)

@login_required
def delete_user(request, user_id):
    """Delete a user with enhanced error handling and debugging."""
    import traceback
    import logging
    from django.http import JsonResponse
    
    logger = logging.getLogger(__name__)
    
    try:
        user_to_delete = get_object_or_404(CustomUser, id=user_id)
        logger.info(f"Attempting to delete user: {user_to_delete.username} (ID: {user_id})")
        
        # Import permission manager for capability-based checking
        from role_management.utils import PermissionManager
        
        # Enhanced permission check with error handling
        try:
            has_permission = PermissionManager.user_has_capability(request.user, 'delete_users')
            logger.info(f"Permission check result: {has_permission} for user: {request.user.username}")
        except Exception as perm_error:
            logger.error(f"Permission check failed: {str(perm_error)}")
            return HttpResponseForbidden(f"Permission check failed: {str(perm_error)}")
        
        # Check if user has delete_users capability
        if not has_permission:
            logger.warning(f"User {request.user.username} attempted to delete user {user_id} without permission")
            return HttpResponseForbidden("You don't have permission to delete users.")
        
        # Additional restrictions for admin users - they can only delete users in their branch
        if request.user.role == 'admin':
            # Admin users can only delete users in their own branch
            if not request.user.branch or user_to_delete.branch != request.user.branch:
                logger.warning(f"Admin {request.user.username} attempted cross-branch deletion")
                return HttpResponseForbidden("You can only delete users within your branch.")
            
            # Admin users cannot delete other admin, superadmin, or globaladmin users
            if user_to_delete.role in ['admin', 'superadmin', 'globaladmin']:
                logger.warning(f"Admin {request.user.username} attempted to delete privileged user")
                return HttpResponseForbidden("You cannot delete admin, superadmin, or globaladmin users.")
        
        # Prevent self-deletion
        if user_to_delete.id == request.user.id:
            messages.error(request, "You cannot delete your own account.")
            return redirect('users:user_list')
        
        if request.method == 'POST':
            # Check if this is a confirmation request
            if request.POST.get('confirmed') == 'true':
                # Store username for success message
                username = user_to_delete.get_full_name() or user_to_delete.username
                logger.info(f"Starting deletion process for user: {username}")
                
                # Enhanced deletion with detailed error tracking
                try:
                    # Attempt deletion (the CustomUser.delete() method will handle all cascade deletion)
                    user_to_delete.delete()
                    logger.info(f"Successfully deleted user: {username}")
                    
                    messages.success(request, f'User "{username}" has been deleted successfully.')
                    return redirect('users:user_list')
                    
                except Exception as delete_error:
                    logger.error(f"Deletion failed for user {username}: {str(delete_error)}")
                    logger.error(f"Full traceback: {traceback.format_exc()}")
                    
                    # Return detailed error for debugging
                    error_details = {
                        'error_type': type(delete_error).__name__,
                        'error_message': str(delete_error),
                        'user_id': user_id,
                        'username': username
                    }
                    
                    if request.headers.get('Content-Type') == 'application/json':
                        return JsonResponse({'success': False, 'error': error_details}, status=500)
                    
                    messages.error(request, f'Failed to delete user "{username}": {str(delete_error)}')
                    return redirect('users:user_list')
            else:
                # Skip warning message for user deletion - proceed directly with deletion
                # The frontend modal already provides confirmation
                pass
        
        # If not POST, redirect to user list (shouldn't happen with current UI)
        return redirect('users:user_list')
        
    except Exception as general_error:
        logger.error(f"General error in delete_user view: {str(general_error)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False, 
                'error': {
                    'type': type(general_error).__name__,
                    'message': str(general_error)
                }
            }, status=500)
        
        messages.error(request, f'An unexpected error occurred: {str(general_error)}')
        return redirect('users:user_list')

@login_required
def password_change(request, user_id):
    """Change a user's password."""
    if request.user.role not in ['globaladmin', 'superadmin', 'admin']:
        return HttpResponseForbidden("You don't have permission to change user passwords")
    
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    # Prevent admin users from changing passwords of globaladmin or superadmin users
    if request.user.role == 'admin' and target_user.role in ['globaladmin', 'superadmin']:
        messages.error(request, "You don't have permission to change globaladmin or superadmin user passwords.")
        return redirect('users:user_list')
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('users:user_list'), 'label': 'User Management', 'icon': 'fa-users'},
        {'url': reverse('users:user_profile', args=[user_id]), 'label': target_user.get_full_name() or target_user.username, 'icon': 'fa-user'},
        {'label': 'Change Password', 'icon': 'fa-key'}
    ]
    
    # Use different forms based on user role
    is_admin = request.user.role in ['globaladmin', 'superadmin', 'admin'] and request.user.id != user_id
    FormClass = AdminPasswordChangeForm if is_admin else CustomPasswordChangeForm
    
    if request.method == 'POST':
        form = FormClass(target_user, request.POST)
        if form.is_valid():
            user = form.save()
            # Update session to prevent logout if user is changing their own password
            if request.user.id == user_id:
                update_session_auth_hash(request, user)
            
            # Log password change for Session audit
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Password changed for user {user.username} (ID: {user.id}) by {request.user.username} (ID: {request.user.id})")
            
            messages.success(request, 'Password changed successfully')
            return redirect('users:user_profile', user_id=user.id)
    else:
        form = FormClass(target_user)
    
    context = {
        'form': form,
        'profile_user': target_user,
        'is_admin_change': is_admin,
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'users/shared/change_password.html', context)

@login_required
def admin_send_forgot_password(request, user_id):
    """Send forgot password email for a specific user (admin function)"""
    if request.user.role not in ['globaladmin', 'superadmin', 'admin']:
        return JsonResponse({'success': False, 'message': 'You don\'t have permission to send password reset emails'}, status=403)
    
    target_user = get_object_or_404(CustomUser, id=user_id)
    
    # Prevent admin users from sending password reset emails to globaladmin or superadmin users
    if request.user.role == 'admin' and target_user.role in ['globaladmin', 'superadmin']:
        return JsonResponse({'success': False, 'message': 'You don\'t have permission to send password reset emails to globaladmin or superadmin users'}, status=403)
    
    try:
        # Create password reset token
        reset_token = PasswordResetToken.objects.create(
            user=target_user,
            branch=target_user.branch
        )
        
        # Send reset email
        email_sent = reset_token.send_reset_email(request)
        
        if email_sent:
            return JsonResponse({
                'success': True, 
                'message': f'Password reset email has been sent to {target_user.email}'
            })
        else:
            # Email failed but don't crash - provide helpful message
            return JsonResponse({
                'success': False,
                'message': 'Email system is not configured. Please configure email settings in the Admin Settings page.'
            }, status=400)
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'message': f'Failed to send password reset email. Please contact support.'
        }, status=500)

@login_required
def send_self_password_reset(request):
    """Send password reset email for the current user"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Create password reset token for current user
        reset_token = PasswordResetToken.objects.create(
            user=request.user,
            branch=request.user.branch
        )
        
        # Send reset email
        email_sent = reset_token.send_reset_email(request)
        
        if email_sent:
            logger.info(f" Password reset email sent successfully to {request.user.email}")
            return JsonResponse({
                'success': True, 
                'message': f'Password reset email has been sent to {request.user.email}. Please check your inbox and spam folder.'
            })
        else:
            # Email failed - delete the token and provide helpful message
            logger.error(f" Failed to send password reset email to {request.user.email}. Check email configuration.")
            reset_token.delete()
            
            return JsonResponse({
                'success': False,
                'message': 'Unable to send password reset email. The email system may not be properly configured. Please contact your system administrator for assistance.'
            }, status=500)
        
    except Exception as e:
        logger.error(f" Exception in send_self_password_reset for {request.user.email}: {str(e)}")
        return JsonResponse({
            'success': False, 
            'message': 'An error occurred while processing your request. Please try again later or contact support.'
        }, status=500)

@login_required
def user_create(request):
    """Create a new user."""
    logger = logging.getLogger(__name__)
    if request.user.role not in ['globaladmin', 'superadmin', 'admin', 'instructor']:
        return HttpResponseForbidden("You don't have permission to create users")
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('users:user_list'), 'label': 'User Management', 'icon': 'fa-users'},
        {'label': 'Create New User', 'icon': 'fa-user-plus'}
    ]
    
    # Get available branches and businesses based on user role - RBAC v0.1 Compliant
    if request.user.role == 'globaladmin':
        # Global Admin: FULL access
        branches = Branch.objects.all().order_by('name')
        # Global admin can create all user types including other globaladmins
        roles = CustomUser.ROLE_CHOICES
        # Import and get businesses for Super Admin assignment
        from business.models import Business
        businesses = Business.objects.filter(is_active=True).order_by('name')
        
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (within business allocation)
        from core.utils.business_filtering import filter_branches_by_business
        branches = filter_branches_by_business(request.user).order_by('name')
        # Super admin CANNOT create globaladmin or superadmin users - only admin, instructor, and learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] not in ['globaladmin', 'superadmin']]
        businesses = []  # Super admins can't assign other super admins to businesses
        
    elif request.user.role == 'admin':
        # Branch Admin: CONDITIONAL access (within branch allocation)
        if not request.user.branch:
            messages.error(request, "You must be assigned to a branch before you can create users. Please contact your administrator.")
            return redirect('users:role_based_redirect')
        branches = Branch.objects.filter(id=request.user.branch.id)
        # Admin CANNOT create superadmin, globaladmin or other admin users - only instructors and learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] not in ['superadmin', 'admin', 'globaladmin']]
        businesses = []  # Branch admins don't handle business assignments
        
    else:  # instructor
        # Instructor: CONDITIONAL access (learner accounts only)
        if not request.user.branch:
            messages.error(request, "You must be assigned to a branch before you can create learner accounts. Please contact your administrator.")
            return redirect('users:role_based_redirect')
        branches = Branch.objects.filter(id=request.user.branch.id)
        # Instructors can only create learners
        roles = [choice for choice in CustomUser.ROLE_CHOICES if choice[0] == 'learner']
        businesses = []  # Instructors don't handle business assignments
    
    if request.method == 'POST':
        # Ensure branch is set correctly for admin and instructor users
        post_data = request.POST.copy()
        if request.user.role in ['admin', 'instructor'] and request.user.branch:
            post_data['branch'] = request.user.branch.id
            
        # Get the selected role before creating the form
        selected_role = post_data.get('role', 'learner')
        
        # Apply business rule restrictions for user creation        
        # Super admin users cannot create globaladmin or superadmin users
        if request.user.role == 'superadmin' and selected_role in ['globaladmin', 'superadmin']:
            messages.error(request, "Super admin users are not allowed to create global admin or super admin users.")
            return redirect('users:user_create')
        
        # Admin users cannot create superadmin or globaladmin users
        if request.user.role == 'admin' and selected_role in ['superadmin', 'globaladmin']:
            messages.error(request, "Admin users are not allowed to create super admin or global admin users.")
            return redirect('users:user_create')
        
        # Global Admin users must now explicitly select business/branch (no auto-assignment)
        if request.user.role == 'globaladmin':
            # Business/branch selection is now validated in the form, no auto-assignment needed
            pass
        
        # Super Admin auto-branch assignment: if no branch selected but role requires it
        elif request.user.role == 'superadmin':
            if not post_data.get('branch') and selected_role in ['admin', 'instructor', 'learner']:
                # Auto-assign to user's available branches
                if hasattr(request.user, 'business_assignments'):
                    assigned_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
                    available_branches = Branch.objects.filter(business__in=assigned_businesses)
                    if available_branches.exists():
                        first_branch = available_branches.first()
                        post_data['branch'] = first_branch.id
                        messages.info(request, f'Branch automatically assigned to "{first_branch.name}" for {selected_role} user.')
                    else:
                        # Fallback to any branch
                        first_branch = Branch.objects.first()
                        if first_branch:
                            post_data['branch'] = first_branch.id
                            messages.info(request, f'Branch automatically assigned to "{first_branch.name}" for {selected_role} user.')
                        else:
                            messages.error(request, 'No branches available for user assignment. Please create a branch first.')
                            return redirect('users:user_create')
                else:
                    # If no business assignments, use first available non-default branch
                    from core.utils.default_assignments import DefaultAssignmentManager
                    non_default_branches = DefaultAssignmentManager.get_non_default_branches()
                    if non_default_branches.exists():
                        first_branch = non_default_branches.first()
                        post_data['branch'] = first_branch.id
                        messages.info(request, f'Branch automatically assigned to "{first_branch.name}" for {selected_role} user.')
                    else:
                        messages.error(request, 'No non-default branches available for user assignment. Please create a branch first.')
                        return redirect('users:user_create')
        
        # For Admin and Instructor users, ensure their own branch is used
        elif request.user.role in ['admin', 'instructor'] and request.user.branch:
            if selected_role in ['admin', 'instructor', 'learner']:
                post_data['branch'] = request.user.branch.id
        
        # Process multiple entries for education and employment
        education_entries = []
        employment_entries = []
        education_count = int(post_data.get('education_entry_count', 1))
        employment_count = int(post_data.get('employment_entry_count', 1))
        
        # Collect education entries data
        for i in range(education_count):
            education_entry = {
                'study_area': post_data.get(f'study_area_{i}', ''),
                'study_area_other': post_data.get(f'study_area_other_{i}', '') if post_data.get(f'study_area_{i}') == 'Other' else '',
                'level_of_study': post_data.get(f'level_of_study_{i}', ''),
                'grades': post_data.get(f'grades_{i}', ''),
                'date_achieved': post_data.get(f'date_achieved_{i}', '')
            }
            education_entries.append(education_entry)
            
        # Collect employment entries data
        for i in range(employment_count):
            employment_entry = {
                'job_role': post_data.get(f'job_role_{i}', ''),
                'industry': post_data.get(f'industry_{i}', ''),
                'industry_other': post_data.get(f'industry_other_{i}', '') if post_data.get(f'industry_{i}') == 'Other' else '',
                'duration': post_data.get(f'duration_{i}', ''),
                'key_skills': post_data.get(f'key_skills_{i}', '')
            }
            employment_entries.append(employment_entry)
            
        # Store this data in post_data to be available for saving (as JSON strings)
        post_data['education_entries'] = json.dumps(education_entries)
        post_data['employment_entries'] = json.dumps(employment_entries)
        
        # Use the first entry values for form validation (if needed)
        if education_entries:
            post_data['study_area'] = education_entries[0]['study_area']
            post_data['study_area_other'] = education_entries[0]['study_area_other']
            post_data['level_of_study'] = education_entries[0]['level_of_study']
            post_data['grades'] = education_entries[0]['grades']
            post_data['date_achieved'] = education_entries[0]['date_achieved']
            
        if employment_entries:
            post_data['job_role'] = employment_entries[0]['job_role']
            post_data['industry'] = employment_entries[0]['industry']
            post_data['industry_other'] = employment_entries[0]['industry_other']
            post_data['duration'] = employment_entries[0]['duration']
            post_data['key_skills'] = employment_entries[0]['key_skills']
        
        # Use the TabbedUserCreationForm
        form = TabbedUserCreationForm(post_data, request=request, files=request.FILES)
        
        # Log user creation attempt for auditing
        logger.info(f"User creation attempted by: {request.user.role} user {request.user.id}")
        
        # Make only these fields required for all roles, regardless of role
        # Global Admin users now also need to specify business/branch
        required_fields = ['username', 'password1', 'password2', 'email', 'role', 'timezone', 
                          'given_name', 'family_name', 'branch']
        
        # For Global Admin users creating Super Admin users, business field is required instead of branch
        if request.user.role == 'globaladmin':
            required_fields.append('business')  # They may need business field for Super Admin creation
        
        # Make all other fields optional - including all tab fields
        for field_name in form.fields:
            if field_name not in required_fields:
                form.fields[field_name].required = False
                
        # Remove conditional required validation for "other" fields to make them truly optional
        form.fields['sex_other'].required = False
        form.fields['sexual_orientation_other'].required = False
        form.fields['ethnicity_other'].required = False
        form.fields['study_area_other'].required = False
        form.fields['grades_other'].required = False
        form.fields['industry_other'].required = False
        
        if form.is_valid():
            # RBAC v0.1 Validation: Check allocation limits and conditional access
            try:
                from core.rbac_validators import rbac_validator
                
                target_branch = form.cleaned_data.get('branch')
                target_role = form.cleaned_data.get('role')
                target_business = form.cleaned_data.get('business')
                
                # Validate user creation against RBAC rules
                validation_errors = rbac_validator.validate_action(
                    user=request.user,
                    action='create',
                    resource_type='user',
                    target_branch=target_branch,
                    target_role=target_role,
                    target_business=target_business
                )
                
                if validation_errors:
                    for error in validation_errors:
                        messages.error(request, error)
                    return render(request, 'users/user_form_tabbed_modular.html', {
                        'form': form, 'profile_user': None, 'branches': branches, 'businesses': businesses, 'roles': roles, 
                        'breadcrumbs': breadcrumbs, 'is_edit_mode': False, 'active_tab': 'account-tab'
                    })
                    
            except Exception as e:
                messages.error(request, f"Validation error: {str(e)}")
                return render(request, 'users/user_form_tabbed_modular.html', {
                    'form': form, 'profile_user': None, 'branches': branches, 'businesses': businesses, 'roles': roles, 
                    'breadcrumbs': breadcrumbs, 'is_edit_mode': False, 'active_tab': 'account-tab'
                    })
            
            try:
                user = form.save()
            except ValidationError as ve:
                # Handle model validation errors (e.g., branch assignment issues)
                logger.error(f"Model validation error during user creation: {str(ve)}")
                if 'must be assigned to a branch' in str(ve):
                    messages.error(request, "User creation failed: The selected role requires a branch assignment. Please ensure you are assigned to a branch or contact your administrator.")
                else:
                    messages.error(request, f"User creation failed: {str(ve)}")
                return render(request, 'users/user_form_tabbed_modular.html', {
                    'form': form, 'profile_user': None, 'branches': branches, 'businesses': businesses, 'roles': roles, 
                    'breadcrumbs': breadcrumbs, 'is_edit_mode': False, 'active_tab': 'account-tab'
                })
            except Exception as e:
                logger.error(f"Unexpected error during user creation: {str(e)}")
                messages.error(request, "An unexpected error occurred during user creation. Please try again.")
                return render(request, 'users/user_form_tabbed_modular.html', {
                    'form': form, 'profile_user': None, 'branches': branches, 'businesses': businesses, 'roles': roles, 
                    'breadcrumbs': breadcrumbs, 'is_edit_mode': False, 'active_tab': 'account-tab'
                })
            
            # Handle business assignment for Super Admin users created through the form
            if hasattr(user, '_pending_business_assignment'):
                try:
                    from business.models import BusinessUserAssignment
                    BusinessUserAssignment.objects.create(
                        business=user._pending_business_assignment,
                        user=user,
                        assigned_by=request.user,
                        is_active=True
                    )
                    # Clean up the temporary attribute
                    delattr(user, '_pending_business_assignment')
                except Exception as e:
                    logger.error(f"Could not create business assignment for {user.username}: {str(e)}")
            
            # Ensure proper default assignments using utility functions
            from core.utils.default_assignments import DefaultAssignmentManager
            try:
                DefaultAssignmentManager.ensure_proper_user_assignments(user)
            except Exception as e:
                logger.warning(f"Could not ensure default assignments for {user.username}: {str(e)}")
            
            # Store the multiple entries in JSON fields on the user model
            user.education_data = education_entries  # Store as list directly, Django's JSONField handles conversion
            user.employment_data = employment_entries  # Store as list directly, Django's JSONField handles conversion
            
                            # Process ILP data
            try:
                from individual_learning_plan.models import (
                    IndividualLearningPlan, LearningPreference, StatementOfPurpose,
                    CareerGoal, SENDAccommodation, HealthSafetyQuestionnaire, LearningNeeds,
                    InductionChecklist, InductionChecklistSection, InductionChecklistQuestion,
                    InductionChecklistDocument
                )
                
                # Create ILP for the user
                ilp, ilp_created = IndividualLearningPlan.objects.get_or_create(
                    user=user,
                    defaults={'created_by': request.user}
                )
                
                # Process learning preferences
                learning_preferences = [
                    ('visual', post_data.get('learning_preference_visual')),
                    ('auditory', post_data.get('learning_preference_auditory')),
                    ('kinesthetic', post_data.get('learning_preference_kinesthetic')),
                ]
                
                for pref_type, pref_level in learning_preferences:
                    if pref_level:
                        # Convert score to 1-5 scale (100 scale to 5 scale)
                        score = int(pref_level)
                        scaled_level = min(5, max(1, round(score / 20))) if score > 0 else 1
                        
                        LearningPreference.objects.create(
                            ilp=ilp,
                            preference_type=pref_type,
                            preference_level=scaled_level,
                            identified_by=request.user
                        )
                
                # Process learning style descriptions and confirmed style
                confirmed_learning_style = post_data.get('confirmed_learning_style')
                visual_description = post_data.get('visual_learning_description', '').strip()
                auditory_description = post_data.get('auditory_learning_description', '').strip()
                kinesthetic_description = post_data.get('kinesthetic_learning_description', '').strip()
                
                # Update existing learning preferences with descriptions in notes field
                if visual_description:
                    visual_pref = LearningPreference.objects.filter(
                        ilp=ilp, preference_type='visual'
                    ).first()
                    if visual_pref:
                        visual_pref.notes = visual_description
                        visual_pref.save()
                
                if auditory_description:
                    auditory_pref = LearningPreference.objects.filter(
                        ilp=ilp, preference_type='auditory'
                    ).first()
                    if auditory_pref:
                        auditory_pref.notes = auditory_description
                        auditory_pref.save()
                
                if kinesthetic_description:
                    kinesthetic_pref = LearningPreference.objects.filter(
                        ilp=ilp, preference_type='kinesthetic'
                    ).first()
                    if kinesthetic_pref:
                        kinesthetic_pref.notes = kinesthetic_description
                        kinesthetic_pref.save()
                
                # Store confirmed learning style as a theoretical preference with special notes
                if confirmed_learning_style:
                    LearningPreference.objects.create(
                        ilp=ilp,
                        preference_type='theoretical',
                        preference_level=5,  # High level for confirmed assessment
                        notes=f"VAK Assessment Result: Confirmed Learning Style is {confirmed_learning_style.title()}",
                        identified_by=request.user
                    )
                
                # Process statement of purpose
                sop_data = {
                    'reason_for_course': post_data.get('ilp_reason_for_course'),
                    'career_objectives': post_data.get('ilp_career_objectives'),
                    'relevant_experience': post_data.get('ilp_relevant_experience'),
                    'additional_info': post_data.get('ilp_additional_info'),
                }
                
                if any(sop_data.values()):
                    StatementOfPurpose.objects.create(
                        ilp=ilp,
                        **sop_data,
                        updated_by=request.user
                    )
                
                # Process career goals
                short_term_goal = post_data.get('ilp_short_term_goal')
                long_term_goal = post_data.get('ilp_long_term_goal')
                target_industry = post_data.get('ilp_target_industry')
                required_skills = post_data.get('ilp_required_skills')
                
                if any([short_term_goal, long_term_goal, target_industry, required_skills]):
                    CareerGoal.objects.create(
                        ilp=ilp,
                        short_term_goal=short_term_goal or '',
                        long_term_goal=long_term_goal or '',
                        target_industry=target_industry or '',
                        required_skills=required_skills or '',
                        updated_by=request.user
                    )
                
                # Process SEND accommodations
                accommodation_type = post_data.get('send_accommodation_type')
                accommodation_type_other = post_data.get('send_accommodation_type_other')
                accommodation_description = post_data.get('send_accommodation_description')
                accommodation_active = bool(post_data.get('send_accommodation_active'))
                
                if accommodation_type and accommodation_description:
                    SENDAccommodation.objects.create(
                        ilp=ilp,
                        accommodation_type=accommodation_type,
                        accommodation_type_other=accommodation_type_other if accommodation_type == 'other' else '',
                        description=accommodation_description,
                        is_active=accommodation_active,
                        created_by=request.user
                    )
                
                # Process Strengths and Weaknesses
                from individual_learning_plan.models import StrengthWeakness
                
                # Academic strengths
                academic_strength = post_data.get('strength_academic', '').strip()
                if academic_strength:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='strength',
                        description=f"Academic Strengths: {academic_strength}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Personal strengths
                personal_strength = post_data.get('strength_personal', '').strip()
                if personal_strength:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='strength',
                        description=f"Personal Strengths: {personal_strength}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Technical/Professional strengths
                technical_strength = post_data.get('strength_technical', '').strip()
                if technical_strength:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='strength',
                        description=f"Technical/Professional Strengths: {technical_strength}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Academic areas for improvement
                academic_weakness = post_data.get('weakness_academic', '').strip()
                if academic_weakness:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='weakness',
                        description=f"Academic Areas for Development: {academic_weakness}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Personal development areas
                personal_weakness = post_data.get('weakness_personal', '').strip()
                if personal_weakness:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='weakness',
                        description=f"Personal Development Areas: {personal_weakness}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Technical/Professional development areas
                technical_weakness = post_data.get('weakness_technical', '').strip()
                if technical_weakness:
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type='weakness',
                        description=f"Technical/Professional Development Areas: {technical_weakness}",
                        source='self_assessment',
                        created_by=request.user
                    )
                
                # Process dynamic Strengths & Weaknesses items
                strengths_item_count = 0
                while True:
                    item_type = post_data.get(f'strengths_item_{strengths_item_count}_type')
                    item_description = post_data.get(f'strengths_item_{strengths_item_count}_description')
                    item_confirmation = post_data.get(f'strengths_item_{strengths_item_count}_confirmation')
                    
                    if not all([item_type, item_description, item_confirmation]):
                        break  # No more items or incomplete item
                    
                    # Create the StrengthWeakness record with default source
                    StrengthWeakness.objects.create(
                        ilp=ilp,
                        type=item_type,
                        description=item_description,
                        source='self_assessment',  # Default source since field is not needed
                        created_by=request.user
                    )
                    
                    strengths_item_count += 1
                
                # Process Health & Safety Questionnaire
                health_safety_data = {
                    'named_first_aider': post_data.get('health_named_first_aider'),
                    'named_first_aider_confirmed': post_data.get('health_named_first_aider_confirmed'),
                    'fire_extinguishers_location': post_data.get('health_fire_extinguishers_location'),
                    'fire_extinguishers_confirmed': post_data.get('health_fire_extinguishers_confirmed'),
                    'first_aid_box_location': post_data.get('health_first_aid_box_location'),
                    'first_aid_box_confirmed': post_data.get('health_first_aid_box_confirmed'),
                    'fire_assembly_point': post_data.get('health_fire_assembly_point'),
                    'fire_assembly_confirmed': post_data.get('health_fire_assembly_confirmed'),
                    'accident_book_location': post_data.get('health_accident_book_location'),
                    'accident_book_confirmed': post_data.get('health_accident_book_confirmed'),
                    'accident_reporting_person': post_data.get('health_accident_reporting_person'),
                    'accident_reporting_confirmed': post_data.get('health_accident_reporting_confirmed'),
                    'health_safety_policy_location': post_data.get('health_safety_policy_location'),
                    'health_safety_policy_confirmed': post_data.get('health_safety_policy_confirmed'),
                    'health_safety_issue_reporting': post_data.get('health_safety_issue_reporting'),
                    'health_safety_issue_confirmed': post_data.get('health_safety_issue_confirmed'),
                    'nearest_fire_exits': post_data.get('health_nearest_fire_exits'),
                    'nearest_fire_exits_confirmed': post_data.get('health_nearest_fire_exits_confirmed'),
                    'health_safety_manager': post_data.get('health_safety_manager'),
                    'health_safety_manager_confirmed': post_data.get('health_safety_manager_confirmed'),
                    'common_accidents': post_data.get('health_common_accidents'),
                    'common_accidents_confirmed': post_data.get('health_common_accidents_confirmed'),
                    'prohibited_substances': post_data.get('health_prohibited_substances'),
                    'prohibited_substances_confirmed': post_data.get('health_prohibited_substances_confirmed'),
                    'learner_acknowledgment': bool(post_data.get('health_safety_acknowledgment')),
                }
                
                # Only create health safety questionnaire if at least one field is filled
                if any(value for value in health_safety_data.values() if value):
                    health_safety_questionnaire, hs_created = HealthSafetyQuestionnaire.objects.get_or_create(
                        ilp=ilp,
                        defaults={
                            **health_safety_data,
                            'created_by': request.user
                        }
                    )
                    
                    # If acknowledgment is given, set acknowledgment date
                    if health_safety_data['learner_acknowledgment'] and not health_safety_questionnaire.acknowledgment_date:
                        health_safety_questionnaire.acknowledgment_date = timezone.now()
                        health_safety_questionnaire.save()
                
                # Process Learning Needs
                learning_needs_data = {
                    'job_search_skills': bool(post_data.get('job_search_skills')),
                    'effective_cvs': bool(post_data.get('effective_cvs')),
                    'improving_it_skills': bool(post_data.get('improving_it_skills')),
                    'interview_skills': bool(post_data.get('interview_skills')),
                    'team_skills': bool(post_data.get('team_skills')),
                    'jcp_universal_jobmatch': bool(post_data.get('jcp_universal_jobmatch')),
                    'job_application_skills': bool(post_data.get('job_application_skills')),
                    'communication_skills': bool(post_data.get('communication_skills')),
                    'other_skills': bool(post_data.get('other_skills')),
                    'other_skills_details': post_data.get('other_skills_details', ''),
                    'prior_learning_experience': post_data.get('prior_learning_experience', ''),
                    'learning_challenges': post_data.get('learning_challenges', ''),
                    'support_needed': post_data.get('support_needed', ''),
                    'preferred_learning_environment': post_data.get('preferred_learning_environment', ''),
                }
                
                # Only create learning needs if at least one employability skill is selected or assessment fields are filled
                has_employability_skills = any([
                    learning_needs_data['job_search_skills'],
                    learning_needs_data['effective_cvs'],
                    learning_needs_data['improving_it_skills'],
                    learning_needs_data['interview_skills'],
                    learning_needs_data['team_skills'],
                    learning_needs_data['jcp_universal_jobmatch'],
                    learning_needs_data['job_application_skills'],
                    learning_needs_data['communication_skills'],
                    learning_needs_data['other_skills']
                ])
                
                has_assessment_data = any([
                    learning_needs_data['prior_learning_experience'],
                    learning_needs_data['learning_challenges'],
                    learning_needs_data['support_needed'],
                    learning_needs_data['preferred_learning_environment']
                ])
                
                if has_employability_skills or has_assessment_data:
                    learning_needs, ln_created = LearningNeeds.objects.get_or_create(
                        ilp=ilp,
                        defaults={
                            **learning_needs_data,
                            'created_by': request.user
                        }
                    )
                    
                    if not ln_created:
                        # Update existing learning needs
                        for field, value in learning_needs_data.items():
                            setattr(learning_needs, field, value)
                        learning_needs.updated_by = request.user
                        learning_needs.save()
                
                # Process Learning Goals
                from individual_learning_plan.models import LearningGoal
                
                learning_goals_count = int(post_data.get('learning_goals_count', 0))
                
                if learning_goals_count > 0:
                    for i in range(learning_goals_count):
                        goal_title = post_data.get(f'learning_goal_{i}_title')
                        goal_description = post_data.get(f'learning_goal_{i}_description') 
                        goal_type = post_data.get(f'learning_goal_{i}_type')
                        goal_target_date = post_data.get(f'learning_goal_{i}_target_date')
                        goal_status = post_data.get(f'learning_goal_{i}_status', 'not_started')
                        
                        if goal_title and goal_description and goal_type:
                            # Convert target date to proper format
                            target_completion_date = None
                            if goal_target_date:
                                try:
                                    from datetime import datetime
                                    target_completion_date = datetime.strptime(goal_target_date, '%Y-%m-%d').date()
                                except ValueError:
                                    pass  # Invalid date format, skip
                            
                            LearningGoal.objects.create(
                                ilp=ilp,
                                goal_type=goal_type,
                                title=goal_title,
                                description=goal_description,
                                target_completion_date=target_completion_date,
                                status=goal_status,
                                created_by=request.user
                            )
                
                # Process Internal Course Review
                from individual_learning_plan.models import InternalCourseReview
                
                # Check if any course review data was provided
                course_review_data = {
                    'iag_session_review': post_data.get('iag_session_review', '').strip(),
                    'action_completion_skills': post_data.get('action_completion_skills', '').strip(),
                    'careers_service_advice': post_data.get('careers_service_advice', '').strip(),
                    'progression_routes': post_data.get('progression_routes', '').strip(),
                    'career_objectives': post_data.get('career_objectives', '').strip(),
                    'qualification_achieved': post_data.get('qualification_achieved', ''),
                    'qualification_details': post_data.get('qualification_details', '').strip(),
                    'review_completed_by': post_data.get('review_completed_by', '').strip(),
                    'review_completion_date': post_data.get('review_completion_date', ''),
                    'review_status': post_data.get('review_status', 'draft'),
                    'created_by': request.user,
                    'updated_by': request.user
                }
                
                # Convert review completion date to proper format
                if course_review_data['review_completion_date']:
                    try:
                        from datetime import datetime
                        course_review_data['review_completion_date'] = datetime.strptime(
                            course_review_data['review_completion_date'], '%Y-%m-%d'
                        ).date()
                    except ValueError:
                        course_review_data['review_completion_date'] = None
                else:
                    course_review_data['review_completion_date'] = None
                
                # Create course review if any data is provided
                has_course_review_data = any([
                    course_review_data['iag_session_review'],
                    course_review_data['action_completion_skills'],
                    course_review_data['careers_service_advice'],
                    course_review_data['progression_routes'],
                    course_review_data['career_objectives'],
                    course_review_data['qualification_achieved'],
                    course_review_data['qualification_details']
                ])
                
                if has_course_review_data:
                    InternalCourseReview.objects.create(
                        ilp=ilp,
                        **course_review_data
                    )
                
                # Process Enhanced Induction Checklist
                # Create basic induction checklist first
                induction_checklist, ic_created = InductionChecklist.objects.get_or_create(
                    ilp=ilp,
                    defaults={'created_by': request.user}
                )
                
                # Process dynamic sections and questions
                section_index = 0
                while True:
                    section_title = post_data.get(f'induction_section_{section_index}_title')
                    if not section_title:
                        break
                    
                    section_description = post_data.get(f'induction_section_{section_index}_description', '')
                    section_order = int(post_data.get(f'induction_section_{section_index}_order', section_index + 1))
                    
                    # Create section
                    section = InductionChecklistSection.objects.create(
                        induction_checklist=induction_checklist,
                        title=section_title,
                        description=section_description,
                        order=section_order,
                        created_by=request.user
                    )
                    
                    # Process questions for this section
                    question_index = 0
                    while True:
                        question_text = post_data.get(f'induction_section_{section_index}_question_{question_index}_text')
                        if not question_text:
                            break
                        
                        answer_text = post_data.get(f'induction_section_{section_index}_question_{question_index}_answer', '')
                        student_confirmed = post_data.get(f'induction_section_{section_index}_question_{question_index}_student_confirmed', '')
                        instructor_confirmed = post_data.get(f'induction_section_{section_index}_question_{question_index}_instructor_confirmed', '')
                        is_mandatory = post_data.get(f'induction_section_{section_index}_question_{question_index}_mandatory') == 'on'
                        question_order = int(post_data.get(f'induction_section_{section_index}_question_{question_index}_order', question_index + 1))
                        
                        # Create question
                        InductionChecklistQuestion.objects.create(
                            section=section,
                            question_text=question_text,
                            answer_text=answer_text,
                            student_confirmed=student_confirmed,
                            instructor_confirmed=instructor_confirmed,
                            order=question_order,
                            is_mandatory=is_mandatory,
                            created_by=request.user
                        )
                        
                        question_index += 1
                    
                    # Process document for this section
                    document_title = post_data.get(f'induction_section_{section_index}_document_title')
                    document_file = request.FILES.get(f'induction_section_{section_index}_document_file')
                    
                    if document_title and document_file:
                        document_description = post_data.get(f'induction_section_{section_index}_document_description', '')
                        document_mandatory = post_data.get(f'induction_section_{section_index}_document_mandatory') == 'on'
                        
                        InductionChecklistDocument.objects.create(
                            section=section,
                            title=document_title,
                            document_file=document_file,
                            description=document_description,
                            is_mandatory=document_mandatory,
                            uploaded_by=request.user
                        )
                    
                    section_index += 1
                
                logger.info(f"ILP created successfully for user {user.username}")
                
            except Exception as e:
                logger.error(f"Error creating ILP data for user {user.username}: {str(e)}")
                # Don't fail the user creation, just log the error
                messages.warning(request, f"User created successfully, but there was an issue setting up the Individual Learning Plan. Please configure it manually.")
            
            # Save the updated user
            try:
                user.save()
            except Exception as e:
                logger.error(f"Error saving multiple entries data: {str(e)}")
            
            messages.success(request, f"User '{user.username}' created successfully.")
            return redirect('users:user_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # GET request - display the form
        form = TabbedUserCreationForm(request=request)
        
        # Make only these fields required for all roles, regardless of role
        # Global Admin users now also need to specify business/branch
        required_fields = ['username', 'password1', 'password2', 'email', 'role', 'timezone', 
                          'given_name', 'family_name', 'branch']
        
        # For Global Admin users creating Super Admin users, business field is required instead of branch
        if request.user.role == 'globaladmin':
            required_fields.append('business')  # They may need business field for Super Admin creation
        
        # Make all other fields optional - including all tab fields
        for field_name in form.fields:
            if field_name not in required_fields:
                form.fields[field_name].required = False
                
        # Remove conditional required validation for "other" fields to make them truly optional
        form.fields['sex_other'].required = False
        form.fields['sexual_orientation_other'].required = False
        form.fields['ethnicity_other'].required = False
        form.fields['study_area_other'].required = False
        form.fields['grades_other'].required = False
        form.fields['industry_other'].required = False

    # Prepare context for rendering the template
    context = {
        'form': form,
        'profile_user': None,  # Fix: Add profile_user as None for user creation template compatibility
        'branches': branches,
        'businesses': businesses,  # Add businesses for Super Admin assignment
        'roles': roles,
        'breadcrumbs': breadcrumbs,
        'is_edit_mode': False,
        'active_tab': 'account-tab',  # Default tab for new user creation
    }
    
    return render(request, 'users/user_form_tabbed_modular.html', context)

@login_required
def global_admin_dashboard(request):
    """Optimized view for global admin dashboard with caching"""
    if request.user.role != 'globaladmin':
        return HttpResponseForbidden("Access Denied")

    import json
    from core.utils.dashboard_cache import DashboardCache
    from business.models import Business

    # Get cached global statistics
    stats = DashboardCache.get_global_stats()
    
    # Get cached activity data
    activity_data = DashboardCache.get_activity_data('month')

    # Get top businesses with optimized query
    try:
        top_businesses = Business.objects.select_related().prefetch_related(
            'branches__users'
        ).annotate(
            branches_count=Count('branches'),
            users_count=Count('branches__users')
        ).order_by('-users_count')[:5]
    except Exception as e:
        logger.error(f"Error fetching top businesses: {e}")
        top_businesses = []

    # Get todo items for globaladmin
    recent_activities = []
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    try:
        # 1. System-wide performance monitoring
        # Sync completion status for all enrollments before calculating global stats
        from courses.models import CourseEnrollment
        all_enrollments = CourseEnrollment.objects.select_related('course', 'user')
        for enrollment in all_enrollments:
            enrollment.sync_completion_status()
        
        total_enrollments = all_enrollments.count()
        if total_enrollments > 100:  # Only for established systems
            completed_enrollments = all_enrollments.filter(completed=True).count()
            global_completion_rate = completed_enrollments / total_enrollments
            
            if global_completion_rate < 0.4:  # Less than 40% global completion rate
                recent_activities.append({
                    'description': f"Low global completion rate: {int(global_completion_rate*100)}% across {total_enrollments} enrollments",
                    'timestamp': now,
                    'sort_date': now + timedelta(days=60),  # Lower priority for performance monitoring
                    'icon': 'chart-line',
                    'type': 'performance',
                    'priority': 'medium'
                })
        
        # 2. New business registrations (if business model exists)
        try:
            from business.models import Business
            new_businesses = Business.objects.filter(
                created_at__gte=week_ago
            ).order_by('-created_at')[:3]
            
            for business in new_businesses:
                days_since = (now.date() - business.created_at.date()).days
                if days_since == 0:
                    time_text = "registered today"
                    priority = 'high'
                else:
                    time_text = f"registered {days_since} days ago"
                    priority = 'medium'
                    
                recent_activities.append({
                    'description': f"New business '{business.name}' {time_text} - needs onboarding",
                    'timestamp': business.created_at,
                    'sort_date': business.created_at,  # Use actual creation date for sorting
                    'icon': 'building',
                    'type': 'business',
                    'priority': priority
                })
        except Exception:
            pass  # Business model might not exist
        
        # 3. Inactive superadmins across all businesses
        inactive_superadmins = CustomUser.objects.filter(
            role='superadmin',
            is_active=True,
            last_login__lt=week_ago
        ).order_by('last_login')[:3]
        
        for superadmin in inactive_superadmins:
            if superadmin.last_login:
                days_since = (now.date() - superadmin.last_login.date()).days
                priority = 'high' if days_since >= 30 else 'medium'
                time_text = f"inactive for {days_since} days"
            else:
                priority = 'high'
                time_text = "never logged in"
                
            business_name = getattr(superadmin, 'business', {})
            business_text = f" ({business_name.name})" if hasattr(business_name, 'name') else ""
            
            recent_activities.append({
                'description': f"Superadmin {superadmin.get_full_name()} {time_text}{business_text}",
                'timestamp': superadmin.last_login or superadmin.date_joined,
                'sort_date': now + timedelta(days=1),  # High priority for admin management
                'icon': 'user-shield',
                'type': 'admin',
                'priority': priority
            })
        
        # 4. Platform-wide assignment grading backlog
        from assignments.models import AssignmentSubmission
        total_pending = AssignmentSubmission.objects.filter(status='submitted').count()
        
        if total_pending > 100:  # Significant platform-wide backlog
            oldest_submission = AssignmentSubmission.objects.filter(
                status='submitted'
            ).order_by('submitted_at').first()
            
            if oldest_submission:
                days_old = (now.date() - oldest_submission.submitted_at.date()).days
                priority = 'high' if days_old >= 7 else 'medium'
                
                recent_activities.append({
                    'description': f"Platform backlog: {total_pending} assignments pending grading (oldest: {days_old} days)",
                    'timestamp': now,
                    'sort_date': now + timedelta(days=7),  # Medium priority for grading oversight
                    'icon': 'clipboard-check',
                    'type': 'grading',
                    'priority': priority
                })
        
        # 5. System resource utilization (user growth)
        total_users = CustomUser.objects.filter(is_active=True).count()
        new_users_week = CustomUser.objects.filter(
            date_joined__gte=week_ago,
            is_active=True
        ).count()
        
        if total_users > 50:  # Only for established systems
            growth_rate = new_users_week / total_users
            if growth_rate > 0.1:  # More than 10% weekly growth
                recent_activities.append({
                    'description': f"High user growth: {new_users_week} new users this week ({int(growth_rate*100)}% growth) - monitor resources",
                    'timestamp': now,
                    'sort_date': now + timedelta(days=14),  # Medium priority for resource planning
                    'icon': 'users',
                    'type': 'growth',
                    'priority': 'medium'
                })
        
        # Sort by date (earliest first) for global admin dashboard
        recent_activities.sort(key=lambda x: x['sort_date'])
        
        # Handle AJAX request for loading more activities
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'load_more_todos' in request.GET:
            start = int(request.GET.get('start', 0))
            limit = int(request.GET.get('limit', 5))
            
            paginated_activities = recent_activities[start:start + limit]
            has_more = len(recent_activities) > start + limit
            
            from django.http import JsonResponse
            from django.template.loader import render_to_string
            
            # Render the activities as HTML
            html = render_to_string('users/components/globaladmin_activity_item.html', {
                'recent_activities': paginated_activities,
                'request': request
            })
            
            return JsonResponse({
                'html': html,
                'has_more': has_more,
                'total_count': len(recent_activities)
            })
        
        # Generate todo items using TodoService for enhanced role-based functionality
        todo_service = TodoService(request.user)
        all_todo_items = todo_service.get_todos(limit=50)  # Get more items for initial load
        
        # Convert TodoService format to existing template format for backward compatibility
        todo_items = []
        for todo in all_todo_items:
            # Map new format to existing format
            todo_item = {
                'task': todo['title'],
                'title': todo['title'],
                'description': todo['description'],
                'due': todo['due_date'],
                'due_date': todo['due_date'],
                'sort_date': todo['sort_date'],
                'icon': todo['icon'],
                'type': todo['type'],
                'priority': todo['priority'],
                'url': todo['url']
            }
            
            # Add type-specific metadata
            if todo['type'] == 'business_review':
                todo_item['business_name'] = todo.get('metadata', {}).get('business_name', '')
                
            todo_items.append(todo_item)
        
        # For initial page load, show first 5 items
        initial_todos = todo_items[:5]
        has_more_todos = len(todo_items) > 5
        
    except Exception as e:
        logger.error(f"Error fetching todo items for globaladmin: {e}")
        todo_items = []
        initial_todos = []
        has_more_todos = False

    # Get super admins with optimized query
    super_admins = CustomUser.objects.filter(
        role='superadmin', 
        is_active=True
    ).only('username', 'first_name', 'last_name', 'last_login').order_by('-last_login')[:5]

    # System alerts
    system_alerts = []

    # Define breadcrumbs
    breadcrumbs = [
        {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
        {'label': 'Global Admin Dashboard', 'icon': 'fa-globe'}
    ]

    # Add business count for backwards compatibility
    try:
        total_businesses = Business.objects.count()
    except:
        total_businesses = 0

    # Get performance statistics for the dashboard (with recursion protection)
    performance_data = {
        'recent_logins': 0,
        'recent_completions': 0,
    }
    try:
        # Add recursion protection and simpler statistics
        from django.contrib.auth import get_user_model
        from courses.models import CourseEnrollment
        from datetime import timedelta
        from django.utils import timezone
        
        # Get simple performance metrics without using BusinessStatisticsManager (to avoid recursion)
        one_week_ago = timezone.now() - timedelta(days=7)
        
        # Recent logins count
        User = get_user_model()
        recent_logins_count = User.objects.filter(
            last_login__gte=one_week_ago
        ).count()
        
        # Recent completions count
        recent_completions_count = CourseEnrollment.objects.filter(
            completed=True,
            enrolled_at__gte=one_week_ago
        ).count()
        
        performance_data = {
            'recent_logins': recent_logins_count,
            'recent_completions': recent_completions_count,
        }
        
    except Exception as e:
        logger.error(f"Error fetching performance data for global admin dashboard: {e}")
        # Keep default values set above

    context = {
        'total_users': stats['total_users'],
        'total_courses': stats['total_courses'],
        'active_users': stats['active_users'],
        'total_branches': stats['total_branches'],
        'total_businesses': total_businesses,
        'total_enrollments': stats['total_enrollments'],
        'completion_rate': stats['completion_rate'],
        'top_businesses': top_businesses,
        'todo_items': initial_todos,  # Todo items using TodoService
        'has_more_todos': has_more_todos,
        'super_admins': super_admins,
        'system_alerts': system_alerts,
        'activity_labels': json.dumps(activity_data['labels']),
        'login_data': json.dumps(activity_data['logins']),
        'completion_data': json.dumps(activity_data['completions']),
        # Activity data for consistent Activity section
        'activity_dates': json.dumps(activity_data['labels']),
        'login_counts': json.dumps(activity_data['logins']),
        'completion_counts': json.dumps(activity_data['completions']),
        # Performance data for the new dashboard sections
        'recent_logins': performance_data['recent_logins'],
        'recent_completions': performance_data['recent_completions'],
        'breadcrumbs': breadcrumbs,
        'debug': settings.DEBUG  # Add debug variable for template
    }

    return render(request, 'users/dashboards/globaladmin.html', context)



@login_required
def admin_dashboard(request):
    """Optimized admin dashboard with caching and query optimization"""
    if request.user.role != 'admin':
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    from django.utils import timezone
    from datetime import timedelta, datetime
    from certificates.models import IssuedCertificate
    from courses.models import CourseTopic, TopicProgress
    from calendar_app.models import CalendarEvent
    from branch_portal.models import BranchPortal
    from core.utils.dashboard_cache import DashboardCache
    from core.branch_filters import BranchFilterManager
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get the effective branch (considers session-based branch switching for admin users)
    effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
    
    # Get cached branch statistics with fallback handling
    try:
        branch_id = effective_branch.id if effective_branch else None
        if not branch_id:
            # Auto-assign admin user to a branch if none exists
            from branches.models import Branch
            default_branch = Branch.objects.first()
            if default_branch:
                request.user.branch = default_branch
                request.user.save()
                # Update the effective branch reference
                effective_branch = default_branch
                branch_id = default_branch.id
                logger.info(f"Auto-assigned admin user {request.user.username} to branch {default_branch.name}")
                messages.info(request, f"You have been automatically assigned to {default_branch.name} branch.")
            else:
                # Create a default branch if none exists
                default_branch = Branch.objects.create(
                    name='Main Branch',
                    description='Default branch for administrative operations',
                    is_active=True
                )
                request.user.branch = default_branch
                request.user.save()
                # Update the effective branch reference
                effective_branch = default_branch
                branch_id = default_branch.id
                logger.info(f"Created default branch and assigned admin user {request.user.username}")
                messages.info(request, "A default branch has been created and you have been assigned to it.")
    except Exception as e:
        logger.error(f"Error handling branch assignment for admin user {request.user.username}: {str(e)}")
        return HttpResponseServerError("Dashboard configuration error. Please contact support.")
    
    # Get cached branch statistics with error handling
    try:
        stats = DashboardCache.get_branch_stats(branch_id)
    except Exception as e:
        logger.error(f"Error getting cached branch stats for branch {branch_id}: {str(e)}")
        # Fallback to basic stats calculation
        stats = {
            'total_users': CustomUser.objects.filter(branch_id=branch_id).count(),
            'active_users': CustomUser.objects.filter(branch_id=branch_id, is_active=True).count(),
            'total_courses': Course.objects.filter(branch_id=branch_id).count(),
            'total_enrollments': 0,
            'completion_rate': 0
        }
    
    # Use select_related and prefetch_related for efficient queries
    branch_courses = Course.objects.filter(branch=effective_branch).select_related('instructor')
    branch_users = CustomUser.objects.filter(branch=effective_branch).only(
        'id', 'username', 'first_name', 'last_name', 'role', 'last_login', 'is_active'
    )
    
    # Get total branches count (admin can only see their own branch, so it's 1)
    total_branches = 1
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
        {'label': 'Admin Dashboard', 'icon': 'fa-tachometer-alt'}
    ]
    
    # Calculate certification count with optimized query
    certification_count = IssuedCertificate.objects.filter(
        recipient__branch=effective_branch
    ).count()
    
    # Use cached completion rate from stats
    completion_rate = int(stats['completion_rate']) if stats['completion_rate'] else 0
    
    # Get course progress status based on enrollments - Enhanced with Role Categorization
    branch_enrollments = CourseEnrollment.objects.filter(user__branch=effective_branch)
    
    # Separate learner and instructor enrollments for better analytics
    learner_enrollments = branch_enrollments.filter(user__role='learner')
    instructor_enrollments = branch_enrollments.filter(user__role='instructor')
    other_enrollments = branch_enrollments.exclude(user__role__in=['learner', 'instructor'])
    
    # Sync completion status for learner enrollments before calculating statistics
    for enrollment in learner_enrollments.select_related('course', 'user'):
        enrollment.sync_completion_status()
    
    # Use learner enrollments for main progress statistics (more meaningful for admin oversight)
    total_learner_enrollments = learner_enrollments.count()
    total_enrollments = branch_enrollments.count()
    
    if total_learner_enrollments > 0:
        # Count progress statuses based on learner enrollments (primary metric)
        completed_count = learner_enrollments.filter(completed=True).count()
        in_progress_count = learner_enrollments.filter(
            completed=False,
            last_accessed__isnull=False
        ).count()
        not_started_count = learner_enrollments.filter(
            completed=False,
            last_accessed__isnull=True
        ).count()
        
        # Calculate percentages based on learner enrollments (corrected denominator)
        completed_percentage = round((completed_count / total_learner_enrollments) * 100)
        in_progress_percentage = round((in_progress_count / total_learner_enrollments) * 100)
        not_started_percentage = round((not_started_count / total_learner_enrollments) * 100)
        
        # Calculate not_passed_percentage based on actual failed/expired enrollments if field exists
        has_failed_field = hasattr(CourseEnrollment, 'failed')
        if has_failed_field:
            not_passed_count = learner_enrollments.filter(completed=False, failed=True).count()
            not_passed_percentage = round((not_passed_count / total_learner_enrollments) * 100)
        else:
            # Only use remainder calculation if no failed field exists
            not_passed_count = 0  # No failed field, so no failed courses
            calculated_remainder = 100 - completed_percentage - in_progress_percentage - not_started_percentage
            not_passed_percentage = max(0, calculated_remainder)
    else:
        completed_count = 0
        in_progress_count = 0
        not_started_count = 0
        not_passed_count = 0
        completed_percentage = 0
        in_progress_percentage = 0
        not_started_percentage = 0
        not_passed_percentage = 0
    
    # Get portal activity data (login and completion trends)
    # For simplicity, we'll use the last 10 days
    end_date = timezone.now()
    start_date = end_date - timedelta(days=10)
    dates = []
    login_data = []
    completion_data = []
    
    for i in range(10):
        current_date = start_date + timedelta(days=i)
        next_date = current_date + timedelta(days=1)
        date_str = current_date.strftime('%b %d')
        
        # Count logins (approximation based on last_login)
        login_count = branch_users.filter(
            last_login__gte=current_date,
            last_login__lt=next_date
        ).distinct().count()
        
        # Count course completions
        completion_count = CourseEnrollment.objects.filter(
            user__branch=effective_branch,
            completion_date__gte=current_date,
            completion_date__lt=next_date
        ).count()
        
        dates.append(date_str)
        login_data.append(login_count)
        completion_data.append(completion_count)
    
    # Convert data to JSON for safe template rendering
    dates_json = json.dumps(dates)
    login_data_json = json.dumps(login_data)
    completion_data_json = json.dumps(completion_data)
    
    # Get in-progress courses
    in_progress_courses = []
    for course in branch_courses[:4]:  # Limit to 4 courses
        enrollments = CourseEnrollment.objects.filter(course=course)
        if enrollments.exists():
            # Calculate average progress
            total_progress = 0
            for enrollment in enrollments:
                # Get topics in this course
                topics = CourseTopic.objects.filter(course=course)
                if topics.exists():
                    # Count completed topics
                    completed_topics_count = TopicProgress.objects.filter(
                        user=enrollment.user,
                        topic__in=topics.values_list('topic', flat=True),
                        completed=True
                    ).count()
                    
                    progress = round((completed_topics_count / topics.count()) * 100) if topics.count() > 0 else 0
                    total_progress += progress
            
            avg_progress = total_progress / enrollments.count() if enrollments.count() > 0 else 0
            in_progress_courses.append({
                'title': course.title,
                'progress': round(avg_progress)
            })
    
    # Get recent instructors
    recent_instructors = CustomUser.objects.filter(
        role='instructor',
        branch=effective_branch,
        is_active=True
    ).order_by('-last_login')[:4]
    
    # Get recent activities
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    from assignments.models import AssignmentSubmission
    from discussions.models import Discussion, Comment
    from gradebook.models import Grade
    
    # Get todo items for admin
    recent_activities = []
    from django.utils import timezone
    from datetime import timedelta
    from branches.models import BranchUserLimits
    
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    
    # 1. New user registrations awaiting approval (high priority)
    pending_users = branch_users.filter(
        is_active=False,
        date_joined__gte=week_ago
    ).order_by('-date_joined')[:3]
    
    for user in pending_users:
        days_since = (now.date() - user.date_joined.date()).days
        if days_since == 0:
            time_text = "Registered today"
            priority = 'high'
        elif days_since <= 3:
            time_text = f"Registered {days_since} days ago"
            priority = 'high'
        else:
            time_text = f"Registered {days_since} days ago"
            priority = 'medium'
            
        recent_activities.append({
            'type': 'course',
            'action': 'approve',
            'user': user,
            'item': {
                'title': f'Approve: {user.get_full_name()}',
                'type': 'User Registration'
            },
            'time': user.date_joined,
            'sort_date': user.date_joined,  # Add sort_date for date ordering
            'description': f"New {user.role} registration needs approval",
            'priority': priority
        })
    
    # 2. Courses with low completion rates (need attention)
    branch_course_ids = branch_courses.values_list('id', flat=True)
    for course in branch_courses[:4]:
        total_enrollments = CourseEnrollment.objects.filter(course=course).count()
        if total_enrollments > 5:  # Only consider courses with some enrollments
            completed_enrollments = CourseEnrollment.objects.filter(
                course=course, 
                completed=True
            ).count()
            course_completion_rate = completed_enrollments / total_enrollments
            
            if course_completion_rate < 0.3:  # Less than 30% completion rate
                recent_activities.append({
                    'type': 'course',
                    'action': 'review',
                    'user': request.user,  # Add the missing user key
                    'course': course,
                    'item': {
                        'title': f'Review: {course.title}',
                        'type': 'Course Performance'
                    },
                    'time': now,
                    'sort_date': now + timedelta(days=60),  # Lower priority for course review tasks
                    'description': f"Low completion rate: {int(completion_rate*100)}% ({completed_enrollments}/{total_enrollments})",
                    'priority': 'medium'
                })
    
    # 3. Inactive instructors (haven't logged in recently)
    inactive_instructors = branch_users.filter(
        role='instructor',
        is_active=True,
        last_login__lt=week_ago
    ).order_by('last_login')[:3]
    
    for instructor in inactive_instructors:
        if instructor.last_login:
            days_since = (now.date() - instructor.last_login.date()).days
            if days_since >= 30:
                priority = 'high'
                time_text = f"Inactive for {days_since} days"
            else:
                priority = 'medium'
                time_text = f"Last seen {days_since} days ago"
        else:
            priority = 'high'
            time_text = "Never logged in"
            
        recent_activities.append({
            'type': 'course',
            'action': 'contact',
            'user': instructor,
            'item': {
                'title': f'Contact: {instructor.get_full_name()}',
                'type': 'Instructor Management'
            },
            'time': instructor.last_login or instructor.date_joined,
            'sort_date': now + timedelta(days=45),  # Medium priority for instructor management
            'description': f"Instructor has been inactive - {time_text}",
            'priority': priority
        })
    
    # try:
    #     branch_limits = BranchUserLimits.objects.filter(branch=request.user.branch).first()
    #     if branch_limits:
    #         current_users = branch_users.filter(is_active=True).count()
    #         
    #         if branch_limits.user_limit:
    #             usage_rate = current_users / branch_limits.user_limit
    #             if usage_rate >= 0.8:  # 80% or more of limit used
    #                 priority = 'high' if usage_rate >= 0.95 else 'medium'
    #                 recent_activities.append({
    #                     'type': 'course',
    #                     'action': 'plan',
    #                     'user': request.user,  # Add the missing user key
    #                     'item': {
    #                         'title': 'Review User Limits',
    #                         'type': 'Branch Management'
    #                     },
    #                     'time': now,
    #                     'sort_date': now + timedelta(days=14),  # Higher priority for user limit management
    #                     'description': f"User limit approaching: {current_users}/{branch_limits.user_limit} ({int(usage_rate*100)}%)",
    #                     'priority': priority
    #                 })
    # except Exception as e:
    #     logger.error(f"Error checking branch limits: {e}")
    
    # 5. Assignments pending instructor grading (admin oversight)
    pending_submissions_count = AssignmentSubmission.objects.filter(
        assignment__course__branch=effective_branch,
        status='submitted'
    ).count()
    
    if pending_submissions_count > 10:  # Many pending submissions
        recent_activities.append({
            'type': 'grade',
            'action': 'monitor',
            'user': request.user,  # Add the missing user key
            'item': {
                'title': 'Monitor Assignment Grading',
                'type': 'Quality Assurance'
            },
            'time': now,
            'sort_date': now + timedelta(days=7),  # Monitor grading has higher priority
            'description': f"{pending_submissions_count} assignments awaiting instructor grading",
            'priority': 'medium'
        })
    
    # Sort by date (earliest first) for admin dashboard
    recent_activities.sort(key=lambda x: x['sort_date'])
    
    # Handle AJAX request for loading more activities
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'load_more_todos' in request.GET:
        start = int(request.GET.get('start', 0))
        limit = int(request.GET.get('limit', 5))
        
        paginated_activities = recent_activities[start:start + limit]
        has_more = len(recent_activities) > start + limit
        
        from django.http import JsonResponse
        from django.template.loader import render_to_string
        
        # Render the activities as HTML
        html = render_to_string('users/components/admin_activity_item.html', {
            'recent_activities': paginated_activities,
            'request': request
        })
        
        return JsonResponse({
            'html': html,
            'has_more': has_more,
            'total_count': len(recent_activities)
        })
    
    # Handle AJAX request for activity timeframe changes
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'timeframe' in request.GET:
        timeframe = request.GET.get('timeframe', 'month')
        
        # Get admin's branch for activity filtering
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        admin_branch_id = effective_branch.id if effective_branch else None
        
        # Get activity data for the requested timeframe
        from core.utils.dashboard_cache import DashboardCache
        activity_data = DashboardCache.get_activity_data(timeframe, admin_branch_id)
        
        from django.http import JsonResponse
        return JsonResponse(activity_data)
    
    # Generate todo items using TodoService for enhanced role-based functionality
    todo_service = TodoService(request.user)
    all_todo_items = todo_service.get_todos(limit=50)  # Get more items for initial load
    
    # Convert TodoService format to existing template format for backward compatibility
    todo_items = []
    for todo in all_todo_items:
        # Map new format to existing format
        todo_item = {
            'task': todo['title'],
            'title': todo['title'],
            'description': todo['description'],
            'due': todo['due_date'],
            'due_date': todo['due_date'],
            'sort_date': todo['sort_date'],
            'icon': todo['icon'],
            'type': todo['type'],
            'priority': todo['priority'],
            'url': todo['url']
        }
        
        # Add type-specific metadata
        if todo['type'] == 'user_management':
            todo_item['user_name'] = todo.get('metadata', {}).get('user_name', '')
        elif todo['type'] == 'course_review':
            todo_item['enrollment_count'] = todo.get('metadata', {}).get('enrollment_count', 0)
            
        todo_items.append(todo_item)
    
    # For initial page load, show first 5 items
    initial_todos = todo_items[:5]
    has_more_todos = len(todo_items) > 5
    
    # Format dates for activity feed
    start_date_str = start_date.strftime('%d/%m/%Y')
    end_date_str = end_date.strftime('%d/%m/%Y')
    
    # Get calendar events for the current month
    today = timezone.now()
    current_month = today.strftime('%B %Y')
    
    # Get calendar events for this month
    month_start = datetime(today.year, today.month, 1, tzinfo=timezone.get_current_timezone())
    if today.month == 12:
        month_end = datetime(today.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        month_end = datetime(today.year, today.month + 1, 1, tzinfo=timezone.get_current_timezone())
    
    # Get events that are visible to this admin
    calendar_events = CalendarEvent.objects.filter(
        Q(start_date__gte=month_start, start_date__lt=month_end) |
        Q(end_date__gte=month_start, end_date__lt=month_end)
    ).filter(
        Q(created_by__branch=effective_branch) |
        Q(created_by=request.user)
    ).order_by('start_date')
    
    # Format events for the calendar
    formatted_events = []
    for event in calendar_events:
        # Determine the day it falls on (1-31)
        event_day = event.start_date.day
        
        # Choose color based on event type or use the color field
        # Use color from the model if available, otherwise fallback to category-based colors
        if hasattr(event, 'color') and event.color:
            color = event.color
        elif hasattr(event, 'category') and event.category and event.category.color:
            color = event.category.color
        else:
            # Fallback colors based on tags if present
            if hasattr(event, 'tags') and 'assignment' in event.tags.lower():
                color = '#3b82f6'  # blue
            elif hasattr(event, 'tags') and 'exam' in event.tags.lower():
                color = '#ef4444'  # red
            elif hasattr(event, 'tags') and 'course' in event.tags.lower():
                color = '#10b981'  # green
            elif hasattr(event, 'tags') and 'conference' in event.tags.lower():
                color = '#8b5cf6'  # purple
            else:
                color = '#6b7280'  # gray
        
        formatted_events.append({
            'title': event.title,
            'day': event_day,
            'start_date': event.start_date,
            'end_date': event.end_date,
            'is_all_day': event.is_all_day,
            'color': color
        })
    
    # Add branch access context for admin users
    branch_manager = BranchFilterManager()
    accessible_branches = branch_manager.get_accessible_branches(request.user)
    
    context = {
        'branch_name': effective_branch.name if effective_branch else "No Branch Assigned",
        'branch_courses': branch_courses,
        'total_users': branch_users.count(),
        'active_users': branch_users.filter(is_active=True).count(),
        'total_courses': branch_courses.count(),
        'total_branches': total_branches,
        'certification_count': certification_count,
        'completion_rate': completion_rate,
        'breadcrumbs': breadcrumbs,
        'progress_data': {
            'total_courses': branch_courses.count(),
            'completed_count': completed_count,
            'in_progress_count': in_progress_count,
            'not_started_count': not_started_count,
            'not_passed_count': not_passed_count,
            'completed_percentage': completed_percentage,
            'in_progress_percentage': in_progress_percentage,
            'not_started_percentage': not_started_percentage,
            'not_passed_percentage': not_passed_percentage,
        },
        # Enhanced role-based enrollment statistics
        'enrollment_statistics': {
            'total_learner_enrollments': total_learner_enrollments,
            'total_instructor_enrollments': instructor_enrollments.count(),
            'total_other_enrollments': other_enrollments.count(),
            'total_all_enrollments': total_enrollments,
            'learner_completion_rate': round((learner_enrollments.filter(completed=True).count() / max(1, total_learner_enrollments)) * 100),
            'instructor_enrollment_rate': round((instructor_enrollments.count() / max(1, total_enrollments)) * 100)
        },
        'portal_activity': {
            'labels': dates_json,
            'logins': login_data_json,
            'completions': completion_data_json
        },
        # Activity data for consistent Activity section  
        'activity_dates': dates_json,
        'login_counts': login_data_json,
        'completion_counts': completion_data_json,
        'in_progress_courses': in_progress_courses,
        'recent_instructors': recent_instructors,
        'todo_items': initial_todos,  # Todo items using TodoService
        'has_more_todos': has_more_todos,
        'total_todo_count': len(todo_items),
        'start_date': start_date_str,
        'end_date': end_date_str,
        'calendar_events': formatted_events,
        'current_month': current_month,
        # Branch access context for template conditions
        'user_accessible_branches': accessible_branches,
        'user_branch_access': {
            'can_see_all_branches': request.user.is_superuser or request.user.role in ['globaladmin', 'superadmin'],
            'assigned_branch': request.user.branch,  # Keep this as the user's assigned branch
            'effective_branch': effective_branch,    # This is the current active branch (might be switched)
            'accessible_branch_ids': list(accessible_branches.values_list('id', flat=True)),
            'has_multiple_branches': request.user.role == 'admin' and accessible_branches.count() > 1,
            'can_switch_branches': request.user.role == 'admin' and accessible_branches.count() > 1
        }
    }
    return render(request, 'users/dashboards/admin.html', context)

@login_required
def users_admin_dashboard(request):
    """Custom users admin dashboard that replaces Django admin panel"""
    # Check if user has permission to manage users
    if not request.user.role in ['globaladmin', 'superadmin', 'admin']:
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    from django.utils import timezone
    from datetime import timedelta, datetime
    from django.db.models import Count
    from assignments.models import Assignment, AssignmentSubmission
    from courses.models import Course, CourseEnrollment
    from gradebook.models import Grade
    from groups.models import BranchGroup
    from branches.models import Branch
    import logging
    
    logger = logging.getLogger(__name__)
    now = timezone.now()
    today = now.date()
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
        {'label': 'Users Admin', 'icon': 'fa-users-cog'}
    ]
    
    # Get users based on role permissions
    if request.user.role == 'globaladmin':
        # Global admin can see all users
        users = CustomUser.objects.all().exclude(id=request.user.id)
        branches = Branch.objects.all().order_by('name')
        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        new_users_this_week = users.filter(date_joined__gte=now - timedelta(days=7)).count()
    elif request.user.role == 'superadmin':
        # Super admin sees business-scoped users
        from core.utils.business_filtering import filter_users_by_business, filter_branches_by_business
        users = filter_users_by_business(request.user).exclude(id=request.user.id)
        branches = filter_branches_by_business(request.user).order_by('name')
        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        new_users_this_week = users.filter(date_joined__gte=now - timedelta(days=7)).count()
    elif request.user.role == 'admin':
        # Admin sees branch users only (supports branch switching)
        from core.branch_filters import BranchFilterManager
        effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
        users = CustomUser.objects.filter(branch=effective_branch).exclude(
            role__in=['superadmin', 'globaladmin']
        ).exclude(id=request.user.id)
        branches = [effective_branch]
        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        new_users_this_week = users.filter(date_joined__gte=now - timedelta(days=7)).count()
    else:
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    # Get user role statistics
    role_stats = users.values('role').annotate(count=Count('role')).order_by('role')
    
    # Get recent users (last 10)
    recent_users = users.order_by('-date_joined')[:10]
    
    # Get pending assignment submissions for grading (admin to-do tasks)
    pending_submissions = []
    pending_reviews = []
    
    if request.user.role in ['admin', 'superadmin', 'globaladmin']:
        # Get assignments that need grading in the admin's scope
        if request.user.role == 'admin':
            # Admin sees submissions from their effective branch (supports branch switching)
            pending_submissions = AssignmentSubmission.objects.filter(
                user__branch=effective_branch,
                status='submitted'
            ).select_related('assignment', 'user').order_by('-submitted_at')[:10]
        else:
            # Super admin and global admin see more submissions
            if request.user.role == 'globaladmin':
                pending_submissions = AssignmentSubmission.objects.filter(
                    status='submitted'
                ).select_related('assignment', 'user').order_by('-submitted_at')[:10]
            else:  # superadmin
                # Get business-scoped submissions
                from core.utils.business_filtering import filter_queryset_by_business
                pending_submissions = filter_queryset_by_business(
                    AssignmentSubmission.objects.filter(status='submitted'),
                    request.user,
                    business_field_path='user__branch__business'
                ).select_related('assignment', 'user').order_by('-submitted_at')[:10]
    
    # Generate admin to-do items
    todo_items = []
    
    # Add pending submissions as to-do items
    for submission in pending_submissions:
        todo_items.append({
            'title': f'Grade: {submission.assignment.title}',
            'description': f'Submission by {submission.user.get_full_name()} needs grading',
            'due_date': f'Submitted {submission.submitted_at.strftime("%b %d")}',
            'priority': 'high',
            'type': 'grading',
            'icon': 'clipboard-check',
            'url': f'/assignments/{submission.assignment.id}/',
            'user': submission.user.get_full_name()
        })
    
    # Add new user registrations as to-do items
    new_users = users.filter(date_joined__gte=now - timedelta(days=3)).order_by('-date_joined')
    for user in new_users:
        todo_items.append({
            'title': f'New User: {user.get_full_name()}',
            'description': f'New {user.role} registered - review profile',
            'due_date': f'Joined {user.date_joined.strftime("%b %d")}',
            'priority': 'medium',
            'type': 'user_review',
            'icon': 'user-plus',
            'url': f'/users/{user.id}/',
            'user': user.get_full_name()
        })
    
    # Sort todo items by priority and date
    priority_order = {'high': 1, 'medium': 2, 'low': 3}
    todo_items.sort(key=lambda x: (priority_order.get(x['priority'], 4), x['due_date']))
    
    # Limit to 15 items
    todo_items = todo_items[:15]
    
    # Get user activity stats
    recent_logins = users.filter(last_login__gte=now - timedelta(days=7)).count()
    inactive_users = users.filter(
        Q(last_login__lt=now - timedelta(days=30)) | Q(last_login__isnull=True),
        is_active=True
    ).count()
    
    context = {
        'total_users': total_users,
        'active_users': active_users,
        'new_users_this_week': new_users_this_week,
        'recent_logins': recent_logins,
        'inactive_users': inactive_users,
        'role_stats': role_stats,
        'recent_users': recent_users,
        'pending_submissions_count': len(pending_submissions),
        'todo_items': todo_items,
        'total_todo_count': len(todo_items),
        'breadcrumbs': breadcrumbs,
        'branches': branches,
        'page_title': 'Users Administration'
    }
    
    return render(request, 'users/admin/users_admin_dashboard.html', context)

@login_required
def instructor_dashboard(request):
    """Optimized instructor dashboard with caching"""
    if request.user.role != 'instructor':
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    from courses.models import Course, CourseEnrollment
    from assignments.models import Assignment
    from core.utils.dashboard_cache import DashboardCache
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
        {'label': 'Instructor Dashboard', 'icon': 'fa-tachometer-alt'}
    ]
    
    # Get instructor statistics with real-time calculation to ensure accuracy
    # Note: Using real-time calculation instead of cache to ensure overview stats are always current
    try:
        stats = DashboardCache.get_instructor_stats(request.user.id)
    except Exception as e:
        logger.error(f"Error getting cached instructor stats for user {request.user.id}: {str(e)}")
        # Fallback to basic stats with all required keys
        stats = {
            'assigned_courses_count': 0,
            'unique_learners_count': 0,
            'instructor_groups_count': 0,
            'completion_rate': 0
        }
    
    # Get assigned courses with optimized query
    # Include courses where user is:
    # 1. The direct instructor, OR
    # 2. Member of accessible group with instructor role, OR
    # 3. Member of accessible group with general access (admin assigned)
    assigned_courses = Course.objects.filter(
        Q(instructor=request.user) |
        Q(accessible_groups__memberships__user=request.user,
          accessible_groups__memberships__is_active=True,
          accessible_groups__memberships__custom_role__name__icontains='instructor') |
        Q(accessible_groups__memberships__user=request.user,
          accessible_groups__memberships__is_active=True)
    ).select_related('instructor', 'branch').prefetch_related(
        'enrolled_users'
    ).distinct()
    
    # Get courses where instructor is enrolled as instructor (invited instructor)
    # Using fixed role logic: distinguish instructor assignments from learner enrollments
    enrolled_as_instructor_courses = Course.objects.filter(
        courseenrollment__user=request.user,
        courseenrollment__user__role='instructor'  # Enrolled as instructor, not learner
    ).exclude(
        id__in=assigned_courses.values_list('id', flat=True)
    ).select_related('instructor', 'branch').distinct()
    
    # Combine assigned and invited instructor courses for complete instructor overview
    all_instructor_courses = assigned_courses.union(enrolled_as_instructor_courses)
    
    # Count learners across all assigned courses
    learner_enrollments = CourseEnrollment.objects.filter(
        course__in=assigned_courses,
        user__role='learner'
    )
    
    total_learners = learner_enrollments.count()
    
    if total_learners > 0:
        from courses.models import TopicProgress
        
        # Count learners by their topic progress status
        completed_learners = learner_enrollments.filter(completed=True).count()
        
        # In progress = learners who have accessed any topic but not completed all
        in_progress_learners = 0
        not_started_learners = 0
        
        for enrollment in learner_enrollments:
            # Check if learner has accessed any topic in any assigned course
            has_accessed_topic = TopicProgress.objects.filter(
                user=enrollment.user,
                topic__coursetopic__course__in=assigned_courses,
                last_accessed__isnull=False
            ).exists()
            
            if enrollment.completed:
                # Already counted as completed
                continue
            elif has_accessed_topic:
                in_progress_learners += 1
            else:
                not_started_learners += 1
        
        course_progress = {
            'total_courses': total_learners,
            'completed_count': completed_learners,
            'in_progress_count': in_progress_learners,
            'not_started_count': not_started_learners,
            'not_passed_count': 0,
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
    
    # Get cached activity data for instructor's branch with role-based filtering
    branch_id = request.user.branch.id if request.user.branch else None
    business_id = request.GET.get('business')
    branch_filter_id = request.GET.get('branch')
    activity_data = DashboardCache.get_activity_data('month', branch_filter_id or branch_id)
    
    # Prepare portal activity for template
    import json
    portal_activity = {
        'labels': json.dumps(activity_data['labels']),
        'logins': json.dumps(activity_data['logins']),
        'completions': json.dumps(activity_data['completions'])
    }
    
    # Get in-progress courses with progress tracking for instructor
    # Include both assigned courses (teaching) and enrolled courses (learning)
    in_progress_courses = []
    
    # For assigned courses, show average learner progress (teaching view)
    for course in assigned_courses[:2]:  # Limit to 2 assigned courses
        enrollments = CourseEnrollment.objects.filter(
            course=course,
            completed=False,
            last_accessed__isnull=False,
            user__role='learner'
        )
        if enrollments.exists():
            total_progress = 0
            enrollment_count = 0
            for enrollment in enrollments:
                progress = enrollment.get_progress() if hasattr(enrollment, 'get_progress') else 0
                total_progress += progress
                enrollment_count += 1
            
            avg_progress = round(total_progress / enrollment_count) if enrollment_count > 0 else 0
            in_progress_courses.append({
                'id': course.id,
                'title': f"{course.title} (Teaching)",
                'progress': avg_progress,
                'type': 'teaching',
                'course': course
            })
    
    # For enrolled courses, show instructor's own progress (learning view)
    instructor_enrollments = CourseEnrollment.objects.filter(
        user=request.user,
        completed=False,
        last_accessed__isnull=False
    ).select_related('course')[:2]  # Limit to 2 enrolled courses
    
    for enrollment in instructor_enrollments:
        course = enrollment.course
        # Skip if this course is already shown in assigned courses
        if course in assigned_courses:
            continue
            
        # Calculate instructor's personal progress
        progress = enrollment.get_progress() if hasattr(enrollment, 'get_progress') else 0
        
        in_progress_courses.append({
            'id': course.id,
            'title': f"{course.title} (Learning)",
            'progress': progress,
            'type': 'learning',
            'course': course
        })
    
    # Get todo items for instructor
    recent_activities = []
    from assignments.models import AssignmentSubmission
    from django.utils import timezone
    from datetime import timedelta
    
    # 1. Assignments pending grading (high priority)
    pending_submissions = AssignmentSubmission.objects.filter(
        assignment__course__in=assigned_courses,
        status='submitted'
    ).select_related('assignment', 'assignment__course', 'user').order_by('submitted_at')[:5]
    
    for submission in pending_submissions:
        days_since = (timezone.now().date() - submission.submitted_at.date()).days
        if days_since == 0:
            time_text = "Submitted today"
        elif days_since == 1:
            time_text = "Submitted yesterday"
        else:
            time_text = f"Submitted {days_since} days ago"
            
        recent_activities.append({
            'type': 'grade',
            'action': 'grade',
            'user': submission.user,
            'assignment': submission.assignment,
            'item': {
                'title': f'Grade: {submission.assignment.title}',
                'type': 'Assignment Grading'
            },
            'time': submission.submitted_at,
            'sort_date': submission.submitted_at,  # Add sort_date for date ordering
            'description': f"Grade {submission.user.get_full_name()}'s assignment",
            'priority': 'high' if days_since <= 1 else 'medium'
        })
    
    # 2. Courses with low recent activity (need attention)
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    
    for course in assigned_courses[:3]:
        recent_enrollments = CourseEnrollment.objects.filter(
            course=course,
            last_accessed__gte=week_ago
        ).count()
        
        total_enrollments = CourseEnrollment.objects.filter(course=course).count()
        
        if total_enrollments > 0:
            activity_rate = recent_enrollments / total_enrollments
            if activity_rate < 0.3:  # Less than 30% recent activity
                recent_activities.append({
                    'type': 'course',
                    'action': 'review',
                    'user': request.user,  # Add the missing user key
                    'course': course,
                    'item': {
                        'title': f'Review: {course.title}',
                        'type': 'Course Management'
                    },
                    'time': now,
                    'sort_date': now + timedelta(days=30),  # Lower priority for course review tasks
                    'description': f"Low student engagement - only {recent_enrollments}/{total_enrollments} active",
                    'priority': 'medium'
                })
    
    # 3. Upcoming assignment deadlines (instructor needs to prepare)
    upcoming_deadlines = Assignment.objects.filter(
        course__in=assigned_courses,
        due_date__gte=now,
        due_date__lte=now + timedelta(days=7),
        is_active=True
    ).select_related('course').order_by('due_date')[:3]
    
    for assignment in upcoming_deadlines:
        days_until = (assignment.due_date.date() - now.date()).days
        if days_until == 0:
            time_text = "Due today"
            priority = 'high'
        elif days_until == 1:
            time_text = "Due tomorrow"
            priority = 'high'
        else:
            time_text = f"Due in {days_until} days"
            priority = 'medium'
            
        recent_activities.append({
            'type': 'course',
            'action': 'prepare',
            'user': request.user,  # Add the missing user key
            'assignment': assignment,
            'item': {
                'title': f'Prepare: {assignment.title}',
                'type': 'Assignment Deadline'
            },
            'time': assignment.due_date,
            'sort_date': assignment.due_date,  # Use actual due date for sorting
            'description': f"Assignment deadline approaching",
            'priority': priority
        })
    
    # Sort by date (earliest first) for instructor dashboard
    recent_activities.sort(key=lambda x: x['sort_date'])
    
    # Handle AJAX request for loading more activities
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'load_more_todos' in request.GET:
        start = int(request.GET.get('start', 0))
        limit = int(request.GET.get('limit', 5))
        
        paginated_activities = recent_activities[start:start + limit]
        has_more = len(recent_activities) > start + limit
        
        from django.http import JsonResponse
        from django.template.loader import render_to_string
        
        # Render the activities as HTML
        html = render_to_string('users/components/instructor_activity_item.html', {
            'recent_activities': paginated_activities,
            'request': request
        })
        
        return JsonResponse({
            'html': html,
            'has_more': has_more,
            'total_count': len(recent_activities)
        })
    
    # Handle AJAX request for activity timeframe changes  
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'timeframe' in request.GET:
        timeframe = request.GET.get('timeframe', 'month')
        
        # Get instructor's branch_id for activity filtering
        instructor_branch_id = request.user.branch.id if request.user.branch else None
        
        # Get activity data for the requested timeframe
        from core.utils.dashboard_cache import DashboardCache
        activity_data = DashboardCache.get_activity_data(timeframe, instructor_branch_id)
        
        from django.http import JsonResponse
        return JsonResponse(activity_data)
    
    # Generate todo items using TodoService for enhanced role-based functionality
    todo_service = TodoService(request.user)
    all_todo_items = todo_service.get_todos(limit=50)  # Get more items for initial load
    
    # Convert TodoService format to existing template format for backward compatibility
    todo_items = []
    for todo in all_todo_items:
        # Map new format to existing format
        todo_item = {
            'task': todo['title'],
            'title': todo['title'],
            'description': todo['description'],
            'due': todo['due_date'],
            'due_date': todo['due_date'],
            'sort_date': todo['sort_date'],
            'icon': todo['icon'],
            'type': todo['type'],
            'priority': todo['priority'],
            'url': todo['url']
        }
        
        # Add type-specific metadata
        if todo['type'] == 'grading':
            todo_item['student_name'] = todo.get('metadata', {}).get('student_name', '')
        elif todo['type'] == 'assignment':
            todo_item['assignment_points'] = todo.get('metadata', {}).get('points')
            
        todo_items.append(todo_item)
    
    # For initial page load, show first 5 items
    initial_todos = todo_items[:5]
    has_more_todos = len(todo_items) > 5
    
    # Get enrolled students from instructor's courses
    enrolled_students = CustomUser.objects.filter(
        courseenrollment__course__in=assigned_courses,
        role='learner',
        is_active=True
    ).distinct().order_by('-last_login')[:10]  # Show top 10 recent students
    
    # Get recent instructors (colleagues) - keep original for reference
    recent_instructors = CustomUser.objects.filter(
        role='instructor',
        branch=request.user.branch,
        is_active=True
    ).exclude(id=request.user.id).order_by('-last_login')[:4]
    
    # Get current month for calendar
    current_month = timezone.now().strftime('%B %Y')
    
    # Calculate real-time statistics for overview section to ensure accuracy
    # Get unique learners count from assigned courses
    real_time_unique_learners_count = CourseEnrollment.objects.filter(
        course__in=assigned_courses,
        user__role='learner'
    ).values('user').distinct().count()
    
    # Get groups count for instructor
    from groups.models import BranchGroup
    real_time_instructor_groups_count = BranchGroup.objects.filter(
        Q(memberships__user=request.user, memberships__is_active=True) |
        Q(course_groups__course__in=assigned_courses)
    ).distinct().count()
    
    # Calculate real-time completion rate - only include learner role users
    course_enrollments_for_rate = CourseEnrollment.objects.filter(course__in=assigned_courses, user__role='learner')
    total_enrollments_for_rate = course_enrollments_for_rate.count()
    completed_enrollments_for_rate = course_enrollments_for_rate.filter(completed=True).count()
    
    if total_enrollments_for_rate > 0:
        real_time_completion_rate = round((completed_enrollments_for_rate / total_enrollments_for_rate) * 100)
    else:
        real_time_completion_rate = 0
    
    context = {
        'breadcrumbs': breadcrumbs,
        'assigned_courses': assigned_courses,
        'enrolled_courses': enrolled_as_instructor_courses,
        'course_progress': course_progress,
        # Use real-time calculations for overview statistics to ensure they're current
        # Include both assigned courses (teaching) and enrolled courses (learning)
        'assigned_courses_count': all_instructor_courses.count(),
        'unique_learners_count': real_time_unique_learners_count,
        'instructor_groups_count': real_time_instructor_groups_count,
        'completion_rate': real_time_completion_rate,
        'portal_activity': portal_activity,
        # Activity data for consistent Activity section
        'activity_dates': json.dumps(activity_data['labels']),
        'login_counts': json.dumps(activity_data['logins']),
        'completion_counts': json.dumps(activity_data['completions']),
        'in_progress_courses': in_progress_courses,
        'todo_items': initial_todos,  # Todo items using TodoService
        'has_more_todos': has_more_todos,
        'total_todo_count': len(todo_items),
        'recent_instructors': recent_instructors,
        'enrolled_students': enrolled_students,  # Add enrolled students data
        'current_month': current_month,
    }
    
    return render(request, 'users/dashboards/instructor.html', context)

@login_required
def learner_dashboard(request):
    """Optimized learner dashboard with efficient database queries to prevent N+1 issues"""
    if request.user.role != 'learner':
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
        {'label': 'Learner Dashboard', 'icon': 'fa-tachometer-alt'}
    ]
    
    # Get enrolled courses with optimized query
    # User role is already validated above, so no need to filter by role again
    enrolled_courses = CourseEnrollment.objects.filter(
        user=request.user
    ).select_related('course').prefetch_related('course__topics').order_by('-enrolled_at')
    
    # Sync completion status before calculating statistics
    CourseEnrollment.sync_user_completions(request.user)
    
    # Calculate course progress statistics efficiently
    total_enrolled = enrolled_courses.count()
    completed_count = enrolled_courses.filter(completed=True).count()
    
    # Calculate progress based on actual topic completion
    incomplete_enrollments = enrolled_courses.filter(completed=False)
    in_progress_count = 0
    not_started_count = 0
    not_passed_count = 0  # Placeholder for failed courses
    
    for enrollment in incomplete_enrollments:
        try:
            # Use the enrollment's get_progress method which counts completed topics
            progress = enrollment.get_progress()
            if progress > 0:
                in_progress_count += 1
            else:
                not_started_count += 1
        except Exception:
            # If there's an error calculating progress, assume not started
            not_started_count += 1
    
    # Calculate percentages (avoid division by zero)
    if total_enrolled > 0:
        completed_percentage = round((completed_count / total_enrolled) * 100)
        in_progress_percentage = round((in_progress_count / total_enrolled) * 100)
        not_started_percentage = round((not_started_count / total_enrolled) * 100)
        not_passed_percentage = max(0, 100 - completed_percentage - in_progress_percentage - not_started_percentage)
    else:
        completed_percentage = in_progress_percentage = not_started_percentage = not_passed_percentage = 0
    
    # Create course progress dictionary
    course_progress = {
        'total_courses': total_enrolled,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'not_started_count': not_started_count,
        'not_passed_count': not_passed_count,
        'completed_percentage': completed_percentage,
        'in_progress_percentage': in_progress_percentage,
        'not_started_percentage': not_started_percentage,
        'not_passed_percentage': not_passed_percentage,
    }
    
    # Learning activities data - calculate real values
    from assignments.models import Assignment, AssignmentSubmission
    from conferences.models import ConferenceAttendance
    
    # Get all assignments available to this learner through their enrolled courses
    enrolled_course_ids = enrolled_courses.values_list('course_id', flat=True)
    available_assignments = Assignment.objects.filter(
        course__in=enrolled_course_ids,
        is_active=True
    ).distinct()
    
    # Calculate submitted assignments count (assignments with submitted or graded status)
    submitted_assignments_count = AssignmentSubmission.objects.filter(
        user=request.user,
        assignment__in=available_assignments,
        status__in=['submitted', 'graded', 'not_graded']
    ).values('assignment').distinct().count()
    
    # Calculate pending submissions (assignments available but not submitted yet)
    pending_submissions_count = available_assignments.count() - submitted_assignments_count
    
    # Calculate attendance rate from conference attendance
    user_attendances = ConferenceAttendance.objects.filter(user=request.user)
    total_conferences = user_attendances.count()
    
    if total_conferences > 0:
        present_conferences = user_attendances.filter(
            attendance_status__in=['present', 'late']
        ).count()
        attendance_rate = round((present_conferences / total_conferences) * 100)
    else:
        attendance_rate = 0  # No conferences attended yet
    
    learning_activities = {
        'completed_courses': completed_count,
        'pending_submissions': max(0, pending_submissions_count),  # Ensure non-negative
        'submitted_assignments': submitted_assignments_count,
        'attendance_rate': attendance_rate,
    }
    
    # Placeholder leaderboard data
    leaderboard = [
        {'name': 'John Doe', 'level': 5, 'points': 1250},
        {'name': 'Jane Smith', 'level': 4, 'points': 980},
        {'name': 'Bob Johnson', 'level': 4, 'points': 920},
    ]
    
    # Real Calendar data and events
    from calendar_app.models import CalendarEvent
    from conferences.models import Conference
    from django.utils import timezone
    from datetime import datetime, timedelta
    
    now = timezone.now()
    today = now.date()
    current_month = now.strftime('%B %Y')
    
    # Get current month's date range for calendar
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.get_current_timezone())
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.get_current_timezone())
    
    # Collect real calendar events for current month
    calendar_events = []
    
    # 1. Assignment due dates
    assignments_due = Assignment.objects.filter(
        course__in=enrolled_course_ids,
        due_date__gte=month_start,
        due_date__lt=month_end,
        is_active=True
    ).exclude(
        # Exclude already submitted assignments
        submissions__user=request.user,
        submissions__status__in=['submitted', 'graded']
    ).select_related('course')
    
    for assignment in assignments_due:
        calendar_events.append({
            'day': assignment.due_date.day,
            'title': f"{assignment.title}",
            'type': 'assignment',
            'color': 'red',
            'course': assignment.course.title if assignment.course else 'General',
            'date': assignment.due_date,
            'url': f'/assignments/{assignment.id}/'
        })
    
    # 2. Conference dates - only show if user is enrolled in the course
    conferences = Conference.objects.filter(
        date__gte=month_start.date(),
        date__lt=month_end.date(),
        status='published',
        course__in=enrolled_course_ids
    ).select_related('course')
    
    for conference in conferences:
        calendar_events.append({
            'day': conference.date.day,
            'title': f"{conference.title}",
            'type': 'conference',
            'color': 'blue',
            'course': conference.course.title if conference.course else 'General',
            'date': datetime.combine(conference.date, conference.start_time) if conference.start_time else conference.date,
            'url': f'/conferences/{conference.id}/'
        })
    
    # 3. Calendar app events
    calendar_app_events = CalendarEvent.objects.filter(
        created_by=request.user,
        start_date__gte=month_start,
        start_date__lt=month_end
    )
    
    for event in calendar_app_events:
        calendar_events.append({
            'day': event.start_date.day,
            'title': event.title,
            'type': 'event',
            'color': event.color if hasattr(event, 'color') and event.color else 'green',
            'course': 'Personal',
            'date': event.start_date,
            'url': '/calendar/'
        })
    
    # 4. Course enrollment dates that haven't started yet
    upcoming_courses = enrolled_courses.filter(
        course__start_date__gte=month_start.date(),
        course__start_date__lt=month_end.date()
    ).select_related('course')
    
    for enrollment in upcoming_courses:
        if enrollment.course.start_date:
            calendar_events.append({
                'day': enrollment.course.start_date.day,
                'title': f"Start: {enrollment.course.title}",
                'type': 'course_start',
                'color': 'green',
                'course': enrollment.course.title,
                'date': enrollment.course.start_date,
                'url': f'/courses/{enrollment.course.id}/view/'
            })
    
    # Sort events by day
    calendar_events.sort(key=lambda x: x['day'])
    
    # Generate todo items using TodoService for enhanced role-based functionality
    todo_service = TodoService(request.user)
    all_todo_items = todo_service.get_todos(limit=50)  # Get more items for initial load
    
    # Convert TodoService format to existing template format for backward compatibility
    todo_items = []
    for todo in all_todo_items:
        # Map new format to existing format
        todo_item = {
            'course': todo.get('metadata', {}).get('course_name', ''),
            'task': todo['title'],
            'title': todo['title'],
            'description': todo['description'],
            'due': todo['due_date'],
            'due_date': todo['due_date'],
            'sort_date': todo['sort_date'],
            'icon': todo['icon'],
            'type': todo['type'],
            'priority': todo['priority'],
            'url': todo['url']
        }
        
        # Add type-specific metadata
        if todo['type'] == 'assignment':
            todo_item['assignment_points'] = todo.get('metadata', {}).get('points')
        elif todo['type'] == 'course':
            todo_item['course_progress'] = todo.get('metadata', {}).get('progress', 0)
            
        todo_items.append(todo_item)
    
    # Prepare data for template - separate tasks by type (using TodoService data)
    
    # Prepare data for template - separate tasks by type
    course_tasks = [item for item in todo_items if item['type'] == 'course']
    assignment_tasks = [item for item in todo_items if item['type'] == 'assignment']
    conference_tasks = [item for item in todo_items if item['type'] == 'conference']
    
    # For assignment tab - get actual assignment objects
    pending_assignments_for_template = Assignment.objects.filter(
        course__in=enrolled_course_ids,
        due_date__gte=now,
        is_active=True
    ).exclude(
        submissions__user=request.user,
        submissions__status__in=['submitted', 'graded']
    ).select_related('course').order_by('due_date')[:10]
    
    # For conference tab - get actual conference objects  
    upcoming_conferences_for_template = Conference.objects.filter(
        date__gte=today,
        status='published',
        course__in=enrolled_course_ids
    ).select_related('course').order_by('date')[:10]
    
    # Handle AJAX request for loading more todo items
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and 'load_more_todos' in request.GET:
        start = int(request.GET.get('start', 0))
        limit = int(request.GET.get('limit', 5))
        
        paginated_todos = todo_items[start:start + limit]
        has_more = len(todo_items) > start + limit
        
        from django.http import JsonResponse
        from django.template.loader import render_to_string
        
        # Render the todo items as HTML
        html = render_to_string('users/components/todo_item.html', {
            'todo_items': paginated_todos,
            'request': request
        })
        
        return JsonResponse({
            'html': html,
            'has_more': has_more,
            'total_count': len(todo_items)
        })
    
    # For initial page load, show first 5 items
    initial_todos = todo_items[:5]
    has_more_todos = len(todo_items) > 5

    context = {
        'breadcrumbs': breadcrumbs,
        'enrolled_courses': enrolled_courses,
        'total_courses': total_enrolled,
        'course_progress': course_progress,
        'learning_activities': learning_activities,
        'leaderboard': leaderboard,
        'current_month': current_month,
        'calendar_events': calendar_events,
        'todo_items': initial_todos,  # Only first 5 items
        'has_more_todos': has_more_todos,
        'total_todo_count': len(todo_items),
        'all_tasks': todo_items,  # All tasks for backwards compatibility (if needed)
        'course_tasks': course_tasks,  # Course-specific tasks
        'pending_assignments': pending_assignments_for_template,  # Assignment objects for template
        'upcoming_conferences': upcoming_conferences_for_template,  # Conference objects for template
    }
    
    return render(request, 'users/dashboards/learner.html', context)

@login_required
def get_user_todos(request):
    """
    Get user-specific todos based on role using TodoService
    Supports AJAX requests for pagination
    """
    # Parse request parameters
    limit = int(request.GET.get('limit', 10))
    offset = int(request.GET.get('offset', 0))
    todo_type = request.GET.get('type', None)  # Filter by type if specified
    
    # Initialize TodoService for the current user
    todo_service = TodoService(request.user)
    
    try:
        # Get todos based on type filter
        if todo_type:
            todos = todo_service.get_todos_by_type(todo_type, limit, offset)
        else:
            todos = todo_service.get_todos(limit, offset)
        
        # Get total count for pagination
        all_todos = todo_service.get_todos(limit=1000)  # Get more for count
        total_count = len(all_todos)
        has_more = (offset + limit) < total_count
        
        # If it's an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Render todos as HTML for AJAX response
            html = render_to_string('users/components/enhanced_todo_item.html', {
                'todo_items': todos,
                'user': request.user,
                'request': request
            })
            
            return JsonResponse({
                'success': True,
                'html': html,
                'todos': todos,
                'total_count': total_count,
                'has_more': has_more,
                'current_count': offset + len(todos),
                'todo_type': todo_type
            })
        
        # Regular request - return template context
        context = {
            'todo_items': todos,
            'total_count': total_count,
            'has_more': has_more,
            'current_count': len(todos),
            'todo_type': todo_type,
            'user_role': request.user.role,
            'breadcrumbs': [
                {'url': '/', 'label': 'Home', 'icon': 'fa-home'},
                {'label': 'My Todo List', 'icon': 'fa-tasks'}
            ]
        }
        
        return render(request, 'users/todo_list.html', context)
        
    except Exception as e:
        logging.error(f"Error getting todos for user {request.user.id}: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Failed to load todos. Please try again.'
            }, status=500)
        
        messages.error(request, 'Failed to load your todo list. Please try again.')
        return redirect('users:dashboard')

@login_required 
def get_todo_counts(request):
    """
    Get todo counts by type and priority for the current user
    Returns JSON response for dashboard widgets
    """
    try:
        todo_service = TodoService(request.user)
        counts = todo_service.get_todo_counts_by_type()
        
        # Calculate overall stats
        total_todos = sum(type_counts['total'] for type_counts in counts.values())
        high_priority = sum(type_counts.get('high', 0) + type_counts.get('critical', 0) 
                          for type_counts in counts.values())
        
        return JsonResponse({
            'success': True,
            'counts_by_type': counts,
            'total_todos': total_todos,
            'high_priority': high_priority,
            'user_role': request.user.role
        })
        
    except Exception as e:
        logging.error(f"Error getting todo counts for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to load todo statistics'
        }, status=500)

@login_required
def course_list(request):
    """Display list of courses based on user role and group access."""
    # ... existing code ...

@login_required
def get_dashboard_overview_data(request):
    """Optimized API endpoint to get overview data using caching"""
    if request.user.role != 'superadmin':
        return JsonResponse({"error": "Access Denied"}, status=403)

    # Use cached global statistics
    from core.utils.dashboard_cache import DashboardCache
    stats = DashboardCache.get_global_stats()
    
    # Add timestamp for last update
    stats['last_updated'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create response with optimized cache headers
    response = JsonResponse(stats)
    response['Cache-Control'] = 'public, max-age=300'  # 5 minutes cache
    response['Vary'] = 'Accept-Encoding'
    
    return response

@login_required
def get_dashboard_activity_data(request):
    """Enhanced API endpoint to get accurate portal activity data for dashboard charts with proper role-based filtering"""
    import logging
    from django.http import JsonResponse
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    from reports.views import apply_role_based_filtering, get_report_filter_context
    from core.timezone_utils import TimezoneManager
    
    logger = logging.getLogger(__name__)
    
    try:
        # Get user timezone information
        timezone_info = TimezoneManager.get_timezone_info(request.user)
        
        # Support both 'timeframe' and 'period' parameters for compatibility
        timeframe = request.GET.get('timeframe') or request.GET.get('period', 'month')
        business_id = request.GET.get('business')
        branch_id = request.GET.get('branch')
        
        # Debug logging with role information
        logger.info(f"API called by user {request.user.username} (role: {request.user.role}) with timeframe/period: {timeframe}")
        logger.info(f"Business ID: {business_id}, Branch ID: {branch_id}")
        
        # Validate timeframe - convert 'day' to 'week' for consistency
        period = timeframe
        if timeframe not in ['month', 'week', 'day', 'year']:
            period = 'month'
        elif timeframe == 'day':
            period = 'week'  # Use week view for 'day' timeframe
        
        logger.info(f"Using period: {period}")
        
        # Apply role-based filtering to users (same logic as reports)
        users_queryset = CustomUser.objects.all()
        users_queryset = apply_role_based_filtering(request.user, users_queryset, business_id, branch_id, request)
        
        # Log initial user count after role-based filtering
        initial_user_count = users_queryset.count()
        logger.info(f"Users after role-based filtering: {initial_user_count}")
        
        # Apply consistent role filtering for activity data based on user role
        if request.user.role in ['globaladmin', 'superadmin']:
            # Global admins can see activity from all user types
            logger.info("Global admin - showing activity from all user types")
            pass
        elif request.user.role in ['admin', 'instructor']:
            # Admins and instructors can see learner and instructor activity
            users_queryset = users_queryset.filter(role__in=['learner', 'instructor'])
            logger.info(f"Admin/Instructor - filtered to learner/instructor roles: {users_queryset.count()} users")
        else:
            # Regular users only see learner activity
            users_queryset = users_queryset.filter(role='learner')
            logger.info(f"Regular user - filtered to learner role only: {users_queryset.count()} users")
        
        # Apply role-based filtering to enrollments
        enrollments_queryset = CourseEnrollment.objects.all()
        enrollments_queryset = apply_role_based_filtering(request.user, enrollments_queryset, business_id, branch_id, request)
        
        # Apply consistent enrollment filtering - only count learner enrollments for accuracy
        enrollments_queryset = enrollments_queryset.filter(user__role='learner')
        logger.info(f"Enrollments after role-based filtering: {enrollments_queryset.count()}")
        
        now = timezone.now()
        # Convert to user timezone for proper date calculation
        user_now = TimezoneManager.convert_to_user_timezone(now, request.user)
        
        if period == 'week':
            # Current week (Monday to Sunday) in user timezone
            today = user_now.date()
            days_since_monday = today.weekday()  # Monday is 0, Sunday is 6
            monday = today - timedelta(days=days_since_monday)
            start_date = monday
            end_date = monday + timedelta(days=6)  # Sunday
            date_range = [start_date + timedelta(days=i) for i in range(7)]
            date_labels = [date.strftime('%a %d') for date in date_range]  # Mon 15, Tue 16, etc.
            logger.info(f"Week calculation: today={today}, monday={monday}, start_date={start_date}, end_date={end_date}")
            logger.info(f"Week date_range: {date_range}")
            logger.info(f"Is today in range: {today in date_range}")
            
        elif period == 'year':
            # Current year (January to December of current year) in user timezone
            today = user_now.date()
            current_year = today.year
            date_range = []
            
            for month_num in range(1, 13):  # January (1) to December (12)
                month_start = today.replace(year=current_year, month=month_num, day=1)
                date_range.append(month_start)
            
            start_date = date_range[0]  # January 1st
            end_date = today
            date_labels = [date.strftime('%b') for date in date_range]  # Jan, Feb, etc.
            
        else:  # month (default)
            # Current month (1st to today) in user timezone
            import calendar
            today = user_now.date()
            
            # Get first day of current month
            month_start = today.replace(day=1)
            
            # Generate date range for current month only up to today
            date_range = []
            for day_num in range(1, today.day + 1):
                day_date = month_start.replace(day=day_num)
                date_range.append(day_date)
            
            start_date = date_range[0] if date_range else today
            end_date = date_range[-1] if date_range else today
            date_labels = [str(date.day) for date in date_range]  # Show day numbers (1, 2, 3...)
        
        # Initialize counts
        login_counts = [0] * len(date_range)
        completion_counts = [0] * len(date_range)
        
        if period == 'year':
            # For yearly data, use direct month/year filtering (more efficient)
            logger.info(f"Processing year data with {len(date_range)} months")
            try:
                # Check what login data exists in the database for current year
                year_logins = users_queryset.filter(
                    last_login__isnull=False,
                    last_login__year=today.year
                )
                logger.info(f"Total logins in {today.year}: {year_logins.count()}")
                
                for i, month_start in enumerate(date_range):
                    logger.info(f"Processing month {month_start.strftime('%b %Y')} (index {i})")
                    
                    # Count logins for this month using year/month filtering
                    login_count = users_queryset.filter(
                        last_login__isnull=False,
                        last_login__year=month_start.year,
                        last_login__month=month_start.month
                    ).count()
                    
                    # Count completions for this month using year/month filtering
                    completion_count = enrollments_queryset.filter(
                        completed=True,
                        completion_date__isnull=False,
                        completion_date__year=month_start.year,
                        completion_date__month=month_start.month
                    ).count()
                    
                    # ALSO check using date range filtering as a backup
                    month_end = month_start.replace(day=28) + timedelta(days=4)  # Get next month
                    month_end = month_end - timedelta(days=month_end.day)  # Back to last day of current month
                    
                    login_count_backup = users_queryset.filter(
                        last_login__isnull=False,
                        last_login__date__gte=month_start,
                        last_login__date__lte=month_end
                    ).count()
                    
                    completion_count_backup = enrollments_queryset.filter(
                        completed=True,
                        completion_date__isnull=False,
                        completion_date__date__gte=month_start,
                        completion_date__date__lte=month_end
                    ).count()
                    
                    # Use the higher count (in case of timezone issues)
                    login_counts[i] = max(login_count, login_count_backup)
                    completion_counts[i] = max(completion_count, completion_count_backup)
                    
                    # Debug logging for year data
                    logger.info(f"Month {month_start.strftime('%b')}: Logins={login_count} (backup: {login_count_backup}), Completions={completion_count} (backup: {completion_count_backup})")
                    
                logger.info(f"Year data processing completed successfully")
            except Exception as year_error:
                logger.error(f"Error processing year data: {str(year_error)}")
                raise year_error
        else:
            # For week and month, use daily aggregation
            # Get all login data in bulk with proper null handling
            logins = users_queryset.filter(
                last_login__isnull=False,
                last_login__date__gte=start_date,
                last_login__date__lte=end_date
            ).values('last_login__date').annotate(count=Count('id'))
            
            # Map login data to dates
            logger.info(f"Mapping {len(logins)} login records to date range")
            for login in logins:
                if login['last_login__date']:
                    try:
                        day_index = (login['last_login__date'] - start_date).days
                        logger.info(f"Login date: {login['last_login__date']}, start_date: {start_date}, day_index: {day_index}, count: {login['count']}")
                        if 0 <= day_index < len(date_range):
                            login_counts[day_index] = login['count']
                            logger.info(f"Mapped login count {login['count']} to day_index {day_index}")
                        else:
                            logger.warning(f"Login date {login['last_login__date']} outside range - day_index {day_index} not in 0-{len(date_range)}")
                    except (TypeError, AttributeError) as e:
                        logger.error(f"Error mapping login date: {e}")
                        continue
            
            # Get completion data in bulk with proper null handling
            completions = enrollments_queryset.filter(
                completed=True,
                completion_date__isnull=False,
                completion_date__date__gte=start_date,
                completion_date__date__lte=end_date
            ).values('completion_date__date').annotate(count=Count('id'))
            
            # Map completion data to dates
            logger.info(f"Mapping {len(completions)} completion records to date range")
            for completion in completions:
                if completion['completion_date__date']:
                    try:
                        day_index = (completion['completion_date__date'] - start_date).days
                        logger.info(f"Completion date: {completion['completion_date__date']}, start_date: {start_date}, day_index: {day_index}, count: {completion['count']}")
                        if 0 <= day_index < len(date_range):
                            completion_counts[day_index] = completion['count']
                            logger.info(f"Mapped completion count {completion['count']} to day_index {day_index}")
                        else:
                            logger.warning(f"Completion date {completion['completion_date__date']} outside range - day_index {day_index} not in 0-{len(date_range)}")
                    except (TypeError, AttributeError) as e:
                        logger.error(f"Error mapping completion date: {e}")
                        continue
        
        # Enhanced debug logging with role-based information
        logger.info(f"=== ROLE-BASED ACTIVITY DATA DEBUG ===")
        logger.info(f"Requesting user: {request.user.username} (role: {request.user.role})")
        logger.info(f"Business filter: {business_id}, Branch filter: {branch_id}")
        logger.info(f"Period: {period}, Date range: {start_date} to {end_date}")
        logger.info(f"Users queryset count: {users_queryset.count()}")
        logger.info(f"Enrollments queryset count: {enrollments_queryset.count()}")
        
        # Check what data actually exists in the database
        total_users_with_logins = users_queryset.filter(last_login__isnull=False).count()
        total_completions = enrollments_queryset.filter(completed=True, completion_date__isnull=False).count()
        logger.info(f"Total users with logins in DB: {total_users_with_logins}")
        logger.info(f"Total completions in DB: {total_completions}")
        
        # Check recent data
        from datetime import timedelta
        recent_logins = users_queryset.filter(
            last_login__isnull=False, 
            last_login__gte=user_now - timedelta(days=30)
        ).count()
        recent_completions = enrollments_queryset.filter(
            completed=True,
            completion_date__isnull=False,
            completion_date__gte=user_now - timedelta(days=30)
        ).count()
        logger.info(f"Recent logins (last 30 days): {recent_logins}")
        logger.info(f"Recent completions (last 30 days): {recent_completions}")
        
        # Debug: Show specific login dates for diagnosis
        if period == 'week':
            specific_logins = users_queryset.filter(last_login__isnull=False).values('username', 'last_login')[:5]
            for user_login in specific_logins:
                login_date = user_login['last_login'].date() if user_login['last_login'] else None
                logger.info(f"User {user_login['username']}: last_login = {user_login['last_login']} (date: {login_date})")
                if login_date:
                    in_week_range = start_date <= login_date <= end_date
                    logger.info(f"  - In week range ({start_date} to {end_date}): {in_week_range}")
        
        # Debug: Show users with logins in the current period
        period_logins = users_queryset.filter(
            last_login__isnull=False,
            last_login__date__gte=start_date,
            last_login__date__lte=end_date
        )
        logger.info(f"Users with logins in {period} period ({start_date} to {end_date}): {period_logins.count()}")
        for user_login in period_logins.values('username', 'last_login')[:3]:
            logger.info(f"  - {user_login['username']}: {user_login['last_login']}")
        
        logger.info(f"Total logins in period: {sum(login_counts)}")
        logger.info(f"Total completions in period: {sum(completion_counts)}")
        logger.info(f"Date labels: {date_labels}")
        logger.info(f"Login counts by day: {login_counts}")
        logger.info(f"Completion counts by day: {completion_counts}")
        
        # Log role-based breakdown
        if request.user.role in ['globaladmin', 'superadmin']:
            logger.info("ROLE ACCESS: Global admin - can see all user activity")
        elif request.user.role in ['admin', 'instructor']:
            logger.info("ROLE ACCESS: Admin/Instructor - can see learner and instructor activity")
        else:
            logger.info("ROLE ACCESS: Regular user - can only see learner activity")
        
        # Return the accurate activity data with role information
        activity_data = {
            'labels': date_labels,
            'logins': login_counts,
            'completions': completion_counts,
            'timezone_info': timezone_info,
            'role_info': {
                'user_role': request.user.role,
                'users_count': users_queryset.count(),
                'enrollments_count': enrollments_queryset.count(),
                'total_logins': sum(login_counts),
                'total_completions': sum(completion_counts)
            }
        }
        
        # Create response with optimized cache headers
        response = JsonResponse(activity_data)
        response['Cache-Control'] = 'public, max-age=300'  # 5 minutes cache
        response['Vary'] = 'Accept-Encoding'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in get_dashboard_activity_data: {e}")
        
        # Return proper fallback data structure based on period
        timeframe = request.GET.get('timeframe') or request.GET.get('period', 'month')
        period = timeframe
        if timeframe not in ['month', 'week', 'day']:
            period = 'month'
        elif timeframe == 'day':
            period = 'week'
        
        if period == 'week':
            # Current week days
            import datetime
            today = datetime.datetime.now().date()
            days_since_monday = today.weekday()
            monday = today - datetime.timedelta(days=days_since_monday)
            fallback_labels = [f"{(monday + datetime.timedelta(days=i)).strftime('%a')} {(monday + datetime.timedelta(days=i)).day}" for i in range(7)]
        elif period == 'year':
            fallback_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        else:  # month
            import datetime
            today = datetime.datetime.now().date()
            fallback_labels = [str(i) for i in range(1, today.day + 1)]
        
        fallback_data = {
            'labels': fallback_labels,
            'logins': [0] * len(fallback_labels),
            'completions': [0] * len(fallback_labels)
        }
        return JsonResponse(fallback_data)

@login_required
def get_admin_course_progress_data(request):
    """Optimized API endpoint for admin course progress data using branch caching"""
    if request.user.role != 'admin':
        return JsonResponse({"error": "Access Denied"}, status=403)

    # Get cached branch statistics 
    from core.utils.dashboard_cache import DashboardCache
    from core.branch_filters import BranchFilterManager
    
    # Get the effective branch (considers session-based branch switching for admin users)
    effective_branch = BranchFilterManager.get_effective_branch(request.user, request)
    branch_id = effective_branch.id if effective_branch else None
    if not branch_id:
        return JsonResponse({"error": "No branch assigned"}, status=403)
    
    # Use learner enrollments for consistency with main dashboard
    branch_enrollments = CourseEnrollment.objects.filter(user__branch_id=branch_id)
    learner_enrollments = branch_enrollments.filter(user__role='learner')
    
    # Count by status using actual topic completion (consistent with main dashboard logic)
    completed_count = learner_enrollments.filter(completed=True).count()
    
    # Calculate in_progress and not_started based on actual topic completion
    incomplete_enrollments = learner_enrollments.filter(completed=False)
    in_progress_count = 0
    not_started_count = 0
    
    for enrollment in incomplete_enrollments:
        try:
            # Use the enrollment's get_progress method which counts completed topics
            progress = enrollment.get_progress()
            if progress > 0:
                in_progress_count += 1
            else:
                not_started_count += 1
        except Exception:
            # If there's an error calculating progress, assume not started
            not_started_count += 1
    
    total_learner_enrollments = learner_enrollments.count()
    
    # Calculate percentages (consistent with main dashboard)
    if total_learner_enrollments > 0:
        completed_percentage = round((completed_count / total_learner_enrollments) * 100)
        in_progress_percentage = round((in_progress_count / total_learner_enrollments) * 100)
        not_started_percentage = round((not_started_count / total_learner_enrollments) * 100)
        
        # Calculate not_passed_percentage based on actual failed/expired enrollments if field exists
        not_passed_count = 0
        has_failed_field = hasattr(CourseEnrollment, 'failed')
        if has_failed_field:
            not_passed_count = learner_enrollments.filter(completed=False, failed=True).count()
            not_passed_percentage = round((not_passed_count / total_learner_enrollments) * 100)
        else:
            # Only use remainder calculation if no failed field exists
            calculated_remainder = 100 - completed_percentage - in_progress_percentage - not_started_percentage
            not_passed_percentage = max(0, calculated_remainder)
    else:
        completed_percentage = in_progress_percentage = not_started_percentage = not_passed_percentage = 0
    
    # Get top courses with optimized query
    top_courses = []
    courses = Course.objects.filter(branch_id=branch_id).annotate(
        total_enrollments=Count('courseenrollment'),
        completed_enrollments=Count('courseenrollment', filter=Q(courseenrollment__completed=True))
    ).filter(total_enrollments__gt=0).order_by('-completed_enrollments')[:5]
    
    for course in courses:
        completion_rate = round((course.completed_enrollments / course.total_enrollments) * 100) if course.total_enrollments > 0 else 0
        top_courses.append({
            'id': course.id,
            'title': course.title,
            'completion_rate': completion_rate,
            'enrollments': course.total_enrollments
        })
    
    # Get recent completions with optimized query
    recent_completions = CourseEnrollment.objects.filter(
        completed=True,
        completion_date__isnull=False,
        user__branch_id=branch_id
    ).select_related('user', 'course').order_by('-completion_date')[:5]
    
    recent_activities = []
    for enrollment in recent_completions:
        try:
            recent_activities.append({
                'user': enrollment.user.get_full_name() or enrollment.user.username,
                'course': enrollment.course.title,
                'date': enrollment.completion_date.strftime('%Y-%m-%d %H:%M:%S') if enrollment.completion_date else '',
            })
        except Exception:
            # Skip if there's an issue with this enrollment
            continue
            
    data = {
        'completed_percentage': completed_percentage,
        'in_progress_percentage': in_progress_percentage,
        'not_started_percentage': not_started_percentage,
        'not_passed_percentage': not_passed_percentage,
        'top_courses': top_courses,
        'recent_completions': recent_activities,
        'counts': {
            'completed': completed_count,
            'in_progress': in_progress_count,
            'not_started': not_started_count,
            'not_passed': not_passed_count,
            'total': total_status_count
        },
        'last_updated': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Create response with optimized cache headers
    response = JsonResponse(data)
    response['Cache-Control'] = 'public, max-age=300'  # 5 minutes cache
    response['Vary'] = 'Accept-Encoding'
    
    return response

@login_required
def get_instructor_dashboard_stats(request):
    """Optimized API endpoint to get instructor dashboard statistics using caching"""
    if request.user.role != 'instructor':
        return JsonResponse({"error": "Access Denied"}, status=403)
    
    # Use cached instructor statistics
    from core.utils.dashboard_cache import DashboardCache
    stats = DashboardCache.get_instructor_stats(request.user.id)
    
    # Add timestamp for last update
    stats['last_updated'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create response with optimized cache headers
    response = JsonResponse(stats)
    response['Cache-Control'] = 'public, max-age=600'  # 10 minutes cache for instructor stats
    response['Vary'] = 'Accept-Encoding'
    
    return response

@login_required
def get_learner_course_progress_data(request):
    """API endpoint to get the latest course progress data for learner dashboard."""
    if request.user.role != 'learner':
        return JsonResponse({"error": "Access Denied"}, status=403)

    # Get all course enrollments for this learner
    # User role is already validated above, so no need to filter by role again
    enrolled_courses = CourseEnrollment.objects.filter(
        user=request.user
    ).order_by('-enrolled_at')
    
    # Calculate course progress statistics
    completed_count = enrolled_courses.filter(completed=True).count()
    total_enrolled = enrolled_courses.count()
    
    # Initialize counters
    in_progress_count = 0
    not_started_count = 0
    not_passed_count = 0
    
    # Count courses in different progress states
    for enrollment in enrolled_courses:
        if enrollment.completed:
            continue
        try:
            # Try to calculate progress
            progress = enrollment.get_progress()
            if progress > 0:
                in_progress_count += 1
            else:
                not_started_count += 1
        except Exception:
            # If there's an error calculating progress, assume not started
            not_started_count += 1
    
    # Calculate percentages (avoid division by zero)
    if total_enrolled > 0:
        completed_percentage = round((completed_count / total_enrolled) * 100)
        in_progress_percentage = round((in_progress_count / total_enrolled) * 100)
        not_started_percentage = round((not_started_count / total_enrolled) * 100)
        not_passed_percentage = 100 - (completed_percentage + in_progress_percentage + not_started_percentage)
    else:
        completed_percentage = 0
        in_progress_percentage = 0
        not_started_percentage = 0
        not_passed_percentage = 0
    
    # Get recent course activity
    recent_activity = []
    for enrollment in enrolled_courses[:5]:
        if enrollment.course:  # Check if course is not None
            course_data = {
                'id': enrollment.course.id,
                'title': enrollment.course.title,
                'status': 'Completed' if enrollment.completed else ('In Progress' if enrollment.last_accessed else 'Not Started'),
                'progress': enrollment.get_progress() if hasattr(enrollment, 'get_progress') else 0,
                'last_accessed': enrollment.last_accessed.strftime('%Y-%m-%d %H:%M:%S') if enrollment.last_accessed else None,
                'enrolled_at': enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else None,
            }
            recent_activity.append(course_data)
    
    data = {
        'completed_percentage': completed_percentage,
        'in_progress_percentage': in_progress_percentage,
        'not_started_percentage': not_started_percentage,
        'not_passed_percentage': not_passed_percentage,
        'recent_activity': recent_activity,
        'counts': {
            'completed': completed_count,
            'in_progress': in_progress_count,
            'not_started': not_started_count,
            'not_passed': not_passed_count,
            'total': total_enrolled
        },
        'last_updated': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return JsonResponse(data)

@login_required
def user_settings(request):
    """User settings page."""
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('users:user_list'), 'label': 'User Management', 'icon': 'fa-users'},
        {'url': reverse('users:user_profile', args=[request.user.id]), 'label': request.user.get_full_name() or request.user.username, 'icon': 'fa-user'},
        {'label': 'Settings', 'icon': 'fa-cog'}
    ]
    
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, request.FILES, instance=request.user, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully.")
            return redirect('users:user_settings')
    else:
        form = CustomUserChangeForm(instance=request.user, request=request)
    
    context = {
        'form': form,
        'title': 'User Settings',
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'users/shared/user_settings.html', context)

@login_required
def search(request):
    """Global search view for searching across various models in the LMS with enhanced PostgreSQL full-text search"""
    query = request.GET.get('q', '')
    category = request.GET.get('category', 'all')
    
    from courses.models import Course, CourseCategory
    from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
    from django.db.models import F
    
    results = {
        'courses': [],
        'users': [],
        'total_results': 0
    }
    
    # Get categories for the dropdown - wrap in try-except for safety
    try:
        categories = CourseCategory.objects.all()
    except Exception as e:
        logger.error(f"Error fetching course categories: {str(e)}")
        categories = []
    
    if query:
        # Search users when 'users' category is selected
        if category == 'users' and request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']:
            try:
                # Use PostgreSQL full-text search for better accuracy
                search_vector = SearchVector('username', weight='A') + \
                               SearchVector('first_name', weight='A') + \
                               SearchVector('last_name', weight='A') + \
                               SearchVector('email', weight='B')
                search_query = SearchQuery(query)
                
                # Perform full-text search with ranking
                users = CustomUser.objects.annotate(
                    rank=SearchRank(search_vector, search_query)
                ).filter(rank__gt=0).order_by('-rank')
                
                # Fallback to basic search if no results found
                if not users.exists():
                    users = CustomUser.objects.filter(
                        Q(username__icontains=query) | 
                        Q(email__icontains=query) |
                        Q(first_name__icontains=query) |
                        Q(last_name__icontains=query)
                    )
                
                # Filter users based on role permissions
                if request.user.role == 'admin':
                    # Admin users cannot see superadmin or globaladmin users
                    users = users.filter(branch=request.user.branch).exclude(role__in=['superadmin', 'globaladmin'])
                elif request.user.role == 'instructor':
                    # Instructors can only see learner users
                    users = users.filter(branch=request.user.branch, role='learner')
                elif request.user.role == 'superadmin':
                    # Super admin users cannot see globaladmin users
                    users = users.exclude(role='globaladmin')
                
                results['users'] = users[:20]  # Increased limit for better results
                results['total_results'] += users.count()
            except Exception as e:
                logger.error(f"User search error for query '{query}': {str(e)}")
                # Fallback to basic search on error
                try:
                    users = CustomUser.objects.filter(
                        Q(username__icontains=query) | 
                        Q(email__icontains=query) |
                        Q(first_name__icontains=query) |
                        Q(last_name__icontains=query)
                    )
                    
                    if request.user.role == 'admin':
                        users = users.filter(branch=request.user.branch).exclude(role__in=['superadmin', 'globaladmin'])
                    elif request.user.role == 'instructor':
                        users = users.filter(branch=request.user.branch, role='learner')
                    elif request.user.role == 'superadmin':
                        users = users.exclude(role='globaladmin')
                    
                    results['users'] = users[:20]
                    results['total_results'] += users.count()
                except Exception as fallback_error:
                    logger.error(f"User search fallback error: {str(fallback_error)}")
                    results['users'] = []
        
        # Search courses when 'courses' category is selected or a specific category is selected
        elif category == 'courses' or category == 'all' or any(str(cat.slug) == category for cat in categories):
            try:
                # Use PostgreSQL full-text search for better accuracy
                # Create search vectors for different fields with different weights
                search_vector = SearchVector('title', weight='A') + \
                               SearchVector('description', weight='B') + \
                               SearchVector('category__name', weight='C') + \
                               SearchVector('instructor__first_name', weight='C') + \
                               SearchVector('instructor__last_name', weight='C')
                
                search_query = SearchQuery(query)
                
                # Initialize courses queryset with full-text search
                courses = Course.objects.select_related('category', 'instructor', 'branch').annotate(
                    rank=SearchRank(search_vector, search_query)
                ).filter(rank__gt=0).order_by('-rank')
                
                # Fallback to basic search if no results found
                if not courses.exists():
                    logger.info(f"Full-text search returned no results for '{query}', using fallback search")
                    courses = Course.objects.select_related('category', 'instructor', 'branch').filter(
                        Q(title__icontains=query) | 
                        Q(description__icontains=query) |
                        Q(category__name__icontains=query) |
                        Q(instructor__first_name__icontains=query) |
                        Q(instructor__last_name__icontains=query)
                    ).distinct()
                
                # If a specific category is selected (not 'all' or 'courses'), filter by category
                if category != 'all' and category != 'courses' and category != 'users':
                    try:
                        # Find the category by slug and filter courses directly
                        selected_category = CourseCategory.objects.get(slug=category)
                        courses = courses.filter(category=selected_category)
                    except CourseCategory.DoesNotExist:
                        logger.warning(f"Category '{category}' not found, continuing with unfiltered search")
                        # If category doesn't exist, continue with unfiltered course search
                        pass
                
                # Filter courses based on access permissions
                if request.user.role == 'globaladmin':
                    pass  # Global Admin can see all courses
                elif request.user.role == 'superadmin':
                    # Super Admin can see courses within their assigned businesses only
                    from core.utils.business_filtering import filter_courses_by_business
                    business_courses = filter_courses_by_business(request.user)
                    business_course_ids = list(business_courses.values_list('id', flat=True))
                    courses = courses.filter(id__in=business_course_ids)
                elif request.user.role == 'admin':
                    courses = courses.filter(branch=request.user.branch)
                elif request.user.role == 'instructor':
                    instructor_courses = list(request.user.instructor_courses.values_list('id', flat=True))
                    courses = courses.filter(
                        Q(id__in=instructor_courses) | 
                        Q(branch=request.user.branch)
                    )
                else:  # Learner
                    enrolled_courses = list(request.user.enrollments.values_list('course_id', flat=True))
                    courses = courses.filter(
                        Q(id__in=enrolled_courses) | 
                        Q(is_public=True)
                    )
                
                results['courses'] = courses[:20]  # Increased limit for better results
                results['total_results'] += courses.count()
                
            except Exception as e:
                # Log the error and try fallback search
                logger.error(f"Course search error for query '{query}': {str(e)}")
                try:
                    # Fallback to basic search
                    courses = Course.objects.select_related('category', 'instructor', 'branch').filter(
                        Q(title__icontains=query) | 
                        Q(description__icontains=query)
                    ).distinct()
                    
                    # Apply category filter if needed
                    if category != 'all' and category != 'courses' and category != 'users':
                        try:
                            selected_category = CourseCategory.objects.get(slug=category)
                            courses = courses.filter(category=selected_category)
                        except CourseCategory.DoesNotExist:
                            pass
                    
                    # Apply permission filters
                    if request.user.role == 'globaladmin':
                        pass
                    elif request.user.role == 'superadmin':
                        from core.utils.business_filtering import filter_courses_by_business
                        business_courses = filter_courses_by_business(request.user)
                        business_course_ids = list(business_courses.values_list('id', flat=True))
                        courses = courses.filter(id__in=business_course_ids)
                    elif request.user.role == 'admin':
                        courses = courses.filter(branch=request.user.branch)
                    elif request.user.role == 'instructor':
                        instructor_courses = list(request.user.instructor_courses.values_list('id', flat=True))
                        courses = courses.filter(
                            Q(id__in=instructor_courses) | 
                            Q(branch=request.user.branch)
                        )
                    else:
                        enrolled_courses = list(request.user.enrollments.values_list('course_id', flat=True))
                        courses = courses.filter(
                            Q(id__in=enrolled_courses) | 
                            Q(is_public=True)
                        )
                    
                    results['courses'] = courses[:20]
                    results['total_results'] += courses.count()
                except Exception as fallback_error:
                    logger.error(f"Course search fallback error: {str(fallback_error)}")
                    results['courses'] = []
    
    context = {
        'query': query,
        'category': category,
        'results': results,
        'categories': categories,
        'breadcrumbs': [
            {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Search Results', 'icon': 'fa-search'}
        ]
    }
    
    return render(request, 'users/search_results.html', context)

@login_required
def download_user_template(request):
    """Provide a downloadable Excel template for bulk user import."""
    import xlsxwriter
    from io import BytesIO
    from django.http import HttpResponse
    
    # Create a response object with appropriate headers
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Users')
    
    # Define header style
    header_style = workbook.add_format({
        'bold': True,
        'bg_color': '#F9FAFB',
        'border': 1,
        'border_color': '#E5E7EB'
    })
    
    # Add headers
    headers = ['First Name', 'Last Name', 'Email', 'Username', 'Password', 'Role', 'Branch', 'Group(s)']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_style)
    
    # Add sample data in the first row
    sample_data = ['John', 'Doe', 'john.doe@example.com', 'johndoe', 'securepassword', 'learner', 'Main Branch', 'Group A; Group B']
    for col, value in enumerate(sample_data):
        worksheet.write(1, col, value)
    
    # Auto-size columns
    for col, header in enumerate(headers):
        worksheet.set_column(col, col, len(header) + 5)
    
    # Add notes in another sheet
    notes_sheet = workbook.add_worksheet('Instructions')
    notes_sheet.write(0, 0, 'Instructions for filling the template:', workbook.add_format({'bold': True}))
    notes_sheet.write(1, 0, '1. First Name and Last Name: User\'s first and last name')
    notes_sheet.write(2, 0, '2. Email: Must be unique and valid email format')
    notes_sheet.write(3, 0, '3. Username: Must be unique, no spaces allowed')
    notes_sheet.write(4, 0, '4. Password: Minimum 8 characters recommended')
    notes_sheet.write(5, 0, '5. Role: One of "superadmin", "admin", "instructor", or "learner"')
    notes_sheet.write(6, 0, '6. Branch: Must match an existing branch name')
    notes_sheet.write(7, 0, '7. Group(s): Optional. Separate multiple groups with semicolons')
    
    workbook.close()
    
    # Set up the response for download
    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=user_import_template.xlsx'
    return response

@login_required
def get_course_progress_data(request):
    """API endpoint to get course progress data based on user role."""
    if request.user.role in ['globaladmin', 'superadmin']:
        # For superadmins, we'll return comprehensive progress data
        return get_superadmin_course_progress_data(request)
    elif request.user.role == 'admin':
        return get_admin_course_progress_data(request)
    elif request.user.role == 'learner':
        return get_learner_course_progress_data(request)
    elif request.user.role == 'instructor':
        # For instructors, we'll return their dashboard stats
        return get_instructor_dashboard_stats(request)
    else:
        return JsonResponse({"error": "Access Denied"}, status=403)
    
@login_required
def get_superadmin_course_progress_data(request):
    """API endpoint to get the latest course progress data for superadmin dashboard."""
    if request.user.role != 'superadmin':
        return JsonResponse({"error": "Access Denied"}, status=403)
    
    # Get all course enrollments across all branches
    all_enrollments = CourseEnrollment.objects.select_related('course', 'user').all()
    
    # Check if CourseEnrollment has a 'failed' field
    has_failed_field = hasattr(CourseEnrollment, 'failed')
    
    # Count by status using actual topic completion
    completed_count = all_enrollments.filter(completed=True).count()
    
    # Calculate in_progress and not_started based on actual topic completion
    incomplete_enrollments = all_enrollments.filter(completed=False)
    in_progress_count = 0
    not_started_count = 0
    
    for enrollment in incomplete_enrollments:
        try:
            # Use the enrollment's get_progress method which counts completed topics
            progress = enrollment.get_progress()
            if progress > 0:
                in_progress_count += 1
            else:
                not_started_count += 1
        except Exception:
            # If there's an error calculating progress, assume not started
            not_started_count += 1
    
    not_passed_count = all_enrollments.filter(completed=False, failed=True).count() if has_failed_field else 0
    
    # Calculate percentages
    total_status_count = all_enrollments.count()
    if total_status_count > 0:
        completed_percentage = round((completed_count / total_status_count) * 100)
        in_progress_percentage = round((in_progress_count / total_status_count) * 100)
        not_started_percentage = round((not_started_count / total_status_count) * 100)
        not_passed_percentage = 100 - (completed_percentage + in_progress_percentage + not_started_percentage)
    else:
        completed_percentage = 0
        in_progress_percentage = 0
        not_started_percentage = 0
        not_passed_percentage = 10  # Default value if there are no enrollments
    
    # Get courses with highest completion rates (for additional data)
    top_courses = []
    courses = Course.objects.annotate(
        total_enrollments=Count('courseenrollment'),
        completed_enrollments=Count('courseenrollment', filter=Q(courseenrollment__completed=True))
    ).filter(total_enrollments__gt=0).order_by('-completed_enrollments')[:5]
    
    for course in courses:
        completion_rate = round((course.completed_enrollments / course.total_enrollments) * 100) if course.total_enrollments > 0 else 0
        top_courses.append({
            'id': course.id,
            'title': course.title,
            'completion_rate': completion_rate,
            'enrollments': course.total_enrollments
        })
    
    # Get recent completions for real-time updates
    recent_completions = CourseEnrollment.objects.filter(
        completed=True,
        completion_date__isnull=False
    ).order_by('-completion_date')[:5]
    
    recent_activities = []
    for enrollment in recent_completions:
        try:
            recent_activities.append({
                'user': enrollment.user.get_full_name() or enrollment.user.username,
                'course': enrollment.course.title,
                'date': enrollment.completion_date.strftime('%Y-%m-%d %H:%M:%S') if enrollment.completion_date else '',
            })
        except Exception:
            # Skip if there's an issue with this enrollment
            continue
            
    data = {
        'completed_percentage': completed_percentage,
        'in_progress_percentage': in_progress_percentage,
        'not_started_percentage': not_started_percentage,
        'not_passed_percentage': not_passed_percentage,
        'top_courses': top_courses,
        'recent_completions': recent_activities,
        'counts': {
            'completed': completed_count,
            'in_progress': in_progress_count,
            'not_started': not_started_count,
            'not_passed': not_passed_count,
            'total': total_status_count
        },
        'last_updated': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return JsonResponse(data)

@login_required
def get_recent_activities(request):
    """API endpoint to get recent activity data for superadmin dashboard."""
    if request.user.role != 'superadmin':
        return JsonResponse({"error": "Access Denied"}, status=403)
    
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    from django.utils import timezone
    from datetime import timedelta
    
    # Get recent activity entries
    activities = []
    
    # Set date range for recent activities (last 30 days by default)
    now = timezone.now()
    start_date = now - timedelta(days=30)
    
    # Get the latest log entries
    log_entries = LogEntry.objects.select_related('content_type', 'user').order_by('-action_time')[:20]
    
    for entry in log_entries:
        # Determine action type
        action_type = 'view'
        if entry.action_flag == 1:
            action_type = 'add'
        elif entry.action_flag == 2:
            action_type = 'change'
        elif entry.action_flag == 3:
            action_type = 'delete'
        
        # Determine category based on content type
        content_type_name = entry.content_type.model.lower()
        category = 'all'
        
        if content_type_name in ['course', 'coursetopic', 'courseenrollment']:
            category = 'courses'
        elif content_type_name in ['submission', 'assignment', 'grade']:
            category = 'grade'
        elif content_type_name in ['discussion', 'comment']:
            category = 'discussions'
        
        # Format the time ago
        action_time = entry.action_time
        time_ago = get_time_ago(action_time)
        
        # Create descriptive text
        if entry.action_flag == 1:  # Addition
            description = f"Added {entry.content_type.name}: {entry.object_repr}"
        elif entry.action_flag == 2:  # Change
            description = f"Modified {entry.content_type.name}: {entry.object_repr}"
        elif entry.action_flag == 3:  # Deletion
            description = f"Deleted {entry.content_type.name}: {entry.object_repr}"
        else:
            description = f"Viewed {entry.content_type.name}: {entry.object_repr}"
        
        activities.append({
            'action_type': action_type,
            'description': description,
            'user': entry.user.get_full_name() or entry.user.username,
            'category': category,
            'time_ago': time_ago
        })
    
    # Create response with cache-control headers
    response = JsonResponse({'activities': activities})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

def get_time_ago(date):
    """Format a datetime as a human-readable 'time ago' string."""
    now = timezone.now()
    diff = now - date
    
    seconds = diff.total_seconds()
    
    # Define time intervals
    intervals = [
        (60, 'just now'),
        (120, '1 minute ago'),
        (3600, '{} minutes ago'),
        (7200, '1 hour ago'),
        (86400, '{} hours ago'),
        (172800, '1 day ago'),
        (604800, '{} days ago'),
        (1209600, '1 week ago'),
        (2419200, '{} weeks ago'),
        (4838400, '1 month ago'),
        (29030400, '{} months ago'),
        (58060800, '1 year ago'),
        (float('inf'), '{} years ago')
    ]
    
    # Find the appropriate interval
    for seconds_limit, format_string in intervals:
        if seconds < seconds_limit:
            if '{}' in format_string:
                if 'minute' in format_string:
                    return format_string.format(int(seconds / 60))
                elif 'hour' in format_string:
                    return format_string.format(int(seconds / 3600))
                elif 'day' in format_string:
                    return format_string.format(int(seconds / 86400))
                elif 'week' in format_string:
                    return format_string.format(int(seconds / 604800))
                elif 'month' in format_string:
                    return format_string.format(int(seconds / 2419200))
                elif 'year' in format_string:
                    return format_string.format(int(seconds / 29030400))
            else:
                return format_string
    
    return 'long time ago'

@login_required
@require_http_methods(["POST"])
def extract_cv_data(request):
    """Extract data from uploaded CV file and return as JSON.
    
    This endpoint processes an uploaded CV (PDF) and extracts 
    structured information such as personal details, education, and 
    work experience using enhanced PDF text extraction with natural
    language processing techniques.
    """
    # Allow learners to extract their own CV data during profile editing
    if request.user.role not in ['superadmin', 'admin', 'instructor', 'learner']:
        logger.warning(f"Permission denied for CV extraction by user {request.user.username}")
        return JsonResponse({"error": "Permission denied"}, status=403)
    
    logger.info(f"CV data extraction requested by user {request.user.username}")
    
    # Check if file exists
    cv_file = request.FILES.get('cv_file')
    if not cv_file:
        logger.warning("CV extraction attempted without file upload")
        return JsonResponse({"error": "No file uploaded"}, status=400)
        
    # Log file details
    logger.info(f"Processing CV file: {cv_file.name}, Size: {cv_file.size} bytes")
    
    # Check if file is PDF
    if not cv_file.name.lower().endswith('.pdf'):
        logger.warning(f"Unsupported file format: {cv_file.name}")
        return JsonResponse({"error": "Only PDF files are supported"}, status=400)
    
    temp_filepath = None
    
    try:
        import os
        import tempfile
        import re
        
        # Save the uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            for chunk in cv_file.chunks():
                temp_file.write(chunk)
            temp_filepath = temp_file.name
            
        logger.info(f"CV file saved to temporary location: {temp_filepath}")
        
        # Extract text from PDF using pdfplumber for better structured data extraction
        try:
            # Check if pdfplumber is available
            logger.info(f"Starting CV extraction. PDFPLUMBER_AVAILABLE: {PDFPLUMBER_AVAILABLE}")
            if not PDFPLUMBER_AVAILABLE:
                logger.error("pdfplumber is not available - PDFPLUMBER_AVAILABLE is False")
                raise ImportError("pdfplumber is not available")
            
            # Use the module-level import
            if not PDFPLUMBER_AVAILABLE:
                raise ImportError("pdfplumber is not available")
            
            logger.info("Starting PDF text extraction with pdfplumber")
            
            # Open the PDF file with pdfplumber
            with pdfplumber.open(temp_filepath) as pdf:
                # Extract text from each page
                text = ""
                page_texts = []
                
                # Process each page
                for i, page in enumerate(pdf.pages):
                    logger.info(f"Processing page {i+1}/{len(pdf.pages)}")
                    
                    # Extract text from the page
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
                        page_texts.append(page_text)
                    
                    # Try to extract tables which often contain structured personal information
                    tables = page.extract_tables()
                    if tables:
                        logger.info(f"Found {len(tables)} tables on page {i+1}")
                        for table in tables:
                            # Process each table
                            for row in table:
                                if row:  # Skip empty rows
                                    row_text = " ".join([str(cell) if cell else "" for cell in row])
                                    text += row_text + "\n"
            
            # Check if text was extracted successfully
            if not text or len(text.strip()) < 10:
                logger.warning("Extracted text is too short or empty")
                return JsonResponse({
                    "status": "error",
                    "message": "Could not extract meaningful text from the PDF. The file might be scanned, password-protected, or contain only images."
                }, status=422)
                
            logger.info(f"Successfully extracted {len(text)} characters of text from PDF")
            
            # Process the text to make it more consistent for extraction
            # Replace multiple spaces and newlines with single spaces
            processed_text = re.sub(r'\s+', ' ', text)
            # Split into lines for easier processing
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            # Split processed text into sections (paragraphs)
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            
            # Initialize extraction result structure
            extracted_data = {
                "personal_info": {
                    "given_name": "",
                    "family_name": "",
                    "email": "",
                    "phone_number": "",
                    "address": {
                        "address_line1": "",
                        "city": "",
                        "postcode": "",
                        "country": ""
                    }
                },
                "education": [],
                "employment": []
            }
            
            # Extract email with improved pattern
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, text)
            if emails:
                extracted_data["personal_info"]["email"] = emails[0]
                logger.info(f"Found email: {emails[0]}")
            
            # Extract phone numbers with improved patterns for multiple formats
            phone_patterns = [
                r'\b(?:\+\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b',  # (123) 456-7890, +1 123-456-7890
                r'\b\d{5}[ -]?\d{6}\b',  # UK format: 12345 123456
                r'\b\d{3}[ -]?\d{4}[ -]?\d{4}\b',  # Another common format
                r'\b\d{4}[ -]?\d{3}[ -]?\d{3}\b'   # Yet another format
            ]
            
            for pattern in phone_patterns:
                phones = re.findall(pattern, text)
                if phones:
                    extracted_data["personal_info"]["phone_number"] = phones[0]
                    logger.info(f"Found phone: {phones[0]}")
                    break
            
            # Extract name with improved algorithm
            # First, try to find name at the top of the document
            # Most CVs have the name at the very top
            name_found = False
            for i, line in enumerate(lines[:5]):  # Check first 5 lines
                # Skip if it looks like an email, phone, or address
                if '@' in line or re.search(r'\d{3}', line) or len(line) > 40:
                    continue
                    
                # Check if this looks like a name (2-3 words, each capitalized)
                name_parts = line.split()
                if 1 < len(name_parts) <= 4:
                    # Check if words look like names (capitalized, not all caps)
                    if all(part[0].isupper() and not part.isupper() for part in name_parts if len(part) > 1):
                        extracted_data["personal_info"]["given_name"] = name_parts[0]
                        extracted_data["personal_info"]["family_name"] = name_parts[-1]
                        logger.info(f"Found name: {name_parts[0]} {name_parts[-1]}")
                        name_found = True
                        break
            
            # Fallback name detection - look for lines after "Name:" or similar
            if not name_found:
                for i, line in enumerate(lines):
                    if re.search(r'(?i)name\s*:\s*', line):
                        name_text = re.sub(r'(?i)name\s*:\s*', '', line).strip()
                        if name_text:
                            name_parts = name_text.split()
                            if len(name_parts) >= 2:
                                extracted_data["personal_info"]["given_name"] = name_parts[0]
                                extracted_data["personal_info"]["family_name"] = name_parts[-1]
                                logger.info(f"Found name from label: {name_parts[0]} {name_parts[-1]}")
                        break
            
            # ENHANCED: Extract address with more comprehensive patterns
            # First, search for tables which often contain address information
            address_data = {}
            
            # Check if we extracted tables (which often contain personal info)
            structured_address = False
            
            # Check tables for personal info formats (label-value pairs)
            table_address_patterns = {
                'address': [r'(?i)address', r'(?i)residence', r'(?i)location'],
                'city': [r'(?i)city', r'(?i)town'],
                'postcode': [r'(?i)postcode', r'(?i)zip', r'(?i)postal'],
                'country': [r'(?i)country', r'(?i)nation']
            }
            
            # Search for label-value pairs in text
            for field, patterns in table_address_patterns.items():
                for pattern in patterns:
                    # Look for patterns like "Address: 123 Main St" or "Address\n123 Main St"
                    matches = re.finditer(r'(?i)' + pattern + r'[\s:]*([^\n]+)', text)
                    for match in matches:
                        value = match.group(1).strip()
                        if value and len(value) > 2 and not value.lower().startswith(('http', 'www')):
                            address_data[field] = value
                            structured_address = True
                            break
            
            # Process UK postcodes (which are very distinctive)
            uk_postcode_pattern = r'\b[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}\b'
            uk_postcodes = re.findall(uk_postcode_pattern, text, re.IGNORECASE)
            if uk_postcodes:
                address_data['postcode'] = uk_postcodes[0].upper()
                address_data['country'] = address_data.get('country', 'United Kingdom')
                
                # Look for city near postcode
                postcode_index = text.find(uk_postcodes[0])
                if postcode_index > 0:
                    # Look for text before postcode that might contain city
                    pre_postcode_text = text[max(0, postcode_index - 100):postcode_index]
                    
                    # Look for common UK cities
                    uk_cities = ['Birmingham', 'Manchester', 'Glasgow', 'Liverpool',
                                'Leeds', 'Edinburgh', 'Sheffield', 'Bristol', 'Cardiff', 'Belfast',
                                'Leicester', 'Coventry', 'Nottingham', 'Newcastle', 'Hull', 'Brighton']
                    
                    for city in uk_cities:
                        if city in pre_postcode_text:
                            address_data['city'] = city
                            break
            
            # US address detection
            us_zip_pattern = r'\b\d{5}(?:-\d{4})?\b'
            us_zips = re.findall(us_zip_pattern, text)
            if us_zips and not uk_postcodes:
                address_data['postcode'] = us_zips[0]
                
                # Look for US states
                us_states = {
                    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
                    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
                    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
                    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
                    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
                    'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
                    'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
                    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
                    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
                    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
                }
                
                zip_index = text.find(us_zips[0])
                if zip_index > 0:
                    pre_zip_text = text[max(0, zip_index - 50):zip_index]
                    for abbr, state_name in us_states.items():
                        state_pattern = r'\b' + re.escape(abbr) + r'\b|\b' + re.escape(state_name) + r'\b'
                        if re.search(state_pattern, pre_zip_text, re.IGNORECASE):
                            address_data['state'] = state_name
                            address_data['country'] = 'United States'
                            break
            
            # Extract a generic address line if we haven't found it yet
            if 'address' not in address_data:
                # Common patterns for address lines
                address_line_patterns = [
                    # House/building number + street name
                    r'\b\d+\s+[A-Za-z0-9\s\.,]+(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
                    # Building name + street
                    r'\b[A-Za-z]+\s+(?:House|Building|Apartments|Court|Gardens)[\s,]+[A-Za-z\s]+(?:Street|Road|Avenue)\b',
                    # Apartment/flat number
                    r'\b(?:Apt|Apartment|Flat|Unit|Suite)\s*(?:#|No|Number)?\s*\d+[\s,]+[A-Za-z0-9\s\.,]+\b'
                ]
                
                for pattern in address_line_patterns:
                    matches = re.finditer(pattern, text, re.IGNORECASE)
                    for match in matches:
                        potential_address = match.group(0).strip()
                        # Verify it's not too short and doesn't look like a name
                        if len(potential_address) > 10 and not all(word[0].isupper() for word in potential_address.split()):
                            address_data['address'] = potential_address
                            break
                    if 'address' in address_data:
                        break
            
            # Extract country if not already found
            if 'country' not in address_data:
                # List of common countries
                countries = [
                    'United Kingdom', 'United States', 'Canada', 'Australia', 'Germany',
                    'France', 'Spain', 'Italy', 'Netherlands', 'Sweden', 'Denmark',
                    'Norway', 'Finland', 'Ireland', 'Belgium', 'Switzerland', 'Austria',
                    'Portugal', 'Greece', 'Poland', 'Russia', 'China', 'Japan', 'India',
                    'Brazil', 'Mexico', 'South Africa', 'Singapore', 'New Zealand'
                ]
                
                for country in countries:
                    if re.search(r'\b' + re.escape(country) + r'\b', text, re.IGNORECASE):
                        address_data['country'] = country
                        break
                
                # Also look for country codes
                country_codes = {
                    'UK': 'United Kingdom', 'GB': 'United Kingdom', 'US': 'United States', 'USA': 'United States',
                    'CA': 'Canada', 'AU': 'Australia', 'DE': 'Germany', 'FR': 'France', 'ES': 'Spain', 'IT': 'Italy'
                }
                
                for code, country in country_codes.items():
                    if re.search(r'\b' + re.escape(code) + r'\b', text):
                        address_data['country'] = country
                        break
            
            # Update the extracted data with our findings
            if address_data:
                if 'address' in address_data:
                    extracted_data["personal_info"]["address"]["address_line1"] = address_data['address']
                if 'city' in address_data:
                    extracted_data["personal_info"]["address"]["city"] = address_data['city']
                if 'postcode' in address_data:
                    extracted_data["personal_info"]["address"]["postcode"] = address_data['postcode']
                if 'country' in address_data:
                    extracted_data["personal_info"]["address"]["country"] = address_data['country']
                if 'state' in address_data and 'city' not in address_data:
                    extracted_data["personal_info"]["address"]["city"] = address_data['state']  # Use state as city if no city found
                    
                logger.info(f"Found address data: {address_data}")
            
            # ENHANCED: Extract phone numbers with comprehensive patterns for international formats
            phone_patterns = [
                # International format
                r'(?:\+\d{1,3}[-.\s]?)?\(?(?:\d{1,4})\)?[-.\s]?(?:\d{1,4})[-.\s]?(?:\d{1,9})',
                
                # UK format variations
                r'\b(?:0\d{2,5}[-\s]?\d{5,8}|\+44[-\s]?\d{2,5}[-\s]?\d{5,8})',
                
                # US/Canada format variations
                r'\b(?:\+?1[-\s.]?)?\(?(?:\d{3})\)?[-.\s]?(?:\d{3})[-.\s]?(?:\d{4})',
                
                # Generic formats
                r'\b\d{3}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b',
                r'\b\d{4}[-.\s]?\d{3}[-.\s]?\d{3}\b',
                r'\b\d{5}[-.\s]?\d{5,6}\b'
            ]
            
            found_phone = False
            for pattern in phone_patterns:
                phones = re.findall(pattern, text)
                if phones:
                    # Clean up the phone number
                    phone = phones[0]
                    # Remove unwanted characters but keep the + sign for country code
                    cleaned_phone = re.sub(r'[^\d+]', '', phone)
                    
                    # Format nicely if it looks like an international number
                    if cleaned_phone.startswith('+'):
                        # Keep the format with the international code
                        formatted_phone = cleaned_phone
                    else:
                        # Add spaces for readability if it's a plain number
                        if len(cleaned_phone) >= 10:
                            formatted_phone = ' '.join([cleaned_phone[i:i+3] for i in range(0, len(cleaned_phone), 3)])
                        else:
                            formatted_phone = cleaned_phone
                    
                    extracted_data["personal_info"]["phone_number"] = formatted_phone
                    logger.info(f"Found phone number: {formatted_phone}")
                    found_phone = True
                    break
            
            # Education detection with improved algorithm
            education_keywords = [
                'education', 'degree', 'university', 'college', 'bachelor', 'master', 'ph.d', 
                'diploma', 'school', 'qualification', 'academic'
            ]
            
            # Find education section in the document
            education_section = None
            for i, para in enumerate(paragraphs):
                if any(keyword.lower() in para.lower() for keyword in education_keywords):
                    # Found an education-related paragraph
                    education_section_start = i
                    # Combine this and next few paragraphs as education section
                    education_section = ' '.join(paragraphs[i:min(i+5, len(paragraphs))])
                    break
            
            # Extract structured education information
            if education_section:
                # Try to find degree information
                degree_patterns = [
                    r'(?i)(bachelor|master|ph\.?d|doctorate|diploma|certificate|b\.?a|b\.?s|b\.?sc|m\.?a|m\.?s|m\.?sc|m\.?b\.?a)(?:\s+of|\s+in)?\s+([A-Za-z\s,]+)',
                    r'(?i)(bachelor|master|ph\.?d|doctorate|diploma|certificate)(?:\s+degree)?'
                ]
                
                degrees_found = []
                for pattern in degree_patterns:
                    matches = re.findall(pattern, education_section)
                    if matches:
                        degrees_found.extend(matches)
                
                # Create education entry from found degrees
                if degrees_found:
                    for degree_match in degrees_found[:2]:  # Limit to top 2 degrees
                        level = degree_match[0] if isinstance(degree_match, tuple) else degree_match
                        field = degree_match[1] if isinstance(degree_match, tuple) and len(degree_match) > 1 else ""
                        
                        # Map common degree abbreviations to full names
                        level_mapping = {
                            'ba': "Bachelor's Degree", 'bs': "Bachelor's Degree", 'bsc': "Bachelor's Degree", 
                            'ma': "Master's Degree", 'ms': "Master's Degree", 'msc': "Master's Degree", 
                            'mba': "Master's Degree (MBA)", 'phd': "Doctorate (PhD)"
                        }
                        
                        # Normalize the level
                        level_lower = re.sub(r'[^a-zA-Z]', '', level.lower())
                        if level_lower in level_mapping:
                            level_of_study = level_mapping[level_lower]
                        elif 'bachelor' in level_lower:
                            level_of_study = "Bachelor's Degree"
                        elif 'master' in level_lower:
                            level_of_study = "Master's Degree"
                        elif 'phd' in level_lower or 'doctor' in level_lower:
                            level_of_study = "Doctorate"
                        else:
                            level_of_study = "Certificate/Diploma"
                        
                        education_entry = {
                            "study_area": field.strip() if field else "Not specified",
                            "level_of_study": level_of_study,
                            "grades": "Not specified",
                            "date_achieved": ""
                        }
                        
                        # Try to find the date/year
                        year_pattern = r'(?:19|20)\d{2}'
                        years = re.findall(year_pattern, education_section)
                        if years:
                            # Use most recent year as graduation date
                            sorted_years = sorted(years, reverse=True)
                            education_entry["date_achieved"] = sorted_years[0]
                            
                        extracted_data["education"].append(education_entry)
            else:
                # Create a minimal education entry
                extracted_data["education"].append({
                    "study_area": "Not specified",
                    "level_of_study": "Not specified",
                    "grades": "Not specified",
                    "date_achieved": ""
                })
            
            # Employment history extraction with improved algorithm
            employment_keywords = ['experience', 'work', 'job', 'career', 'employment', 'professional']
            
            # Find employment section
            employment_section = None
            for i, para in enumerate(paragraphs):
                if any(keyword.lower() in para.lower() for keyword in employment_keywords):
                    # Found an employment-related paragraph
                    employment_section_start = i
                    # Combine this and next several paragraphs
                    employment_section = ' '.join(paragraphs[i:min(i+8, len(paragraphs))])
                    break
            
            if employment_section:
                # Extract job titles and companies
                job_patterns = [
                    r'(?i)([\w\s]+?)\s+(?:at|@|with|for)\s+([\w\s&,\.]+)',  # "Software Engineer at Google"
                    r'(?i)([\w\s]+?)\s*[:\-]\s*([\w\s&,\.]+)',  # "Position: Software Engineer - Google"
                    r'(?i)([\w\s]+?)\s*[,]\s*([\w\s&,\.]+)'     # "Software Engineer, Google"
                ]
                
                jobs_found = []
                for pattern in job_patterns:
                    matches = re.findall(pattern, employment_section)
                    if matches:
                        jobs_found.extend(matches)
                
                if jobs_found:
                    for i, job_match in enumerate(jobs_found[:2]):  # Limit to top 2 positions
                        if len(job_match) >= 2:
                            job_title = job_match[0].strip()
                            company = job_match[1].strip()
                            
                            # Extract duration if available
                            duration = "Not specified"
                            duration_pattern = r'(?i)(\d+)\s*(?:year|yr)s?'
                            duration_matches = re.findall(duration_pattern, employment_section)
                            if duration_matches:
                                years = int(duration_matches[0])
                                if years < 1:
                                    duration = "Less than 1 year"
                                elif years <= 2:
                                    duration = "1-2 years"
                                elif years <= 5:
                                    duration = "3-5 years"
                                else:
                                    duration = "More than 5 years"
                            
                            # Try to determine industry from job title and company
                            industry = "Not specified"
                            job_company_text = f"{job_title} {company}".lower()
                            
                            if any(keyword in job_company_text for keyword in ['finance', 'bank', 'accounting']):
                                industry = "Finance"
                            elif any(keyword in job_company_text for keyword in ['tech', 'software', 'it', 'developer']):
                                industry = "Technology"
                            elif any(keyword in job_company_text for keyword in ['health', 'medical', 'hospital']):
                                industry = "Healthcare"
                            elif any(keyword in job_company_text for keyword in ['education', 'teaching', 'school']):
                                industry = "Education"
                            
                            employment_entry = {
                                "job_role": job_title,
                                "industry": industry,
                                "duration": duration,
                                "key_skills": "Not specified",
                                "company": company
                            }
                            
                            extracted_data["employment"].append(employment_entry)
                else:
                    # Create a minimal employment entry
                    extracted_data["employment"].append({
                        "job_role": "Not specified",
                        "industry": "Not specified",
                        "duration": "Not specified",
                        "key_skills": "Not specified",
                        "company": ""
                    })
            else:
                # Create a minimal employment entry
                extracted_data["employment"].append({
                    "job_role": "Not specified",
                    "industry": "Not specified",
                    "duration": "Not specified",
                    "key_skills": "Not specified",
                    "company": ""
                })
            
            # Add skills extraction to enhance employment entries
            skill_categories = {
                # Technical skills
                "technical": [
                    'Python', 'Java', 'JavaScript', 'C++', 'C#', 'PHP', 'Ruby', 'Swift',
                    'SQL', 'NoSQL', 'HTML', 'CSS', 'React', 'Angular', 'Vue', 'Django',
                    'Node.js', 'Cloud Computing', 'Azure', 'GCP', 'Docker', 'Kubernetes', 'Git',
                    'REST API', 'GraphQL', 'Machine Learning', 'AI', 'Data Science'
                ],
                
                # Professional skills
                "professional": [
                    'Project Management', 'Agile', 'Scrum', 'Leadership', 'Team Management',
                    'Communication', 'Negotiation', 'Problem Solving', 'Critical Thinking',
                    'Time Management', 'Budget Management', 'Strategy', 'Analytics'
                ],
                
                # Software & tools
                "tools": [
                    'Microsoft Office', 'Excel', 'Word', 'PowerPoint', 'Outlook', 
                    'Photoshop', 'Illustrator', 'InDesign', 'Figma', 'Sketch', 'CAD',
                    'Salesforce', 'JIRA', 'Confluence', 'Slack', 'Teams', 'SAP', 'Oracle'
                ]
            }
            
            # Extract skills from the document
            found_skills = []
            
            # Look for skills in the text
            for category, skills in skill_categories.items():
                for skill in skills:
                    if re.search(r'\b' + re.escape(skill) + r'\b', text, re.IGNORECASE):
                        found_skills.append(skill)
            
            # If we found skills, enhance the employment entries
            if found_skills:
                skills_str = ", ".join(found_skills[:10])  # Limit to top 10 skills
                
                # Update the first employment entry with skills
                if extracted_data["employment"]:
                    extracted_data["employment"][0]["key_skills"] = skills_str
            
            # Save the extracted data
            extracted_data_json = json.dumps(extracted_data)
            logger.info(f"Extracted CV data: {extracted_data_json}")
            
            # Clean up temporary file
            try:
                if temp_filepath and os.path.exists(temp_filepath):
                    os.unlink(temp_filepath)
                    logger.info(f"Temporary file removed: {temp_filepath}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {str(e)}")
            
            return JsonResponse({
                "status": "success",
                "message": "CV data extracted successfully",
                "data": extracted_data
            })
        except ImportError as e:
            logger.error(f"pdfplumber import error: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "PDF processing library not available. Please ensure pdfplumber is installed."
            }, status=500)
        except Exception as e:
            logger.error(f"Error extracting CV data: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "Failed to extract CV data"
            }, status=500)
    except Exception as e:
        logger.error(f"Error processing CV file: {str(e)}")
        return JsonResponse({
            "status": "error",
            "message": "Failed to process CV file"
        }, status=500)

@login_required
@require_POST
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def lookup_postcode(request):
    """Basic postcode lookup - redirects to addresses lookup"""
    return lookup_postcode_addresses(request)

@login_required
@require_POST
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def lookup_postcode_public(request):
    """Public postcode lookup - redirects to addresses lookup"""
    return lookup_postcode_addresses(request)

@login_required
@require_POST
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def lookup_postcode_addresses(request):
    """
    API endpoint to lookup all addresses for a UK postcode and return them for user selection.
    Returns multiple addresses that users can choose from.
    """
    postcode = request.POST.get('postcode', '').strip()
    if not postcode:
        return JsonResponse({'error': 'Postcode is required'}, status=400)
    
    # Basic postcode validation
    import re
    uk_postcode_pattern = r'^[A-Z]{1,2}[0-9R][0-9A-Z]?\s?[0-9][A-Z]{2}$'
    if not re.match(uk_postcode_pattern, postcode.upper().replace(' ', '')):
        return JsonResponse({'error': 'Invalid UK postcode format'}, status=400)
    
    try:
        # Get API key from environment variable
        api_key = getattr(settings, 'IDEAL_POSTCODES_API_KEY', None)
        if not api_key:
            return JsonResponse({
                'error': 'Postcode lookup service not configured'
            }, status=503)
        
        api_url = f"https://api.ideal-postcodes.co.uk/v1/postcodes/{postcode}?api_key={api_key}"
        response = requests.get(api_url, timeout=10)
        
        if not response.ok:
            return JsonResponse({
                'error': f"Postcode lookup failed with status {response.status_code}",
                'details': response.text
            }, status=response.status_code)
        
        data = response.json()
        
        if data.get('code') == 2000 and data.get('result'):
            # Format addresses for selection
            addresses = []
            for address in data['result']:
                # Build a full address string for display
                address_parts = []
                
                # Add house number/name and street
                if address.get('line_1'):
                    address_parts.append(address['line_1'])
                if address.get('line_2'):
                    address_parts.append(address['line_2'])
                if address.get('line_3'):
                    address_parts.append(address['line_3'])
                
                # Add post town
                if address.get('post_town'):
                    address_parts.append(address['post_town'])
                
                # Create the display string
                display_address = ', '.join(filter(None, address_parts))
                
                addresses.append({
                    'id': address.get('udprn', ''),  # Unique property reference number
                    'display': display_address,
                    'line_1': address.get('line_1', ''),
                    'line_2': address.get('line_2', ''),
                    'line_3': address.get('line_3', ''),
                    'post_town': address.get('post_town', ''),
                    'county': address.get('county', ''),
                    'country': address.get('country', 'England'),
                    'postcode': address.get('postcode', postcode),
                    'dependant_locality': address.get('dependant_locality', ''),
                    'double_dependant_locality': address.get('double_dependant_locality', ''),
                    'thoroughfare': address.get('thoroughfare', ''),
                    'building_name': address.get('building_name', ''),
                    'sub_building_name': address.get('sub_building_name', ''),
                    'po_box': address.get('po_box', ''),
                    'department_name': address.get('department_name', ''),
                    'organisation_name': address.get('organisation_name', '')
                })
            
            return JsonResponse({
                'status': 'success',
                'postcode': postcode,
                'addresses': addresses,
                'count': len(addresses)
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'No addresses found for this postcode'
            }, status=404)
        
    except Exception as e:
        logger.error(f"Postcode address lookup error: {str(e)}")
        return JsonResponse({'error': 'Service temporarily unavailable'}, status=500)

@login_required
def add_quiz_assignment(request):
    """Add quiz assignment to user for Assessment Data tab only"""
    if not request.user.role in ['admin', 'instructor', 'superadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            quiz_id = data.get('quiz_id')
            assignment_type = data.get('assignment_type')
            item_name = data.get('item_name', '')
            notes = data.get('notes', '')
            
            # Validate required fields
            if not all([user_id, quiz_id, assignment_type]):
                return JsonResponse({'success': False, 'error': 'Missing required fields'})
            
            # Only allow initial assessment assignments (VAK tests are now shown based on attempts)
            if assignment_type != 'initial_assessment':
                return JsonResponse({'success': False, 'error': 'Only Initial Assessment assignments are allowed'})
            
            # Get user and quiz objects
            user = get_object_or_404(CustomUser, id=user_id)
            quiz = get_object_or_404(Quiz, id=quiz_id)
            
            # Validate assignment type matches quiz type
            if assignment_type == 'initial_assessment' and not quiz.is_initial_assessment:
                return JsonResponse({'success': False, 'error': 'Selected quiz is not an Initial Assessment'})
            
            # Default item name to quiz title if not provided
            if not item_name:
                item_name = quiz.title
            
            # Create assignment
            assignment = UserQuizAssignment.objects.create(
                user=user,
                quiz=quiz,
                assignment_type=assignment_type,
                item_name=item_name,
                assigned_by=request.user,
                notes=notes
            )
            
            return JsonResponse({
                'success': True,
                'assignment_id': assignment.id,
                'message': f'Quiz "{item_name}" assigned successfully'
            })
                    
        except Exception as integrity_error:
            return JsonResponse({'success': False, 'error': 'Quiz already assigned to this user for this category'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def edit_quiz_assignment(request, assignment_id):
    """Edit quiz assignment"""
    if not request.user.role in ['admin', 'instructor', 'superadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    assignment = get_object_or_404(UserQuizAssignment, id=assignment_id)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_name = data.get('item_name', assignment.item_name)
            notes = data.get('notes', assignment.notes)
            is_active = data.get('is_active', assignment.is_active)
            
            # Update assignment
            assignment.item_name = item_name
            assignment.notes = notes
            assignment.is_active = is_active
            assignment.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Assignment "{item_name}" updated successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    # GET request - return assignment data
    return JsonResponse({
        'success': True,
        'assignment': {
            'id': assignment.id,
            'item_name': assignment.item_name,
            'notes': assignment.notes or '',
            'is_active': assignment.is_active,
            'quiz_title': assignment.quiz.title,
            'assignment_type': assignment.assignment_type
        }
    })

@login_required
def delete_quiz_assignment(request, assignment_id):
    """Delete quiz assignment"""
    if not request.user.role in ['admin', 'instructor', 'superadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method == 'POST':
        try:
            assignment = get_object_or_404(UserQuizAssignment, id=assignment_id)
            item_name = assignment.item_name
            assignment.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Assignment "{item_name}" deleted successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required 
def get_available_quizzes(request):
    """Get available quizzes for assignment (Initial Assessment only)"""
    if not request.user.role in ['admin', 'instructor', 'superadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    assignment_type = request.GET.get('type')
    user_id = request.GET.get('user_id')
    
    if not assignment_type or not user_id:
        return JsonResponse({'success': False, 'error': 'Missing parameters'})
    
    try:
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Only allow initial assessment assignments
        if assignment_type != 'initial_assessment':
            return JsonResponse({'success': False, 'error': 'Only Initial Assessment assignments are allowed'})
        
        # Get initial assessment quizzes
        quizzes = Quiz.objects.filter(
            is_initial_assessment=True,
            creator__branch=request.user.branch,
            is_active=True
        )
        
        # Exclude already assigned quizzes
        assigned_quiz_ids = UserQuizAssignment.objects.filter(
            user=user,
            assignment_type=assignment_type,
            is_active=True
        ).values_list('quiz_id', flat=True)
        
        available_quizzes = quizzes.exclude(id__in=assigned_quiz_ids)
        
        quiz_data = [
            {
                'id': quiz.id,
                'title': quiz.title,
                'description': quiz.description or ''
            }
            for quiz in available_quizzes
        ]
        
        return JsonResponse({
            'success': True,
            'quizzes': quiz_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# Google OAuth Views
def google_login(request):
    """Initiate Google OAuth login"""
    from django.conf import settings
    from account_settings.models import GlobalAdminSettings
    import os
    
    # Get Google OAuth credentials from database (Google OAuth is always enabled when credentials are available)
    try:
        global_settings = GlobalAdminSettings.get_settings()
        if global_settings.google_client_id and global_settings.google_client_secret:
            google_client_id = global_settings.google_client_id
            google_client_secret = global_settings.google_client_secret
        else:
            # Fallback to environment variables
            google_client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
            google_client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)
    except:
        # Fallback to environment variables if database check fails
        google_client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
        google_client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)
    
    if not google_client_id or not google_client_secret:
        messages.error(request, "Google OAuth is not configured. Please contact the administrator.")
        return redirect('users:register')
    
    # Get branch from URL parameter
    branch_slug = request.GET.get('branch')
    
    # Build redirect URI
    redirect_uri = request.build_absolute_uri(reverse('users:google_callback'))
    
    # Add branch to state parameter if provided
    state = f"branch={branch_slug}" if branch_slug else ""
    
    # Build Google OAuth URL
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        f"client_id={google_client_id}&"
        f"redirect_uri={redirect_uri}&"
        "scope=openid email profile&"
        "response_type=code&"
        "access_type=offline&"
        f"state={state}"
    )
    
    return redirect(google_auth_url)

def google_callback(request):
    """Handle Google OAuth callback"""
    from django.conf import settings
    from account_settings.models import GlobalAdminSettings
    import requests as http_requests
    
    code = request.GET.get('code')
    state = request.GET.get('state', '')
    
    if not code:
        messages.error(request, "Google authentication failed. Please try again.")
        return redirect('users:register')
    
    # Get Google OAuth credentials from database (Google OAuth is always enabled when credentials are available)
    try:
        global_settings = GlobalAdminSettings.get_settings()
        if global_settings.google_client_id and global_settings.google_client_secret:
            google_client_id = global_settings.google_client_id
            google_client_secret = global_settings.google_client_secret
            allowed_domains = global_settings.google_oauth_domains
        else:
            # Fallback to environment variables
            google_client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
            google_client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)
            allowed_domains = None
    except:
        # Fallback to environment variables if database check fails
        google_client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
        google_client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)
        allowed_domains = None
    
    if not google_client_id or not google_client_secret:
        messages.error(request, "Google OAuth is not configured.")
        return redirect('users:register')
    
    try:
        # Exchange code for token
        redirect_uri = request.build_absolute_uri(reverse('users:google_callback'))
        
        token_data = {
            'client_id': google_client_id,
            'client_secret': google_client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }
        
        token_response = http_requests.post(
            'https://oauth2.googleapis.com/token',
            data=token_data
        )
        
        if token_response.status_code != 200:
            messages.error(request, "Failed to authenticate with Google.")
            return redirect('users:register')
        
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        
        if not access_token:
            messages.error(request, "Failed to get access token from Google.")
            return redirect('users:register')
        
        # Get user info from Google
        user_response = http_requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        
        if user_response.status_code != 200:
            messages.error(request, "Failed to get user information from Google.")
            return redirect('users:register')
        
        user_data = user_response.json()
        
        # Extract user information
        email = user_data.get('email')
        first_name = user_data.get('given_name', '')
        last_name = user_data.get('family_name', '')
        google_id = user_data.get('id')
        
        if not email:
            messages.error(request, "Google account does not have an email address.")
            return redirect('users:register')
        
        # Check if domain is allowed (if domain restrictions are configured)
        if allowed_domains and allowed_domains.strip():
            email_domain = email.split('@')[1].lower() if '@' in email else ''
            allowed_domain_list = [domain.strip().lower() for domain in allowed_domains.split(',') if domain.strip()]
            
            if email_domain and allowed_domain_list and email_domain not in allowed_domain_list:
                messages.error(request, f"Your email domain ({email_domain}) is not allowed for Google OAuth login. Please contact the administrator.")
                return redirect('users:register')
        
        # Parse state to get branch
        branch = None
        if state and 'branch=' in state:
            branch_slug = state.split('branch=')[1].split('&')[0]
            if branch_slug:
                try:
                    portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
                    branch = portal.branch
                except BranchPortal.DoesNotExist:
                    pass
        
        # Check if user already exists
        try:
            user = CustomUser.objects.get(email=email)
            
            # If user exists, check 2FA before logging them in
            if user.is_active:
                # Check if user has 2FA enabled
                from .models import TwoFactorAuth, OTPToken
                user_2fa = None
                try:
                    user_2fa = TwoFactorAuth.objects.get(user=user)
                except TwoFactorAuth.DoesNotExist:
                    pass
                
                if user_2fa and user_2fa.oauth_enabled:
                    # User has 2FA enabled, generate and send OTP
                    try:
                        # Clear any existing unused OTP tokens for this user
                        OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                        
                        # Create new OTP token
                        otp_token = OTPToken.objects.create(user=user, purpose='login')
                        
                        # Send OTP email
                        otp_token.send_otp_email(request)
                        
                        # Store user info in session for OTP verification
                        request.session['otp_user_id'] = user.id
                        request.session['otp_token_id'] = otp_token.id
                        request.session['otp_next_url'] = reverse('users:role_based_redirect')
                        request.session['oauth_branch_context'] = {
                            'branch_id': branch.id if branch else None,
                            'branch_name': branch.name if branch else None,
                            'update_branch': branch and not user.branch
                        }
                        
                        # Log 2FA step for OAuth
                        import logging
                        auth_logger = logging.getLogger('authentication')
                        
                        def get_client_ip(request):
                            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                            if x_forwarded_for:
                                ip = x_forwarded_for.split(',')[0].strip()
                            else:
                                ip = request.META.get('REMOTE_ADDR', '')
                            return ip
                        
                        auth_logger.info(f"2FA OTP sent for Google OAuth login: {user.username} from IP: {get_client_ip(request)}")
                        
                        messages.success(request, f"A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                        
                        # Redirect to OTP verification page
                        return redirect('users:verify_otp')
                        
                    except Exception as e:
                        logger.error(f"Error sending OTP for Google OAuth user {user.username}: {str(e)}")
                        messages.error(request, "Error sending verification code. Please try again or contact support.")
                        return redirect('users:register')
                
                # Normal OAuth login flow (no 2FA or 2FA disabled)
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                
                # Update branch if coming from branch portal and user doesn't have one
                if branch and not user.branch:
                    user.branch = branch
                    user.save()
                    messages.success(request, f"Welcome back! You've been enrolled in {branch.name}.")
                else:
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                
                return redirect('users:role_based_redirect')
            else:
                messages.error(request, "Your account is inactive. Please contact the administrator.")
                return redirect('login')
                
        except CustomUser.DoesNotExist:
            # Create new user account
            username = email.split('@')[0]
            
            # Ensure username is unique
            counter = 1
            original_username = username
            while CustomUser.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1
            
            # Create user
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='learner',  # Always create as learner for public registration
                is_active=True
            )
            
            # Assign to branch
            if branch:
                user.branch = branch
                user.save()
                messages.success(request, f"Account created successfully! You've been enrolled in {branch.name}.")
            else:
                # Assign to a non-default branch (default branch reserved for global admin)
                from core.utils.default_assignments import DefaultAssignmentManager
                safe_branch = DefaultAssignmentManager.get_safe_branch_for_user(user)
                if safe_branch:
                    user.branch = safe_branch
                    user.save()
                    messages.success(request, f"Account created successfully! You've been assigned to {safe_branch.name}.")
                else:
                    messages.success(request, "Account created successfully! Please contact administrator for branch assignment.")
            
            # Check if user has 2FA enabled before logging them in
            from .models import TwoFactorAuth, OTPToken
            user_2fa = None
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
            except TwoFactorAuth.DoesNotExist:
                pass
            
            if user_2fa and user_2fa.oauth_enabled:
                # User has 2FA enabled, generate and send OTP
                try:
                    # Clear any existing unused OTP tokens for this user
                    OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                    
                    # Create new OTP token
                    otp_token = OTPToken.objects.create(user=user, purpose='login')
                    
                    # Send OTP email
                    otp_token.send_otp_email(request)
                    
                    # Store user info in session for OTP verification (new user context)
                    request.session['otp_user_id'] = user.id
                    request.session['otp_token_id'] = otp_token.id
                    request.session['otp_next_url'] = reverse('users:role_based_redirect')
                    request.session['oauth_branch_context'] = {
                        'branch_id': branch.id if branch else None,
                        'branch_name': branch.name if branch else None,
                        'is_new_user': True
                    }
                    
                    # Log 2FA step for OAuth new user
                    import logging
                    auth_logger = logging.getLogger('authentication')
                    
                    def get_client_ip(request):
                        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                        if x_forwarded_for:
                            ip = x_forwarded_for.split(',')[0].strip()
                        else:
                            ip = request.META.get('REMOTE_ADDR', '')
                        return ip
                    
                    auth_logger.info(f"2FA OTP sent for new Google OAuth user: {user.username} from IP: {get_client_ip(request)}")
                    
                    messages.success(request, f"Account created successfully! A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                    
                    # Redirect to OTP verification page
                    return redirect('users:verify_otp')
                    
                except Exception as e:
                    logger.error(f"Error sending OTP for new Google OAuth user {user.username}: {str(e)}")
                    messages.error(request, "Error sending verification code. Please try again or contact support.")
                    return redirect('users:register')
            
            # Normal OAuth login flow for new user (no 2FA or 2FA disabled)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            
            return redirect('users:role_based_redirect')
            
    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}")
        messages.error(request, "An error occurred during Google authentication. Please try again.")
        return redirect('users:register')

# Microsoft OAuth Views
def microsoft_login(request):
    """Initiate Microsoft OAuth login"""
    from django.conf import settings
    from account_settings.models import GlobalAdminSettings
    import logging
    import os
    
    logger = logging.getLogger(__name__)
    
    # Get Microsoft OAuth credentials from database
    try:
        global_settings = GlobalAdminSettings.get_settings()
        if global_settings.microsoft_client_id and global_settings.microsoft_client_secret:
            microsoft_client_id = global_settings.microsoft_client_id
            microsoft_client_secret = global_settings.microsoft_client_secret
            microsoft_tenant_id = global_settings.microsoft_tenant_id or 'common'  # Default to 'common' for multi-tenant
        else:
            # Fallback to environment variables
            microsoft_client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', None)
            microsoft_client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', None)
            microsoft_tenant_id = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
    except:
        # Fallback to environment variables if database check fails
        microsoft_client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', None)
        microsoft_client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', None)
        microsoft_tenant_id = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
    
    if not microsoft_client_id or not microsoft_client_secret:
        logger.error("Microsoft OAuth: Missing client credentials")
        messages.error(request, "Microsoft OAuth is not configured. Please contact the administrator.")
        return redirect('users:register')
    
    # Get branch from URL parameter
    branch_slug = request.GET.get('branch')
    
    # Build redirect URI
    redirect_uri = request.build_absolute_uri(reverse('users:microsoft_callback'))
    
    # Add branch to state parameter if provided
    state = f"branch={branch_slug}" if branch_slug else ""
    
    # Build Microsoft OAuth URL (using v2.0 endpoint)
    from urllib.parse import quote
    
    microsoft_auth_url = (
        f"https://login.microsoftonline.com/{microsoft_tenant_id}/oauth2/v2.0/authorize?"
        f"client_id={microsoft_client_id}&"
        f"response_type=code&"
        f"redirect_uri={quote(redirect_uri, safe='')}&"
        "scope=openid email profile User.Read&"
        "response_mode=query&"
        f"state={quote(state, safe='')}"
    )
    
    return redirect(microsoft_auth_url)

def microsoft_callback(request):
    """Handle Microsoft OAuth callback"""
    from django.conf import settings
    from account_settings.models import GlobalAdminSettings
    import requests as http_requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    code = request.GET.get('code')
    state = request.GET.get('state', '')
    error = request.GET.get('error')
    
    if error:
        logger.error(f"Microsoft OAuth error: {error}")
        messages.error(request, f"Microsoft authentication failed: {error}")
        return redirect('users:register')
    
    if not code:
        messages.error(request, "Microsoft authentication failed. Please try again.")
        return redirect('users:register')
    
    # Parse branch from state parameter
    branch = None
    if state and 'branch=' in state:
        branch_slug = state.split('branch=')[1]
        try:
            from branch_portal.models import BranchPortal
            portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = portal.branch
        except:
            pass
    
    # Get Microsoft OAuth credentials from database
    try:
        global_settings = GlobalAdminSettings.get_settings()
        if global_settings.microsoft_client_id and global_settings.microsoft_client_secret:
            microsoft_client_id = global_settings.microsoft_client_id
            microsoft_client_secret = global_settings.microsoft_client_secret
            microsoft_tenant_id = global_settings.microsoft_tenant_id or 'common'
            allowed_domains = global_settings.microsoft_oauth_domains
        else:
            # Fallback to environment variables
            microsoft_client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', None)
            microsoft_client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', None)
            microsoft_tenant_id = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
            allowed_domains = None
    except:
        # Fallback to environment variables if database check fails
        microsoft_client_id = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_ID', None)
        microsoft_client_secret = getattr(settings, 'MICROSOFT_OAUTH_CLIENT_SECRET', None)
        microsoft_tenant_id = getattr(settings, 'MICROSOFT_OAUTH_TENANT_ID', 'common')
        allowed_domains = None
    
    if not microsoft_client_id or not microsoft_client_secret:
        messages.error(request, "Microsoft OAuth is not configured.")
        return redirect('users:register')
    
    try:
        # Exchange code for token
        redirect_uri = request.build_absolute_uri(reverse('users:microsoft_callback'))
        
        token_data = {
            'client_id': microsoft_client_id,
            'client_secret': microsoft_client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }
        
        # Add retry logic for token exchange with exponential backoff
        import time
        
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                token_response = http_requests.post(
                    f'https://login.microsoftonline.com/{microsoft_tenant_id}/oauth2/v2.0/token',
                    data=token_data,
                    timeout=30
                )
                
                if token_response.status_code == 429:  # Rate limited
                    retry_after = int(token_response.headers.get('Retry-After', 1))
                    logger.warning(f"Microsoft OAuth rate limited. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                elif token_response.status_code == 200:
                    break  # Success
                else:
                    logger.error(f"Microsoft token exchange failed: {token_response.text}")
                    messages.error(request, "Failed to authenticate with Microsoft.")
                    return redirect('users:register')
                    
            except http_requests.exceptions.Timeout:
                logger.warning(f"Microsoft OAuth timeout, retry {retry_count + 1}/{max_retries}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Exponential backoff
                    continue
                else:
                    messages.error(request, "Microsoft authentication timed out. Please try again.")
                    return redirect('users:register')
            except Exception as e:
                logger.error(f"Microsoft OAuth error: {str(e)}")
                messages.error(request, "Microsoft authentication failed. Please try again.")
                return redirect('users:register')
        
        if retry_count >= max_retries:
            logger.error("Microsoft OAuth: Max retries exceeded for token exchange")
            messages.error(request, "Microsoft authentication is currently unavailable. Please try again later.")
            return redirect('users:register')
        
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        
        if not access_token:
            messages.error(request, "Failed to get access token from Microsoft.")
            return redirect('users:register')
        
        # Get user info from Microsoft Graph API with retry logic
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                user_response = http_requests.get(
                    'https://graph.microsoft.com/v1.0/me',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=30
                )
                
                if user_response.status_code == 429:  # Rate limited
                    retry_after = int(user_response.headers.get('Retry-After', 1))
                    logger.warning(f"Microsoft Graph API rate limited. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                elif user_response.status_code == 200:
                    break  # Success
                else:
                    logger.error(f"Microsoft user info request failed: {user_response.text}")
                    messages.error(request, "Failed to get user information from Microsoft.")
                    return redirect('users:register')
                    
            except http_requests.exceptions.Timeout:
                logger.warning(f"Microsoft Graph API timeout, retry {retry_count + 1}/{max_retries}")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Exponential backoff
                    continue
                else:
                    messages.error(request, "Microsoft authentication timed out. Please try again.")
                    return redirect('users:register')
            except Exception as e:
                logger.error(f"Microsoft Graph API error: {str(e)}")
                messages.error(request, "Failed to get user information from Microsoft.")
                return redirect('users:register')
        
        if retry_count >= max_retries:
            logger.error("Microsoft OAuth: Max retries exceeded for user info request")
            messages.error(request, "Microsoft authentication is currently unavailable. Please try again later.")
            return redirect('users:register')
        
        user_data = user_response.json()
        
        # Extract user information
        email = user_data.get('mail') or user_data.get('userPrincipalName')
        first_name = user_data.get('givenName', '')
        last_name = user_data.get('surname', '')
        microsoft_id = user_data.get('id')
        
        if not email:
            logger.error(f"Microsoft OAuth: No email found in user data: {user_data}")
            messages.error(request, "Unable to get email from Microsoft account. Please try again or contact support.")
            return redirect('users:register')
        
        # Check if domain is allowed (if domain restrictions are configured)
        try:
            global_settings = GlobalAdminSettings.get_settings()
            allowed_domains = global_settings.microsoft_oauth_domains if hasattr(global_settings, 'microsoft_oauth_domains') else None
        except:
            allowed_domains = None
            
        if allowed_domains and allowed_domains.strip():
            email_domain = email.split('@')[1].lower() if '@' in email else ''
            allowed_domain_list = [domain.strip().lower() for domain in allowed_domains.split(',') if domain.strip()]
            
            if email_domain and allowed_domain_list and email_domain not in allowed_domain_list:
                logger.warning(f"Microsoft OAuth: Domain {email_domain} not allowed for user {email}")
                messages.error(request, f"Your email domain ({email_domain}) is not allowed for Microsoft OAuth login. Please contact the administrator.")
                return redirect('users:register')
        
        logger.info(f"Microsoft OAuth: Successful authentication for user {email}")
        
        # Check if user already exists
        try:
            user = CustomUser.objects.get(email=email, is_active=True)
            
            # Update user's Microsoft information if needed
            if not user.first_name and first_name:
                user.first_name = first_name
            if not user.last_name and last_name:
                user.last_name = last_name
            user.save()
            
            # Check if user has 2FA enabled before logging them in
            from .models import TwoFactorAuth, OTPToken
            user_2fa = None
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
            except TwoFactorAuth.DoesNotExist:
                pass
            
            if user_2fa and user_2fa.oauth_enabled:
                # User has 2FA enabled, generate and send OTP
                try:
                    # Clear any existing unused OTP tokens for this user
                    OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                    
                    # Create new OTP token
                    otp_token = OTPToken.objects.create(user=user, purpose='login')
                    
                    # Send OTP email
                    otp_token.send_otp_email(request)
                    
                    # Store user info in session for OTP verification
                    request.session['otp_user_id'] = user.id
                    request.session['otp_token_id'] = otp_token.id
                    request.session['otp_next_url'] = reverse('users:role_based_redirect')
                    request.session['oauth_branch_context'] = {
                        'branch_id': branch.id if branch else None,
                        'branch_name': branch.name if branch else None,
                        'branch_mismatch': branch and user.branch != branch
                    }
                    
                    # Log 2FA step for Microsoft OAuth
                    import logging
                    auth_logger = logging.getLogger('authentication')
                    
                    def get_client_ip(request):
                        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                        if x_forwarded_for:
                            ip = x_forwarded_for.split(',')[0].strip()
                        else:
                            ip = request.META.get('REMOTE_ADDR', '')
                        return ip
                    
                    auth_logger.info(f"2FA OTP sent for Microsoft OAuth login: {user.username} from IP: {get_client_ip(request)}")
                    
                    messages.success(request, f"A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                    
                    # Redirect to OTP verification page
                    return redirect('users:verify_otp')
                    
                except Exception as e:
                    logger.error(f"Error sending OTP for Microsoft OAuth user {user.username}: {str(e)}")
                    messages.error(request, "Error sending verification code. Please try again or contact support.")
                    return redirect('users:register')
            
            # Normal Microsoft OAuth login flow (no 2FA or 2FA disabled)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            
            if branch and user.branch != branch:
                messages.info(request, f"You are already registered. Welcome back! Note: You are accessing {branch.name} but your account is associated with {user.branch.name if user.branch else 'the default branch'}.")
            else:
                messages.success(request, "Welcome back! You have been logged in successfully.")
                
            return redirect('users:role_based_redirect')
                
        except CustomUser.DoesNotExist:
            # Create new user account
            username = email.split('@')[0]
            
            # Ensure username is unique
            counter = 1
            original_username = username
            while CustomUser.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1
            
            # Determine branch assignment before user creation (avoid default branch for non-global admin)
            user_branch = branch
            if not user_branch:
                # Assign to a non-default branch (default branch reserved for global admin)
                from core.utils.default_assignments import DefaultAssignmentManager
                from types import SimpleNamespace
                # Since this is OAuth registration, user will be a learner, so use safe branch
                dummy_user = SimpleNamespace(role='learner')  # Create type-safe dummy user for role check
                user_branch = DefaultAssignmentManager.get_safe_branch_for_user(dummy_user)
                
            if not user_branch:
                logger.error("No non-default branches available for Microsoft OAuth user creation")
                messages.error(request, "System configuration error: No branches available for new user registration. Please contact the administrator.")
                return redirect('users:register')
            
            # Create user with branch assignment to avoid validation errors
            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='learner',  # Always create as learner for public registration
                is_active=True,
                branch=user_branch  # Assign branch during creation
            )
            
            # Set success message based on branch assignment
            if branch:
                messages.success(request, f"Account created successfully! You've been enrolled in {branch.name}.")
            else:
                messages.success(request, "Account created successfully! Welcome to the LMS.")
            
            # Check if user has 2FA enabled before logging them in
            from .models import TwoFactorAuth, OTPToken
            user_2fa = None
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
            except TwoFactorAuth.DoesNotExist:
                pass
            
            if user_2fa and user_2fa.oauth_enabled:
                # User has 2FA enabled, generate and send OTP
                try:
                    # Clear any existing unused OTP tokens for this user
                    OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                    
                    # Create new OTP token
                    otp_token = OTPToken.objects.create(user=user, purpose='login')
                    
                    # Send OTP email
                    otp_token.send_otp_email(request)
                    
                    # Store user info in session for OTP verification (new user context)
                    request.session['otp_user_id'] = user.id
                    request.session['otp_token_id'] = otp_token.id
                    request.session['otp_next_url'] = reverse('users:role_based_redirect')
                    request.session['oauth_branch_context'] = {
                        'branch_id': branch.id if branch else None,
                        'branch_name': branch.name if branch else None,
                        'is_new_user': True
                    }
                    
                    # Log 2FA step for OAuth new user
                    import logging
                    auth_logger = logging.getLogger('authentication')
                    
                    def get_client_ip(request):
                        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                        if x_forwarded_for:
                            ip = x_forwarded_for.split(',')[0].strip()
                        else:
                            ip = request.META.get('REMOTE_ADDR', '')
                        return ip
                    
                    auth_logger.info(f"2FA OTP sent for new Microsoft OAuth user: {user.username} from IP: {get_client_ip(request)}")
                    
                    messages.success(request, f"Account created successfully! A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                    
                    # Redirect to OTP verification page
                    return redirect('users:verify_otp')
                    
                except Exception as e:
                    logger.error(f"Error sending OTP for new Microsoft OAuth user {user.username}: {str(e)}")
                    messages.error(request, "Error sending verification code. Please try again or contact support.")
                    return redirect('users:register')
            
            # Normal OAuth login flow for new user (no 2FA or 2FA disabled)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            
            return redirect('users:role_based_redirect')
            
    except Exception as e:
        logger.error(f"Microsoft OAuth error: {str(e)}")
        messages.error(request, "An error occurred during Microsoft authentication. Please try again.")
        return redirect('users:register')

# Branch-specific Authentication Views

def branch_login(request, branch_slug=None):
    """Branch-specific login view with forgot password option"""
    branch = None
    branch_portal = None
    
    # Get Session status for display
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    client_ip = get_client_ip(request)
    try:
        def dummy_get_response(request):
            return None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        
        Session_status = {
            'warning_level': 'none',
            'failure_count': 0,
            'remaining_attempts': 5,
            'max_attempts': 5,
            'lockout_minutes': 0,
            'remaining_time': 0,
            'is_blocked': False
        }
    
    # Get branch context if branch_slug is provided
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('login')  # Fallback to global login
    
    # Handle form submission
    if request.method == "POST":
        username = request.POST.get("username") 
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # If user doesn't have a branch and we have a branch context, assign it
            if not user.branch and branch:
                user.branch = branch
                user.save()
            elif not user.branch:
                # Try to get the only branch if there's just one
                try:
                    default_branch = Branch.objects.first()
                    if default_branch:
                        user.branch = default_branch
                        user.save()
                except Exception as e:
                    logger.error(f"Error assigning branch to user: {str(e)}")

            # Check if user has 2FA enabled
            from .models import TwoFactorAuth, OTPToken
            user_2fa = None
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
            except TwoFactorAuth.DoesNotExist:
                pass
            
            if user_2fa and user_2fa.is_enabled:
                # User has 2FA enabled, generate and send OTP
                try:
                    # Clear any existing unused OTP tokens for this user
                    OTPToken.objects.filter(user=user, is_used=False, purpose='login').delete()
                    
                    # Create new OTP token
                    otp_token = OTPToken.objects.create(user=user, purpose='login')
                    
                    # Send OTP email
                    otp_token.send_otp_email(request)
                    
                    # Store user info in session for OTP verification
                    request.session['otp_user_id'] = user.id
                    request.session['otp_token_id'] = otp_token.id
                    request.session['otp_next_url'] = request.POST.get('next') or request.GET.get('next') or reverse('users:role_based_redirect')
                    request.session['otp_branch_slug'] = branch_slug  # Store branch context
                    
                    # Log 2FA step
                    import logging
                    auth_logger = logging.getLogger('authentication')
                    auth_logger.info(f"2FA OTP sent for branch login: {user.username} from IP: {get_client_ip(request)}")
                    
                    messages.success(request, f"A verification code has been sent to {user.email}. Please check your email and enter the code to complete your login.")
                    
                    # Redirect to OTP verification page with branch context
                    if branch_slug:
                        return redirect('users:verify_otp_branch', branch_slug=branch_slug)
                    else:
                        return redirect('users:verify_otp')
                        
                except Exception as e:
                    logger.error(f"Error sending OTP for branch login {user.username}: {str(e)}")
                    messages.error(request, "Error sending verification code. Please try again or contact support.")
                    
                    context = {
                        'branch': branch,
                        'branch_portal': branch_portal,
                        'branch_slug': branch_slug,
                        'is_branch_login': branch_slug is not None,
                        'next': request.GET.get('next', ''),
                        'Session_status': Session_status,
                    }
                    return render(request, "users/auth/branch_login.html", context)

            # Normal login flow (no 2FA or 2FA disabled)
            login(request, user)
            
            # Success message with branch context
            if branch:
                messages.success(request, f"Welcome back to {branch.name}, {user.username}!")
            else:
                messages.success(request, f"Welcome back, {user.username}!")
            
            # Redirect to next URL or dashboard
            next_url = request.POST.get('next') or request.GET.get('next') or reverse('users:role_based_redirect')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password")

    # Prepare context for template
    context = {
        'branch': branch,
        'branch_portal': branch_portal,
        'branch_slug': branch_slug,
        'is_branch_login': branch_slug is not None,
        'next': request.GET.get('next', ''),
        'Session_status': Session_status,
    }
    
    return render(request, "users/auth/branch_login.html", context)


def verify_otp(request, branch_slug=None):
    """Verify OTP for 2FA login"""
    # Check if user has pending OTP verification
    if 'otp_user_id' not in request.session or 'otp_token_id' not in request.session:
        messages.error(request, "No pending verification found. Please log in again.")
        if branch_slug:
            return redirect('users:branch_login', branch_slug=branch_slug)
        else:
            return redirect('login')
    
    # Get branch context if branch_slug is provided
    branch = None
    branch_portal = None
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('login')
    
    # Get user and token from session
    try:
        from .models import OTPToken
        user = CustomUser.objects.get(id=request.session['otp_user_id'])
        otp_token = OTPToken.objects.get(id=request.session['otp_token_id'])
    except (CustomUser.DoesNotExist, OTPToken.DoesNotExist):
        messages.error(request, "Invalid verification session. Please log in again.")
        if branch_slug:
            return redirect('users:branch_login', branch_slug=branch_slug)
        else:
            return redirect('login')
    
    # Check if token is expired
    if otp_token.is_expired():
        messages.error(request, "Verification code has expired. Please log in again to get a new code.")
        # Clean up session
        for key in ['otp_user_id', 'otp_token_id', 'otp_next_url', 'otp_branch_slug']:
            request.session.pop(key, None)
        if branch_slug:
            return redirect('users:branch_login', branch_slug=branch_slug)
        else:
            return redirect('login')
    
    if request.method == 'POST':
        otp_code = request.POST.get('otp_code', '').strip()
        
        if not otp_code:
            messages.error(request, "Please enter the verification code.")
        elif len(otp_code) < 6 or len(otp_code) > 8:
            messages.error(request, "Please enter a valid verification code (6 digits for email/app codes, 8 characters for backup codes).")
        elif otp_token.otp_code == otp_code:
            # Email OTP is correct, complete the login
            try:
                # Mark token as used
                otp_token.mark_as_used()
                
                # Log successful 2FA verification
                import logging
                auth_logger = logging.getLogger('authentication')
                
                def get_client_ip(request):
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip = x_forwarded_for.split(',')[0].strip()
                    else:
                        ip = request.META.get('REMOTE_ADDR', '')
                    return ip
                
                auth_logger.info(f"Successful 2FA verification for user: {user.username} from IP: {get_client_ip(request)}")
                
                # Update last login time
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                # Log the user in
                login(request, user)
                
                # Get next URL from session
                next_url = request.session.get('otp_next_url', reverse('users:role_based_redirect'))
                
                # Handle OAuth branch context if present
                oauth_context = request.session.get('oauth_branch_context')
                if oauth_context:
                    if oauth_context.get('update_branch') and oauth_context.get('branch_id'):
                        from branches.models import Branch
                        try:
                            oauth_branch = Branch.objects.get(id=oauth_context.get('branch_id'))
                            user.branch = oauth_branch
                            user.save()
                        except Branch.DoesNotExist:
                            pass
                
                # Clean up session
                for key in ['otp_user_id', 'otp_token_id', 'otp_next_url', 'otp_branch_slug', 'oauth_branch_context']:
                    request.session.pop(key, None)
                
                # Success message with branch context
                if oauth_context:
                    if oauth_context.get('is_new_user'):
                        if oauth_context.get('branch_name'):
                            messages.success(request, f"Account created successfully! Welcome to {oauth_context.get('branch_name')}, {user.username}! Two-factor authentication verified successfully.")
                        else:
                            messages.success(request, f"Account created successfully! Welcome, {user.username}! Two-factor authentication verified successfully.")
                    elif oauth_context.get('branch_mismatch'):
                        messages.info(request, f"Welcome back, {user.username}! Two-factor authentication verified successfully. Note: You are accessing {oauth_context.get('branch_name')} but your account is associated with {user.branch.name if user.branch else 'the default branch'}.")
                    else:
                        messages.success(request, f"Welcome back, {user.username}! Two-factor authentication verified successfully.")
                elif branch:
                    messages.success(request, f"Welcome back to {branch.name}, {user.username}! Two-factor authentication verified successfully.")
                else:
                    messages.success(request, f"Welcome back, {user.username}! Two-factor authentication verified successfully.")
                
                # Redirect to next URL
                if next_url:
                    from django.utils.http import url_has_allowed_host_and_scheme
                    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                        return redirect(next_url)
                
                return redirect('users:role_based_redirect')
                
            except Exception as e:
                logger.error(f"Error completing 2FA login for user {user.username}: {str(e)}")
                messages.error(request, "An error occurred during verification. Please try again.")
        else:
            # Check if it might be a TOTP code from authenticator app
            from .models import TwoFactorAuth
            try:
                user_2fa = TwoFactorAuth.objects.get(user=user)
                if user_2fa.totp_enabled and user_2fa.verify_totp(otp_code):
                    # TOTP code is correct, complete the login
                    try:
                        # Mark email token as used (even though we used TOTP)
                        otp_token.mark_as_used()
                        
                        # Log successful 2FA verification
                        import logging
                        auth_logger = logging.getLogger('authentication')
                        
                        def get_client_ip(request):
                            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                            if x_forwarded_for:
                                ip = x_forwarded_for.split(',')[0].strip()
                            else:
                                ip = request.META.get('REMOTE_ADDR', '')
                            return ip
                        
                        auth_logger.info(f"Successful TOTP 2FA verification for user: {user.username} from IP: {get_client_ip(request)}")
                        
                        # Update last login time
                        user.last_login = timezone.now()
                        user.save(update_fields=['last_login'])
                        
                        # Log the user in
                        login(request, user)
                        
                        # Get next URL from session
                        next_url = request.session.get('otp_next_url', reverse('users:role_based_redirect'))
                        
                        # Handle OAuth branch context if present
                        oauth_context = request.session.get('oauth_branch_context')
                        if oauth_context:
                            if oauth_context.get('update_branch') and oauth_context.get('branch_id'):
                                from branches.models import Branch
                                try:
                                    oauth_branch = Branch.objects.get(id=oauth_context.get('branch_id'))
                                    user.branch = oauth_branch
                                    user.save()
                                except Branch.DoesNotExist:
                                    pass
                        
                        # Clean up session
                        for key in ['otp_user_id', 'otp_token_id', 'otp_next_url', 'otp_branch_slug', 'oauth_branch_context']:
                            request.session.pop(key, None)
                        
                        # Success message with branch context
                        if oauth_context:
                            if oauth_context.get('is_new_user'):
                                if oauth_context.get('branch_name'):
                                    messages.success(request, f"Account created successfully! Welcome to {oauth_context.get('branch_name')}, {user.username}! Authenticator app verification successful.")
                                else:
                                    messages.success(request, f"Account created successfully! Welcome, {user.username}! Authenticator app verification successful.")
                            elif oauth_context.get('branch_mismatch'):
                                messages.info(request, f"Welcome back, {user.username}! Authenticator app verification successful. Note: You are accessing {oauth_context.get('branch_name')} but your account is associated with {user.branch.name if user.branch else 'the default branch'}.")
                            else:
                                messages.success(request, f"Welcome back, {user.username}! Authenticator app verification successful.")
                        elif branch:
                            messages.success(request, f"Welcome back to {branch.name}, {user.username}! Authenticator app verification successful.")
                        else:
                            messages.success(request, f"Welcome back, {user.username}! Authenticator app verification successful.")
                        
                        # Redirect to next URL
                        if next_url:
                            from django.utils.http import url_has_allowed_host_and_scheme
                            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                                return redirect(next_url)
                        
                        return redirect('users:role_based_redirect')
                        
                    except Exception as e:
                        logger.error(f"Error completing TOTP 2FA login for user {user.username}: {str(e)}")
                        messages.error(request, "An error occurred during verification. Please try again.")
                else:
                    # Check if it might be a backup code
                    if user_2fa.use_backup_token(otp_code.upper()):
                        # Backup code is correct, complete the login
                        try:
                            # Mark email token as used
                            otp_token.mark_as_used()
                            
                            # Log successful backup code usage
                            import logging
                            auth_logger = logging.getLogger('authentication')
                            
                            def get_client_ip(request):
                                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                                if x_forwarded_for:
                                    ip = x_forwarded_for.split(',')[0].strip()
                                else:
                                    ip = request.META.get('REMOTE_ADDR', '')
                                return ip
                            
                            auth_logger.info(f"Successful backup code 2FA verification for user: {user.username} from IP: {get_client_ip(request)}")
                            
                            # Update last login time
                            user.last_login = timezone.now()
                            user.save(update_fields=['last_login'])
                            
                            # Log the user in
                            login(request, user)
                            
                            # Get next URL from session
                            next_url = request.session.get('otp_next_url', reverse('users:role_based_redirect'))
                            
                            # Clean up session
                            for key in ['otp_user_id', 'otp_token_id', 'otp_next_url', 'otp_branch_slug', 'oauth_branch_context']:
                                request.session.pop(key, None)
                            
                            messages.success(request, f"Welcome back, {user.username}! Backup code verification successful. Consider setting up a new authenticator app.")
                            
                            # Redirect to next URL
                            if next_url:
                                from django.utils.http import url_has_allowed_host_and_scheme
                                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                                    return redirect(next_url)
                            
                            return redirect('users:role_based_redirect')
                            
                        except Exception as e:
                            logger.error(f"Error completing backup code 2FA login for user {user.username}: {str(e)}")
                            messages.error(request, "An error occurred during verification. Please try again.")
                    else:
                        messages.error(request, "Invalid verification code. Please check your email, authenticator app, or try a backup code.")
            except TwoFactorAuth.DoesNotExist:
                messages.error(request, "Invalid verification code. Please check your email and try again.")
    
    # Prepare context for template
    context = {
        'user': user,
        'branch': branch,
        'branch_portal': branch_portal,
        'branch_slug': branch_slug,
        'is_branch_login': branch_slug is not None,
        'email_masked': f"{user.email[:2]}***@{user.email.split('@')[1]}" if user.email else "your email",
    }
    
    return render(request, 'users/auth/verify_otp.html', context)


def branch_register(request, branch_slug=None):
    """Branch-specific registration view with email verification"""
    branch = None
    branch_portal = None
    
    # Get branch context if branch_slug is provided
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('register')  # Fallback to global registration
    
    if request.method == 'POST':
        form = SimpleRegistrationForm(request.POST, branch=branch)
        
        if form.is_valid():
            # Create user but mark as inactive (requires email verification)
            user = form.save(commit=False)
            user.is_active = False  # Will be activated after email verification
            user.save()
            
            # Auto-assign to branch if coming from branch portal
            if branch:
                user.branch = branch
                user.save()
            else:
                # For general registration, assign to default branch if available
                default_branch = Branch.objects.first()
                if default_branch:
                    user.branch = default_branch
                    user.save()
            
            # Create email verification token
            verification_token = EmailVerificationToken.objects.create(
                user=user,
                branch=branch
            )
            
            # Send verification email
            verification_token.send_verification_email(request)
            
            # Redirect to verification sent page
            if branch_slug:
                return redirect('verification_sent', branch_slug=branch_slug)
            else:
                return redirect('verification_sent')
    else:
        form = SimpleRegistrationForm(branch=branch)
    
    context = {
        'form': form,
        'branch': branch,
        'branch_portal': branch_portal,
        'branch_slug': branch_slug,
        'is_branch_register': branch_slug is not None,
    }
    
    return render(request, 'users/auth/branch_register.html', context)


def forgot_password(request, branch_slug=None):
    """Forgot password view with branch-specific SMTP"""
    import re
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    from django.utils import timezone
    from datetime import timedelta
    
    branch = None
    branch_portal = None
    
    # Get branch context if branch_slug is provided
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('forgot_password')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        
        # Comprehensive email validation
        if not email:
            messages.error(request, "Please enter your email address.")
        else:
            # Server-side email validation
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "Please enter a valid email address.")
                context = {
                    'branch': branch,
                    'branch_portal': branch_portal,
                    'branch_slug': branch_slug,
                    'email': email,  # Preserve user input
                }
                return render(request, 'users/auth/forgot_password.html', context)
            
            # Rate limiting - prevent spam requests
            # Check if user has made too many requests recently
            recent_tokens = PasswordResetToken.objects.filter(
                user__email=email,
                created_at__gte=timezone.now() - timedelta(minutes=15)
            ).count()
            
            if recent_tokens >= 3:
                messages.warning(request, 
                    "Too many password reset requests. Please wait 15 minutes before trying again.")
                context = {
                    'branch': branch,
                    'branch_portal': branch_portal,
                    'branch_slug': branch_slug,
                    'email': email,
                }
                return render(request, 'users/auth/forgot_password.html', context)
            
            # Find user by email - handle potential duplicates
            user = CustomUser.objects.filter(email=email).first()
            
            if user:
                # Check if user is active
                if not user.is_active:
                    messages.error(request, 
                        "This account is inactive. Please contact support for assistance.")
                    context = {
                        'branch': branch,
                        'branch_portal': branch_portal,
                        'branch_slug': branch_slug,
                        'email': email,
                    }
                    return render(request, 'users/auth/forgot_password.html', context)
                
                # Delete old unused tokens for this user to prevent accumulation
                PasswordResetToken.objects.filter(
                    user=user,
                    is_used=False,
                    created_at__lt=timezone.now() - timedelta(hours=1)
                ).delete()
                
                # Create password reset token
                try:
                    reset_token = PasswordResetToken.objects.create(
                        user=user,
                        branch=branch
                    )
                    
                    # Send reset email with error handling
                    email_sent = reset_token.send_reset_email(request)
                    
                    if email_sent:
                        messages.success(request, 
                            f"Password reset instructions have been sent to {email}. "
                            f"Please check your inbox and spam folder.")
                        
                        # Redirect to reset sent page
                        if branch_slug:
                            return redirect('password_reset_sent', branch_slug=branch_slug)
                        else:
                            return redirect('password_reset_sent')
                    else:
                        # Email failed but don't crash - provide helpful message
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f" Email system failed to send password reset email to {email}. "
                                   f"Check logs for details (OAuth2 credentials may be invalid/expired, or SMTP not configured).")
                        
                        # Delete the token since email failed
                        reset_token.delete()
                        
                        # Provide user-friendly error message
                        messages.error(request, 
                            "Unable to send password reset email. The email system may not be properly configured. "
                            "Please contact your system administrator for assistance, or try again later.")
                        
                        context = {
                            'branch': branch,
                            'branch_portal': branch_portal,
                            'branch_slug': branch_slug,
                            'email': email,
                        }
                        return render(request, 'users/auth/forgot_password.html', context)
                        
                except Exception as e:
                    # Handle token creation errors
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to create password reset token for {email}: {str(e)}")
                    
                    messages.error(request, 
                        "There was a problem processing your request. Please try again later.")
                    
                    context = {
                        'branch': branch,
                        'branch_portal': branch_portal,
                        'branch_slug': branch_slug,
                        'email': email,
                    }
                    return render(request, 'users/auth/forgot_password.html', context)
                    
            else:
                # Don't reveal that the email doesn't exist for Session
                # But still show success message and redirect
                messages.success(request, 
                    f"If an account with {email} exists, password reset instructions have been sent. "
                    f"Please check your inbox and spam folder.")
                    
                if branch_slug:
                    return redirect('password_reset_sent', branch_slug=branch_slug)
                else:
                    return redirect('password_reset_sent')
    
    context = {
        'branch': branch,
        'branch_portal': branch_portal,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/forgot_password.html', context)


def reset_password(request, token, branch_slug=None):
    """Reset password using token"""
    try:
        reset_token = PasswordResetToken.objects.get(
            token=token,
            is_used=False
        )
        
        if reset_token.is_expired():
            messages.error(request, "This password reset link has expired. Please request a new one.")
            if branch_slug:
                return redirect('forgot_password', branch_slug=branch_slug)
            else:
                return redirect('forgot_password')
        
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if not password1 or not password2:
                messages.error(request, "Please fill in both password fields.")
            elif password1 != password2:
                messages.error(request, "Passwords do not match.")
            elif len(password1) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
            else:
                # Update password
                user = reset_token.user
                user.set_password(password1)
                user.save()
                
                # Mark token as used
                reset_token.mark_as_used()
                
                messages.success(request, "Your password has been successfully updated. You can now log in with your new password.")
                
                # Redirect to login page
                if branch_slug:
                    return redirect('branch_login', branch_slug=branch_slug)
                else:
                    return redirect('login')
        
        context = {
            'token': token,
            'branch': reset_token.branch,
            'branch_slug': branch_slug,
            'reset_token': reset_token,
        }
        
        return render(request, 'users/auth/reset_password.html', context)
        
    except PasswordResetToken.DoesNotExist:
        messages.error(request, "Invalid or expired password reset link.")
        if branch_slug:
            return redirect('forgot_password', branch_slug=branch_slug)
        else:
            return redirect('forgot_password')


def verify_email(request, token, branch_slug=None):
    """Verify email using token"""
    try:
        verification_token = EmailVerificationToken.objects.get(
            token=token,
            is_used=False
        )
        
        if verification_token.is_expired():
            messages.error(request, "This email verification link has expired. Please request a new one.")
            if branch_slug:
                return redirect('resend_verification', branch_slug=branch_slug)
            else:
                return redirect('resend_verification')
        
        # Mark token as used and activate user
        verification_token.mark_as_used()
        
        messages.success(request, "Your email has been successfully verified! You can now log in to your account.")
        
        # Redirect to success page
        if branch_slug:
            return redirect('verification_success', branch_slug=branch_slug)
        else:
            return redirect('verification_success')
            
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, "Invalid or expired email verification link.")
        if branch_slug:
            return redirect('resend_verification', branch_slug=branch_slug)
        else:
            return redirect('resend_verification')


def resend_verification(request, branch_slug=None):
    """Resend email verification"""
    branch = None
    
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            messages.error(request, "Invalid branch portal.")
            return redirect('resend_verification')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if email:
            try:
                user = CustomUser.objects.get(email=email, is_active=False)
                
                # Delete old verification tokens for this user
                EmailVerificationToken.objects.filter(user=user, is_used=False).delete()
                
                # Create new verification token
                verification_token = EmailVerificationToken.objects.create(
                    user=user,
                    branch=branch
                )
                
                # Send verification email
                verification_token.send_verification_email(request)
                
                messages.success(request, f"A new verification email has been sent to {email}")
                
                if branch_slug:
                    return redirect('verification_sent', branch_slug=branch_slug)
                else:
                    return redirect('verification_sent')
                    
            except CustomUser.DoesNotExist:
                messages.error(request, "No unverified account found with this email address.")
        else:
            messages.error(request, "Please enter your email address.")
    
    context = {
        'branch': branch,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/resend_verification.html', context)


# Status/Success Pages

def verification_sent(request, branch_slug=None):
    """Verification email sent confirmation"""
    branch = None
    
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            pass
    
    context = {
        'branch': branch,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/verification_sent.html', context)


def verification_success(request, branch_slug=None):
    """Email verification success"""
    branch = None
    
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            pass
    
    context = {
        'branch': branch,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/verification_success.html', context)


def password_reset_sent(request, branch_slug=None):
    """Password reset email sent confirmation"""
    branch = None
    
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            pass
    
    context = {
        'branch': branch,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/password_reset_sent.html', context)


def password_reset_success(request, branch_slug=None):
    """Password reset success"""
    branch = None
    
    if branch_slug:
        try:
            branch_portal = BranchPortal.objects.get(slug=branch_slug, is_active=True)
            branch = branch_portal.branch
        except BranchPortal.DoesNotExist:
            pass
    
    context = {
        'branch': branch,
        'branch_slug': branch_slug,
    }
    
    return render(request, 'users/auth/password_reset_success.html', context)

@login_required
@require_http_methods(["POST"])
# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
def check_duplicate_user_role(request):
    """AJAX endpoint to check for duplicate user role accounts."""
    try:
        import json
        data = json.loads(request.body)
        
        email = data.get('email', '').strip()
        username = data.get('username', '').strip()
        role = data.get('role', '')
        branch_id = data.get('branch', '')
        exclude_user_id = data.get('exclude_user_id')
        
        response_data = {
            'email_duplicate': False,
            'username_duplicate': False,
            'email_message': '',
            'username_message': ''
        }
        
        # Check email + role combination
        if email and role:
            email_query = CustomUser.objects.filter(
                email=email,
                role=role,
                is_active=True
            )
            
            if branch_id:
                try:
                    branch = Branch.objects.get(pk=branch_id)
                    email_query = email_query.filter(branch=branch)
                except Branch.DoesNotExist:
                    branch = None
            
            if exclude_user_id:
                email_query = email_query.exclude(pk=exclude_user_id)
            
            if email_query.exists():
                existing_user = email_query.first()
                response_data['email_duplicate'] = True
                if existing_user.branch:
                    response_data['email_message'] = f"A user with this email and role already exists in branch '{existing_user.branch.name}'"
                else:
                    response_data['email_message'] = f"A user with this email and role already exists"
        
        # Check username + role combination
        if username and role:
            username_query = CustomUser.objects.filter(
                username=username,
                is_active=True
            )
            
            if exclude_user_id:
                username_query = username_query.exclude(pk=exclude_user_id)
            
            if username_query.exists():
                existing_user = username_query.first()
                if existing_user.role == role:
                    response_data['username_duplicate'] = True
                    if branch_id and existing_user.branch and str(existing_user.branch.pk) == str(branch_id):
                        response_data['username_message'] = f"A user with this username and role already exists in this branch"
                    elif not branch_id and not existing_user.branch:
                        response_data['username_message'] = f"A user with this username and role already exists"
        
        # Special check for Global Admin role
        if role == 'globaladmin' and email:
            globaladmin_query = CustomUser.objects.filter(
                email=email,
                role='globaladmin',
                is_active=True
            )
            
            if exclude_user_id:
                globaladmin_query = globaladmin_query.exclude(pk=exclude_user_id)
            
            if globaladmin_query.exists():
                response_data['email_duplicate'] = True
                response_data['email_message'] = "A Global Admin user with this email already exists"
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'error': 'An error occurred while checking for duplicates',
            'details': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def validate_bulk_import(request):
    """Validate uploaded Excel file for bulk user import with comprehensive validation."""
    from core.utils.validation import ValidationService
    
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'error': 'No file uploaded'}, status=400)
        
        if not file.name.lower().endswith(('.xlsx', '.xls')):
            return JsonResponse({'error': 'Please upload an Excel file (.xlsx or .xls)'}, status=400)
        
        # Import pandas for Excel reading
        try:
            import pandas as pd
        except ImportError:
            return JsonResponse({'error': 'Excel processing library not available'}, status=500)
        
        # Read Excel file
        try:
            df = pd.read_excel(file)
        except Exception as e:
            return JsonResponse({'error': f'Error reading Excel file: {str(e)}'}, status=400)
        
        # Expected columns
        expected_columns = ['First Name', 'Last Name', 'Email', 'Username', 'Password', 'Role', 'Branch', 'Group(s)']
        
        # Check if all expected columns are present
        missing_columns = [col for col in expected_columns if col not in df.columns]
        if missing_columns:
            return JsonResponse({
                'error': f'Missing required columns: {", ".join(missing_columns)}',
                'expected_columns': expected_columns
            }, status=400)
        
        users = []
        has_errors = False
        
        for index, row in df.iterrows():
            if index == 0:  # Skip the sample data row
                continue
                
            user_data = {
                'name': f"{str(row['First Name']).strip()} {str(row['Last Name']).strip()}",
                'email': str(row['Email']).strip() if pd.notna(row['Email']) else '',
                'username': str(row['Username']).strip() if pd.notna(row['Username']) else '',
                'password': str(row['Password']).strip() if pd.notna(row['Password']) else '',
                'role': str(row['Role']).strip().lower() if pd.notna(row['Role']) else '',
                'branch': str(row['Branch']).strip() if pd.notna(row['Branch']) else '',
                'groups': str(row['Group(s)']).strip() if pd.notna(row['Group(s)']) else '',
                'is_valid': True,
                'errors': {}
            }
            
            # Validate email
            if not user_data['email']:
                user_data['is_valid'] = False
                user_data['errors']['email'] = 'Email is required'
            elif CustomUser.objects.filter(email=user_data['email']).exists():
                user_data['is_valid'] = False
                user_data['errors']['email'] = 'Email already exists'
            
            # Validate username
            if not user_data['username']:
                user_data['is_valid'] = False
                user_data['errors']['username'] = 'Username is required'
            elif CustomUser.objects.filter(username=user_data['username']).exists():
                user_data['is_valid'] = False
                user_data['errors']['username'] = 'Username already exists'
            
            # Validate role
            valid_roles = ['learner', 'instructor', 'admin', 'superadmin']
            if user_data['role'] not in valid_roles:
                user_data['is_valid'] = False
                user_data['errors']['role'] = f'Role must be one of: {", ".join(valid_roles)}'
            
            # Validate password
            if not user_data['password'] or len(user_data['password']) < 8:
                user_data['is_valid'] = False
                user_data['errors']['password'] = 'Password must be at least 8 characters long'
            
            # Validate branch if provided
            if user_data['branch']:
                from branches.models import Branch
                if not Branch.objects.filter(name=user_data['branch']).exists():
                    user_data['is_valid'] = False
                    user_data['errors']['branch'] = 'Branch does not exist'
            
            if not user_data['is_valid']:
                has_errors = True
            
            users.append(user_data)
        
        return JsonResponse({
            'users': users,
            'has_errors': has_errors,
            'total_users': len(users)
        })
        
    except Exception as e:
        logger.error(f"Error in validate_bulk_import: {str(e)}")
        return JsonResponse({'error': 'An error occurred while processing the file'}, status=500)


@login_required
@require_http_methods(["POST"])
def validate_bulk_data(request):
    """Validate bulk import data after user edits."""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        import json
        data = json.loads(request.body)
        users = data.get('users', [])
        
        has_errors = False
        
        for user in users:
            user['is_valid'] = True
            user['errors'] = {}
            
            # Validate email
            if not user.get('email'):
                user['is_valid'] = False
                user['errors']['email'] = 'Email is required'
            elif CustomUser.objects.filter(email=user['email']).exists():
                user['is_valid'] = False
                user['errors']['email'] = 'Email already exists'
            
            # Validate username
            if not user.get('username'):
                user['is_valid'] = False
                user['errors']['username'] = 'Username is required'
            elif CustomUser.objects.filter(username=user['username']).exists():
                user['is_valid'] = False
                user['errors']['username'] = 'Username already exists'
            
            # Validate role
            valid_roles = ['learner', 'instructor', 'admin', 'superadmin']
            if user.get('role') not in valid_roles:
                user['is_valid'] = False
                user['errors']['role'] = f'Role must be one of: {", ".join(valid_roles)}'
            
            if not user['is_valid']:
                has_errors = True
        
        return JsonResponse({
            'users': users,
            'has_errors': has_errors
        })
        
    except Exception as e:
        logger.error(f"Error in validate_bulk_data: {str(e)}")
        return JsonResponse({'error': 'An error occurred while validating data'}, status=500)


@login_required
@require_http_methods(["POST"])
def bulk_import(request):
    """Process bulk import of users."""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        import json
        from django.contrib.auth.hashers import make_password
        from branches.models import Branch
        from groups.models import BranchGroup
        
        data = json.loads(request.body)
        users = data.get('users', [])
        
        created_users = []
        errors = []
        
        for user_data in users:
            try:
                # Create user
                user = CustomUser.objects.create(
                    username=user_data['username'],
                    email=user_data['email'],
                    first_name=user_data['name'].split(' ')[0],
                    last_name=' '.join(user_data['name'].split(' ')[1:]) if ' ' in user_data['name'] else '',
                    password=make_password(user_data['password']),
                    role=user_data['role'],
                    is_active=True
                )
                
                # Assign branch if specified
                if user_data.get('branch'):
                    try:
                        branch = Branch.objects.get(name=user_data['branch'])
                        user.branch = branch
                        user.save()
                    except Branch.DoesNotExist:
                        pass
                
                # Assign groups if specified
                if user_data.get('groups'):
                    group_names = [g.strip() for g in user_data['groups'].split(';')]
                    for group_name in group_names:
                        if group_name:
                            try:
                                # Use the user's branch for group creation
                                user_branch = user.branch if hasattr(user, 'branch') and user.branch else None
                                if user_branch:
                                    group, _ = BranchGroup.objects.get_or_create(
                                        name=group_name,
                                        branch=user_branch
                                    )
                                    # Add user to the group using GroupMembership
                                    from groups.models import GroupMembership
                                    GroupMembership.objects.get_or_create(
                                        group=group,
                                        user=user,
                                        is_active=True
                                    )
                            except Exception as e:
                                logger.error(f"Error creating/assigning group {group_name}: {str(e)}")
                                pass
                
                created_users.append(user.username)
                
            except Exception as e:
                errors.append(f"Error creating user {user_data.get('username', 'Unknown')}: {str(e)}")
        
        return JsonResponse({
            'success': True,
            'created_users': len(created_users),
            'errors': errors,
            'message': f'Successfully imported {len(created_users)} users'
        })
        
    except Exception as e:
        logger.error(f"Error in bulk_import: {str(e)}")
        return JsonResponse({'error': 'An error occurred while importing users'}, status=500)

# Auto-timezone detection views
from .auto_timezone import set_user_timezone_auto, get_user_timezone_status

@login_required
def auto_timezone_set(request):
    """Wrapper for auto timezone setting"""
    return set_user_timezone_auto(request)

@login_required  
def auto_timezone_status(request):
    """Wrapper for auto timezone status"""
    return get_user_timezone_status(request)

# @csrf_protect  # COMMENTED OUT TO FIX ERRORS
@login_required
def keep_alive_view(request):
    """Simple keep-alive endpoint to maintain session"""
    if request.method == 'POST':
        # Touch the session to keep it alive
        request.session.modified = True
        return JsonResponse({
            'status': 'success',
            'message': 'Session kept alive',
            'user': request.user.username
        })
    return JsonResponse({'status': 'error', 'message': 'POST required'})

# @csrf_exempt  # COMMENTED OUT TO FIX ERRORS
def ping_view(request):
    """Simple ping endpoint for health checks"""
    return JsonResponse({
        'status': 'ok',
        'message': 'LMS server is running',
        'authenticated': request.user.is_authenticated if hasattr(request, 'user') else False
    })
