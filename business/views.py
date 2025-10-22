from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse
from django.db import models
from django.db.models import Count
from .models import Business, BusinessUserAssignment
from users.models import CustomUser
from branches.models import Branch
from django.views.decorators.http import require_POST
import json

@login_required
def business_list(request):
    """View for listing businesses - accessible by Global Admin and Super Admin"""
    from core.rbac_decorators import require_conditional_access
    
    # RBAC v0.1 Validation: Apply conditional access for business management
    if request.user.role == 'globaladmin':
        pass  # FULL access - no restrictions
    elif request.user.role == 'superadmin':
        # CONDITIONAL access - can only view businesses they're assigned to
        pass  # Validation handled in queryset filtering below
    else:
        return HttpResponseForbidden("You don't have permission to view businesses")

    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Business Management', 'icon': 'fa-building'}
    ]

    # Get base queryset with annotation
    businesses = Business.objects.annotate(
        branches_count=Count('branches'),
        super_admins_count=Count('user_assignments', filter=models.Q(user_assignments__is_active=True))
    ).order_by('name')

    # Filter based on user role
    if request.user.role == 'superadmin':
        # Super admins can only see businesses they're assigned to
        businesses = businesses.filter(
            user_assignments__user=request.user,
            user_assignments__is_active=True
        )
    # Global admins can see all businesses (no filtering needed)

    # Apply search filter
    search_query = request.GET.get('q')
    if search_query:
        businesses = businesses.filter(
            models.Q(name__icontains=search_query) |
            models.Q(description__icontains=search_query)
        )

    # Handle pagination
    per_page = int(request.GET.get('per_page', 10))
    page = request.GET.get('page', 1)
    paginator = Paginator(businesses, per_page)
    
    try:
        businesses = paginator.page(page)
    except PageNotAnInteger:
        businesses = paginator.page(1)
    except EmptyPage:
        businesses = paginator.page(paginator.num_pages)

    context = {
        'businesses': businesses,
        'breadcrumbs': breadcrumbs,
        'search_query': search_query,
        'per_page': per_page,
        'user_role': request.user.role,
    }

    return render(request, 'business/business_list.html', context)

@login_required
def business_create(request):
    """Create a new business - only accessible by Global Admin"""
    if request.user.role != 'globaladmin':
        return HttpResponseForbidden("Only Global Admins can create businesses")

    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('business:business_list'), 'label': 'Business Management', 'icon': 'fa-building'},
        {'label': 'Create Business', 'icon': 'fa-plus'}
    ]

    if request.method == 'POST':
        try:
            # Create business
            business = Business.objects.create(
                name=request.POST.get('name'),
                description=request.POST.get('description', ''),
                address_line1=request.POST.get('address_line1', ''),
                address_line2=request.POST.get('address_line2', ''),
                city=request.POST.get('city', ''),
                state_province=request.POST.get('state_province', ''),
                postal_code=request.POST.get('postal_code', ''),
                country=request.POST.get('country', 'United Kingdom'),
                phone=request.POST.get('phone', ''),
                email=request.POST.get('email', ''),
                website=request.POST.get('website', ''),
                is_active=request.POST.get('is_active') == 'on'
            )

            messages.success(request, f'Business "{business.name}" created successfully!')
            return redirect('business:business_detail', business_id=business.id)

        except Exception as e:
            messages.error(request, f'Error creating business: {str(e)}')

    context = {
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'business/business_create.html', context)

@login_required
def business_detail(request, business_id):
    """View business details - RBAC v0.1 Compliant"""
    from core.rbac_validators import rbac_validator
    
    business = get_object_or_404(Business, id=business_id)
    
    # RBAC v0.1 Validation: Check conditional access to business
    validation_errors = rbac_validator.validate_action(
        user=request.user,
        action='view',
        resource_type='business',
        resource=business
    )
    
    if validation_errors:
        return HttpResponseForbidden(f"Access denied: {'; '.join(validation_errors)}")

    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('business:business_list'), 'label': 'Business Management', 'icon': 'fa-building'},
        {'label': business.name, 'icon': 'fa-eye'}
    ]

    # Get business statistics
    statistics = business.get_business_statistics()
    
    # Get assigned super admins
    super_admins = business.user_assignments.filter(is_active=True).select_related('user', 'assigned_by')
    
    # Get branches
    branches = business.branches.filter(is_active=True).annotate(
        admins_count=Count('users', filter=models.Q(users__role='admin')),
        instructors_count=Count('users', filter=models.Q(users__role='instructor')),
        learners_count=Count('users', filter=models.Q(users__role='learner'))
    )

    # Get available super admin users for assignment (only for Global Admin)
    available_super_admins = []
    if request.user.role == 'globaladmin':
        assigned_user_ids = business.user_assignments.filter(is_active=True).values_list('user_id', flat=True)
        available_super_admins = CustomUser.objects.filter(
            role='superadmin'
        ).exclude(id__in=assigned_user_ids)

    context = {
        'business': business,
        'statistics': statistics,
        'super_admins': super_admins,
        'branches': branches,
        'available_super_admins': available_super_admins,
        'breadcrumbs': breadcrumbs,
        'user_role': request.user.role,
    }

    return render(request, 'business/business_detail.html', context)

