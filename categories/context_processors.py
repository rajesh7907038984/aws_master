from .models import CourseCategory
from django.conf import settings
from django.utils import timezone

def categories_processor(request):
    """Add active categories to the global template context with role-based filtering."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        # For anonymous users, show no categories
        return {'categories': CourseCategory.objects.none()}
    
    # Get categories directly without caching for now
    categories = get_user_accessible_categories(request.user)
    
    return {'categories': categories}

def get_user_accessible_categories(user):
    """
    Get categories accessible to user based on their role.
    - Global Admin: All categories
    - Super Admin: Categories from branches under their assigned businesses
    - Regular users: Categories from their assigned branch only
    """
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin can see all categories
        return CourseCategory.objects.filter(is_active=True).order_by('name')
    
    elif user.role == 'superadmin':
        # Super Admin can see categories from branches under their assigned businesses
        if hasattr(user, 'business_assignments'):
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            return CourseCategory.objects.filter(
                is_active=True,
                branch__business__in=assigned_businesses
            ).order_by('name')
        return CourseCategory.objects.none()
    
    elif user.role in ['admin', 'instructor', 'learner']:
        # Regular users can only see categories from their assigned branch
        if user.branch:
            return CourseCategory.objects.filter(
                is_active=True,
                branch=user.branch
            ).order_by('name')
        return CourseCategory.objects.none()
    
    # Default: no categories
    return CourseCategory.objects.none() 