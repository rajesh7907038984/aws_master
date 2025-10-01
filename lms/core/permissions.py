"""
Centralized Permission Management System
Consolidates all permission checking logic to eliminate duplication
"""

from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)


class PermissionManager:
    """
    Centralized permission management system
    Replaces all scattered permission checking functions
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
            
        user_level = PermissionManager.ROLE_HIERARCHY.get(user.role, 0)
        required_level = PermissionManager.ROLE_HIERARCHY.get(required_role, 0)
        
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
        if PermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can edit courses in their business
        if user.role == 'superadmin':
            return course.instructor.business == user.business
            
        # Admin and instructor can edit courses in their branch or their own courses
        if user.role in ['admin', 'instructor']:
            return (
                course.instructor == user or
                course.instructor.branch == user.branch
            )
            
        return False
    
    @staticmethod
    def can_delete_course(user, course):
        """Centralized course delete permission check"""
        return PermissionManager.can_edit_course(user, course)
    
    @staticmethod
    def can_create_course(user):
        """Centralized course creation permission check"""
        if not user or user.is_anonymous:
            return False
            
        return PermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_edit_topic(user, topic, course):
        """Centralized topic edit permission check"""
        return PermissionManager.can_edit_course(user, course)
    
    @staticmethod
    def can_create_quiz(user):
        """Centralized quiz creation permission check"""
        if not user or user.is_anonymous:
            return False
            
        return PermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_edit_quiz(user, quiz):
        """Centralized quiz edit permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can edit any quiz
        if PermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can edit quizzes in their business
        if user.role == 'superadmin':
            return quiz.created_by.business == user.business
            
        # Admin and instructor can edit quizzes in their branch or their own quizzes
        if user.role in ['admin', 'instructor']:
            return (
                quiz.created_by == user or
                quiz.created_by.branch == user.branch
            )
            
        return False
    
    @staticmethod
    def can_grade_submission(user):
        """Centralized grading permission check"""
        if not user or user.is_anonymous:
            return False
            
        return PermissionManager.has_role_permission(user, 'instructor')
    
    @staticmethod
    def can_access_course_content(user, course):
        """Centralized course content access permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Instructors, admins, and higher can always access
        if PermissionManager.has_role_permission(user, 'instructor'):
            return True
            
        # Learners can access if enrolled
        if user.role == 'learner':
            return course.enrollments.filter(user=user).exists()
            
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
            
        return PermissionManager.has_role_permission(user, 'admin')
    
    @staticmethod
    def can_access_branch(user, branch):
        """Centralized branch access permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can access any branch
        if PermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Users can access their own branch
        return user.branch == branch
    
    @staticmethod
    def can_manage_business(user, business):
        """Centralized business management permission check"""
        if not user or user.is_anonymous:
            return False
            
        # Superuser and global admin can manage any business
        if PermissionManager.is_superuser_or_global_admin(user):
            return True
            
        # Superadmin can manage their own business
        if user.role == 'superadmin':
            return user.business == business
            
        return False


class PermissionMixin:
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
        return self.check_permission(PermissionManager.can_edit_course, course)
    
    def check_course_create_permission(self):
        """Check course creation permission"""
        return self.check_permission(PermissionManager.can_create_course)
    
    def check_quiz_edit_permission(self, quiz):
        """Check quiz edit permission"""
        return self.check_permission(PermissionManager.can_edit_quiz, quiz)
    
    def check_quiz_create_permission(self):
        """Check quiz creation permission"""
        return self.check_permission(PermissionManager.can_create_quiz)
    
    def check_grading_permission(self):
        """Check grading permission"""
        return self.check_permission(PermissionManager.can_grade_submission)


class PermissionDecorator:
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
                    if not PermissionManager.can_edit_course(request.user, course):
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
                    if not PermissionManager.can_edit_quiz(request.user, quiz):
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
    return PermissionManager.can_edit_course(user, course)


def check_course_edit_permission(user, course):
    """Backward compatibility wrapper"""
    return PermissionManager.can_edit_course(user, course)


def check_topic_edit_permission(user, topic, course, check_for='edit'):
    """Backward compatibility wrapper"""
    return PermissionManager.can_edit_topic(user, topic, course)


def check_quiz_edit_permission(user, quiz):
    """Backward compatibility wrapper"""
    return PermissionManager.can_edit_quiz(user, quiz)


def check_course_catalog_permission(user, course):
    """Backward compatibility wrapper"""
    return PermissionManager.can_view_course_catalog(user, course)


def check_course_content_permission(user, course):
    """Backward compatibility wrapper"""
    return PermissionManager.can_access_course_content(user, course)


def has_course_delete_permission(user, course):
    """Backward compatibility wrapper"""
    return PermissionManager.can_delete_course(user, course)


def has_course_edit_permission(user, course):
    """Backward compatibility wrapper"""
    return PermissionManager.can_edit_course(user, course)
