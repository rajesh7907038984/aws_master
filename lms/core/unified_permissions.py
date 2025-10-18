"""
Unified Permission System for LMS
Consolidates all permission checking logic into a single, consistent system
"""

from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class UnifiedPermissionManager:
    """
    Centralized permission management system that replaces all scattered permission checking
    """
    
    # Role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {
        'learner': 1,
        'instructor': 2,
        'admin': 3,
        'superadmin': 4,
        'globaladmin': 5,
    }
    
    @staticmethod
    def has_role_permission(user, required_role):
        """Check if user has required role or higher"""
        if not user or user.is_anonymous:
            return False
            
        user_level = UnifiedPermissionManager.ROLE_HIERARCHY.get(user.role, 0)
        required_level = UnifiedPermissionManager.ROLE_HIERARCHY.get(required_role, 0)
        
        return user_level >= required_level
    
    @staticmethod
    def is_superuser_or_global_admin(user):
        """Check if user is superuser or global admin"""
        return user.is_superuser or getattr(user, 'role', None) == 'globaladmin'
    
    @staticmethod
    def can_edit_course(user, course):
        """Centralized course edit permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can edit any course
        if UnifiedPermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can edit courses in their business
        if user.role == 'superadmin':
            if hasattr(course, 'instructor') and hasattr(course.instructor, 'business'):
                return course.instructor.business == user.business
            return True
            
        # Admin and instructor can edit courses in their branch or their own courses
        if user.role in ['admin', 'instructor']:
            return (
                (hasattr(course, 'instructor') and course.instructor == user) or
                (hasattr(course, 'instructor') and hasattr(course.instructor, 'branch') and 
                 course.instructor.branch == user.branch)
            )
            
        return False
    
    @staticmethod
    def can_delete_course(user, course):
        """Centralized course delete permission check"""
        return UnifiedPermissionManager.can_edit_course(user, course)
    
    @staticmethod
    def can_create_course(user):
        """Centralized course creation permission check"""
        if not user or user.is_anonymous:
            return False
            
        return UnifiedPermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_edit_topic(user, topic, course):
        """Centralized topic edit permission check"""
        return UnifiedPermissionManager.can_edit_course(user, course)
    
    @staticmethod
    def can_create_quiz(user):
        """Centralized quiz creation permission check"""
        if not user or user.is_anonymous:
            return False
            
        return UnifiedPermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_edit_quiz(user, quiz):
        """Centralized quiz edit permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can edit any quiz
        if UnifiedPermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can edit quizzes in their business
        if user.role == 'superadmin':
            if hasattr(quiz, 'created_by') and hasattr(quiz.created_by, 'business'):
                return quiz.created_by.business == user.business
            return True
            
        # Admin and instructor can edit quizzes in their branch or their own quizzes
        if user.role in ['admin', 'instructor']:
            return (
                (hasattr(quiz, 'created_by') and quiz.created_by == user) or
                (hasattr(quiz, 'created_by') and hasattr(quiz.created_by, 'branch') and 
                 quiz.created_by.branch == user.branch)
            )
            
        return False
    
    @staticmethod
    def can_grade_submission(user):
        """Centralized grading permission check"""
        if not user or user.is_anonymous:
            return False
            
        return UnifiedPermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_access_course_content(user, course):
        """Centralized course content access permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Instructors, admins, and higher can always access
        if UnifiedPermissionManager.has_role_permission(user, 'instructor'):
            return True
            
        # Learners can access if enrolled
        if user.role == 'learner':
            if hasattr(course, 'courseenrollment_set'):
                return course.courseenrollment_set.filter(user=user).exists()
            return False
            
        return False
    
    @staticmethod
    def can_view_course_catalog(user, course):
        """Centralized course catalog view permission check"""
        if not user or user.is_anonymous:
            return False
            
        # All authenticated users can view catalog
        return True
    
    @staticmethod
    def can_manage_users(user):
        """Centralized user management permission check"""
        if not user or user.is_anonymous:
            return False
            
        return UnifiedPermissionManager.has_role_permission(user, 'admin')
    
    @staticmethod
    def can_access_branch(user, branch):
        """Centralized branch access permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can access any branch
        if UnifiedPermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Users can access their own branch
        return user.branch == branch
    
    @staticmethod
    def can_manage_business(user, business):
        """Centralized business management permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can manage any business
        if UnifiedPermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can manage their own business
        if user.role == 'superadmin':
            if hasattr(user, 'business_assignments'):
                return user.business_assignments.filter(business=business, is_active=True).exists()
            return False
            
        return False
    
    @staticmethod
    def can_assign_role(user, target_role, target_user):
        """Check if user can assign a role to another user"""
        if not user or user.is_anonymous:
            return False
        
        # Must be able to manage the role
        if not UnifiedPermissionManager.can_manage_role(user, target_role):
            return False
        
        # Get user's highest role for hierarchy validation
        user_highest_role = UnifiedPermissionManager.get_user_highest_role(user)
        if not user_highest_role:
            return False
        
        # Enhanced hierarchy check: assigner must have higher role than target role
        if isinstance(target_role, str):
            target_role_level = UnifiedPermissionManager.ROLE_HIERARCHY.get(target_role, 0)
        else:
            target_role_level = target_role.hierarchy_level
            
        if user_highest_role.hierarchy_level < target_role_level:
            return False
        elif user_highest_role.hierarchy_level == target_role_level:
            # Only allow same-level assignment if both are global admin
            if not (user_highest_role.name == 'globaladmin' and target_role == 'globaladmin'):
                return False
        
        # Only globaladmin can assign globaladmin roles
        if target_role == 'globaladmin':
            return user.role == 'globaladmin'
        
        # Only superadmin or globaladmin can assign superadmin roles
        if target_role == 'superadmin':
            return user.role in ['superadmin', 'globaladmin']
        
        # Super admin users cannot assign globaladmin roles
        if target_role == 'globaladmin' and user.role == 'superadmin':
            return False
        
        # Admin users cannot assign superadmin, globaladmin, or admin roles
        if target_role in ['superadmin', 'globaladmin', 'admin'] and user.role == 'admin':
            return False
        
        # Branch-based restrictions
        if hasattr(user, 'branch') and hasattr(target_user, 'branch'):
            # Non-superadmins can only assign roles within their branch
            if user.branch_id != target_user.branch_id:
                if user.role != 'superadmin':
                    return False
        
        return True
    
    @staticmethod
    def can_manage_role(user, target_role):
        """Check if user can manage (create/edit/delete) a specific role"""
        if not user or user.is_anonymous:
            return False
        
        # Superuser can manage all roles
        if user.is_superuser:
            return True
        
        user_highest_role = UnifiedPermissionManager.get_user_highest_role(user)
        if not user_highest_role:
            return False
        
        # Can only manage roles of lower hierarchy
        if isinstance(target_role, str):
            target_role_level = UnifiedPermissionManager.ROLE_HIERARCHY.get(target_role, 0)
            target_role_name = target_role
        else:
            target_role_level = target_role.hierarchy_level
            target_role_name = target_role.name
        
        # Additional business rules for role management restrictions
        if user_highest_role.name == 'superadmin' and target_role_name == 'globaladmin':
            return False
        
        if user_highest_role.name == 'admin' and target_role_name in ['superadmin', 'globaladmin', 'admin']:
            return False
        
        return user_highest_role.hierarchy_level > target_role_level
    
    @staticmethod
    def get_user_highest_role(user):
        """Get the highest hierarchical role for a user"""
        if not user or user.is_anonymous:
            return None
        
        # Start with primary role
        highest_role = None
        highest_level = -1
        
        if hasattr(user, 'role') and user.role:
            highest_role = user.role
            highest_level = UnifiedPermissionManager.ROLE_HIERARCHY.get(user.role, 0)
        
        # Check assigned roles
        try:
            from role_management.models import UserRole
            user_roles = UserRole.objects.filter(
                user=user, 
                is_active=True,
                role__is_active=True
            ).select_related('role')
            
            for user_role in user_roles:
                if user_role.is_expired:
                    continue
                    
                if user_role.role.hierarchy_level > highest_level:
                    highest_role = user_role.role
                    highest_level = user_role.role.hierarchy_level
        except ImportError:
            pass
        
        return highest_role


class UnifiedPermissionMixin:
    """
    Mixin for views that need permission checking
    Provides consistent permission checking across all views
    """
    
    def check_permission(self, permission_func, *args, **kwargs):
        """Generic permission checking method"""
        if not permission_func(self.request.user, *args, **kwargs):
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied',
                    'error_type': 'permission_denied'
                }, status=403)
            
            messages.error(self.request, 'You do not have permission to perform this action.')
            raise PermissionDenied()
        
        return True
    
    def check_course_edit_permission(self, course):
        """Check course edit permission"""
        return self.check_permission(UnifiedPermissionManager.can_edit_course, course)
    
    def check_course_create_permission(self):
        """Check course creation permission"""
        return self.check_permission(UnifiedPermissionManager.can_create_course)
    
    def check_quiz_edit_permission(self, quiz):
        """Check quiz edit permission"""
        return self.check_permission(UnifiedPermissionManager.can_edit_quiz, quiz)
    
    def check_quiz_create_permission(self):
        """Check quiz creation permission"""
        return self.check_permission(UnifiedPermissionManager.can_create_quiz)
    
    def check_grading_permission(self):
        """Check grading permission"""
        return self.check_permission(UnifiedPermissionManager.can_grade_submission)


class UnifiedPermissionDecorator:
    """
    Decorator for function-based views that need permission checking
    """
    
    @staticmethod
    def require_permission(permission_func, *args, **kwargs):
        """Decorator factory for permission checking"""
        def decorator(view_func):
            def wrapper(request, *view_args, **view_kwargs):
                if not permission_func(request.user, *args, **kwargs):
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': 'Permission denied',
                            'error_type': 'permission_denied'
                        }, status=403)
                    
                    messages.error(request, 'You do not have permission to perform this action.')
                    raise PermissionDenied()
                
                return view_func(request, *view_args, **view_kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def require_course_edit(course_param='course_id'):
        """Decorator for course edit permission"""
        def decorator(view_func):
            def wrapper(request, *args, **kwargs):
                course_id = kwargs.get(course_param)
                if course_id:
                    from courses.models import Course
                    course = Course.objects.get(id=course_id)
                    if not UnifiedPermissionManager.can_edit_course(request.user, course):
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'error': 'Permission denied',
                                'error_type': 'permission_denied'
                            }, status=403)
                        
                        messages.error(request, 'You do not have permission to edit this course.')
                        raise PermissionDenied()
                
                return view_func(request, *args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def require_quiz_edit(quiz_param='quiz_id'):
        """Decorator for quiz edit permission"""
        def decorator(view_func):
            def wrapper(request, *args, **kwargs):
                quiz_id = kwargs.get(quiz_param)
                if quiz_id:
                    from quiz.models import Quiz
                    quiz = Quiz.objects.get(id=quiz_id)
                    if not UnifiedPermissionManager.can_edit_quiz(request.user, quiz):
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'error': 'Permission denied',
                                'error_type': 'permission_denied'
                            }, status=403)
                        
                        messages.error(request, 'You do not have permission to edit this quiz.')
                        raise PermissionDenied()
                
                return view_func(request, *args, **kwargs)
            return wrapper
        return decorator


# Backward compatibility - keep old function names for gradual migration
def check_course_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_edit_course(user, course)


def check_course_edit_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_edit_course(user, course)


def check_topic_edit_permission(user, topic, course, check_for='edit'):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_edit_topic(user, topic, course)


def check_quiz_edit_permission(user, quiz):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_edit_quiz(user, quiz)


def check_course_catalog_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_view_course_catalog(user, course)


def check_course_content_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_access_course_content(user, course)


def has_course_delete_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_delete_course(user, course)


def has_course_edit_permission(user, course):
    """Backward compatibility wrapper"""
    return UnifiedPermissionManager.can_edit_course(user, course)
