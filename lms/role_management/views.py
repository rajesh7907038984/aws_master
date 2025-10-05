from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.urls import reverse
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.core.exceptions import ValidationError
from .models import Role, RoleCapability, UserRole, RoleAuditLog
from .utils import (
    PermissionManager, RoleValidator, AuditLogger, 
    require_capability, get_available_capabilities, get_capability_categories,
    enhanced_csrf_protect, SessionMonitor, SessionErrorHandler
)
from django.contrib.auth import get_user_model
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()

# Create your views here.

@login_required
@require_capability('manage_roles', redirect_url='role_management:role_list')
@enhanced_csrf_protect
def role_create(request):
    """Create a new role with enhanced validation and audit logging."""
    
    # Check if user is admin role - restrict to custom roles only
    is_admin_user = request.user.role == 'admin'
    
    if request.method == 'POST':
        try:
            # Extract form data
            role_data = {
                'name': request.POST.get('name'),
                'custom_name': request.POST.get('custom_name') if request.POST.get('name') == 'custom' else None,
                'description': request.POST.get('description', ''),
            }
            
            # For admin users, enforce custom role only
            if is_admin_user and role_data['name'] != 'custom':
                error_msg = "Branch Admin users can only create custom roles within their branch level."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return _render_role_create_form(request, role_data)
            
            # Validate role creation
            validation_errors = RoleValidator.validate_role_creation(role_data, request.user)
            if validation_errors:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': '; '.join(validation_errors)})
                for error in validation_errors:
                    messages.error(request, error)
                return _render_role_create_form(request, role_data)
            
            # Check if user can create this type of role
            if not PermissionManager.can_user_manage_role(request.user, role_data['name']):
                error_msg = "You don't have permission to create this type of role."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return _render_role_create_form(request, role_data)
            
            # Additional restriction: Admin users cannot create superadmin roles
            if request.user.role == 'admin' and role_data['name'] == 'superadmin':
                error_msg = "Branch Admin users are not allowed to create superadmin roles."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return _render_role_create_form(request, role_data)
            
            # Additional restriction: Super admin users cannot create globaladmin roles
            if request.user.role == 'superadmin' and role_data['name'] == 'globaladmin':
                error_msg = "Super admin users are not allowed to create global admin roles."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return _render_role_create_form(request, role_data)
            
            # Create the role and capabilities in a transaction
            with transaction.atomic():
                # Create the role
                role = Role.objects.create(
                    name=role_data['name'],
                    custom_name=role_data['custom_name'],
                    description=role_data['description'],
                    created_by=request.user
                )
                
                # Get capabilities from form or use defaults
                capabilities = request.POST.getlist('capabilities')
                if not capabilities and role_data['name'] != 'custom':
                    capabilities = Role.objects.get_default_capabilities(role_data['name'])
                
                # For branch admins, restrict capabilities to branch-level only
                if is_admin_user:
                    # Define admin-level capabilities that branch admins can include
                    allowed_capabilities = [
                        # User management capabilities (branch scope only)
                        'view_users', 'create_users', 'manage_users',
                        # Course management capabilities (branch scope only)
                        'view_courses', 'create_courses', 'manage_courses',
                        # Assignment management
                        'view_assignments', 'create_assignments', 'manage_assignments', 'grade_assignments',
                        # Group management
                        'view_groups', 'create_groups', 'manage_groups', 'manage_group_members',
                        # Other branch-level capabilities
                        'view_quizzes', 'create_quizzes', 'manage_quizzes', 'grade_quizzes',
                        'view_progress', 'manage_progress',
                        'view_reports', 'export_reports',
                        'manage_notifications', 'send_notifications'
                    ]
                    # CRITICAL Session: REJECT (don't filter) unauthorized capabilities
                    restricted_capabilities = [cap for cap in capabilities if cap not in allowed_capabilities]
                    if restricted_capabilities:
                        # Log Session violation
                        logger.error(f"Session VIOLATION: Branch Admin {request.user.username} attempted to create role with unauthorized capabilities: {restricted_capabilities}")
                        
                        # Create audit log for Session violation
                        AuditLogger.log_role_action(
                            user=request.user,
                            action='create',
                            role=None,
                            description=f"REJECTED: Attempt to create role with unauthorized capabilities: {restricted_capabilities}",
                            metadata={
                                'violation_type': 'unauthorized_capabilities',
                                'attempted_capabilities': restricted_capabilities,
                                'user_role': request.user.role,
                                'Session_level': 'critical'
                            },
                            request=request
                        )
                        
                        error_msg = f"Session policy violation: Branch Admins cannot assign the following capabilities: {', '.join(restricted_capabilities)}. Role creation rejected."
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': error_msg})
                        messages.error(request, error_msg)
                        return _render_role_create_form(request, role_data)
                
                # Add capabilities
                for cap in capabilities:
                    RoleCapability.objects.create(
                        role=role,
                        capability=cap,
                        description=f"Capability for {cap}",
                        created_by=request.user
                    )
                
                # Log the action
                AuditLogger.log_role_action(
                    user=request.user,
                    action='create',
                    role=role,
                    description=f"Created role '{role}' with {len(capabilities)} capabilities",
                    metadata={'capabilities': capabilities},
                    request=request
                )
            
            # Handle AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'Role "{role}" created successfully.',
                    'redirect_url': reverse('role_management:role_detail', args=[role.id])
                })
            
            messages.success(request, f'Role "{role}" created successfully.')
            return redirect('role_management:role_detail', role_id=role.id)
            
        except ValidationError as e:
            # Use secure error handler for validation errors
            sanitized_errors = SessionErrorHandler.handle_validation_error(e, request)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                if isinstance(sanitized_errors, dict) and 'error' in sanitized_errors:
                    return JsonResponse({'success': False, 'error': sanitized_errors['error']})
                else:
                    error_messages = []
                    for field, errors in sanitized_errors.items():
                        for error in errors:
                            error_messages.append(f"{field}: {error}")
                    return JsonResponse({'success': False, 'error': '; '.join(error_messages)})
            
            if isinstance(sanitized_errors, dict) and 'error' in sanitized_errors:
                messages.error(request, sanitized_errors['error'])
            else:
                for field, errors in sanitized_errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        except Exception as e:
            # Use secure error handler for all general exceptions
            sanitized_error = SessionErrorHandler.log_and_sanitize_error(
                e, request, 'system', 'role_create'
            )
            
            # Check for specific error types that need special handling
            error_msg = str(e).lower()
            redis_error_indicators = [
                'connecting to', 'connection refused', 'connection error',
                'redis', 'timeout', 'connection timed out', 'error 111',
                'connectionerror', 'connecttimeouterror', 'redisconnectionerror',
                'unable to connect', 'failed to connect', 'no route to host'
            ]
            
            is_redis_error = any(indicator in error_msg for indicator in redis_error_indicators)
            
            if is_redis_error:
                # Handle Redis errors gracefully
                try:
                    from django.core.cache import cache
                    PermissionManager.clear_user_cache(request.user)
                    
                    warning_msg = SessionErrorHandler.sanitize_error_message(
                        'Role created successfully, but caching may be temporarily unavailable.',
                        'system', 
                        request.user.role in ['globaladmin', 'superadmin']
                    )
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': warning_msg,
                            'redirect_url': reverse('role_management:role_list')
                        })
                    messages.warning(request, warning_msg)
                    return redirect('role_management:role_list')
                except Exception:
                    pass  # Fall through to general error handling
            
            # General error response
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': sanitized_error})
            messages.error(request, sanitized_error)
    
    return _render_role_create_form(request)

