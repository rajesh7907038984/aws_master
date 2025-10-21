from django.db.models import Q
from lms_rubrics.models import Rubric


def get_filtered_rubrics_for_user(user, course=None):
    """
    Get filtered rubrics based on user role following RBAC rules.
    
    Global Admin: Can see ALL rubrics
    Super Admin: Can see rubrics from branches under their business
    Admin/Instructor: Can see rubrics from their branch
    
    Args:
        user: The user requesting rubrics
        course: Optional course to further filter rubrics
        
    Returns:
        QuerySet of filtered rubrics
    """
    if not user:
        return Rubric.objects.none()
    
    # Base queryset
    base_queryset = Rubric.objects.all()
    
    # Apply role-based filtering
    if user.role == 'globaladmin' or user.is_superuser:
        # Global Admin: Show all rubrics
        rubrics = base_queryset
        
    elif user.role == 'superadmin':
        # Super Admin: Show rubrics from all branches under their business(es)
        if hasattr(user, 'business_assignments'):
            assigned_businesses = user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            rubrics = base_queryset.filter(
                branch__business__in=assigned_businesses
            )
        else:
            rubrics = Rubric.objects.none()
            
    elif user.role in ['admin', 'instructor']:
        # Admin/Instructor: Show only rubrics from their branch
        if user.branch:
            rubrics = base_queryset.filter(branch=user.branch)
        else:
            rubrics = Rubric.objects.none()
    else:
        # Other roles: No access to rubrics
        rubrics = Rubric.objects.none()
    
    # Further filter by course if provided
    if course and rubrics.exists():
        # Include course-specific rubrics and general rubrics (no course assigned)
        rubrics = rubrics.filter(
            Q(course=course) | Q(course__isnull=True)
        ).distinct()
    
    return rubrics.order_by('title') 