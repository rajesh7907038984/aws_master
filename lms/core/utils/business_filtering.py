"""
Business filtering utilities for Super Admin users.

This module provides consistent business filtering logic to ensure Super Admin users
only see data from their assigned businesses across all views and models.
"""

from django.db.models import Q


def get_superadmin_business_filter(user):
    """
    Get the business IDs that a Super Admin user has access to.
    
    Args:
        user: CustomUser instance with role 'superadmin'
        
    Returns:
        list: List of business IDs the user can access, empty list if none
    """
    if user.role != 'superadmin':
        return []
    
    if hasattr(user, 'business_assignments'):
        return list(user.business_assignments.filter(is_active=True).values_list('business', flat=True))
    
    return []


def filter_queryset_by_business(queryset, user, business_field_path='business'):
    """
    Filter a queryset to only include records within Super Admin's assigned businesses.
    
    Args:
        queryset: Django QuerySet to filter
        user: CustomUser instance
        business_field_path: String path to the business field (e.g., 'business', 'branch__business', 'user__business')
        
    Returns:
        QuerySet: Filtered queryset based on user's business access
    """
    # Global Admin sees everything
    if user.role == 'globaladmin' or user.is_superuser:
        return queryset
    
    # Super Admin sees only their assigned businesses
    if user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(user)
        if assigned_businesses:
            filter_kwargs = {f"{business_field_path}__in": assigned_businesses}
            return queryset.filter(**filter_kwargs)
        else:
            return queryset.none()
    
    # For other roles, return the queryset as-is (they have their own filtering logic)
    return queryset


def filter_branches_by_business(user):
    """
    Get branches that a Super Admin user has access to based on their business assignments.
    
    Args:
        user: CustomUser instance
        
    Returns:
        QuerySet: Branch objects the user can access
    """
    from branches.models import Branch
    
    # Global Admin sees all branches
    if user.role == 'globaladmin' or user.is_superuser:
        return Branch.objects.all()
    
    # Super Admin sees only branches within their assigned businesses
    if user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(user)
        if assigned_businesses:
            return Branch.objects.filter(business__in=assigned_businesses)
        else:
            return Branch.objects.none()
    
    # For other roles, handle according to their specific logic
    if user.role == 'admin' and user.branch:
        return Branch.objects.filter(id=user.branch.id)
    elif user.role == 'instructor' and user.branch:
        return Branch.objects.filter(id=user.branch.id)
    
    return Branch.objects.none()


def filter_users_by_business(user):
    """
    Get users that a Super Admin user has access to based on their business assignments.
    
    Args:
        user: CustomUser instance
        
    Returns:
        QuerySet: CustomUser objects the user can access
    """
    from users.models import CustomUser
    
    # Global Admin sees all users except themselves
    if user.role == 'globaladmin' or user.is_superuser:
        return CustomUser.objects.all().exclude(id=user.id)
    
    # Super Admin sees users within their assigned businesses (excluding themselves and global admins)
    if user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(user)
        if assigned_businesses:
            return CustomUser.objects.filter(
                branch__business__in=assigned_businesses
            ).exclude(role='globaladmin').exclude(id=user.id)
        else:
            return CustomUser.objects.none()
    
    # For other roles, handle according to their specific logic
    if user.role == 'admin' and user.branch:
        return CustomUser.objects.filter(
            branch=user.branch
        ).exclude(role__in=['superadmin', 'globaladmin']).exclude(id=user.id)
    elif user.role == 'instructor' and user.branch:
        return CustomUser.objects.filter(
            branch=user.branch, role='learner'
        ).exclude(id=user.id)
    
    return CustomUser.objects.none()


def filter_courses_by_business(user):
    """
    Get courses that a Super Admin user has access to based on their business assignments.
    
    Args:
        user: CustomUser instance
        
    Returns:
        QuerySet: Course objects the user can access
    """
    from courses.models import Course
    
    # Global Admin sees all courses
    if user.role == 'globaladmin' or user.is_superuser:
        return Course.objects.all()
    
    # Super Admin sees courses within their assigned businesses
    if user.role == 'superadmin':
        assigned_businesses = get_superadmin_business_filter(user)
        if assigned_businesses:
            return Course.objects.filter(branch__business__in=assigned_businesses)
        else:
            return Course.objects.none()
    
    # For other roles, handle according to their specific logic
    if user.role == 'admin' and user.branch:
        return Course.objects.filter(branch=user.branch)
    elif user.role == 'instructor':
        return Course.objects.filter(instructor=user)
    
    return Course.objects.none()


def get_business_scoped_context(user):
    """
    Get business-scoped context data for templates.
    
    Args:
        user: CustomUser instance
        
    Returns:
        dict: Context data with business-scoped objects
    """
    context = {
        'user_businesses': [],
        'accessible_branches': filter_branches_by_business(user),
        'is_business_scoped': user.role == 'superadmin',
    }
    
    if user.role == 'superadmin':
        context['user_businesses'] = get_superadmin_business_filter(user)
    
    return context 