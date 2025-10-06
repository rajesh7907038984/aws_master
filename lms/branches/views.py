from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

from .models import Branch, AdminBranchAssignment
from users.models import CustomUser
from core.branch_filters import (
    set_admin_active_branch, 
    get_admin_active_branch,
    clear_admin_active_branch,
    get_admin_switchable_branches,
    BranchFilterManager
)
from core.rbac_decorators import require_superadmin_or_higher
from core.utils.business_filtering import filter_branches_by_business, get_superadmin_business_filter
from business.models import Business

logger = logging.getLogger(__name__)


@login_required
@require_POST
@csrf_protect
def switch_branch(request):
    """
    Switch the active branch for an admin user.
    """
    if request.user.role != 'admin':
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Only admin users can switch branches'})
        messages.error(request, 'Only admin users can switch branches.')
        return redirect('users:role_based_redirect')
    
    branch_id = request.POST.get('branch_id')
    if not branch_id:
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Branch ID is required'})
        messages.error(request, 'Branch ID is required.')
        return redirect('users:role_based_redirect')
    
    try:
        branch_id = int(branch_id)
    except ValueError:
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Invalid branch ID'})
        messages.error(request, 'Invalid branch ID.')
        return redirect('users:role_based_redirect')
    
    # Switch to the branch
    success = set_admin_active_branch(request, branch_id)
    
    if success:
        branch = Branch.objects.get(id=branch_id)
        logger.info(f"Admin user {request.user.username} switched to branch {branch.name}")
        
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({
                'success': True, 
                'message': f'Switched to {branch.name}',
                'branch_name': branch.name,
                'branch_id': branch.id
            })
        
        messages.success(request, f'Successfully switched to {branch.name}')
    else:
        logger.warning(f"Failed branch switch attempt by {request.user.username} to branch ID {branch_id}")
        
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Unable to switch to the selected branch'})
        
        messages.error(request, 'Unable to switch to the selected branch.')
    
    return redirect('users:role_based_redirect')


@login_required
@require_POST
@csrf_protect
def reset_to_primary_branch(request):
    """
    Reset admin user to their primary branch.
    """
    if request.user.role != 'admin':
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Only admin users can reset branches'})
        messages.error(request, 'Only admin users can reset branches.')
        return redirect('users:role_based_redirect')
    
    clear_admin_active_branch(request)
    primary_branch_name = request.user.branch.name if request.user.branch else 'Primary Branch'
    
    logger.info(f"Admin user {request.user.username} reset to primary branch {primary_branch_name}")
    
    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'success': True, 
            'message': f'Reset to {primary_branch_name}',
            'branch_name': primary_branch_name,
            'branch_id': request.user.branch.id if request.user.branch else None
        })
    
    messages.success(request, f'Reset to your primary branch: {primary_branch_name}')
    return redirect('users:role_based_redirect')


@login_required
def get_user_branches(request):
    """
    Get the branches available to the current admin user (for AJAX).
    """
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Only admin users can access this endpoint'}, status=403)
    
    accessible_branches = BranchFilterManager.get_accessible_branches(request.user)
    current_branch = get_admin_active_branch(request)
    
    branches_data = []
    for branch in accessible_branches:
        branches_data.append({
            'id': branch.id,
            'name': branch.name,
            'business_name': branch.business.name if branch.business else None,
            'is_primary': branch == request.user.branch,
            'is_current': branch == current_branch
        })
    
    return JsonResponse({
        'branches': branches_data,
        'current_branch_id': current_branch.id if current_branch else None,
        'current_branch_name': current_branch.name if current_branch else None
    })