def _render_role_create_form(request, role_data=None):
    """Helper function to render the role creation form"""
    is_admin_user = request.user.role == 'admin'
    
    # Filter role choices based on user permissions and admin restrictions
    role_choices = []
    for choice in Role.ROLE_CHOICES:
        role_name = choice[0]
        
        # Admin users can only create custom roles
        if is_admin_user and role_name != 'custom':
            continue
            
        # Super admin users cannot create globaladmin roles
        if request.user.role == 'superadmin' and role_name == 'globaladmin':
            continue
            
        # Admin users cannot create superadmin or globaladmin roles
        if request.user.role == 'admin' and role_name in ['superadmin', 'globaladmin']:
            continue
        
        if PermissionManager.can_user_manage_role(request.user, choice[0]):
            role_choices.append(choice)
    
    # Get default capabilities for roles and filter based on user role
    default_capabilities = {}
    capability_categories = get_capability_categories()
    
    # For branch admins, restrict capabilities they can see/assign
    if is_admin_user:
        # Define branch-level capability categories that branch admins can manage
        branch_admin_allowed_categories = [
            'User Management', 
            'Course Management', 
            'Assignment Management', 
            'Group Management', 
            'Quiz Management',
            'Progress Tracking',
            'Reporting',
            'Communication'
        ]
        
        # Filter out capabilities that aren't branch-level
        filtered_categories = {}
        for category, capabilities in capability_categories.items():
            if category in branch_admin_allowed_categories:
                # Filter capabilities within allowed categories
                branch_admin_allowed_capabilities = [
                    # User management capabilities (branch scope only)
                    'view_users', 'create_users', 'manage_users',
                    # Course management capabilities (branch scope only)
                    'view_courses', 'create_courses', 'manage_courses',
                    # Assignment management
                    'view_assignments', 'create_assignments', 'manage_assignments', 'grade_assignments',
                    # Group management
                    'view_groups', 'create_groups', 'manage_groups', 'manage_group_members',
                    # Quiz management
                    'view_quizzes', 'create_quizzes', 'manage_quizzes', 'grade_quizzes', 'take_quizzes',
                    # Progress tracking
                    'view_progress', 'manage_progress',
                    # Reporting
                    'view_reports', 'export_reports',
                    # Communication
                    'view_messages', 'create_messages', 'manage_messages',
                    'manage_notifications', 'send_notifications',
                    # Other safe capabilities
                    'view_certificates_templates'
                ]
                filtered_capabilities = [cap for cap in capabilities if cap in branch_admin_allowed_capabilities]
                if filtered_capabilities:
                    filtered_categories[category] = filtered_capabilities
        
        capability_categories = filtered_categories
        
        # Admin users see only instructor and learner default capabilities
        default_capabilities = {
            'instructor': Role.objects.get_default_capabilities('instructor'),
            'learner': Role.objects.get_default_capabilities('learner')
        }
    
    context = {
        'role_choices': role_choices,
        'capability_categories': capability_categories,
        'role_data': role_data or {},
        'is_admin_user': is_admin_user,
        'default_capabilities': default_capabilities,
        'breadcrumbs': [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('role_management:role_list'), 'label': 'Role Management', 'icon': 'fa-user-shield'},
            {'label': 'Create Role'}
        ]
    }
    
    return render(request, 'role_management/role_create.html', context)