@login_required
def business_edit(request, business_id):
    """Edit business details - RBAC v0.1 Compliant"""
    from core.rbac_validators import rbac_validator
    
    business = get_object_or_404(Business, id=business_id)
    
    # RBAC v0.1 Validation: Check conditional access to edit business
    validation_errors = rbac_validator.validate_action(
        user=request.user,
        action='edit',
        resource_type='business',
        resource=business
    )
    
    if validation_errors:
        return HttpResponseForbidden(f"Access denied: {'; '.join(validation_errors)}")

    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('business:business_list'), 'label': 'Business Management', 'icon': 'fa-building'},
        {'url': reverse('business:business_detail', kwargs={'business_id': business.id}), 'label': business.name},
        {'label': 'Edit', 'icon': 'fa-edit'}
    ]

    if request.method == 'POST':
        try:
            # Update business
            business.name = request.POST.get('name', business.name)
            business.description = request.POST.get('description', business.description)
            business.address_line1 = request.POST.get('address_line1', business.address_line1)
            business.address_line2 = request.POST.get('address_line2', business.address_line2)
            business.city = request.POST.get('city', business.city)
            business.state_province = request.POST.get('state_province', business.state_province)
            business.postal_code = request.POST.get('postal_code', business.postal_code)
            business.country = request.POST.get('country', business.country)
            business.phone = request.POST.get('phone', business.phone)
            business.email = request.POST.get('email', business.email)
            business.website = request.POST.get('website', business.website)
            business.is_active = request.POST.get('is_active') == 'on'
            
            business.save()

            messages.success(request, f'Business "{business.name}" updated successfully!')
            return redirect('business:business_detail', business_id=business.id)

        except Exception as e:
            messages.error(request, f'Error updating business: {str(e)}')

    context = {
        'business': business,
        'breadcrumbs': breadcrumbs,
    }

    return render(request, 'business/business_edit.html', context)

@login_required
def business_delete(request, business_id):
    """Delete a business - only accessible by Global Admin"""
    if request.user.role != 'globaladmin':
        return HttpResponseForbidden("Only Global Admins can delete businesses")

    business = get_object_or_404(Business, id=business_id)

    if request.method == 'POST':
        try:
            business_name = business.name
            business.delete()
            messages.success(request, f'Business "{business_name}" deleted successfully!')
            return redirect('business:business_list')
        except Exception as e:
            messages.error(request, f'Error deleting business: {str(e)}')
            return redirect('business:business_detail', business_id=business.id)

    return redirect('business:business_detail', business_id=business.id)

@login_required
@require_POST
def assign_user_to_business(request, business_id):
    """Assign a Super Admin user to a business"""
    if request.user.role != 'globaladmin':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Only Global Admins can assign users to businesses'})
        else:
            messages.error(request, 'Only Global Admins can assign users to businesses')
            return redirect('business:business_detail', business_id=business_id)

    business = get_object_or_404(Business, id=business_id)
    
    try:
        user_id = request.POST.get('user_id')
        user = get_object_or_404(CustomUser, id=user_id, role='superadmin')
        
        # Check if assignment already exists
        assignment, created = BusinessUserAssignment.objects.get_or_create(
            business=business,
            user=user,
            defaults={'assigned_by': request.user, 'is_active': True}
        )
        
        if created:
            messages.success(request, f'Super Admin "{user.get_full_name() or user.username}" assigned to business "{business.name}" successfully!')
            success_message = 'User assigned successfully'
        elif assignment.is_active:
            messages.warning(request, 'User is already assigned to this business')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'User is already assigned to this business'})
            else:
                return redirect('business:business_edit', business_id=business_id)
        else:
            assignment.is_active = True
            assignment.assigned_by = request.user
            assignment.save()
            messages.success(request, f'Super Admin "{user.get_full_name() or user.username}" re-assigned to business "{business.name}" successfully!')
            success_message = 'User re-assigned successfully'
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': success_message})
        else:
            # For regular form submissions, redirect to the business edit page
            return redirect('business:business_edit', business_id=business_id)
                
    except Exception as e:
        error_message = f'Error assigning user: {str(e)}'
        messages.error(request, error_message)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        else:
            return redirect('business:business_edit', business_id=business_id)

@login_required
@require_POST
def unassign_user_from_business(request, business_id, user_id):
    """Unassign a Super Admin user from a business"""
    if request.user.role != 'globaladmin':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Only Global Admins can unassign users from businesses'})
        else:
            messages.error(request, 'Only Global Admins can unassign users from businesses')
            return redirect('business:business_detail', business_id=business_id)

    business = get_object_or_404(Business, id=business_id)
    user = get_object_or_404(CustomUser, id=user_id)
    
    try:
        assignment = get_object_or_404(
            BusinessUserAssignment,
            business=business,
            user=user,
            is_active=True
        )
        
        assignment.is_active = False
        assignment.save()
        
        messages.success(request, f'Super Admin "{user.get_full_name() or user.username}" unassigned from business "{business.name}" successfully!')
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'User unassigned successfully'})
        else:
            # For regular form submissions, redirect to the business edit page
            return redirect('business:business_edit', business_id=business_id)
        
    except Exception as e:
        error_message = f'Error unassigning user: {str(e)}'
        messages.error(request, error_message)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': error_message})
        else:
            return redirect('business:business_edit', business_id=business_id)
