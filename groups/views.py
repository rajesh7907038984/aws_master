from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.db import transaction
from .models import BranchGroup, GroupMembership, GroupMemberRole, CourseGroupAccess, CourseGroup
from .forms import BranchGroupForm, GroupMembershipForm, CourseGroupAccessForm
from courses.models import Course, CourseEnrollment
from users.models import CustomUser
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
from role_management.models import Role
from django.core.management import call_command
import logging
from itertools import groupby
from operator import attrgetter
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

@login_required
def group_list(request):
    """List all groups and access control settings."""
    # Remove automatic group check functionality
    
    # Check if user has permission to view groups
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'instructor', 'admin', 'learner'] or
            (request.user.role == 'admin' and request.user.branch)):
        messages.error(request, "You don't have permission to view groups.")
        return redirect('dashboard_instructor')
    
    # Get user groups and course groups by their type
    user_groups = BranchGroup.objects.filter(group_type='user').distinct()
    course_groups = BranchGroup.objects.filter(group_type='course').distinct()
    
    # If the user is a learner, only show course groups they are already added to
    if request.user.role == 'learner':
        user_memberships = GroupMembership.objects.filter(user=request.user, is_active=True)
        user_group_ids = user_memberships.values_list('group_id', flat=True)
        course_groups = course_groups.filter(id__in=user_group_ids)
    # For Super Admin, filter by business
    elif request.user.role == 'superadmin':
        # Get branches from the user's assigned businesses
        from core.utils.business_filtering import filter_branches_by_business
        allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
        user_groups = user_groups.filter(branch__in=allowed_branches)
        course_groups = course_groups.filter(branch__in=allowed_branches)
    # Filter groups based on user's branch if not superuser
    elif not request.user.is_superuser and request.user.branch:
        user_groups = user_groups.filter(branch=request.user.branch)
        course_groups = course_groups.filter(branch=request.user.branch)
    
    # Get all access control roles organized by group type
    access_control_roles_qs = GroupMemberRole.objects.select_related('group').order_by('group__name', 'name')
    
    # Filter access control roles based on user role
    if request.user.role == 'superadmin':
        # Filter roles by groups in branches within user's businesses
        from core.utils.business_filtering import filter_branches_by_business
        allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
        access_control_roles_qs = access_control_roles_qs.filter(
            group__branch__in=allowed_branches
        )
    elif not request.user.is_superuser and request.user.branch:
        # Filter by user's branch
        access_control_roles_qs = access_control_roles_qs.filter(group__branch=request.user.branch)
    
    # Group roles by group
    grouped_access_control = []
    # Group by group ID, handling None group (Global Roles) separately if needed
    for group, roles_iterator in groupby(access_control_roles_qs, key=attrgetter('group')):
        roles = list(roles_iterator)
        if not roles:
            continue

        # Combine role names
        # Sort roles by a predefined order or name if necessary for consistent naming
        role_names = sorted([role.name for role in roles])
        if len(roles) == 1:
            combined_role_name = roles[0].name # Use the existing name if only one role
        else:
            # Combine multiple role names, potentially removing 'Role' from each first
            # Example: ['Admin Role', 'Instructor Role'] -> 'Admin + Instructor Role'
            base_names = [name.replace(' Role', '').strip() for name in role_names]
            combined_role_name = ' + '.join(base_names) + ' Role' 
            
        if not combined_role_name.strip(): # Handle cases where role name might be empty
             combined_role_name = roles[0].name if roles else "Unknown Role"


        # Aggregate permissions (True if any role in the group has the permission)
        permissions = {
            'can_view': any(role.can_view for role in roles),
            'can_edit': any(role.can_edit for role in roles),
            'can_manage_members': any(role.can_manage_members for role in roles),
            'can_manage_content': any(role.can_manage_content for role in roles),
        }
        
        # Use the first role's ID for potential actions (or decide on a different strategy)
        # Note: Actions might need rethinking for grouped roles.
        first_role_id = roles[0].id

        grouped_access_control.append({
            'group_name': group.name if group else "Global Roles",
            'group_id': group.id if group else None,
            'combined_role_name': combined_role_name,
            'permissions': permissions,
            'first_role_id': first_role_id, # Pass first role ID for potential actions
            # Optionally pass all role IDs if needed: 'role_ids': [role.id for role in roles]
        })
        
    # Check if user can create groups - RBAC v0.1 Compliant
    can_create = (request.user.is_superuser or request.user.is_staff or 
                 request.user.role in ['globaladmin', 'superadmin', 'admin'] or
                 (request.user.role == 'instructor' and request.user.branch))
    
    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Groups & Access Control', 'icon': 'fa-users'}
    ]
    
    # Default tab for learners should be course-groups
    default_tab = 'course-groups' if request.user.role == 'learner' else 'user-groups'
    
    context = {
        'user_groups': user_groups,
        'course_groups': course_groups,
        'grouped_access_control': grouped_access_control,
        'can_create': can_create,
        'breadcrumbs': breadcrumbs,
        'default_tab': default_tab
    }
    return render(request, 'groups/group_list.html', context)

@login_required
def group_detail(request, group_id):
    """Display group details."""
    group = get_object_or_404(BranchGroup, id=group_id)
    
    # Check permissions
    if not (request.user.is_superuser or 
            (request.user.role == 'admin' and request.user.branch == group.branch) or
            group.memberships.filter(user=request.user, is_active=True).exists()):
        return HttpResponseForbidden("You don't have permission to view this group.")
    
    # Check if user can manage the group
    can_manage = request.user.is_superuser or \
                 (request.user.role == 'admin' and request.user.branch == group.branch) or \
                 group.memberships.filter(
                     user=request.user,
                     custom_role__can_manage_members=True,
                     is_active=True
                 ).exists()

    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
        {'label': group.name, 'icon': 'fa-user-group'}
    ]

    context = {
        'group': group,
        'members': group.memberships.filter(is_active=True).select_related('user', 'custom_role'),
        'can_manage': can_manage,
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'groups/group_detail.html', context)