@login_required
@require_capability('view_roles', redirect_url='dashboard_admin')
def role_list(request):
    """Display list of roles with enhanced filtering and permissions."""
    
    # Check if user is admin role - show only custom roles
    is_admin_user = request.user.role == 'admin'
    
    # Get search and filter parameters
    query = request.GET.get('q', '')
    role_type = request.GET.get('role_type', '')
    status_filter = request.GET.get('status', 'all')
    
    # Base queryset with optimizations
    roles = Role.objects.select_related('created_by').prefetch_related('capabilities', 'user_roles__user').order_by('name')
    
    # Apply role-based filtering
    if request.user.role == 'globaladmin':
        # Global admin can see ALL roles from all businesses and branches without any filtering
        pass  # No filtering needed - global admin has system-wide access
    elif is_admin_user:
        # Admin users can only see custom roles and instructor/learner roles (for reference)
        roles = roles.filter(name__in=['custom', 'instructor', 'learner'])
    else:
        user_highest_role = PermissionManager.get_user_highest_role(request.user)
        if user_highest_role and user_highest_role.name == 'superadmin':
            # Super admin users: business-scoped filtering for custom roles
            # Get the businesses this super admin is assigned to
            from business.models import BusinessUserAssignment
            user_businesses = BusinessUserAssignment.objects.filter(
                user=request.user,
                is_active=True
            ).values_list('business_id', flat=True)
            
            if user_businesses:
                # Get super admin users from the same businesses
                business_super_admins = BusinessUserAssignment.objects.filter(
                    business_id__in=user_businesses,
                    is_active=True,
                    user__role='superadmin'
                ).values_list('user_id', flat=True)
                
                # Filter roles: system roles (except globaladmin) + custom roles created by same-business super admins
                roles = roles.filter(
                    Q(name__in=['superadmin', 'admin', 'instructor', 'learner']) |  # System roles
                    Q(name='custom', created_by_id__in=business_super_admins)  # Custom roles from same business
                )
            else:
                # If super admin has no business assignment, only show system roles
                roles = roles.filter(name__in=['superadmin', 'admin', 'instructor', 'learner'])
        elif user_highest_role and user_highest_role.name != 'superadmin':
            # Users can only see roles they can manage
            manageable_roles = []
            for role in roles:
                if PermissionManager.can_user_manage_role(request.user, role):
                    manageable_roles.append(role.pk)
            roles = roles.filter(pk__in=manageable_roles)
    
    # Apply search filter
    if query:
        roles = roles.filter(
            Q(name__icontains=query) |
            Q(custom_name__icontains=query) |
            Q(description__icontains=query)
        )
    
    # Apply role type filter
    if role_type:
        roles = roles.filter(name=role_type)
    
    # Apply status filter
    if status_filter == 'active':
        roles = roles.filter(is_active=True)
    elif status_filter == 'inactive':
        roles = roles.filter(is_active=False)
    
    # Add additional data to roles for template
    for role in roles:
        role.capabilities_count = role.capabilities.filter(is_active=True).count()
        role.users_count = role.user_roles.filter(is_active=True).count()
        role.can_edit = PermissionManager.can_user_manage_role(request.user, role)
        role.can_delete = role.can_be_deleted(requesting_user=request.user)[0] and PermissionManager.can_user_manage_role(request.user, role)
        # Add capability_list for template compatibility
        role.capability_list = list(role.capabilities.filter(is_active=True).values_list('capability', flat=True))
    
    # Handle pagination
    per_page = int(request.GET.get('per_page', 10))
    page = request.GET.get('page', 1)
    
    paginator = Paginator(roles, per_page)
    
    try:
        paginated_roles = paginator.page(page)
    except PageNotAnInteger:
        paginated_roles = paginator.page(1)
    except EmptyPage:
        paginated_roles = paginator.page(paginator.num_pages)

    context = {
        'roles': paginated_roles,
        'current_page': int(page),
        'per_page': per_page,
        'paginator': paginator,
        'page_obj': paginated_roles,
        'query': query,
        'role_type': role_type,
        'status_filter': status_filter,
        'role_choices': Role.ROLE_CHOICES,
        'can_create_role': PermissionManager.user_has_capability(request.user, 'create_roles'),
        'is_admin_user': is_admin_user,
        'breadcrumbs': [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Role Management', 'icon': 'fa-user-shield'}
        ]
    }
    
    return render(request, 'role_management/role_list.html', context)

