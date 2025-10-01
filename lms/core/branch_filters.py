"""
Centralized branch filtering utilities for consistent data access across the LMS.
Ensures admin, instructor, and learner users only see data from their assigned branch.
Now supports session-based branch switching for admin users with additional branch assignments.
"""

from django.db.models import Q
from django.core.exceptions import PermissionDenied
from functools import wraps


class BranchFilterManager:
    """
    Centralized manager for applying branch-based filtering across the LMS.
    """
    
    @staticmethod
    def get_effective_branch(user, request=None):
        """
        Get the effective branch for the user, considering session-based switching for admin users.
        
        Args:
            user: The requesting user
            request: The request object (optional, for session access)
            
        Returns:
            Branch object or None
        """
        # For non-admin users or users without request, return their assigned branch
        if user.role != 'admin' or not request:
            return user.branch
            
        # For admin users, check if they have an active branch in session
        active_branch_id = request.session.get('admin_active_branch_id')
        if active_branch_id:
            from branches.models import Branch, AdminBranchAssignment
            try:
                active_branch = Branch.objects.get(id=active_branch_id, is_active=True)
                
                # Verify user has access to this branch
                if (active_branch == user.branch or 
                    AdminBranchAssignment.objects.filter(
                        user=user, 
                        branch=active_branch, 
                        is_active=True
                    ).exists()):
                    return active_branch
                else:
                    # Invalid session branch, clear it
                    del request.session['admin_active_branch_id']
            except Branch.DoesNotExist:
                # Invalid branch ID in session, clear it
                del request.session['admin_active_branch_id']
        
        # Default to user's primary branch
        return user.branch
    
    @staticmethod
    def filter_queryset_by_branch(user, queryset, request=None):
        """
        Apply branch filtering to any queryset based on user role.
        Now supports session-based branch switching for admin users.
        
        Args:
            user: The requesting user
            queryset: Django queryset to filter
            request: The request object (optional, for session access)
            
        Returns:
            Filtered queryset based on user's branch access
        """
        # Global Admin and Super Admin: Full access
        if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
            return queryset
            
        # Anonymous users: No access
        if not user.is_authenticated:
            return queryset.none()
            
        # Get effective branch (considers session switching for admin users)
        effective_branch = BranchFilterManager.get_effective_branch(user, request)
        
        # Users without effective branch assignment: No access
        if not effective_branch:
            return queryset.none()
            
        # Get model name to determine filtering strategy
        model_name = queryset.model.__name__
        
        # Apply branch filtering based on model type
        if hasattr(queryset.model, 'branch'):
            # Direct branch relationship
            return queryset.filter(branch=effective_branch)
            
        elif model_name == 'CustomUser':
            # User filtering - same branch only
            return queryset.filter(branch=effective_branch)
            
        elif model_name in ['Course', 'Topic', 'Quiz', 'Assignment']:
            # Course-related models
            if hasattr(queryset.model, 'branch'):
                return queryset.filter(branch=effective_branch)
            elif hasattr(queryset.model, 'course'):
                return queryset.filter(course__branch=effective_branch)
            elif hasattr(queryset.model, 'topic'):
                return queryset.filter(topic__coursetopic__course__branch=effective_branch)
                
        elif model_name in ['CourseEnrollment', 'TopicProgress']:
            # Enrollment and progress models
            return queryset.filter(user__branch=effective_branch)
            
        elif model_name in ['Conference', 'ConferenceAttendance']:
            # Conference models
            if hasattr(queryset.model, 'created_by'):
                return queryset.filter(created_by__branch=effective_branch)
            elif hasattr(queryset.model, 'user'):
                return queryset.filter(user__branch=effective_branch)
                
        elif model_name in ['Discussion', 'Comment']:
            # Discussion models
            if hasattr(queryset.model, 'course'):
                return queryset.filter(course__branch=effective_branch)
            elif hasattr(queryset.model, 'discussion'):
                return queryset.filter(discussion__course__branch=effective_branch)
                
        elif model_name in ['BranchGroup', 'GroupMembership']:
            # Group models
            if hasattr(queryset.model, 'branch'):
                return queryset.filter(branch=effective_branch)
            elif hasattr(queryset.model, 'group'):
                return queryset.filter(group__branch=effective_branch)
                
        elif model_name == 'Event':
            # Event models - filter by user's branch
            return queryset.filter(user__branch=effective_branch)
                
        # Default: try to filter by branch if available
        if hasattr(queryset.model, 'branch'):
            return queryset.filter(branch=effective_branch)
            
        # If no specific filtering strategy found, return empty queryset for safety
        return queryset.none()
    
    @staticmethod
    def check_object_access(user, obj, request=None):
        """
        Check if user has access to a specific object based on branch.
        Now supports session-based branch switching for admin users.
        
        Args:
            user: The requesting user
            obj: Model instance to check access for
            request: The request object (optional, for session access)
            
        Returns:
            Boolean indicating access permission
        """
        # Global Admin and Super Admin: Full access
        if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
            return True
            
        # Anonymous users: No access
        if not user.is_authenticated:
            return False
            
        # Get effective branch (considers session switching for admin users)
        effective_branch = BranchFilterManager.get_effective_branch(user, request)
        
        # Users without effective branch assignment: No access
        if not effective_branch:
            return False
            
        # Check direct branch relationship
        if hasattr(obj, 'branch'):
            return obj.branch == effective_branch
            
        # Check indirect branch relationships
        if hasattr(obj, 'user') and hasattr(obj.user, 'branch'):
            return obj.user.branch == effective_branch
            
        if hasattr(obj, 'course') and hasattr(obj.course, 'branch'):
            return obj.course.branch == effective_branch
            
        if hasattr(obj, 'created_by') and hasattr(obj.created_by, 'branch'):
            return obj.created_by.branch == effective_branch
            
        # Default: no access
        return False
    
    @staticmethod
    def get_accessible_branches(user):
        """
        Get list of branches the user has access to.
        Now includes additional branch assignments for admin users.
        
        Args:
            user: The requesting user
            
        Returns:
            QuerySet of accessible Branch objects
        """
        from branches.models import Branch, AdminBranchAssignment
        
        # Global Admin and Super Admin: All branches
        if user.is_superuser or user.role in ['globaladmin', 'superadmin']:
            return Branch.objects.all()
            
        # Super Admin with business assignments
        if user.role == 'superadmin' and hasattr(user, 'business_assignments'):
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            return Branch.objects.filter(business__in=assigned_businesses)
            
        # Admin users: Primary branch + additional assigned branches
        if user.role == 'admin':
            # Start with user's primary branch
            accessible_branches = Branch.objects.filter(id=user.branch.id) if user.branch else Branch.objects.none()
            
            # Add additional assigned branches
            additional_branches = Branch.objects.filter(
                additional_admin_assignments__user=user,
                additional_admin_assignments__is_active=True
            )
            
            # Combine and return unique branches
            return (accessible_branches | additional_branches).distinct()
            
        # Other users: Only their assigned branch
        if user.branch:
            return Branch.objects.filter(id=user.branch.id)
            
        return Branch.objects.none()