@login_required
def group_create(request):
    """Create a new group."""
    # Check if user has permission to create groups - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to create groups.")
        return redirect('groups:group_list')

    # Fix: Explicitly get the type parameter correctly from the query string
    group_type = request.GET.get('type', 'user')
    # Fix: Ensure tab is explicitly set based on group_type
    tab = request.GET.get('tab', 'user-groups' if group_type == 'user' else 'course-groups')
    template = 'groups/course_group_form.html' if group_type == 'course' else 'groups/group_form.html'
    
    # Get available courses for course groups
    available_courses = None
    if group_type == 'course':
        if request.user.is_superuser:
            available_courses = Course.objects.filter(is_active=True).order_by('title')
        elif request.user.role == 'superadmin':
            # Super admins see courses from branches within their businesses
            from core.utils.business_filtering import filter_branches_by_business
            allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
            available_courses = Course.objects.filter(
                is_active=True,
                branch__in=allowed_branches
            ).order_by('title')
        elif request.user.role == 'admin':
            # Updated query to include all courses in the branch, regardless of creator
            available_courses = Course.objects.filter(
                is_active=True,
                branch=request.user.branch
            ).order_by('title')
        elif request.user.role == 'instructor':
            # Instructors can only create groups for their own courses
            available_courses = Course.objects.filter(
                Q(instructor=request.user) |
                Q(accessible_groups__memberships__user=request.user,
                  accessible_groups__memberships__is_active=True,
                  accessible_groups__memberships__custom_role__can_manage_content=True)
            ).distinct().order_by('title')
        else:
            available_courses = Course.objects.none()
    
    if request.method == 'POST':
        # Fix: Create a copy of the POST data to add/modify parameters as needed
        post_data = request.POST.copy()
        # Explicitly set the group_type in the form data
        post_data['group_type'] = group_type
        form = BranchGroupForm(post_data, user=request.user)
        # Fix: Get tab from POST data or default to the previously determined tab
        tab = post_data.get('tab', tab)
        
        # Ensure branch is set if form is disabled
        if not form.is_valid() and 'branch' in form.errors and request.user.branch:
            # Set branch directly
            post_data['branch'] = request.user.branch.id
            form = BranchGroupForm(post_data, user=request.user)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save the form with the correct group_type
                    group = form.save()
                    
                    # Handle user memberships for user type groups
                    if group_type == 'user':
                        selected_users = request.POST.getlist('users[]')
                        if selected_users:
                            for user_id in selected_users:
                                GroupMembership.objects.create(
                                    group=group,
                                    user_id=user_id,
                                    is_active=True,
                                    invited_by=request.user
                                )
                    
                    # Handle course access for course type groups
                    elif group_type == 'course':
                        selected_courses = request.POST.getlist('courses[]')
                        if selected_courses:
                            # Remove all existing course access and add selected ones
                            CourseGroupAccess.objects.filter(group=group).delete()
                            
                            # Add new courses
                            for course_id in selected_courses:
                                # Create CourseGroupAccess
                                CourseGroupAccess.objects.create(
                                    group=group,
                                    course_id=course_id,
                                    assigned_by=request.user
                                )
                                
                                # Also create CourseGroup entries
                                CourseGroup.objects.get_or_create(
                                    group=group,
                                    course_id=course_id,
                                    defaults={'created_by': request.user}
                                )
                
                messages.success(request, f"Group '{group.name}' has been created successfully.")
                return redirect(f"{reverse('groups:group_list')}?tab={tab}")
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        form.add_error(field if field != '__all__' else None, error)
    else:
        form = BranchGroupForm(user=request.user)

    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
        {'label': f'Create {"Course " if group_type == "course" else ""}Group', 'icon': 'fa-plus'}
    ]

    context = {
        'form': form,
        'breadcrumbs': breadcrumbs,
        'title': f'Create {"Course " if group_type == "course" else ""}Group',
        'group_type': group_type,
        'available_courses': available_courses,
        'tab': tab
    }

    # Add available users for user type groups
    if group_type == 'user':
        if request.user.role == 'instructor':
            # Modified: For instructors, show all users from the same branch (both instructors and learners)
            # except for superadmin and admin role users
            context['available_users'] = CustomUser.objects.filter(
                is_active=True,
                branch=request.user.branch
            ).exclude(
                role__in=['superadmin', 'admin']
            ).order_by('first_name', 'last_name')
        elif request.user.role == 'superadmin':
            # For super admins, show users from branches within their businesses
            from core.utils.business_filtering import filter_branches_by_business
            allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
            context['available_users'] = CustomUser.objects.filter(
                is_active=True,
                branch__in=allowed_branches
            ).exclude(
                role__in=['globaladmin', 'superadmin']  # Exclude global/super admins
            ).order_by('first_name', 'last_name')
        else:
            # For admins and superusers, show all users from the branch
            user_query = CustomUser.objects.filter(
                is_active=True,
                branch=request.user.branch
            )
            
            # Hide superadmin users for admin users
            if request.user.role == 'admin' and not request.user.is_superuser:
                user_query = user_query.exclude(role='superadmin')
                
            context['available_users'] = user_query.order_by('first_name', 'last_name')
    
    return render(request, template, context)

@login_required
def group_edit(request, group_id):
    """Edit a group."""
    # Check if user has permission to edit groups - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to edit groups.")
        return redirect('groups:group_list')
    
    group = get_object_or_404(BranchGroup, id=group_id)
    
    # Check if user has permission to edit this specific group
    if request.user.role == 'superadmin':
        # Super admin can only edit groups in branches within their businesses
        from core.utils.business_filtering import filter_branches_by_business
        allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
        if group.branch_id not in allowed_branches:
            messages.error(request, "You don't have permission to edit this group.")
            return redirect('groups:group_list')
    elif not request.user.is_superuser and request.user.branch and group.branch != request.user.branch:
        messages.error(request, "You don't have permission to edit this group.")
        return redirect('groups:group_list')
    
    group_type = request.GET.get('type', 'course' if group.course_access.exists() else 'user')
    tab = 'course-groups' if group_type == 'course' else 'user-groups'

    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
        {'label': f'Edit {group.name}', 'icon': 'fa-edit'}
    ]

    if request.method == 'POST':
        # Get form data
        name = request.POST.get('name')
        description = request.POST.get('description')
        is_active = request.POST.get('is_active') == 'on'
        
        # Update basic group info
        group.name = name
        group.description = description
        group.is_active = is_active
        group.save()

        if group_type == 'user':
            # Handle user memberships
            selected_users = request.POST.getlist('users[]')
            current_members = set(group.memberships.values_list('user_id', flat=True))
            selected_users = set(map(int, selected_users))

            # Add new members
            for user_id in selected_users - current_members:
                GroupMembership.objects.create(
                    group=group,
                    user_id=user_id,
                    is_active=True,
                    invited_by=request.user
                )

            # Remove unselected members
            GroupMembership.objects.filter(
                group=group,
                user_id__in=current_members - selected_users
            ).delete()

        elif group_type == 'course':
            # Handle course access
            selected_courses = request.POST.getlist('courses[]')
            
            # Remove all existing course access and add selected ones
            CourseGroupAccess.objects.filter(group=group).delete()
            
            # Add new courses
            for course_id in selected_courses:
                CourseGroupAccess.objects.create(
                    group=group,
                    course_id=course_id,
                    assigned_by=request.user
                )

        messages.success(request, f'Group "{group.name}" has been updated successfully.')
        
        # Redirect to group list with tab if specified, otherwise to group detail
        return redirect(f"{reverse('groups:group_list')}?tab={tab}")

    # Prepare context based on group type
    context = {
        'group': group,
        'group_type': group_type,
        'breadcrumbs': breadcrumbs
    }

    if group_type == 'user':
        # Get all active users from the same branch, excluding existing members
        if request.user.role == 'instructor':
            # For instructors, show users from the same branch, excluding admins and superadmins
            context['available_users'] = CustomUser.objects.filter(
                is_active=True,
                branch=request.user.branch
            ).exclude(
                role__in=['superadmin', 'admin']
            ).exclude(
                id__in=group.memberships.filter(is_active=True).values_list('user_id', flat=True)
            ).order_by('first_name', 'last_name')
        elif request.user.role == 'superadmin':
            # For super admins, show users from branches within their businesses
            from core.utils.business_filtering import filter_branches_by_business
            allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
            context['available_users'] = CustomUser.objects.filter(
                is_active=True,
                branch__in=allowed_branches
            ).exclude(
                role__in=['globaladmin', 'superadmin']  # Exclude global/super admins
            ).exclude(
                id__in=group.memberships.filter(is_active=True).values_list('user_id', flat=True)
            ).order_by('first_name', 'last_name')
        else:
            # For admins and superusers, show all users from the branch
            context['available_users'] = CustomUser.objects.filter(
                is_active=True,
                branch=request.user.branch
            ).exclude(
                id__in=group.memberships.filter(is_active=True).values_list('user_id', flat=True)
            ).order_by('first_name', 'last_name')
        
        # Get current members
        context['current_members'] = group.memberships.select_related('user').filter(is_active=True)

    elif group_type == 'course':
        # Get all active courses
        if request.user.is_superuser:
            context['available_courses'] = Course.objects.filter(
                is_active=True
            ).order_by('title')
        elif request.user.role == 'superadmin':
            # Super admins see courses from branches within their businesses
            from core.utils.business_filtering import filter_branches_by_business
            allowed_branches = filter_branches_by_business(request.user).values_list('id', flat=True)
            context['available_courses'] = Course.objects.filter(
                is_active=True,
                branch__in=allowed_branches
            ).order_by('title')
        elif request.user.role == 'admin':
            # Filter courses by admin's branch
            context['available_courses'] = Course.objects.filter(
                is_active=True,
                branch=request.user.branch
            ).order_by('title')
        elif request.user.role == 'instructor':
            context['available_courses'] = Course.objects.filter(
                Q(instructor=request.user) |
                Q(accessible_groups__memberships__user=request.user,
                  accessible_groups__memberships__is_active=True,
                  accessible_groups__memberships__custom_role__can_manage_content=True)
            ).distinct().order_by('title')
        else:
            context['available_courses'] = Course.objects.none()
            
        # Get course groups where this group is the primary course group
        # This automatically identifies the course this group was created for
        course_links = CourseGroup.objects.filter(group=group).select_related('course')
        if course_links.exists():
            context['primary_course_ids'] = [cl.course.id for cl in course_links]
            
            # If this is an auto-created course group, we should pre-select the primary course
            # This ensures when editing, the course doesn't lose its association with its own group
            if not request.POST and not request.GET.get('submitted'):
                # Check if there are any selected courses in the form
                current_course_ids = list(group.course_access.values_list('course_id', flat=True))
                
                # If no selected courses and we have primary courses, pre-select them
                if not current_course_ids and context['primary_course_ids']:
                    # Create CourseGroupAccess entries if they don't exist
                    for course_id in context['primary_course_ids']:
                        CourseGroupAccess.objects.get_or_create(
                            group=group,
                            course_id=course_id,
                            defaults={'assigned_by': request.user}
                        )
                    # Message to inform the user
                    messages.info(request, "Automatically added this group's primary course.")

    return render(request, 'groups/group_edit.html', context)