@login_required
@require_capability('view_roles')
def role_detail(request, role_id):
    """View role details with audit history and enhanced information."""
    
    role = get_object_or_404(Role, id=role_id)
    
    # Check if user can view this role
    if not PermissionManager.can_user_manage_role(request.user, role) and not PermissionManager.user_has_capability(request.user, 'view_roles'):
        return HttpResponseForbidden("You don't have permission to view this role.")
    
    # Additional business-scoped access check for super admin users (global admin exempt)
    if request.user.role == 'superadmin' and request.user.role != 'globaladmin' and role.name == 'custom':
        from business.models import BusinessUserAssignment
        user_businesses = BusinessUserAssignment.objects.filter(
            user=request.user,
            is_active=True
        ).values_list('business_id', flat=True)
        
        if user_businesses and role.created_by:
            # Check if the role creator belongs to the same business
            creator_in_same_business = BusinessUserAssignment.objects.filter(
                user=role.created_by,
                business_id__in=user_businesses,
                is_active=True
            ).exists()
            
            if not creator_in_same_business:
                return HttpResponseForbidden("You don't have permission to view this role.")
    
    # Get role data with optimizations
    capabilities = role.capabilities.filter(is_active=True).order_by('capability')
    capability_values = list(capabilities.values_list('capability', flat=True))
    
    # Get users assigned to this role
    user_roles = UserRole.objects.filter(
        role=role, 
        is_active=True
    ).select_related('user', 'assigned_by').order_by('-assigned_at')
    
    # Filter out global admin users for super admin viewers
    if request.user.role == 'superadmin':
        user_roles = user_roles.exclude(user__role='globaladmin')
    
    # Get audit history
    audit_history = AuditLogger.get_role_audit_history(role, limit=50)
    
    # Check permissions for actions
    can_edit = PermissionManager.can_user_manage_role(request.user, role)
    can_delete, delete_warning_message = role.can_be_deleted()
    can_delete = can_delete and PermissionManager.can_user_manage_role(request.user, role)
    
    # Get role statistics
    total_capabilities = capabilities.count()
    total_users = user_roles.count()
    active_assignments = user_roles.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).count()
    
    context = {
        'role': role,
        'capabilities': capabilities,
        'capability_values': capability_values,
        'all_capabilities': get_available_capabilities(),
        'user_roles': user_roles,
        'audit_history': audit_history,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'delete_warning_message': delete_warning_message,
        'stats': {
            'total_capabilities': total_capabilities,
            'total_users': total_users,
            'active_assignments': active_assignments,
        },
        'breadcrumbs': [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('role_management:role_list'), 'label': 'Role Management', 'icon': 'fa-user-shield'},
            {'label': str(role)}
        ]
    }
    
    return render(request, 'role_management/role_detail.html', context)

