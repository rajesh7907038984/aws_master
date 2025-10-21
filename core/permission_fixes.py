"""
Permission Fixes for LMS
This module provides more permissive permission checking functions
to fix overly restrictive access controls that were causing bugs.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

def check_course_edit_permission_fixed(user, course):
    """
    More permissive course edit permission check
    Fixes overly restrictive permission checks that were blocking legitimate users
    """
    if not user or not user.is_authenticated:
        return False
    
    # Super users and global admins always have access
    if user.is_superuser or user.role == 'globaladmin':
        return True
    
    # Course instructors can always edit their courses
    if hasattr(course, 'instructor') and course.instructor == user:
        return True
    
    # Branch admins can edit courses in their branch
    if user.role == 'admin' and hasattr(course, 'branch') and course.branch == user.branch:
        return True
    
    # Super admins can edit courses they're assigned to
    if user.role == 'superadmin':
        # Check if user is assigned to the course's business
        if hasattr(course, 'business') and course.business:
            from business.models import BusinessUserAssignment
            if BusinessUserAssignment.objects.filter(
                user=user, 
                business=course.business, 
                is_active=True
            ).exists():
                return True
    
    # Regular instructors can edit if they have management access
    if user.role == 'instructor':
        # Check if user has been granted management access to this course
        from courses.models import CourseEnrollment
        enrollment = CourseEnrollment.objects.filter(
            user=user, 
            course=course, 
            enrollment_source='instructor_management'
        ).first()
        if enrollment:
            return True
    
    return False

def check_course_permission_fixed(user, course):
    """
    More permissive course access permission check
    """
    if not user or not user.is_authenticated:
        return False
    
    # Super users and global admins always have access
    if user.is_superuser or user.role == 'globaladmin':
        return True
    
    # Course instructors always have access
    if hasattr(course, 'instructor') and course.instructor == user:
        return True
    
    # Branch admins can access courses in their branch
    if user.role == 'admin' and hasattr(course, 'branch') and course.branch == user.branch:
        return True
    
    # Super admins can access courses in their assigned businesses
    if user.role == 'superadmin':
        if hasattr(course, 'business') and course.business:
            from business.models import BusinessUserAssignment
            if BusinessUserAssignment.objects.filter(
                user=user, 
                business=course.business, 
                is_active=True
            ).exists():
                return True
    
    # Check if user is enrolled in the course
    from courses.models import CourseEnrollment
    if CourseEnrollment.objects.filter(user=user, course=course).exists():
        return True
    
    return False

def check_topic_edit_permission_fixed(user, topic, course=None):
    """
    More permissive topic edit permission check
    """
    if not user or not user.is_authenticated:
        return False
    
    # Super users and global admins always have access
    if user.is_superuser or user.role == 'globaladmin':
        return True
    
    # Get course from topic if not provided
    if not course and hasattr(topic, 'course'):
        course = topic.course
    elif not course and hasattr(topic, 'courses'):
        course = topic.courses.first()
    
    if course:
        # Use the course permission check
        return check_course_edit_permission_fixed(user, course)
    
    return False

def permission_denied_response(request, message="Permission denied"):
    """
    Standardized permission denied response
    """
    if request.headers.get('Content-Type') == 'application/json' or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': message}, status=403)
    else:
        messages.error(request, message)
        return redirect('users:role_based_redirect')

def safe_permission_check(permission_func, *args, **kwargs):
    """
    Safely execute permission check with error handling
    """
    try:
        return permission_func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Permission check error: {str(e)}")
        # Default to more permissive on error
        return True