@login_required
def member_add(request, group_id):
    """Add a member to the group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    
    # Check if the group is a user group or a course group
    is_user_group = not group.course_access.exists()
    tab = 'user-groups' if is_user_group else 'course-groups'
    
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch == group.branch) or
            (hasattr(request.user, 'group_memberships') and
             request.user.group_memberships.filter(
                 group_id=group_id, 
                 role__can_manage_members=True,
                 is_active=True
             ).exists())):
        messages.error(request, "You don't have permission to add members to this group.")
        return redirect('groups:group_detail', group_id=group_id)
    
    # Get available users
    available_users = CustomUser.objects.filter(is_active=True)
    
    # If the user is not a superuser, filter users by branch
    if not request.user.is_superuser and request.user.branch:
        if request.user.role == 'instructor':
            # For instructors, show users from the same branch, excluding admins and superadmins
            available_users = available_users.filter(branch=request.user.branch).exclude(role__in=['superadmin', 'admin'])
        else:
            # For admins, show all users from the branch
            available_users = available_users.filter(branch=request.user.branch)
    
    # Exclude users already in the group
    existing_user_ids = group.memberships.values_list('user_id', flat=True)
    available_users = available_users.exclude(id__in=existing_user_ids)
    
    if request.method == 'POST':
        selected_users = request.POST.getlist('users[]')
        custom_role_id = request.POST.get('custom_role')
        
        tab = request.POST.get('tab', tab)
        
        if selected_users:
            custom_role = None
            if custom_role_id:
                custom_role = get_object_or_404(GroupMemberRole, id=custom_role_id, group=group)
            
            for user_id in selected_users:
                GroupMembership.objects.create(
                    group=group,
                    user_id=user_id,
                    custom_role=custom_role,
                    is_active=True,
                    invited_by=request.user
                )
                
                # If this is a course group with auto enrollment and the role has auto_enroll enabled
                if not is_user_group and custom_role and custom_role.auto_enroll:
                    # Auto-enroll in all courses in the group
                    for course_access in group.course_access.all():
                        from core.utils.enrollment import EnrollmentService
                        from users.models import CustomUser
                        user = CustomUser.objects.get(id=user_id)
                        EnrollmentService.create_or_get_enrollment(
                            user=user,
                            course=course_access.course,
                            source='auto_group_role'
                        )
            
            if len(selected_users) == 1:
                user = CustomUser.objects.get(id=selected_users[0])
                user_name = user.get_full_name() or user.username
                messages.success(request, f"User '{user_name}' has been added to the group.")
            else:
                messages.success(request, f"{len(selected_users)} users have been added to the group.")
            
            # Redirect back to the appropriate tab
            if tab:
                return redirect(f"{reverse('groups:group_list')}?tab={tab}")
            else:
                return redirect('groups:group_detail', group_id=group.id)
        else:
            messages.error(request, "Please select at least one user to add to the group.")
    else:
        # Prepare breadcrumbs
        breadcrumbs = [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
            {'url': reverse('groups:group_detail', args=[group_id]), 'label': group.name, 'icon': 'fa-user-group'},
            {'label': 'Add Member', 'icon': 'fa-user-plus'}
        ]
        
        # Get available roles for this group
        available_roles = GroupMemberRole.objects.filter(group=group)
        
        return render(request, 'groups/member_form.html', {
            'group': group,
            'breadcrumbs': breadcrumbs,
            'available_users': available_users,
            'available_roles': available_roles,
            'is_user_group': is_user_group,
            'tab': tab
        })

@login_required
def member_edit(request, group_id, membership_id):
    """Edit a member's role in the group"""
    membership = get_object_or_404(
        GroupMembership, 
        id=membership_id, 
        group_id=group_id
    )
    
    # Check permissions
    if not (request.user.is_superuser or 
            (request.user.role == 'admin' and request.user.branch == membership.group.branch) or
            membership.group.memberships.filter(
                user=request.user,
                custom_role__can_manage_members=True,
                is_active=True
            ).exists()):
        return HttpResponseForbidden("You don't have permission to edit member roles.")

    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
        {'url': reverse('groups:group_detail', args=[membership.group.id]), 'label': membership.group.name, 'icon': 'fa-user-group'},
        {'label': 'Edit Member', 'icon': 'fa-user-edit'}
    ]

    if request.method == 'POST':
        form = GroupMembershipForm(request.POST, instance=membership, group=membership.group, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Member role updated successfully.')
            return redirect('groups:group_detail', group_id=group_id)
    else:
        form = GroupMembershipForm(instance=membership, group=membership.group, user=request.user)

    return render(request, 'groups/member_form.html', {
        'form': form,
        'group': membership.group,
        'member': membership.user,
        'title': 'Edit Member Role',
        'breadcrumbs': breadcrumbs
    })

@login_required
def course_access_manage(request, group_id):
    """Manage course access for a group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    tab = request.GET.get('tab', '')
    
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_superuser or 
            request.user.role == 'globaladmin' or
            (request.user.role == 'superadmin' and hasattr(group, 'branch') and group.branch and
             hasattr(group.branch, 'business') and 
             request.user.business_assignments.filter(business=group.branch.business, is_active=True).exists()) or
            (request.user.role == 'admin' and request.user.branch == group.branch) or
            (request.user.role == 'instructor' and group.memberships.filter(
                user=request.user,
                custom_role__can_manage_members=True,
                is_active=True
            ).exists())):
        return HttpResponseForbidden("You don't have permission to manage course access for this group.")
    
    # Get courses that match the branch, if applicable
    if request.user.is_superuser:
        available_courses = Course.objects.all()
    elif request.user.branch:
        available_courses = Course.objects.filter(branch=request.user.branch)
    else:
        available_courses = Course.objects.none()
    
    # Exclude already accessible courses
    available_courses = available_courses.exclude(
        id__in=group.accessible_courses.values_list('id', flat=True)
    )
    
    # Check if group has instructor roles
    has_instructor_role = group.custom_roles.filter(
        name__icontains='instructor'
    ).exists()
    
    if request.method == 'POST':
        form = CourseGroupAccessForm(request.POST, user=request.user)
        tab = request.POST.get('tab', '')
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    course_ids = request.POST.getlist('course_ids')
                    can_modify = request.POST.get('can_modify') == 'on' or has_instructor_role
                    
                    if course_ids:
                        courses = Course.objects.filter(id__in=course_ids)
                        
                        # Add courses to the group
                        for course in courses:
                            CourseGroupAccess.objects.create(
                                course=course,
                                group=group,
                                can_modify=can_modify,
                                assigned_by=request.user
                            )
                        
                        # If group has active members, enroll them in all courses
                        active_members = group.memberships.filter(is_active=True)
                        for membership in active_members:
                            for course in courses:
                                from core.utils.enrollment import EnrollmentService
                                EnrollmentService.create_or_get_enrollment(
                                    user=membership.user,
                                    course=course,
                                    source='auto_group_course_add'
                                )
                        
                        messages.success(request, f"{len(course_ids)} courses added to group successfully!")
                    else:
                        messages.warning(request, "No courses selected.")
                    
                # Redirect back to group detail page with tab parameter if provided
                if tab:
                    return redirect(f"{reverse('groups:group_list')}?tab={tab}")
                else:
                    return redirect('groups:group_detail', group_id=group.id)
            except Exception as e:
                messages.error(request, f"Error adding courses: {str(e)}")
    else:
        form = CourseGroupAccessForm(user=request.user)

    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups', 'icon': 'fa-users'},
        {'url': reverse('groups:group_detail', args=[group.id]), 'label': group.name, 'icon': 'fa-group'},
        {'label': 'Manage Course Access', 'icon': 'fa-book'}
    ]

    context = {
        'form': form,
        'group': group,
        'available_courses': available_courses,
        'has_instructor_role': has_instructor_role,
        'breadcrumbs': breadcrumbs,
        'tab': tab
    }
    
    return render(request, 'groups/course_access_form.html', context)

@login_required
def remove_course_access(request, group_id, course_id):
    """Remove a course access from a group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role == 'globaladmin' or
            (request.user.role == 'superadmin' and hasattr(group, 'branch') and group.branch and
             hasattr(group.branch, 'business') and 
             request.user.business_assignments.filter(business=group.branch.business, is_active=True).exists()) or
            (request.user.role == 'admin' and request.user.branch == group.branch) or
            (request.user.role == 'instructor' and group.memberships.filter(
                user=request.user,
                custom_role__can_manage_members=True,
                is_active=True
            ).exists())):
        messages.error(request, "You don't have permission to remove course access.")
        return redirect('groups:group_detail', group_id=group.id)
    
    # Check if the course is actually accessible by this group
    if not CourseGroupAccess.objects.filter(group=group, course=course).exists():
        messages.error(request, "This course is not associated with this group.")
        return redirect('groups:group_detail', group_id=group.id)
    
    if request.method == 'POST':
        # Delete the course access
        CourseGroupAccess.objects.filter(group=group, course=course).delete()
        messages.success(request, f"Course access removed successfully.")
        return redirect(f"{reverse('groups:group_list')}?tab=course-groups")
    
    return redirect('groups:group_detail', group_id=group.id)