@login_required
@require_capability('manage_roles')
@enhanced_csrf_protect
def role_edit(request, role_id):
    """Edit role with enhanced validation and audit logging."""
    
    role = get_object_or_404(Role, id=role_id)
    
    # Check if user can manage this role
    if not PermissionManager.can_user_manage_role(request.user, role):
        messages.error(request, "You don't have permission to edit this role.")
        return redirect('role_management:role_list')
    
    # Additional business-scoped access check for super admin users (global admin exempt)
    if request.user.role == 'superadmin' and request.user.role != 'globaladmin' and role.name == 'custom':
        from business.models import BusinessUserAssignment
        user_businesses = BusinessUserAssignment.objects.filter(
            user=request.user,
            is_active=True
        ).values_list('business_id', flat=True)
        
        if user_businesses and role.created_by:
            # Check if the role creator belongs to the same business
            creator_in_same_business = BusinessUserAssignment.objects.filter(
                user=role.created_by,
                business_id__in=user_businesses,
                is_active=True
            ).exists()
            
            if not creator_in_same_business:
                messages.error(request, "You don't have permission to edit this role.")
                return redirect('role_management:role_list')
    
    # Check if user is admin role - restrict to custom roles only
    is_admin_user = request.user.role == 'admin'
    
    # Branch admins can only edit custom roles
    if is_admin_user and role.name != 'custom':
        messages.error(request, "Branch Admin users can only edit custom roles within their branch level.")
        return redirect('role_management:role_list')
    
    if request.method == 'POST':
        try:
            # Extract form data
            role_data = {
                'name': request.POST.get('name'),
                'custom_name': request.POST.get('custom_name') if request.POST.get('name') == 'custom' else None,
                'description': request.POST.get('description', ''),
            }
            capabilities = request.POST.getlist('capabilities')
            
            # For admin users, enforce custom role only
            if is_admin_user and role_data['name'] != 'custom':
                messages.error(request, "Branch Admin users can only edit custom roles.")
                return _render_role_edit_form(request, role, role_data)
            
            # Validate the changes
            validation_errors = RoleValidator.validate_role_editing(role_data, request.user, exclude_role_id=role.id)
            
            if validation_errors:
                for error in validation_errors:
                    messages.error(request, error)
                return _render_role_edit_form(request, role, role_data)
            
            # For branch admins, restrict capabilities to branch-level only
            if is_admin_user:
                # Define admin-level capabilities that branch admins can include
                allowed_capabilities = [
                    # User management capabilities (branch scope only)
                    'view_users', 'create_users', 'manage_users',
                    # Course management capabilities (branch scope only)
                    'view_courses', 'create_courses', 'manage_courses',
                    # Assignment management
                    'view_assignments', 'create_assignments', 'manage_assignments', 'grade_assignments',
                    # Group management
                    'view_groups', 'create_groups', 'manage_groups', 'manage_group_members',
                    # Other branch-level capabilities
                    'view_quizzes', 'create_quizzes', 'manage_quizzes', 'grade_quizzes', 'take_quizzes',
                    # Progress tracking
                    'view_progress', 'manage_progress',
                    # Reporting
                    'view_reports', 'export_reports',
                    # Communication
                    'view_messages', 'create_messages', 'manage_messages',
                    'manage_notifications', 'send_notifications',
                    # Other safe capabilities
                    'view_certificates_templates'
                ]
                # CRITICAL Session: REJECT (don't filter) unauthorized capabilities
                restricted_capabilities = [cap for cap in capabilities if cap not in allowed_capabilities]
                if restricted_capabilities:
                    # Log Session violation
                    logger.error(f"Session VIOLATION: Branch Admin {request.user.username} attempted to edit role with unauthorized capabilities: {restricted_capabilities}")
                    
                    # Create audit log for Session violation
                    AuditLogger.log_role_action(
                        user=request.user,
                        action='update',
                        role=role,
                        description=f"REJECTED: Attempt to edit role with unauthorized capabilities: {restricted_capabilities}",
                        metadata={
                            'violation_type': 'unauthorized_capabilities',
                            'attempted_capabilities': restricted_capabilities,
                            'user_role': request.user.role,
                            'Session_level': 'critical',
                            'target_role_id': role.id
                        },
                        request=request
                    )
                    
                    error_msg = f"Session policy violation: Branch Admins cannot assign the following capabilities: {', '.join(restricted_capabilities)}. Role edit rejected."
                    messages.error(request, error_msg)
                    return _render_role_edit_form(request, role, role_data)
            
            # Track changes for audit
            changes = {}
            if role.name != role_data['name']:
                changes['name'] = {'old': role.name, 'new': role_data['name']}
            if role.custom_name != role_data['custom_name']:
                changes['custom_name'] = {'old': role.custom_name, 'new': role_data['custom_name']}
            if role.description != role_data['description']:
                changes['description'] = {'old': role.description, 'new': role_data['description']}
            
            old_capabilities = set(role.get_capabilities())
            new_capabilities = set(capabilities)
            if old_capabilities != new_capabilities:
                changes['capabilities'] = {
                    'added': list(new_capabilities - old_capabilities),
                    'removed': list(old_capabilities - new_capabilities)
                }
            
            # Update role in a transaction
            with transaction.atomic():
                # Update basic info
                role.name = role_data['name']
                role.custom_name = role_data['custom_name']
                role.description = role_data['description']
                role.save()
                
                # Update capabilities
                role.capabilities.all().delete()
                for cap in capabilities:
                    RoleCapability.objects.create(
                        role=role,
                        capability=cap,
                        description=f"Capability for {cap}",
                        created_by=request.user
                    )
                
                # Log the changes
                if changes:
                    AuditLogger.log_role_action(
                        user=request.user,
                        action='update',
                        role=role,
                        description=f"Updated role '{role}' with changes: {list(changes.keys())}",
                        metadata={'changes': changes},
                        request=request
                    )
            
            messages.success(request, f'Role "{role}" updated successfully.')
            return redirect('role_management:role_detail', role_id=role.id)
            
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
        except Exception as e:
            logger.error(f"Error updating role: {str(e)}", exc_info=True)
            messages.error(request, f'Error updating role: {str(e)}')
    
    return _render_role_edit_form(request, role)

