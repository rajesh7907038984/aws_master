"""
RBAC Decorators for LMS System
Provides decorators for enforcing RBAC v0.1 permissions throughout the application
"""

from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .rbac_validators import rbac_validator
import logging

logger = logging.getLogger(__name__)

def require_rbac_permission(action, resource_type, get_resource=None, **validation_kwargs):
    """
    Decorator to enforce RBAC permissions on views
    
    Args:
        action: The action being performed (create, view, edit, delete)
        resource_type: Type of resource (user, course, business, branch, etc.)
        get_resource: Function to extract resource from view kwargs (optional)
        **validation_kwargs: Additional validation parameters
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('users:custom_login')
            
            try:
                # Extract resource if function provided
                resource = None
                if get_resource:
                    resource = get_resource(request, *args, **kwargs)
                
                # Build validation context
                validation_context = validation_kwargs.copy()
                validation_context.update(kwargs)
                
                # Validate RBAC permissions
                validation_errors = rbac_validator.validate_action(
                    user=request.user,
                    action=action,
                    resource_type=resource_type,
                    resource=resource,
                    **validation_context
                )
                
                if validation_errors:
                    logger.warning(f"RBAC access denied for user {request.user.username}: {'; '.join(validation_errors)}")
                    return HttpResponseForbidden(f"Access denied: {'; '.join(validation_errors)}")
                    
            except Exception as e:
                logger.error(f"RBAC validation error in {view_func.__name__}: {str(e)}")
                return HttpResponseForbidden("Access validation error")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def require_conditional_access(resource_type, action):
    """
    Simplified decorator for conditional access validation
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('users:custom_login')
            
            # Global Admin always has access
            if request.user.role == 'globaladmin':
                return view_func(request, *args, **kwargs)
            
            # Apply conditional access rules based on resource type
            if resource_type == 'business':
                # Super Admin: CONDITIONAL (assigned businesses only)
                if request.user.role == 'superadmin':
                    business_id = kwargs.get('business_id')
                    if business_id and not request.user.business_assignments.filter(business_id=business_id, is_active=True).exists():
                        return HttpResponseForbidden("Access denied: You can only access businesses you are assigned to")
                elif request.user.role not in ['globaladmin']:
                    return HttpResponseForbidden("Access denied: Insufficient permissions for business management")
                    
            elif resource_type == 'branch':
                # Super Admin: CONDITIONAL (within their businesses)
                if request.user.role == 'superadmin':
                    branch_id = kwargs.get('branch_id')
                    if branch_id:
                        from branches.models import Branch
                        try:
                            branch = Branch.objects.get(id=branch_id)
                            if not request.user.business_assignments.filter(business=branch.business, is_active=True).exists():
                                return HttpResponseForbidden("Access denied: You can only access branches within your assigned businesses")
                        except Branch.DoesNotExist:
                            return HttpResponseForbidden("Branch not found")
                # Branch Admin: SELF (own branch only)
                elif request.user.role == 'admin':
                    branch_id = kwargs.get('branch_id')
                    if branch_id and str(request.user.branch_id) != str(branch_id):
                        return HttpResponseForbidden("Access denied: You can only access your own branch")
                elif request.user.role not in ['globaladmin', 'superadmin', 'admin']:
                    return HttpResponseForbidden("Access denied: Insufficient permissions for branch management")
                    
            elif resource_type == 'course':
                # Course-specific conditional access
                course_id = kwargs.get('course_id') or kwargs.get('pk')
                if course_id:
                    from courses.models import Course
                    try:
                        course = Course.objects.get(id=course_id)
                        if action in ['edit', 'delete']:
                            from courses.views import check_course_edit_permission
                            if not check_course_edit_permission(request.user, course):
                                return HttpResponseForbidden("Access denied: You cannot edit this course")
                        elif action == 'view':
                            from courses.views import check_course_permission
                            if not check_course_permission(request.user, course):
                                return HttpResponseForbidden("Access denied: You cannot view this course")
                    except Course.DoesNotExist:
                        return HttpResponseForbidden("Course not found")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def require_business_scope(view_func):
    """
    Decorator to ensure Super Admins can only access resources within their assigned businesses
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        
        # Global Admin has FULL access
        if request.user.role == 'globaladmin':
            return view_func(request, *args, **kwargs)
        
        # Super Admin: Validate business scope
        if request.user.role == 'superadmin':
            # Check if the resource being accessed is within their assigned businesses
            business_id = kwargs.get('business_id')
            branch_id = kwargs.get('branch_id')
            
            if business_id:
                if not request.user.business_assignments.filter(business_id=business_id, is_active=True).exists():
                    return HttpResponseForbidden("Access denied: You can only access businesses you are assigned to")
            elif branch_id:
                from branches.models import Branch
                try:
                    branch = Branch.objects.get(id=branch_id)
                    if not request.user.business_assignments.filter(business=branch.business, is_active=True).exists():
                        return HttpResponseForbidden("Access denied: You can only access branches within your assigned businesses")
                except Branch.DoesNotExist:
                    return HttpResponseForbidden("Branch not found")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def require_self_access_only(view_func):
    """
    Decorator to ensure users can only access their own data (for learner SELF access)
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        
        # Global Admin and Super Admin have broader access
        if request.user.role in ['globaladmin', 'superadmin']:
            return view_func(request, *args, **kwargs)
        
        # Branch Admin can access users in their branch
        if request.user.role == 'admin':
            user_id = kwargs.get('user_id')
            if user_id:
                from users.models import CustomUser
                try:
                    target_user = CustomUser.objects.get(id=user_id)
                    if target_user.branch != request.user.branch:
                        return HttpResponseForbidden("Access denied: You can only access users in your branch")
                except CustomUser.DoesNotExist:
                    return HttpResponseForbidden("User not found")
        
        # Instructor can access assigned learners
        elif request.user.role == 'instructor':
            user_id = kwargs.get('user_id')
            if user_id:
                from users.models import CustomUser
                try:
                    target_user = CustomUser.objects.get(id=user_id)
                    if target_user.assigned_instructor != request.user and target_user != request.user:
                        return HttpResponseForbidden("Access denied: You can only access assigned learners or your own profile")
                except CustomUser.DoesNotExist:
                    return HttpResponseForbidden("User not found")
        
        # Learner: SELF access only
        elif request.user.role == 'learner':
            user_id = kwargs.get('user_id')
            if user_id and str(user_id) != str(request.user.id):
                return HttpResponseForbidden("Access denied: You can only access your own profile")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def require_assignment_scope(view_func):
    """
    Decorator to ensure instructors can only access courses/resources they are assigned to
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        
        # Global Admin and Super Admin have broader access
        if request.user.role in ['globaladmin', 'superadmin']:
            return view_func(request, *args, **kwargs)
        
        # Branch Admin can access resources in their branch
        if request.user.role == 'admin':
            return view_func(request, *args, **kwargs)
        
        # Instructor: Assignment-based access
        if request.user.role == 'instructor':
            course_id = kwargs.get('course_id') or kwargs.get('pk')
            if course_id:
                from courses.models import Course
                try:
                    course = Course.objects.get(id=course_id)
                    # Check if instructor is assigned to this course
                    if (course.instructor != request.user and 
                        not course.accessible_groups.filter(
                            memberships__user=request.user,
                            memberships__is_active=True
                        ).exists()):
                        return HttpResponseForbidden("Access denied: You can only access courses you are assigned to")
                except Course.DoesNotExist:
                    return HttpResponseForbidden("Course not found")
        
        # Learner: Enrolled courses only
        elif request.user.role == 'learner':
            course_id = kwargs.get('course_id') or kwargs.get('pk')
            if course_id:
                from courses.models import Course
                try:
                    course = Course.objects.get(id=course_id)
                    # Check if learner is enrolled or has group access
                    if (not course.courseenrollment_set.filter(user=request.user).exists() and
                        not course.accessible_groups.filter(
                            memberships__user=request.user,
                            memberships__is_active=True
                        ).exists()):
                        return HttpResponseForbidden("Access denied: You can only access courses you are enrolled in")
                except Course.DoesNotExist:
                    return HttpResponseForbidden("Course not found")
        
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# Convenience decorators for common patterns
def require_globaladmin(view_func):
    """Decorator to require Global Admin role"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        if request.user.role != 'globaladmin':
            return HttpResponseForbidden("Access denied: Global Admin role required")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def require_superadmin_or_higher(view_func):
    """Decorator to require Super Admin role or higher"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        if request.user.role not in ['globaladmin', 'superadmin']:
            return HttpResponseForbidden("Access denied: Super Admin role or higher required")
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def require_admin_or_higher(view_func):
    """Decorator to require Admin role or higher"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:custom_login')
        if request.user.role not in ['globaladmin', 'superadmin', 'admin']:
            return HttpResponseForbidden("Access denied: Admin role or higher required")
        return view_func(request, *args, **kwargs)
    return _wrapped_view 