@login_required
def role_create(request):
    """Create a new access control role."""
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to create access control roles.")
        return redirect('groups:group_list')
    
    tab = request.GET.get('tab', 'access')
    
    # Get available groups for selection
    course_groups = BranchGroup.objects.filter(group_type='course').distinct()
    user_groups = BranchGroup.objects.filter(group_type='user').distinct()
    
    if not request.user.is_superuser and request.user.branch:
        course_groups = course_groups.filter(branch=request.user.branch)
        user_groups = user_groups.filter(branch=request.user.branch)
    
    # Get existing roles from the database
    roles = Role.objects.all().order_by('name')
    
    # Define available user roles based on user's permissions and existing roles
    available_roles = []
    for role in roles:
        if role.name == 'custom':
            # Only add custom roles for superadmin users
            if request.user.is_superuser and role.custom_name:
                available_roles.append({
                    'value': f"custom_{role.id}",
                    'name': role.custom_name
                })
            continue
        
        # Hide globaladmin role option
        if role.name == 'globaladmin':
            continue
        
        # Only show admin/superadmin roles to superusers
        if role.name in ['superadmin', 'admin'] and not request.user.is_superuser:
            continue
            
        # Only show instructor role to admins and superadmins
        if role.name == 'instructor' and not (request.user.is_superuser or request.user.role == 'admin'):
            continue
            
        available_roles.append({
            'value': role.name,
            'name': role.name
        })
    
    # We no longer need to add a general "Custom Role" option since we added each custom role individually
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get list of user_roles instead of a single value
                user_roles = request.POST.getlist('user_role[]')
                course_group_id = request.POST.get('course_group')
                # Get users_group_id as a single value
                users_group_id = request.POST.get('users_group')
                auto_enroll = request.POST.get('auto_enroll') == 'on'
                
                # Determine basic permissions
                can_view = True
                
                # Create role linked to the course group
                course_group = None
                if course_group_id:
                    course_group = BranchGroup.objects.get(id=course_group_id)
                
                # Role name will include all selected roles
                role_names = []
                
                # Determine highest permissions from all selected roles
                can_edit = False
                can_manage_members = False
                can_manage_content = False
                
                # Process each selected role
                for user_role in user_roles:
                    if user_role == 'learner':
                        role_names.append('Learner')
                    elif user_role == 'instructor':
                        role_names.append('Instructor')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'admin':
                        role_names.append('Admin')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'superadmin':
                        role_names.append('Super Admin')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role.startswith('custom_'):
                        # Custom role selected - extract the role ID
                        custom_role_id = user_role.replace('custom_', '')
                        try:
                            custom_role = Role.objects.get(id=custom_role_id, name='custom')
                            role_names.append(custom_role.custom_name)
                        except Role.DoesNotExist:
                            role_names.append('Custom Role')
                        
                        # For custom roles, still get permissions from form
                        if 'can_edit' in request.POST:
                            can_edit = True
                        if 'can_manage_members' in request.POST:
                            can_manage_members = True
                        if 'can_manage_content' in request.POST:
                            can_manage_content = True
                
                # Create a combined role name
                if not role_names:
                    role_name = f"Custom Role - {timezone.now().strftime('%Y%m%d%H%M%S')}"
                else:
                    role_name = f"{' + '.join(role_names)} Role"
                
                # Create the role
                role = GroupMemberRole.objects.create(
                    name=role_name,
                    description=f"Access control role for {role_name}",
                    group=course_group,
                    can_view=can_view,
                    can_edit=can_edit,
                    can_manage_members=can_manage_members,
                    can_manage_content=can_manage_content,
                    auto_enroll=auto_enroll
                )
                
                # Get all courses from the course group
                courses = []
                if course_group:
                    courses = list(course_group.accessible_courses.all())
                
                # Assign this role to the specified user group
                if users_group_id:
                    users_group = BranchGroup.objects.get(id=users_group_id)
                    
                    # Assign role to all active users in the group
                    for membership in users_group.memberships.filter(is_active=True):
                        GroupMembership.objects.update_or_create(
                            user=membership.user,
                            group=course_group,
                            defaults={
                                'custom_role': role,
                                'is_active': True,
                                'invited_by': request.user
                            }
                        )
                        
                        # Enroll user in all courses if auto_enroll is enabled
                        if auto_enroll:
                            for course in courses:
                                CourseEnrollment.objects.get_or_create(
                                    user=membership.user,
                                    course=course,
                                    defaults={
                                        'enrolled_at': timezone.now()
                                    }
                                )
                
                messages.success(request, f"Access Control Role '{role_name}' created successfully.")
                return redirect(f"{reverse('groups:group_list')}?tab={tab}")
                
        except Exception as e:
            messages.error(request, f"Error creating access control role: {str(e)}")
    
    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups & Access Control', 'icon': 'fa-users'},
        {'label': 'Create Access Control Role', 'icon': 'fa-shield-alt'}
    ]
    
    context = {
        'course_groups': course_groups,
        'user_groups': user_groups,
        'available_roles': available_roles,
        'breadcrumbs': breadcrumbs,
        'tab': tab
    }
    
    return render(request, 'groups/access_control_create.html', context)