def _render_role_edit_form(request, role, role_data=None):
    """Helper function to render the role edit form"""
    is_admin_user = request.user.role == 'admin'
    
    # Filter role choices based on user permissions
    role_choices = []
    for choice in Role.ROLE_CHOICES:
        # Apply business rules for role editing restrictions
        role_name = choice[0]
        
        # Admin users can only edit custom roles
        if is_admin_user and role_name != 'custom':
            continue
            
        # Super admin users cannot edit globaladmin roles
        if request.user.role == 'superadmin' and role_name == 'globaladmin':
            continue
            
        # Admin users cannot edit superadmin or globaladmin roles
        if request.user.role == 'admin' and role_name in ['superadmin', 'globaladmin']:
            continue
        
        if PermissionManager.can_user_manage_role(request.user, choice[0]):
            role_choices.append(choice)
    
    # Get current capabilities
    current_capabilities = list(role.capabilities.values_list('capability', flat=True))
    
    # Get capability categories and filter based on user role
    capability_categories = get_capability_categories()
    
    # For branch admins, restrict capabilities they can see/assign
    if is_admin_user:
        # Define branch-level capability categories that branch admins can manage
        branch_admin_allowed_categories = [
            'User Management', 
            'Course Management', 
            'Assignment Management', 
            'Group Management', 
            'Quiz Management',
            'Progress Tracking',
            'Reporting',
            'Communication'
        ]
        
        # Filter out capabilities that aren't branch-level
        filtered_categories = {}
        for category, capabilities in capability_categories.items():
            if category in branch_admin_allowed_categories:
                # Filter capabilities within allowed categories
                branch_admin_allowed_capabilities = [
                    # User management capabilities (branch scope only)
                    'view_users', 'create_users', 'manage_users',
                    # Course management capabilities (branch scope only)
                    'view_courses', 'create_courses', 'manage_courses',
                    # Assignment management
                    'view_assignments', 'create_assignments', 'manage_assignments', 'grade_assignments',
                    # Group management
                    'view_groups', 'create_groups', 'manage_groups', 'manage_group_members',
                    # Quiz management
                    'view_quizzes', 'create_quizzes', 'manage_quizzes', 'grade_quizzes', 'take_quizzes',
                    # Progress tracking
                    'view_progress', 'manage_progress',
                    # Reporting
                    'view_reports', 'export_reports',
                    # Communication
                    'view_messages', 'create_messages', 'manage_messages',
                    'manage_notifications', 'send_notifications',
                    # Other safe capabilities
                    'view_certificates_templates'
                ]
                filtered_capabilities = [cap for cap in capabilities if cap in branch_admin_allowed_capabilities]
                if filtered_capabilities:
                    filtered_categories[category] = filtered_capabilities
        
        capability_categories = filtered_categories
        
        # Also ensure that any existing capabilities that would now be restricted are removed
        if current_capabilities:
            current_capabilities = [cap for cap in current_capabilities if cap in branch_admin_allowed_capabilities]
    
    context = {
        'role': role,
        'capabilities': current_capabilities,
        'role_choices': role_choices,
        'capability_categories': capability_categories,
        'role_data': role_data or {
            'name': role.name,
            'custom_name': role.custom_name,
            'description': role.description,
        },
        'breadcrumbs': [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('role_management:role_list'), 'label': 'Role Management', 'icon': 'fa-user-shield'},
            {'url': reverse('role_management:role_detail', kwargs={'role_id': role.id}), 'label': str(role)},
            {'label': 'Edit Role'}
        ]
    }
    
    return render(request, 'role_management/role_edit.html', context)

@login_required
@require_capability('delete_roles')
def role_delete(request, role_id):
    """Delete a role with proper validation and audit logging."""
    
    role = get_object_or_404(Role, id=role_id)
    
    # Check if user can manage this role
    if not PermissionManager.can_user_manage_role(request.user, role):
        messages.error(request, "You don't have permission to delete this role.")
        return redirect('role_management:role_list')
    
    # Additional business-scoped access check for super admin users (global admin exempt)
    if request.user.role == 'superadmin' and request.user.role != 'globaladmin' and role.name == 'custom':
        from business.models import BusinessUserAssignment
        user_businesses = BusinessUserAssignment.objects.filter(
            user=request.user,
            is_active=True
        ).values_list('business_id', flat=True)
        
        if user_businesses and role.created_by:
            # Check if the role creator belongs to the same business
            creator_in_same_business = BusinessUserAssignment.objects.filter(
                user=role.created_by,
                business_id__in=user_businesses,
                is_active=True
            ).exists()
            
            if not creator_in_same_business:
                messages.error(request, "You don't have permission to delete this role.")
                return redirect('role_management:role_list')
    
    # Check if role can be deleted
    can_delete, message = role.can_be_deleted(requesting_user=request.user)
    if not can_delete:
        messages.error(request, f'Cannot delete role: {message}')
        return redirect('role_management:role_detail', role_id=role.id)
    
    if request.method == 'POST':
        try:
            role_name = str(role)
            
            # Log the deletion before actually deleting
            AuditLogger.log_role_action(
                user=request.user,
                action='delete',
                role=role,
                description=f"Deleted role '{role_name}'",
                metadata={'role_data': {
                    'name': role.name,
                    'custom_name': role.custom_name,
                    'description': role.description,
                    'capabilities': role.get_capabilities()
                }},
                request=request
            )
            
            # Delete the role
            role.delete()
            messages.success(request, f'Role "{role_name}" deleted successfully.')
            return redirect('role_management:role_list')
            
        except Exception as e:
            logger.error(f"Error deleting role: {str(e)}", exc_info=True)
            messages.error(request, f'Error deleting role: {str(e)}')
            return redirect('role_management:role_detail', role_id=role.id)
    
    return redirect('role_management:role_detail', role_id=role.id)

