"""
API Views for User Management
Provides JSON endpoints for dynamic group and course selection
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from branches.models import Branch
from groups.models import BranchGroup
from courses.models import Course
import json


@login_required
@require_http_methods(["GET"])
def get_branch_groups(request, branch_id):
    """
    API endpoint to get groups and courses for a specific branch
    """
    try:
        branch = get_object_or_404(Branch, id=branch_id)
        
        # Check if user has permission to access this branch
        if not request.user.is_superuser and request.user.role not in ['globaladmin', 'superadmin', 'admin']:
            if request.user.branch != branch:
                return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Get user groups from the branch
        user_groups = BranchGroup.objects.filter(
            branch=branch,
            group_type='user',
            is_active=True
        ).order_by('name').values('id', 'name', 'description')
        
        # Get course groups from the branch
        course_groups = BranchGroup.objects.filter(
            branch=branch,
            group_type='course',
            is_active=True
        ).order_by('name').values('id', 'name', 'description')
        
        # If this is for editing a specific user, include their current group memberships
        # even if they're from different branches or inactive
        target_user_id = request.GET.get('user_id')
        if target_user_id:
            try:
                from .models import CustomUser
                target_user = CustomUser.objects.get(id=target_user_id)
                
                # Get user's current group memberships
                user_current_groups = target_user.group_memberships.filter(
                    group__group_type='user',
                    is_active=True
                ).values_list('group', flat=True)
                
                course_current_groups = target_user.group_memberships.filter(
                    group__group_type='course',
                    is_active=True
                ).values_list('group', flat=True)
                
                # Include current memberships in the results
                if user_current_groups.exists():
                    current_user_groups = BranchGroup.objects.filter(
                        id__in=user_current_groups
                    ).values('id', 'name', 'description')
                    # Union with existing groups
                    user_groups = user_groups.union(current_user_groups)
                
                if course_current_groups.exists():
                    current_course_groups = BranchGroup.objects.filter(
                        id__in=course_current_groups
                    ).values('id', 'name', 'description')
                    # Union with existing groups
                    course_groups = course_groups.union(current_course_groups)
                    
            except CustomUser.DoesNotExist:
                pass  # Continue with branch-only groups if user not found
        
        # Get courses
        courses = Course.objects.filter(
            branch=branch,
            is_active=True
        ).order_by('title').values('id', 'title', 'description')
        
        return JsonResponse({
            'user_groups': list(user_groups),
            'course_groups': list(course_groups),
            'courses': list(courses)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def get_group_courses(request, group_id):
    """
    API endpoint to get courses accessible to a specific group
    """
    try:
        group = get_object_or_404(BranchGroup, id=group_id)
        
        # Check if user has permission to access this group
        if not request.user.is_superuser and request.user.role not in ['globaladmin', 'superadmin']:
            if request.user.branch != group.branch:
                return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Get courses accessible to this group
        courses = group.accessible_courses.filter(is_active=True).order_by('title').values(
            'id', 'title', 'description'
        )
        
        return JsonResponse({
            'courses': list(courses)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def update_user_groups(request, user_id):
    """
    API endpoint to update user group memberships
    """
    try:
        from .models import CustomUser
        from groups.models import GroupMembership
        
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Check if user has permission to modify this user
        if not request.user.is_superuser and request.user.role not in ['globaladmin', 'superadmin']:
            if request.user.branch != user.branch:
                return JsonResponse({'error': 'Permission denied'}, status=403)
        
        data = json.loads(request.body)
        user_groups = data.get('user_groups', [])
        course_groups = data.get('course_groups', [])
        
        # Update user group memberships
        current_user_groups = set(user.group_memberships.filter(
            group__group_type='user',
            is_active=True
        ).values_list('group', flat=True))
        
        new_user_groups = set(user_groups)
        groups_to_add = new_user_groups - current_user_groups
        groups_to_remove = current_user_groups - new_user_groups
        
        # Add user to new groups
        for group_id in groups_to_add:
            group = BranchGroup.objects.get(id=group_id)
            GroupMembership.objects.get_or_create(
                group=group,
                user=user,
                defaults={
                    'is_active': True,
                    'invited_by': request.user
                }
            )
        
        # Remove user from groups
        for group_id in groups_to_remove:
            GroupMembership.objects.filter(
                group_id=group_id,
                user=user
            ).update(is_active=False)
        
        # Update course group memberships
        current_course_groups = set(user.group_memberships.filter(
            group__group_type='course',
            is_active=True
        ).values_list('group', flat=True))
        
        new_course_groups = set(course_groups)
        course_groups_to_add = new_course_groups - current_course_groups
        course_groups_to_remove = current_course_groups - new_course_groups
        
        # Add user to new course groups
        for group_id in course_groups_to_add:
            group = BranchGroup.objects.get(id=group_id)
            GroupMembership.objects.get_or_create(
                group=group,
                user=user,
                defaults={
                    'is_active': True,
                    'invited_by': request.user
                }
            )
            
            # Auto-enroll in courses accessible to this group
            from courses.models import CourseEnrollment
            from django.utils import timezone
            
            for course in group.accessible_courses.all():
                CourseEnrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={
                        'enrolled_at': timezone.now(),
                        'enrollment_source': 'auto_group'
                    }
                )
        
        # Remove user from course groups
        for group_id in course_groups_to_remove:
            GroupMembership.objects.filter(
                group_id=group_id,
                user=user
            ).update(is_active=False)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