@login_required
def role_edit(request, role_id):
    """Edit an existing access control role."""
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to edit access control roles.")
        return redirect('groups:group_list')
    
    role = get_object_or_404(GroupMemberRole, id=role_id)
    tab = request.GET.get('tab', 'access')
    
    # Get available groups for selection - use group_type instead of course_access
    course_groups = BranchGroup.objects.filter(group_type='course').distinct()
    user_groups = BranchGroup.objects.filter(group_type='user').distinct()
    
    if not request.user.is_superuser and request.user.branch:
        course_groups = course_groups.filter(branch=request.user.branch)
        user_groups = user_groups.filter(branch=request.user.branch)
    
    # Get existing roles from the database
    roles = Role.objects.all().order_by('name')
    
    # Define available user roles based on user's permissions and existing roles
    available_roles = []
    for system_role in roles:
        if system_role.name == 'custom':
            # Only add custom roles for superadmin users
            if request.user.is_superuser and system_role.custom_name:
                available_roles.append({
                    'value': f"custom_{system_role.id}",
                    'name': system_role.custom_name
                })
            continue
        
        # Hide globaladmin role option
        if system_role.name == 'globaladmin':
            continue
        
        # Only show admin/superadmin roles to superusers
        if system_role.name in ['superadmin', 'admin'] and not request.user.is_superuser:
            continue
            
        # Only show instructor role to admins and superadmins
        if system_role.name == 'instructor' and not (request.user.is_superuser or request.user.role == 'admin'):
            continue
            
        available_roles.append({
            'value': system_role.name,
            'name': system_role.name
        })
    
    # We no longer need to add a general "Custom Role" option since we added each custom role individually
    
    # Get current role and associated groups
    current_role = role  # The role is already fetched at the beginning of the function
    current_user_groups = []
    current_user_groups_ids = []
    
    if current_role and current_role.group:
        # Get users assigned this role
        memberships = GroupMembership.objects.filter(
            group=current_role.group, 
            custom_role=current_role,
            is_active=True
        ).select_related('user')
        
        users_with_role = [membership.user for membership in memberships]
        
        # Find groups containing these users
        for user_group in user_groups:
            user_memberships = user_group.memberships.filter(is_active=True)
            group_users = [membership.user for membership in user_memberships]
            
            # Check if any users in this group have the role
            common_users = set(users_with_role).intersection(set(group_users))
            if common_users:
                current_user_groups.append(user_group)
                current_user_groups_ids.append(user_group.id)
    
    # Add default option if there's no current user group
    if not current_user_groups_ids and len(user_groups) > 0:
        # If we have user groups but none are selected, pre-select the first one
        current_user_groups.append(user_groups[0])
        current_user_groups_ids.append(user_groups[0].id)
    
    if request.method == 'POST':
        tab = request.POST.get('tab', 'access')
        try:
            with transaction.atomic():
                user_roles = request.POST.getlist('user_role[]')
                course_group_id = request.POST.get('course_group')
                # Updated to use get instead of getlist for single select
                users_group_id = request.POST.get('users_group')
                auto_enroll = request.POST.get('auto_enroll') == 'on'
                
                # Initialize permission variables
                can_view = True
                can_edit = False
                can_manage_members = False
                can_manage_content = False
                
                # Process permissions from all selected roles
                role_names = []
                for user_role in user_roles:
                    if user_role == 'learner':
                        role_names.append('Learner')
                    elif user_role == 'instructor':
                        role_names.append('Instructor')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'admin':
                        role_names.append('Admin')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'superadmin':
                        role_names.append('Super Admin')
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role.startswith('custom_'):
                        # Custom role selected - extract the role ID
                        custom_role_id = user_role.replace('custom_', '')
                        try:
                            custom_role = Role.objects.get(id=custom_role_id)
                            role_names.append(custom_role.custom_name)
                        except Role.DoesNotExist:
                            role_names.append("Custom Role")
                
                # Custom role permissions from form 
                if 'can_edit' in request.POST:
                    can_edit = True
                if 'can_manage_members' in request.POST:
                    can_manage_members = True
                if 'can_manage_content' in request.POST:
                    can_manage_content = True
                
                # Create role name based on selected roles
                if not role_names:
                    role_name = f"Custom Role - {timezone.now().strftime('%Y%m%d%H%M%S')}"
                else:
                    role_name = f"{' + '.join(role_names)} Role"
                
                # Get the course group
                course_group = BranchGroup.objects.get(id=course_group_id)
                
                # Update the role
                role.name = role_name
                role.group = course_group
                role.can_view = can_view
                role.can_edit = can_edit
                role.can_manage_members = can_manage_members
                role.can_manage_content = can_manage_content
                # Always set auto_enroll to True to ensure users are automatically enrolled
                role.auto_enroll = True if auto_enroll or auto_enroll == 'on' else False
                role.save()
                
                # Get all courses from the course group
                courses = course_group.accessible_courses.all()
                
                # Clear existing memberships for this role
                existing_memberships = GroupMembership.objects.filter(custom_role=role)
                existing_memberships.update(custom_role=None)
                
                # Process user group
                if users_group_id:
                    try:
                        users_group = BranchGroup.objects.get(id=users_group_id)
                        
                        # Assign role to all active users in the group
                        for membership in users_group.memberships.filter(is_active=True):
                            GroupMembership.objects.update_or_create(
                                user=membership.user,
                                group=course_group,
                                defaults={
                                    'custom_role': role,
                                    'is_active': True,
                                    'invited_by': request.user
                                }
                            )
                            
                            # Enroll user in all courses if auto_enroll is enabled
                            if auto_enroll:
                                for course in courses:
                                    CourseEnrollment.objects.get_or_create(
                                        user=membership.user,
                                        course=course,
                                        defaults={
                                            'enrolled_at': timezone.now()
                                        }
                                    )
                    except BranchGroup.DoesNotExist:
                        messages.warning(request, f"User group with ID {users_group_id} not found.")
                
                messages.success(request, f"Access Control Role '{role_name}' updated successfully.")
                return redirect(f"{reverse('groups:group_list')}?tab={tab}")
                
        except Exception as e:
            messages.error(request, f"Error updating access control role: {str(e)}")
    
    # Determine current role for pre-selecting in the form
    current_role_type = ''
    current_role_types = []
    if current_role:
        # Add roles based on the permissions
        if current_role.can_manage_members and current_role.can_manage_content and current_role.can_edit:
            current_role_types.append('instructor')
            current_role_types.append('admin')
            # Only add superadmin if user is superuser
            if request.user.is_superuser:
                current_role_types.append('superadmin')
        elif current_role.can_edit and (current_role.can_manage_members or current_role.can_manage_content):
            current_role_types.append('instructor')
        # Remove the automatic selection of learner based on absence of permissions
        # Don't auto-select any role if no advanced permissions are detected
            
        # Try to match with system roles for backward compatibility
        for system_role in ['superadmin', 'admin', 'instructor', 'learner']:
            if system_role in current_role.name.lower() and system_role not in current_role_types:
                current_role_types.append(system_role)
                if not current_role_type:  # Keep first match for backward compatibility
                    current_role_type = system_role
            
            # If no match with system roles, it's a custom role
            if not current_role_type:
                # Check if it matches one of our custom roles
                for role_obj in roles:
                    if role_obj.name == 'custom' and role_obj.custom_name and role_obj.custom_name in current_role.name:
                        custom_role_id = f"custom_{role_obj.id}"
                        current_role_types.append(custom_role_id)
                        current_role_type = custom_role_id
                        break
                
                # If still no match, it's a generic custom role
                if not current_role_type:
                    current_role_type = 'custom'
                    current_role_types.append('custom')
    
    # Prepare breadcrumbs
    breadcrumbs = [
        {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('groups:group_list'), 'label': 'Groups & Access Control', 'icon': 'fa-users'},
        {'label': f'Edit Access Control Role: {role.name}', 'icon': 'fa-edit'}
    ]
    
    context = {
        'role': role,
        'course_groups': course_groups,
        'user_groups': user_groups,
        'available_roles': available_roles,
        'breadcrumbs': breadcrumbs,
        'current_course_group': role.group.id if role.group else None,
        'current_role_type': current_role_type,
        'current_role_types': current_role_types,  # Add the list of roles
        'current_user_groups': current_user_groups,
        'current_user_groups_ids': current_user_groups_ids,
        'current_role': current_role,
        'tab': tab
    }
    
    return render(request, 'groups/access_control_edit.html', context)