@login_required
@require_capability('manage_roles')
@enhanced_csrf_protect
def assign_role(request):
    """AJAX endpoint to assign a role to a user with enhanced Session validation."""
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        from django.db import transaction
        from .utils import PermissionManager
        
        # Session monitoring for anomalous behavior
        anomalies = SessionMonitor.check_for_anomalies(request.user)
        if anomalies:
            SessionMonitor.log_Session_event(
                'anomalous_behavior_detected',
                request.user,
                f"Anomalies during role assignment: {'; '.join(anomalies)}",
                severity='high',
                request=request
            )
        
        user_id = request.POST.get('user_id')
        role_id = request.POST.get('role_id')
        expires_days = request.POST.get('expires_days')
        
        if not user_id or not role_id:
            return JsonResponse({'success': False, 'error': 'Missing user_id or role_id'})
        
        user = get_object_or_404(User, id=user_id)
        role = get_object_or_404(Role, id=role_id)
        
        # Branch admin specific validation
        if request.user.role == 'admin':
            # Branch admins can only assign custom roles
            if role.name != 'custom':
                return JsonResponse({
                    'success': False,
                    'error': 'Branch Admin users can only assign custom roles'
                })
            
            # Branch admins can only assign roles to users within their branch
            if not hasattr(user, 'branch') or not hasattr(request.user, 'branch') or user.branch != request.user.branch:
                return JsonResponse({
                    'success': False,
                    'error': 'Branch Admin users can only assign roles to users within their branch'
                })
        
        # Comprehensive Session validation
        Session_violations = []
        try:
            Session_violations = PermissionManager.validate_role_assignment_Session(
                user, role, user, request.user
            )
        except Exception as e:
            logger.error(f"Error validating role assignment: {str(e)}", exc_info=True)
            Session_violations = [str(e)]
        
        if Session_violations:
            return JsonResponse({
                'success': False, 
                'error': 'Session validation failed: ' + '; '.join(Session_violations)
            })
        
        # Apply business rule restrictions for role assignment
        # Super admin users cannot assign globaladmin roles
        if request.user.role == 'superadmin' and role.name == 'globaladmin':
            return JsonResponse({
                'success': False, 
                'error': 'Super admin users are not allowed to assign global admin roles'
            })
        
        # Admin users cannot assign superadmin, globaladmin, or admin roles
        if request.user.role == 'admin' and role.name in ['superadmin', 'globaladmin', 'admin']:
            return JsonResponse({
                'success': False, 
                'error': 'Branch Admin users are not allowed to assign super admin, global admin, or admin roles'
            })
        
        # Double-check permissions
        if not PermissionManager.can_user_assign_role(request.user, role, user):
            return JsonResponse({
                'success': False, 
                'error': 'You do not have permission to assign this role'
            })
        
        # Use atomic transaction for data consistency
        with transaction.atomic():
            # Calculate expiration date
            expires_at = None
            if expires_days:
                try:
                    days = int(expires_days)
                    if days > 0:
                        # Validate maximum duration
                        max_days = 365 * 2  # 2 years max
                        if days > max_days:
                            return JsonResponse({
                                'success': False, 
                                'error': f'Role assignment duration cannot exceed {max_days} days'
                            })
                        expires_at = timezone.now() + timezone.timedelta(days=days)
                except (ValueError, TypeError):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Invalid expiration days value'
                    })
            
            # Create role assignment with enhanced validation
            user_role = UserRole(
                user=user,
                role=role,
                assigned_by=request.user,
                expires_at=expires_at
            )
            
            # The model's clean() and save() methods will handle additional validations
            user_role.save()
            
            # Log the assignment with enhanced metadata
            AuditLogger.log_role_action(
                user=request.user,
                action='assign',
                role=role,
                target_user=user,
                description=f"Assigned role '{role}' to user '{user.username}'",
                metadata={
                    'expires_at': expires_at.isoformat() if expires_at else None,
                    'assignment_id': user_role.pk,
                    'branch_id': getattr(user, 'branch_id', None),
                    'assigner_role': getattr(request.user, 'role', None)
                },
                request=request
            )
        
        return JsonResponse({
            'success': True,
            'message': f'Role "{role}" assigned to user "{user.username}" successfully.',
            'assignment_id': user_role.pk
        })
        
    except ValidationError as e:
        # Handle validation errors from model
        error_message = str(e)
        if hasattr(e, 'message_dict'):
            error_message = '; '.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
            
        return JsonResponse({
            'success': False, 
            'error': f'Validation error: {error_message}'
        })
        
    except Exception as e:
        error_message = SessionErrorHandler.log_and_sanitize_error(
            e, request, error_type='system', operation='role assignment'
        )
        return JsonResponse({
            'success': False, 
            'error': error_message
        })