def require_branch_access(view_func):
    """
    Decorator to ensure views automatically apply branch filtering.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
            
        # Users without branch (except global/super admin) cannot access branch-specific content
        if (not request.user.branch and 
            request.user.role not in ['globaladmin', 'superadmin'] and 
            not request.user.is_superuser):
            raise PermissionDenied("Branch assignment required")
            
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def filter_context_by_branch(context, user, request=None):
    """
    Filter context data by branch for consistent template rendering.
    Now supports session-based branch switching for admin users.
    
    Args:
        context: Template context dictionary
        user: The requesting user
        request: The request object (optional, for session access)
        
    Returns:
        Updated context with branch-filtered data
    """
    branch_manager = BranchFilterManager()
    
    # Filter common context items
    if 'courses' in context and hasattr(context['courses'], 'model'):
        context['courses'] = branch_manager.filter_queryset_by_branch(user, context['courses'], request)
        
    if 'users' in context and hasattr(context['users'], 'model'):
        context['users'] = branch_manager.filter_queryset_by_branch(user, context['users'], request)
        
    if 'branches' in context:
        context['branches'] = branch_manager.get_accessible_branches(user)
        
    # Add user's accessible branches to context
    accessible_branches = branch_manager.get_accessible_branches(user)
    effective_branch = branch_manager.get_effective_branch(user, request)
    
    context['user_accessible_branches'] = accessible_branches
    context['user_branch_access'] = {
        'can_see_all_branches': user.is_superuser or user.role in ['globaladmin', 'superadmin'],
        'assigned_branch': user.branch,
        'effective_branch': effective_branch,
        'accessible_branch_ids': list(accessible_branches.values_list('id', flat=True)),
        'has_multiple_branches': user.role == 'admin' and accessible_branches.count() > 1,
        'can_switch_branches': user.role == 'admin' and accessible_branches.count() > 1
    }
    
    return context


class BranchFilterMixin:
    """
    Mixin for class-based views to automatically apply branch filtering.
    Now supports session-based branch switching for admin users.
    """
    
    def get_queryset(self):
        """Override to apply branch filtering automatically."""
        queryset = super().get_queryset()
        return BranchFilterManager.filter_queryset_by_branch(self.request.user, queryset, self.request)
    
    def get_context_data(self, **kwargs):
        """Override to filter context data by branch."""
        context = super().get_context_data(**kwargs)
        return filter_context_by_branch(context, self.request.user, self.request)


# Utility functions for common filtering patterns
def get_user_courses(user):
    """Get courses accessible to the user based on their branch."""
    from courses.models import Course
    return BranchFilterManager.filter_queryset_by_branch(user, Course.objects.all())


def get_user_students(user):
    """Get students accessible to the user based on their branch."""
    from users.models import CustomUser
    students = CustomUser.objects.filter(role='learner')
    return BranchFilterManager.filter_queryset_by_branch(user, students)


def get_user_instructors(user):
    """Get instructors accessible to the user based on their branch."""
    from users.models import CustomUser
    instructors = CustomUser.objects.filter(role='instructor')
    return BranchFilterManager.filter_queryset_by_branch(user, instructors)


def can_user_access_object(user, obj, request=None):
    """Check if user can access a specific object based on branch."""
    return BranchFilterManager.check_object_access(user, obj, request) 


# Session management utilities for admin branch switching
def set_admin_active_branch(request, branch_id):
    """
    Set the active branch for an admin user in session.
    
    Args:
        request: The request object
        branch_id: ID of the branch to set as active
        
    Returns:
        Boolean indicating success
    """
    user = request.user
    if user.role != 'admin':
        return False
        
    from branches.models import Branch, AdminBranchAssignment
    try:
        # Verify the branch exists and user has access to it
        branch = Branch.objects.get(id=branch_id, is_active=True)
        
        # Check if user has access (primary branch or additional assignment)
        has_access = (
            branch == user.branch or
            AdminBranchAssignment.objects.filter(
                user=user, 
                branch=branch, 
                is_active=True
            ).exists()
        )
        
        if has_access:
            request.session['admin_active_branch_id'] = branch_id
            return True
    except Branch.DoesNotExist:
        pass
        
    return False


def get_admin_active_branch(request):
    """
    Get the current active branch for an admin user.
    
    Args:
        request: The request object
        
    Returns:
        Branch object or None
    """
    return BranchFilterManager.get_effective_branch(request.user, request)


def clear_admin_active_branch(request):
    """
    Clear the active branch for an admin user (revert to primary branch).
    
    Args:
        request: The request object
    """
    if 'admin_active_branch_id' in request.session:
        del request.session['admin_active_branch_id']


def get_admin_switchable_branches(user):
    """
    Get branches the admin user can switch to.
    
    Args:
        user: The admin user
        
    Returns:
        QuerySet of Branch objects
    """
    if user.role != 'admin':
        return Branch.objects.none()
        
    from branches.models import AdminBranchAssignment
    return AdminBranchAssignment.get_user_accessible_branches(user)