@login_required
def role_delete(request, role_id):
    """Delete an access control role."""
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to delete access control roles.")
        return redirect('groups:group_list')
    
    role = get_object_or_404(GroupMemberRole, id=role_id)
    
    if request.method == 'POST':
        role_name = role.name
        role.delete()
        messages.success(request, f"Access Control Role '{role_name}' deleted successfully.")
        return redirect(f"{reverse('groups:group_list')}?tab=access-control")
    
    # If not POST, redirect to list view
    return redirect('groups:group_list')

@login_required
def group_delete(request, group_id):
    """Delete a group."""
    # Check if user has permission to delete groups - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to delete groups.")
        return redirect('groups:group_list')
    
    group = get_object_or_404(BranchGroup, id=group_id)
    
    # Check if user is in the same branch as the group (except for superusers)
    if not request.user.is_superuser and request.user.branch and group.branch != request.user.branch:
        messages.error(request, "You don't have permission to delete this group.")
        return redirect('groups:group_list')
    
    if request.method == 'POST':
        group_name = group.name
        is_course_group = group.course_access.exists()
        tab = 'course-groups' if is_course_group else 'user-groups'
        
        try:
            # First delete related objects to avoid constraint issues
            GroupMembership.objects.filter(group=group).delete()
            CourseGroupAccess.objects.filter(group=group).delete()
            GroupMemberRole.objects.filter(group=group).delete()
            
            # Then delete the group
            group.delete()
            messages.success(request, f"Group '{group_name}' deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting group: {str(e)}")
        
        return redirect(f"{reverse('groups:group_list')}?tab={tab}")
    
    # If not POST, redirect to list view
    return redirect('groups:group_list')