# Super Admin Management Views
@login_required
@require_superadmin_or_higher
def manage_admin_branches(request):
    """
    Super admin interface to manage admin users' additional branch assignments.
    """
    if request.user.role == 'superadmin':
        # Super admins can only see admin users and branches within their assigned businesses
        accessible_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
        accessible_branches = Branch.objects.filter(business__in=accessible_businesses, is_active=True)
        
        # Filter admin users to only show those in businesses the super admin has access to
        admin_users = CustomUser.objects.filter(
            role='admin',
            is_active=True,
            branch__business__in=accessible_businesses
        ).select_related('branch', 'branch__business')
        
        # Get accessible businesses for display
        accessible_businesses_objects = Business.objects.filter(id__in=accessible_businesses, is_active=True)
    else:  # globaladmin
        # Global admins can manage all admin users and all businesses
        accessible_branches = Branch.objects.filter(is_active=True)
        admin_users = CustomUser.objects.filter(role='admin', is_active=True)
        accessible_businesses_objects = Business.objects.filter(is_active=True)
    
    # Get current assignments
    assignments = AdminBranchAssignment.objects.filter(
        is_active=True,
        user__in=admin_users,
        branch__in=accessible_branches
    ).select_related('user', 'branch', 'assigned_by')
    
    context = {
        'admin_users': admin_users,
        'accessible_branches': accessible_branches,
        'accessible_businesses': accessible_businesses_objects,
        'assignments': assignments,
        'page_title': 'Manage Admin Branch Assignments'
    }
    
    return render(request, 'branches/manage_admin_branches.html', context)


@login_required
@require_superadmin_or_higher
@require_POST
@csrf_protect
def assign_admin_to_branch(request):
    """
    Assign an admin user to an additional branch.
    """
    admin_user_id = request.POST.get('admin_user_id')
    branch_id = request.POST.get('branch_id')
    notes = request.POST.get('notes', '').strip()
    
    if not admin_user_id or not branch_id:
        messages.error(request, 'Admin user and branch are required.')
        return redirect('branches:manage_admin_branches')
    
    try:
        admin_user = get_object_or_404(CustomUser, id=admin_user_id, role='admin', is_active=True)
        branch = get_object_or_404(Branch, id=branch_id, is_active=True)
        
        # Validation: ensure super admin has access to the target branch
        if request.user.role == 'superadmin':
            branch_business = branch.business
            accessible_businesses = list(request.user.business_assignments.filter(is_active=True).values_list('business', flat=True))
            
            # Super admins can assign any admin user to branches within their accessible businesses
            if branch_business.id not in accessible_businesses:
                raise PermissionDenied("You don't have access to assign users to this branch")
        
        # Create the assignment
        with transaction.atomic():
            assignment, created = AdminBranchAssignment.objects.get_or_create(
                user=admin_user,
                branch=branch,
                defaults={
                    'assigned_by': request.user,
                    'notes': notes,
                    'is_active': True
                }
            )
            
            if created:
                logger.info(f"Admin {request.user.username} assigned {admin_user.username} to branch {branch.name}")
                messages.success(request, f'Successfully assigned {admin_user.get_full_name()} to {branch.name}')
            else:
                if not assignment.is_active:
                    assignment.is_active = True
                    assignment.assigned_by = request.user
                    assignment.notes = notes
                    assignment.save()
                    messages.success(request, f'Reactivated assignment: {admin_user.get_full_name()} to {branch.name}')
                else:
                    messages.warning(request, f'{admin_user.get_full_name()} is already assigned to {branch.name}')
    
    except (CustomUser.DoesNotExist, Branch.DoesNotExist):
        messages.error(request, 'Invalid admin user or branch selected.')
    except Exception as e:
        logger.error(f"Error assigning admin to branch: {str(e)}")
        messages.error(request, 'An error occurred while assigning the admin to the branch.')
    
    return redirect('branches:manage_admin_branches')