@login_required
@require_capability('manage_roles')
def unassign_role(request):
    """AJAX endpoint to unassign a role from a user."""
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        user_role_id = request.POST.get('user_role_id')
        user_role = get_object_or_404(UserRole, id=user_role_id)
        
        # Branch admin specific validation
        if request.user.role == 'admin':
            # Branch admins can only unassign custom roles
            if user_role.role.name != 'custom':
                return JsonResponse({
                    'success': False,
                    'error': 'Branch Admin users can only manage custom roles'
                })
            
            # Branch admins can only unassign roles from users within their branch
            if not hasattr(user_role.user, 'branch') or not hasattr(request.user, 'branch') or user_role.user.branch != request.user.branch:
                return JsonResponse({
                    'success': False,
                    'error': 'Branch Admin users can only manage roles for users within their branch'
                })
        # Check permissions
        if not PermissionManager.can_user_assign_role(request.user, user_role.role, user_role.user):
            return JsonResponse({'success': False, 'error': 'You do not have permission to unassign this role'})
        
        # Log the unassignment before deletion
        AuditLogger.log_role_action(
            user=request.user,
            action='unassign',
            role=user_role.role,
            target_user=user_role.user,
            description=f"Unassigned role '{user_role.role}' from user '{user_role.user.username}'",
            request=request
        )
        
        # Delete the assignment
        user_role.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Role unassigned successfully.'
        })
        
    except Exception as e:
        logger.error(f"Error unassigning role: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_capability('view_roles')
def role_audit_log(request, role_id):
    """View audit log for a specific role."""
    
    role = get_object_or_404(Role, id=role_id)
    
    # Check permissions
    if not PermissionManager.can_user_manage_role(request.user, role) and not PermissionManager.user_has_capability(request.user, 'view_roles'):
        return HttpResponseForbidden("You don't have permission to view this role's audit log.")
    
    # Get audit history with pagination
    audit_logs = AuditLogger.get_role_audit_history(role, limit=500)
    
    per_page = int(request.GET.get('per_page', 20))
    page = request.GET.get('page', 1)
    
    paginator = Paginator(audit_logs, per_page)
    
    try:
        paginated_logs = paginator.page(page)
    except PageNotAnInteger:
        paginated_logs = paginator.page(1)
    except EmptyPage:
        paginated_logs = paginator.page(paginator.num_pages)
    
    context = {
        'role': role,
        'audit_logs': paginated_logs,
        'paginator': paginator,
        'page_obj': paginated_logs,
        'breadcrumbs': [
            {'url': reverse('dashboard_admin'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('role_management:role_list'), 'label': 'Role Management', 'icon': 'fa-user-shield'},
            {'url': reverse('role_management:role_detail', kwargs={'role_id': role.id}), 'label': str(role)},
            {'label': 'Audit Log'}
        ]
    }
    
    return render(request, 'role_management/role_audit_log.html', context)

@login_required
@require_capability('manage_roles')
def bulk_role_action(request):
    """Handle bulk actions on roles (activate/deactivate)."""
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        action = request.POST.get('action')
        role_ids = request.POST.getlist('role_ids')
        
        if not action or not role_ids:
            return JsonResponse({'success': False, 'error': 'Missing action or role IDs'})
        
        roles = Role.objects.filter(id__in=role_ids)
        
        # Check permissions for each role
        permitted_roles = []
        for role in roles:
            if PermissionManager.can_user_manage_role(request.user, role):
                permitted_roles.append(role)
        
        if not permitted_roles:
            return JsonResponse({'success': False, 'error': 'You do not have permission to perform this action on any of the selected roles'})
        
        # Perform the action
        updated_count = 0
        
        if action == 'activate':
            for role in permitted_roles:
                if not role.is_active:
                    role.is_active = True
                    role.save()
                    updated_count += 1
                    
                    # Log the action
                    AuditLogger.log_role_action(
                        user=request.user,
                        action='update',
                        role=role,
                        description=f"Activated role '{role}'",
                        request=request
                    )
        
        elif action == 'deactivate':
            for role in permitted_roles:
                if role.is_active and role.name not in ['superadmin', 'admin']:  # Prevent deactivating critical roles
                    role.is_active = False
                    role.save()
                    updated_count += 1
                    
                    # Log the action
                    AuditLogger.log_role_action(
                        user=request.user,
                        action='update',
                        role=role,
                        description=f"Deactivated role '{role}'",
                        request=request
                    )
        
        return JsonResponse({
            'success': True,
            'message': f'{updated_count} roles updated successfully.'
        })
        
    except Exception as e:
        logger.error(f"Error performing bulk role action: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})