@login_required
def member_delete(request, group_id, membership_id):
    """Delete a member from a group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    membership = get_object_or_404(GroupMembership, id=membership_id, group=group)
    
    # Check if user has permission to manage members - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch == group.branch) or
            (membership.invited_by == request.user)):
        messages.error(request, "You don't have permission to remove members from this group.")
        return redirect('groups:group_detail', group_id=group_id)
    
    if request.method == 'POST':
        user_name = membership.user.get_full_name() or membership.user.username
        membership.delete()
        messages.success(request, f"User '{user_name}' has been removed from the group.")
        
    # Determine tab parameter based on group type
    tab = 'course-groups' if group.course_access.exists() else 'user-groups'
    
    # If the user came from the group list page with a tab parameter, redirect back there
    referer = request.META.get('HTTP_REFERER', '')
    if 'group_list' in referer and 'tab=' in referer:
        return redirect(referer)
    
    # Otherwise redirect to the group detail page
    return redirect('groups:group_detail', group_id=group_id)

@login_required
def access_control_edit(request, group_id):
    """Edit access control settings for a group."""
    group = get_object_or_404(BranchGroup, id=group_id)
    tab = 'access-control'
    
    # Check permissions - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch == group.branch)):
        messages.error(request, "You don't have permission to edit access control settings.")
        return redirect('groups:group_list')
    
    # Get available groups for selection
    course_groups = BranchGroup.objects.filter(group_type='course').distinct()
    user_groups = BranchGroup.objects.filter(group_type='user').distinct()
    
    if not request.user.is_superuser and request.user.branch:
        course_groups = course_groups.filter(branch=request.user.branch)
        user_groups = user_groups.filter(branch=request.user.branch)
    
    # Get existing roles from the database
    roles = Role.objects.all().order_by('name')
    
    # Define available user roles based on user's permissions and existing roles
    available_roles = []
    for system_role in roles:
        if system_role.name == 'custom':
            # Only add custom roles for superadmin users
            if request.user.is_superuser and system_role.custom_name:
                available_roles.append({
                    'value': f"custom_{system_role.id}",
                    'name': system_role.custom_name
                })
            continue
        
        # Only show admin/superadmin roles to superusers
        if system_role.name in ['superadmin', 'admin'] and not request.user.is_superuser:
            continue
            
        # Only show instructor role to admins and superadmins
        if system_role.name == 'instructor' and not (request.user.is_superuser or request.user.role == 'admin'):
            continue
            
        available_roles.append({
            'value': system_role.name,
            'name': system_role.name
        })
    
    # Get current role and settings
    current_role = GroupMemberRole.objects.filter(group=group).first()
    current_role_type = current_role.name if current_role else ''
    current_course_group = group.course_access.first().group.id if group.course_access.exists() else None
    current_user_groups_ids = list(group.memberships.filter(is_active=True).values_list('user__groups__id', flat=True).distinct())
    
    context = {
        'group': group,
        'available_roles': available_roles,
        'current_role': current_role,
        'current_role_type': current_role_type,
        'current_course_group': current_course_group,
        'current_user_groups_ids': current_user_groups_ids,
        'course_groups': course_groups,
        'user_groups': user_groups,
        'tab': tab,
        'breadcrumbs': [
            {'name': 'Groups', 'url': reverse('groups:group_list')},
            {'name': 'Access Control', 'url': '#'},
            {'name': 'Edit', 'url': '#'}
        ]
    }
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                user_roles = request.POST.getlist('user_role[]')
                course_group_id = request.POST.get('course_group')
                users_group_id = request.POST.get('users_group')
                auto_enroll = request.POST.get('auto_enroll') == 'on'
                
                # Process each selected role
                for user_role in user_roles:
                    # Determine role name and permissions based on user_role
                    can_view = True
                    can_edit = False
                    can_manage_members = False
                    can_manage_content = False
                    
                    if user_role == 'learner':
                        role_name = 'Learner Role'
                    elif user_role == 'instructor':
                        role_name = 'Instructor Role'
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'admin':
                        role_name = 'Admin Role'
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role == 'superadmin':
                        role_name = 'Super Admin Role'
                        can_edit = True
                        can_manage_members = True
                        can_manage_content = True
                    elif user_role.startswith('custom_'):
                        custom_role_id = user_role.split('_')[1]
                        try:
                            custom_role = Role.objects.get(id=custom_role_id)
                            role_name = f"Custom Role: {custom_role.custom_name}"
                            can_edit = request.POST.get('can_edit') == 'on'
                            can_manage_members = request.POST.get('can_manage_members') == 'on'
                            can_manage_content = request.POST.get('can_manage_content') == 'on'
                        except Role.DoesNotExist:
                            continue
                    else:
                        continue
                    
                    # Create or update role
                    role = GroupMemberRole.objects.create(
                        name=role_name,
                        description=f"Access control role for {role_name}",
                        group=group,
                        can_view=can_view,
                        can_edit=can_edit,
                        can_manage_members=can_manage_members,
                        can_manage_content=can_manage_content,
                        auto_enroll=auto_enroll
                    )
                    
                    # Get all courses from the course group
                    courses = list(group.accessible_courses.all())
                    
                    # Process user group
                    if users_group_id:
                        try:
                            users_group = BranchGroup.objects.get(id=users_group_id)
                            
                            # Assign role to all active users in the group
                            for membership in users_group.memberships.filter(is_active=True):
                                GroupMembership.objects.update_or_create(
                                    user=membership.user,
                                    group=group,
                                    defaults={
                                        'custom_role': role,
                                        'is_active': True,
                                        'invited_by': request.user
                                    }
                                )
                                
                                # Enroll user in all courses if auto_enroll is enabled
                                if auto_enroll:
                                    for course in courses:
                                        CourseEnrollment.objects.get_or_create(
                                            user=membership.user,
                                            course=course,
                                            defaults={
                                                'enrolled_at': timezone.now()
                                            }
                                        )
                        except BranchGroup.DoesNotExist:
                            messages.warning(request, f"User group with ID {users_group_id} not found.")
                
                messages.success(request, f"Access Control for {group.name} updated successfully.")
                return redirect(f"{reverse('groups:group_list')}?tab={tab}")
                
        except Exception as e:
            messages.error(request, f"Error updating access control: {str(e)}")
    
    return render(request, 'groups/access_control_edit.html', context)

@login_required
@require_POST
def group_bulk_delete(request):
    """Delete multiple groups at once."""
    # Check if user has permission to delete groups - RBAC v0.1 Compliant
    if not (request.user.is_staff or 
            request.user.role in ['globaladmin', 'superadmin', 'admin'] or
            (request.user.role == 'instructor' and request.user.branch)):
        messages.error(request, "You don't have permission to delete groups.")
        return redirect('groups:group_list')
    
    group_ids = request.POST.getlist('group_ids[]')
    tab = request.POST.get('tab', 'user-groups')
    
    if not group_ids:
        messages.error(request, "No groups selected for deletion.")
        return redirect(f"{reverse('groups:group_list')}?tab={tab}")
    
    try:
        with transaction.atomic():
            # Get all groups that belong to the user's branch (if they have one)
            groups = BranchGroup.objects.filter(id__in=group_ids)
            if not request.user.is_superuser and request.user.branch:
                groups = groups.filter(branch=request.user.branch)
            
            # Delete related objects first
            group_ids = list(groups.values_list('id', flat=True))
            GroupMembership.objects.filter(group_id__in=group_ids).delete()
            CourseGroupAccess.objects.filter(group_id__in=group_ids).delete()
            GroupMemberRole.objects.filter(group_id__in=group_ids).delete()
            
            # Delete the groups
            deleted_count = groups.delete()[0]
            
            messages.success(request, f"Successfully deleted {deleted_count} group(s).")
    except Exception as e:
        messages.error(request, f"Error deleting groups: {str(e)}")
    
    return redirect(f"{reverse('groups:group_list')}?tab={tab}")


# ============ Azure AD Group Import Views ============

from django.http import JsonResponse

@login_required
def azure_groups_list(request):
    """Fetch and display Azure AD groups for import mapping"""
    # Check if user is branch admin with Teams integration enabled
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({
            'success': False,
            'error': 'Only branch admins can import Azure AD groups'
        }, status=403)
    
    if not request.user.branch:
        return JsonResponse({
            'success': False,
            'error': 'User must belong to a branch to import Azure AD groups'
        }, status=403)
    
    # Check if Teams integration is enabled for this branch
    if not request.user.branch.teams_integration_enabled:
        return JsonResponse({
            'success': False,
            'error': 'Microsoft Teams integration is not enabled for your branch. Please contact your administrator.'
        }, status=403)
    
    try:
        from .azure_ad_utils import AzureADGroupAPI, AzureADAPIError
        from .models import AzureADGroupImport
        
        # Initialize Azure AD API
        api = AzureADGroupAPI(request.user.branch)
        
        # Get all groups organized by type
        categorized_groups = api.get_groups_by_type()
        
        # Get already imported groups for this branch
        imported_group_ids = AzureADGroupImport.objects.filter(
            branch=request.user.branch,
            is_active=True
        ).values_list('azure_group_id', flat=True)
        
        # Mark already imported groups
        for category in categorized_groups.values():
            for group in category:
                group['already_imported'] = group['id'] in imported_group_ids
        
        return JsonResponse({
            'success': True,
            'groups': categorized_groups,
            'branch_name': request.user.branch.name
        })
        
    except AzureADAPIError as e:
        logger.error(f"Azure AD API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Error fetching Azure AD groups: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
def azure_group_member_counts(request):
    """Fetch member counts for specific Azure AD groups"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)
    
    # Check permissions
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({
            'success': False,
            'error': 'Only branch admins can access Azure AD groups'
        }, status=403)
    
    if not request.user.branch or not request.user.branch.teams_integration_enabled:
        return JsonResponse({
            'success': False,
            'error': 'Teams integration not enabled'
        }, status=403)
    
    try:
        import json
        from .azure_ad_utils import AzureADGroupAPI, AzureADAPIError
        
        # Parse request data
        data = json.loads(request.body)
        group_ids = data.get('group_ids', [])
        
        if not group_ids:
            return JsonResponse({'success': True, 'counts': {}})
        
        # Initialize Azure AD API
        api = AzureADGroupAPI(request.user.branch)
        
        # Fetch member counts for each group
        counts = {}
        for group_id in group_ids:
            try:
                count = api.get_group_member_count(group_id)
                counts[group_id] = count
            except Exception as e:
                logger.warning(f"Could not fetch count for group {group_id}: {str(e)}")
                counts[group_id] = 0
        
        return JsonResponse({
            'success': True,
            'counts': counts
        })
        
    except Exception as e:
        logger.error(f"Error fetching member counts: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
def azure_group_import(request):
    """Import Azure AD groups and their members to LMS"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)
    
    # Check permissions
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({
            'success': False,
            'error': 'Only branch admins can import Azure AD groups'
        }, status=403)
    
    if not request.user.branch:
        return JsonResponse({
            'success': False,
            'error': 'User must belong to a branch'
        }, status=403)
    
    try:
        import json
        from .azure_ad_utils import AzureADGroupAPI, AzureADAPIError
        from .models import AzureADGroupImport, AzureADUserMapping
        from users.models import CustomUser
        from django.contrib.auth.hashers import make_password
        import secrets
        import string
        
        # Parse request data
        data = json.loads(request.body)
        group_mappings = data.get('group_mappings', [])
        
        if not group_mappings:
            return JsonResponse({
                'success': False,
                'error': 'No group mappings provided'
            }, status=400)
        
        # Initialize Azure AD API
        api = AzureADGroupAPI(request.user.branch)
        
        imported_groups = []
        imported_users_count = 0
        errors = []
        
        with transaction.atomic():
            for mapping in group_mappings:
                azure_group_id = mapping.get('azure_group_id')
                azure_group_name = mapping.get('azure_group_name')
                assigned_role = mapping.get('assigned_role', 'learner')
                
                if not azure_group_id or not azure_group_name:
                    continue
                
                try:
                    # Check if this Azure group is already imported
                    existing_import = AzureADGroupImport.objects.filter(
                        azure_group_id=azure_group_id,
                        branch=request.user.branch
                    ).first()
                    
                    if existing_import:
                        errors.append(f"Group '{azure_group_name}' is already imported")
                        continue
                    
                    # Create or get LMS group
                    lms_group, created = BranchGroup.objects.get_or_create(
                        name=f"{azure_group_name} (Azure)",
                        branch=request.user.branch,
                        defaults={
                            'description': f'Imported from Azure AD group: {azure_group_name}',
                            'created_by': request.user,
                            'group_type': 'user'
                        }
                    )
                    
                    # Create Azure group import record
                    azure_import = AzureADGroupImport.objects.create(
                        azure_group_id=azure_group_id,
                        azure_group_name=azure_group_name,
                        lms_group=lms_group,
                        branch=request.user.branch,
                        assigned_role=assigned_role,
                        imported_by=request.user
                    )
                    
                    # Fetch group members from Azure AD
                    members = api.get_group_members(azure_group_id)
                    
                    logger.info(f"Starting to import {len(members)} members from Azure AD group: {azure_group_name}")
                    
                    # Import users
                    skipped_count = 0
                    for member in members:
                        try:
                            azure_user_id = member.get('id')
                            email = member.get('mail') or member.get('userPrincipalName')
                            display_name = member.get('displayName', '')
                            given_name = member.get('givenName', '')
                            surname = member.get('surname', '')
                            
                            if not email:
                                logger.warning(f"Skipping user without email: {azure_user_id} - {display_name}")
                                skipped_count += 1
                                continue
                            
                            # Generate username from email
                            username = email.split('@')[0]
                            
                            # Check if user already exists
                            lms_user = CustomUser.objects.filter(email=email).first()
                            
                            if not lms_user:
                                # Create new user with auto-generated password
                                alphabet = string.ascii_letters + string.digits + string.punctuation
                                temp_password = ''.join(secrets.choice(alphabet) for i in range(16))
                                
                                # Ensure unique username
                                base_username = username
                                counter = 1
                                while CustomUser.objects.filter(username=username).exists():
                                    username = f"{base_username}{counter}"
                                    counter += 1
                                
                                lms_user = CustomUser.objects.create(
                                    username=username,
                                    email=email,
                                    first_name=given_name,
                                    last_name=surname,
                                    role=assigned_role,
                                    branch=request.user.branch,
                                    password=make_password(temp_password),
                                    is_active=True
                                )
                                imported_users_count += 1
                                logger.info(f"Created new user: {email} with role: {assigned_role}")
                            else:
                                # Update existing user's branch and role if needed
                                if not lms_user.branch:
                                    lms_user.branch = request.user.branch
                                if lms_user.role != assigned_role:
                                    lms_user.role = assigned_role
                                lms_user.save()
                                logger.info(f"Updated existing user: {email}")
                            
                            # Create Azure user mapping
                            AzureADUserMapping.objects.get_or_create(
                                azure_user_id=azure_user_id,
                                azure_group_import=azure_import,
                                defaults={
                                    'azure_email': email,
                                    'lms_user': lms_user
                                }
                            )
                            
                            # Add user to LMS group
                            GroupMembership.objects.get_or_create(
                                group=lms_group,
                                user=lms_user,
                                defaults={
                                    'invited_by': request.user,
                                    'is_active': True
                                }
                            )
                            
                        except Exception as user_error:
                            logger.error(f"Error importing user {member.get('mail')}: {str(user_error)}")
                            logger.exception("Full traceback:")
                            skipped_count += 1
                            continue
                    
                    logger.info(f"Import completed for group {azure_group_name}: {imported_users_count} users imported, {skipped_count} skipped")
                    
                    imported_groups.append({
                        'azure_name': azure_group_name,
                        'lms_name': lms_group.name,
                        'members_count': len(members),
                        'imported_count': imported_users_count,
                        'skipped_count': skipped_count,
                        'role': assigned_role
                    })
                    
                except Exception as group_error:
                    logger.error(f"Error importing group {azure_group_name}: {str(group_error)}")
                    errors.append(f"Error importing '{azure_group_name}': {str(group_error)}")
                    continue
        
        return JsonResponse({
            'success': True,
            'imported_groups': imported_groups,
            'imported_users_count': imported_users_count,
            'errors': errors
        })
        
    except AzureADAPIError as e:
        logger.error(f"Azure AD API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Error importing Azure AD groups: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
def azure_group_sync(request):
    """Sync Azure AD groups - add new members to existing imported groups"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method allowed'}, status=405)
    
    # Check permissions
    if request.user.role not in ['admin', 'superadmin', 'globaladmin']:
        return JsonResponse({
            'success': False,
            'error': 'Only branch admins can sync Azure AD groups'
        }, status=403)
    
    if not request.user.branch:
        return JsonResponse({
            'success': False,
            'error': 'User must belong to a branch'
        }, status=403)
    
    try:
        from .azure_ad_utils import AzureADGroupAPI, AzureADAPIError
        from .models import AzureADGroupImport, AzureADUserMapping
        from users.models import CustomUser
        from django.contrib.auth.hashers import make_password
        import secrets
        import string
        
        # Initialize Azure AD API
        api = AzureADGroupAPI(request.user.branch)
        
        # Get all active Azure imports for this branch
        azure_imports = AzureADGroupImport.objects.filter(
            branch=request.user.branch,
            is_active=True
        )
        
        if not azure_imports.exists():
            return JsonResponse({
                'success': False,
                'error': 'No Azure AD groups have been imported yet'
            }, status=400)
        
        synced_groups = []
        new_users_count = 0
        
        with transaction.atomic():
            for azure_import in azure_imports:
                try:
                    # Fetch current members from Azure AD
                    members = api.get_group_members(azure_import.azure_group_id)
                    
                    # Get existing Azure user IDs for this import
                    existing_azure_ids = set(
                        azure_import.user_mappings.values_list('azure_user_id', flat=True)
                    )
                    
                    new_members_added = 0
                    skipped_count = 0
                    
                    for member in members:
                        azure_user_id = member.get('id')
                        
                        # Skip if user is already mapped
                        if azure_user_id in existing_azure_ids:
                            continue
                        
                        try:
                            email = member.get('mail') or member.get('userPrincipalName')
                            display_name = member.get('displayName', '')
                            given_name = member.get('givenName', '')
                            surname = member.get('surname', '')
                            
                            if not email:
                                logger.warning(f"Skipping user without email: {azure_user_id} - {display_name}")
                                skipped_count += 1
                                continue
                            
                            # Generate username from email
                            username = email.split('@')[0]
                            
                            # Check if user already exists
                            lms_user = CustomUser.objects.filter(email=email).first()
                            
                            if not lms_user:
                                # Create new user
                                alphabet = string.ascii_letters + string.digits + string.punctuation
                                temp_password = ''.join(secrets.choice(alphabet) for i in range(16))
                                
                                # Ensure unique username
                                base_username = username
                                counter = 1
                                while CustomUser.objects.filter(username=username).exists():
                                    username = f"{base_username}{counter}"
                                    counter += 1
                                
                                lms_user = CustomUser.objects.create(
                                    username=username,
                                    email=email,
                                    first_name=given_name,
                                    last_name=surname,
                                    role=azure_import.assigned_role,
                                    branch=request.user.branch,
                                    password=make_password(temp_password),
                                    is_active=True
                                )
                                new_users_count += 1
                                logger.info(f"Created new user during sync: {email}")
                            else:
                                # Update user's branch if needed
                                if not lms_user.branch:
                                    lms_user.branch = request.user.branch
                                    lms_user.save()
                            
                            # Create Azure user mapping
                            AzureADUserMapping.objects.get_or_create(
                                azure_user_id=azure_user_id,
                                azure_group_import=azure_import,
                                defaults={
                                    'azure_email': email,
                                    'lms_user': lms_user
                                }
                            )
                            
                            # Add user to LMS group
                            GroupMembership.objects.get_or_create(
                                group=azure_import.lms_group,
                                user=lms_user,
                                defaults={
                                    'invited_by': request.user,
                                    'is_active': True
                                }
                            )
                            
                            new_members_added += 1
                            
                        except Exception as user_error:
                            logger.error(f"Error syncing user {member.get('mail')}: {str(user_error)}")
                            continue
                    
                    # Update last synced time
                    azure_import.last_synced_at = timezone.now()
                    azure_import.save()
                    
                    synced_groups.append({
                        'azure_name': azure_import.azure_group_name,
                        'lms_name': azure_import.lms_group.name,
                        'new_members': new_members_added
                    })
                    
                except Exception as group_error:
                    logger.error(f"Error syncing group {azure_import.azure_group_name}: {str(group_error)}")
                    continue
        
        return JsonResponse({
            'success': True,
            'synced_groups': synced_groups,
            'new_users_count': new_users_count
        })
        
    except AzureADAPIError as e:
        logger.error(f"Azure AD API error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Error syncing Azure AD groups: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)