@login_required
@require_superadmin_or_higher
@require_POST
@csrf_protect
def remove_admin_from_branch(request):
    """
    Remove an admin user's assignment from an additional branch.
    """
    assignment_id = request.POST.get('assignment_id')
    
    if not assignment_id:
        messages.error(request, 'Assignment ID is required.')
        return redirect('branches:manage_admin_branches')
    
    try:
        assignment = get_object_or_404(AdminBranchAssignment, id=assignment_id, is_active=True)
        
        # Validation: ensure super admin has access to this assignment
        if request.user.role == 'superadmin':
            accessible_businesses = list(request.user.business_assignments.filter(is_active=True).values_list('business', flat=True))
            if assignment.branch.business.id not in accessible_businesses:
                raise PermissionDenied("You don't have access to manage this assignment")
        
        # Deactivate the assignment with transaction support
        with transaction.atomic():
            assignment.is_active = False
            assignment.save()
            
            logger.info(f"Admin {request.user.username} removed {assignment.user.username} from branch {assignment.branch.name}")
            messages.success(request, f'Successfully removed {assignment.user.get_full_name()} from {assignment.branch.name}')
    
    except AdminBranchAssignment.DoesNotExist:
        logger.warning(f"Assignment not found - ID: {assignment_id}, User: {request.user.username}")
        messages.error(request, 'Assignment not found or already removed.')
    except PermissionDenied as pe:
        logger.warning(f"Permission denied for {request.user.username}: {str(pe)}")
        messages.error(request, str(pe))
    except Exception as e:
        logger.error(f"Error removing admin from branch: {str(e)}", exc_info=True)
        messages.error(request, 'An error occurred while removing the admin from the branch. Please try again or contact support.')
    
    return redirect('branches:manage_admin_branches')


@login_required
@require_superadmin_or_higher
@require_POST
@csrf_protect
def edit_admin_assignment(request):
    """
    Edit an admin user's assignment (admin user, branch, and notes).
    """
    assignment_id = request.POST.get('assignment_id')
    admin_user_id = request.POST.get('admin_user_id')
    branch_id = request.POST.get('branch_id')
    notes = request.POST.get('notes', '').strip()
    
    if not assignment_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Assignment ID is required.'})
        messages.error(request, 'Assignment ID is required.')
        return redirect('branches:manage_admin_branches')
    
    try:
        assignment = get_object_or_404(AdminBranchAssignment, id=assignment_id, is_active=True)
        
        # Validation: ensure super admin has access to this assignment
        if request.user.role == 'superadmin':
            accessible_businesses = list(request.user.business_assignments.filter(is_active=True).values_list('business', flat=True))
            if assignment.branch.business.id not in accessible_businesses:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': "You don't have access to manage this assignment"})
                raise PermissionDenied("You don't have access to manage this assignment")
        
        # Handle admin user change
        if admin_user_id and admin_user_id != str(assignment.user.id):
            try:
                new_admin_user = get_object_or_404(CustomUser, id=admin_user_id, role='admin', is_active=True)
                
                # Validate that the new admin user is accessible to the super admin
                if request.user.role == 'superadmin':
                    if new_admin_user.branch and new_admin_user.branch.business:
                        if new_admin_user.branch.business.id not in accessible_businesses:
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                return JsonResponse({'success': False, 'error': "You don't have access to assign this admin user"})
                            raise PermissionDenied("You don't have access to assign this admin user")
                
                assignment.user = new_admin_user
                logger.info(f"Admin {request.user.username} changed assignment {assignment.id} user from {assignment.user.username} to {new_admin_user.username}")
            except CustomUser.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Invalid admin user selected.'})
                messages.error(request, 'Invalid admin user selected.')
                return redirect('branches:manage_admin_branches')
        
        # Handle branch change
        if branch_id and branch_id != str(assignment.branch.id):
            try:
                new_branch = get_object_or_404(Branch, id=branch_id, is_active=True)
                
                # Validate that the new branch is accessible to the super admin
                if request.user.role == 'superadmin':
                    if new_branch.business and new_branch.business.id not in accessible_businesses:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': "You don't have access to assign to this branch"})
                        raise PermissionDenied("You don't have access to assign to this branch")
                
                # Check if the new assignment would create a duplicate
                existing_assignment = AdminBranchAssignment.objects.filter(
                    user=assignment.user,
                    branch=new_branch,
                    is_active=True
                ).exclude(id=assignment.id).first()
                
                if existing_assignment:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': f'{assignment.user.get_full_name()} is already assigned to {new_branch.name}'})
                    messages.error(request, f'{assignment.user.get_full_name()} is already assigned to {new_branch.name}')
                    return redirect('branches:manage_admin_branches')
                
                # Prevent assignment to user's primary branch
                if assignment.user.branch == new_branch:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': 'Cannot assign admin to their primary branch'})
                    messages.error(request, 'Cannot assign admin to their primary branch')
                    return redirect('branches:manage_admin_branches')
                
                assignment.branch = new_branch
                logger.info(f"Admin {request.user.username} changed assignment {assignment.id} branch to {new_branch.name}")
            except Branch.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Invalid branch selected.'})
                messages.error(request, 'Invalid branch selected.')
                return redirect('branches:manage_admin_branches')
        
        # Update the assignment with transaction support
        with transaction.atomic():
            assignment.notes = notes
            assignment.save()
            
            logger.info(f"Admin {request.user.username} updated assignment {assignment.id}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True, 
                    'message': f'Successfully updated assignment for {assignment.user.get_full_name()}'
                })
            
            messages.success(request, f'Successfully updated assignment for {assignment.user.get_full_name()}')
    
    except AdminBranchAssignment.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Assignment not found.'})
        messages.error(request, 'Assignment not found.')
    except PermissionDenied as pe:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(pe)})
        messages.error(request, str(pe))
    except Exception as e:
        logger.error(f"Error updating assignment: {str(e)}", exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'An error occurred while updating the assignment.'})
        messages.error(request, 'An error occurred while updating the assignment.')
    
    return redirect('branches:manage_admin_branches')


