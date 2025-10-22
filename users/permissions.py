from courses.models import Course
from django.core.exceptions import PermissionDenied
from django.db.models import Q

def check_course_edit_permission(user, course):
    """
    Check if the user has permission to edit a SCORM course.
    """
    # Explicitly deny access to learners
    if user.role == 'learner':
        return False
        
    if user.is_superuser:
        return True
    if user.role == 'admin' and course.branch == user.branch:
        return True
    if user.role == 'instructor' and course.instructor == user:
        return True
    if course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True,
        course_access__can_modify=True
    ).exists():
        return True
    return False

class BranchAccessMixin:
    def has_branch_access(self, user, obj=None):
        """
        Check if user has access to the branch-specific object
        """
        if user.is_superuser:
            return True
            
        if not user.branch:
            return False
            
        if hasattr(obj, 'branch'):
            return obj.branch == user.branch
        
        return False

    def filter_branch_queryset(self, user, queryset):
        """
        Filter queryset based on user's branch access
        """
        if user.is_superuser:
            return queryset
            
        if not user.branch:
            return queryset.none()
            
        return queryset.filter(branch=user.branch)
