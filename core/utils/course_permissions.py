"""
Course permission utilities that properly handle role-based access logic.

This module fixes the logical error where instructor roles were being treated as learners
when enrolled in courses. It provides clear separation between:
- Learner access (enrollment-based)
- Instructor access (role-based assignment)  
- Admin access (branch-based)
"""

from django.db.models import Q
from django.contrib.auth import get_user_model

CustomUser = get_user_model()


class CourseAccessManager:
    """
    Utility class to handle course access logic with proper role separation.
    Fixes the issue where instructors enrolled in courses were treated as learners.
    """
    
    @staticmethod
    def get_user_course_role(user, course):
        """
        Determine the user's role in a specific course context.
        Returns: 'primary_instructor', 'invited_instructor', 'learner', 'admin', 'viewer', 'none'
        """
        if user.is_superuser:
            return 'superuser'
            
        # Branch admin access
        if user.role == 'admin' and course.branch == user.branch:
            return 'admin'
            
        # Primary instructor (course creator/assigned instructor)
        if user.role == 'instructor' and course.instructor == user:
            return 'primary_instructor'
            
        # Invited instructor (enrolled instructor or group-assigned)
        if user.role == 'instructor':
            # Check enrollment as instructor
            if course.enrolled_users.filter(id=user.id).exists():
                return 'invited_instructor'
                
            # Check group access as instructor
            if course.accessible_groups.filter(
                memberships__user=user,
                memberships__is_active=True
            ).exists():
                return 'invited_instructor'
            
            return 'none'  # Instructor with no access to this course
            
        # Learner role - only if actually enrolled as learner
        if user.role == 'learner':
            if course.enrolled_users.filter(id=user.id).exists() and course.is_active:
                return 'learner'
            # Check group access for learners
            if course.accessible_groups.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__custom_role__can_view=True
            ).exists() and course.is_active:
                return 'learner'
            return 'none'  # Learner with no access
            
        # Other roles - check group access only
        if course.accessible_groups.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__custom_role__can_view=True
        ).exists():
            return 'viewer'
            
        return 'none'
    
    @staticmethod
    def can_user_access_course(user, course):
        """
        Check if user can access course with proper role-based logic.
        """
        role_in_course = CourseAccessManager.get_user_course_role(user, course)
        return role_in_course != 'none'
    
    @staticmethod
    def can_user_modify_course(user, course):
        """
        Check if user can modify course content with proper role-based logic.
        """
        role_in_course = CourseAccessManager.get_user_course_role(user, course)
        return role_in_course in [
            'superuser', 'admin', 'primary_instructor', 'invited_instructor'
        ]
    
    @staticmethod
    def get_course_learners(course):
        """
        Get only actual learners enrolled in the course.
        """
        return CustomUser.objects.filter(
            role='learner',
            id__in=course.enrolled_users.values_list('id', flat=True)
        )
    
    @staticmethod
    def get_course_instructors(course):
        """
        Get all instructors associated with the course.
        """
        instructors = set()
        
        # Primary instructor
        if course.instructor:
            instructors.add(course.instructor)
            
        # Enrolled instructors
        enrolled_instructors = CustomUser.objects.filter(
            role='instructor',
            id__in=course.enrolled_users.values_list('id', flat=True)
        )
        instructors.update(enrolled_instructors)
        
        # Group-assigned instructors
        group_instructors = CustomUser.objects.filter(
            role='instructor',
            group_memberships__group__in=course.accessible_groups.all(),
            group_memberships__is_active=True
        ).distinct()
        instructors.update(group_instructors)
        
        return list(instructors)
    
    @staticmethod
    def get_course_admins(course):
        """
        Get admins who can access the course.
        """
        if not course.branch:
            return CustomUser.objects.none()
            
        return CustomUser.objects.filter(
            role='admin',
            branch=course.branch
        )
    
    @staticmethod
    def categorize_course_users(course):
        """
        Categorize all users associated with a course by their actual roles.
        Returns dictionary with categorized user lists.
        """
        # Get all enrolled users
        from courses.models import CourseEnrollment
        enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
        
        categorized_users = {
            'learners': [],
            'instructors': [],
            'admins': [],
            'others': []
        }
        
        for enrollment in enrollments:
            user = enrollment.user
            role_in_course = CourseAccessManager.get_user_course_role(user, course)
            
            if role_in_course == 'learner':
                categorized_users['learners'].append({
                    'user': user,
                    'enrollment': enrollment,
                    'course_role': 'Learner',
                    'can_modify': False
                })
            elif role_in_course in ['primary_instructor', 'invited_instructor']:
                categorized_users['instructors'].append({
                    'user': user,
                    'enrollment': enrollment,
                    'course_role': 'Primary Instructor' if role_in_course == 'primary_instructor' else 'Invited Instructor',
                    'can_modify': True
                })
            elif role_in_course == 'admin':
                categorized_users['admins'].append({
                    'user': user,
                    'enrollment': enrollment,
                    'course_role': 'Branch Admin',
                    'can_modify': True
                })
            elif role_in_course == 'superuser':
                # Superusers (superadmins, globaladmins) go to admins category
                categorized_users['admins'].append({
                    'user': user,
                    'enrollment': enrollment,
                    'course_role': user.get_role_display(),
                    'can_modify': True
                })
            else:
                categorized_users['others'].append({
                    'user': user,
                    'enrollment': enrollment,
                    'course_role': user.get_role_display(),
                    'can_modify': False
                })
        
        return categorized_users


def is_course_learner(user, course):
    """
    Helper function to check if user is specifically a learner in a course.
    This fixes the logic error where instructors were treated as learners.
    """
    return (user.role == 'learner' and 
            course.enrolled_users.filter(id=user.id).exists() and
            course.is_active)


def is_course_instructor(user, course):
    """
    Helper function to check if user is an instructor for a course.
    """
    if user.role != 'instructor':
        return False
        
    # Primary instructor
    if course.instructor == user:
        return True
        
    # Invited instructor (enrolled)
    if course.enrolled_users.filter(id=user.id).exists():
        return True
        
    # Group-assigned instructor
    return course.accessible_groups.filter(
        memberships__user=user,
        memberships__is_active=True
    ).exists()


def get_user_course_permissions(user, course):
    """
    Get detailed permissions for a user in a course context.
    """
    access_manager = CourseAccessManager()
    role_in_course = access_manager.get_user_course_role(user, course)
    
    permissions = {
        'can_view': role_in_course != 'none',
        'can_modify': role_in_course in ['superuser', 'admin', 'primary_instructor', 'invited_instructor'],
        'can_enroll_users': role_in_course in ['superuser', 'admin', 'primary_instructor', 'invited_instructor'],
        'can_delete': role_in_course in ['superuser', 'admin', 'primary_instructor'],
        'role_in_course': role_in_course,
        'display_role': {
            'superuser': 'Super User',
            'admin': 'Branch Admin', 
            'primary_instructor': 'Primary Instructor',
            'invited_instructor': 'Invited Instructor',
            'learner': 'Learner',
            'viewer': 'Viewer',
            'none': 'No Access'
        }.get(role_in_course, 'Unknown')
    }
    
    return permissions