@login_required
@require_superadmin_or_higher
def get_admin_branch_assignments(request, admin_user_id):
    """
    Get current branch assignments for a specific admin user (AJAX endpoint).
    """
    if request.user.role not in ['superadmin', 'globaladmin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        admin_user = get_object_or_404(CustomUser, id=admin_user_id, role='admin', is_active=True)
        
        # Validation for super admins - they can view assignments for any admin user
        # The assignment creation/deletion will be controlled by the target branch permissions
        if request.user.role == 'superadmin':
            # No additional validation needed here - super admins can view any admin user's assignments
            # Branch-level permissions are enforced during assignment operations
            pass
        
        # Get primary branch
        primary_branch = {
            'id': admin_user.branch.id if admin_user.branch else None,
            'name': admin_user.branch.name if admin_user.branch else None,
            'business_name': admin_user.branch.business.name if admin_user.branch and admin_user.branch.business else None
        }
        
        # Get additional assignments
        assignments = AdminBranchAssignment.objects.filter(
            user=admin_user, 
            is_active=True
        ).select_related('branch', 'branch__business')
        
        additional_branches = []
        for assignment in assignments:
            additional_branches.append({
                'assignment_id': assignment.id,
                'branch_id': assignment.branch.id,
                'branch_name': assignment.branch.name,
                'business_name': assignment.branch.business.name if assignment.branch.business else None,
                'assigned_at': assignment.assigned_at.isoformat(),
                'notes': assignment.notes
            })
        
        return JsonResponse({
            'user_id': admin_user.id,
            'user_name': admin_user.get_full_name(),
            'primary_branch': primary_branch,
            'additional_branches': additional_branches
        })
    
    except Exception as e:
        logger.error(f"Error getting admin branch assignments: {str(e)}")
        return JsonResponse({'error': 'An error occurred'}, status=500)


@login_required
@require_superadmin_or_higher
def manage_branches(request):
    """
    List and manage branches for global admin and super admin users.
    """
    # Use the business filtering utility for consistent filtering across the app
    branches = filter_branches_by_business(request.user).select_related('business').order_by('business__name', 'name')
    
    if request.user.role == 'superadmin':
        # Get businesses that super admin has access to
        accessible_business_ids = get_superadmin_business_filter(request.user)
        businesses = Business.objects.filter(id__in=accessible_business_ids)
        
        # Debug: Log the accessible businesses for super admin
        logger.info(f"Super admin {request.user.username} accessible businesses: {accessible_business_ids}")
        logger.info(f"Filtered branches count: {branches.count()}, businesses count: {businesses.count()}")
        
        # Check if super admin has no business assignments
        if not accessible_business_ids:
            logger.warning(f"Super admin {request.user.username} has no active business assignments!")
            messages.warning(request, "You have no active business assignments. Please contact a Global Admin to assign you to a business.")
    else:  # globaladmin
        # Global admins can manage all businesses
        businesses = Business.objects.all()
    
    # Get branch statistics
    branch_stats = {}
    for branch in branches:
        stats = branch.get_branch_statistics()
        branch_stats[branch.id] = stats
    
    context = {
        'branches': branches,
        'businesses': businesses,
        'branch_stats': branch_stats,
        'page_title': 'Manage Branches'
    }
    
    return render(request, 'branches/branch_list.html', context)


@login_required
@require_superadmin_or_higher  
@require_POST
@csrf_protect
def create_branch(request):
    """
    Create a new branch.
    """
    branch_name = request.POST.get('branch_name', '').strip()
    business_id = request.POST.get('business_id')
    description = request.POST.get('description', '').strip()
    
    if not branch_name:
        messages.error(request, 'Branch name is required.')
        return redirect('branches:branch_list')
        
    if not business_id:
        messages.error(request, 'Business selection is required.')
        return redirect('branches:branch_list')
    
    try:
        business = get_object_or_404(Business, id=business_id, is_active=True)
        
        # Validation: ensure user has access to the business
        if request.user.role == 'superadmin':
            # Super admin users can only create branches in businesses they are assigned to
            accessible_business_ids = get_superadmin_business_filter(request.user)
            if business.id not in accessible_business_ids:
                messages.error(request, f"You don't have permission to create branches in '{business.name}'. You can only create branches in businesses you are assigned to.")
                return redirect('branches:branch_list')
        
        # Validate branch creation using the existing validator
        from core.rbac_validators import AllocationValidator
        errors = AllocationValidator.validate_branch_creation(request.user, business)
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('branches:branch_list')
        
        # Create the branch
        with transaction.atomic():
            branch = Branch.objects.create(
                name=branch_name,
                business=business,
                description=description,
                is_active=True
            )
            
            logger.info(f"Branch '{branch_name}' created by {request.user.username} in business '{business.name}'")
            messages.success(request, f'Successfully created branch "{branch_name}" in {business.name}')
    
    except Business.DoesNotExist:
        messages.error(request, 'Selected business not found.')
    except Exception as e:
        logger.error(f"Error creating branch: {str(e)}")
        messages.error(request, 'An error occurred while creating the branch.')
    
    return redirect('branches:branch_list')


@login_required
@require_superadmin_or_higher
@require_POST
@csrf_protect  
def edit_branch(request, branch_id):
    """
    Edit an existing branch.
    """
    branch = get_object_or_404(Branch, id=branch_id, is_active=True)
    
    # Validation: ensure user has access to this branch
    if request.user.role == 'superadmin':
        accessible_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
        if branch.business and branch.business.id not in accessible_businesses:
            raise PermissionDenied("You don't have access to edit this branch")
    
    branch_name = request.POST.get('branch_name', '').strip()
    description = request.POST.get('description', '').strip()
    sharepoint_integration = request.POST.get('sharepoint_integration_enabled') == 'on'
    order_management = request.POST.get('order_management_enabled') == 'on'
    scorm_integration = request.POST.get('scorm_integration_enabled') == 'on'
    
    if not branch_name:
        messages.error(request, 'Branch name is required.')
        return redirect('branches:branch_list')
    
    try:
        with transaction.atomic():
            branch.name = branch_name
            branch.description = description
            branch.sharepoint_integration_enabled = sharepoint_integration
            branch.order_management_enabled = order_management
            branch.scorm_integration_enabled = scorm_integration
            branch.save()
            
            logger.info(f"Branch '{branch.name}' updated by {request.user.username}")
            messages.success(request, f'Successfully updated branch "{branch.name}"')
    
    except Exception as e:
        logger.error(f"Error updating branch: {str(e)}")
        messages.error(request, 'An error occurred while updating the branch.')
    
    return redirect('branches:branch_list')


@login_required
@require_superadmin_or_higher
@require_POST
@csrf_protect
def delete_branch(request, branch_id):
    """
    Deactivate a branch (soft delete).
    """
    # Enhanced logging for debugging
    logger.info(f"Delete branch request - User: {request.user.username} (role: {request.user.role}), Branch ID: {branch_id}")
    
    try:
        branch = get_object_or_404(Branch, id=branch_id, is_active=True)
        logger.info(f"Found branch: {branch.name} (ID: {branch.id}) in business: {branch.business.name if branch.business else 'None'}")
    except Branch.DoesNotExist:
        logger.error(f"Branch not found or inactive - ID: {branch_id}, User: {request.user.username}")
        messages.error(request, f'Branch not found or already deleted.')
        return redirect('branches:branch_list')
    
    # Validation: ensure user has access to this branch
    if request.user.role == 'superadmin':
        accessible_businesses = list(request.user.business_assignments.filter(is_active=True).values_list('business', flat=True))
        logger.info(f"Super admin accessible businesses: {accessible_businesses}")
        
        if branch.business and branch.business.id not in accessible_businesses:
            logger.warning(f"Access denied - Super admin {request.user.username} tried to delete branch {branch.name} (business: {branch.business.id}) but only has access to businesses: {accessible_businesses}")
            messages.error(request, f"You don't have permission to delete this branch. You can only delete branches in businesses you are assigned to.")
            return redirect('branches:branch_list')
    
    # Check if branch has users
    user_count = branch.get_branch_users().filter(is_active=True).count()
    logger.info(f"Branch {branch.name} has {user_count} active users")
    
    if user_count > 0:
        logger.info(f"Cannot delete branch {branch.name} - has {user_count} active users")
        messages.error(request, f'Cannot delete branch "{branch.name}" because it has {user_count} active users. Please reassign users first.')
        return redirect('branches:branch_list')
    
    try:
        with transaction.atomic():
            branch.is_active = False
            branch.save()
            
            # Also deactivate any admin branch assignments for this branch
            deactivated_assignments = AdminBranchAssignment.objects.filter(branch=branch, is_active=True).update(is_active=False)
            logger.info(f"Deactivated {deactivated_assignments} admin branch assignments for branch {branch.name}")
            
            logger.info(f"Branch '{branch.name}' successfully deactivated by {request.user.username}")
            messages.success(request, f'Successfully deleted branch "{branch.name}"')
    
    except ValidationError as ve:
        logger.error(f"Validation error deleting branch {branch.name}: {ve}")
        messages.error(request, f'Cannot delete branch "{branch.name}": {ve.message if hasattr(ve, "message") else str(ve)}')
    except Exception as e:
        logger.error(f"Unexpected error deleting branch {branch.name}: {str(e)}", exc_info=True)
        messages.error(request, f'An unexpected error occurred while deleting branch "{branch.name}". Please try again or contact support.')
    
    logger.info(f"Redirecting to branch list after delete attempt for branch ID {branch_id}")
    return redirect('branches:branch_list')