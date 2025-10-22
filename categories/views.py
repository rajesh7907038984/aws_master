from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from .models import CourseCategory
from .forms import CourseCategoryForm
from role_management.utils import require_capability, PermissionManager

# Create your views here.

@login_required
@require_capability('view_categories')
def category_list(request):
    # Apply business/branch filtering based on user capabilities
    if PermissionManager.user_has_capability(request.user, 'manage_categories') and (request.user.is_superuser or request.user.role == 'globaladmin'):
        categories = CourseCategory.objects.all()
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped categories)
        from core.utils.business_filtering import filter_queryset_by_business
        categories = filter_queryset_by_business(
            CourseCategory.objects.all(), 
            request.user, 
            business_field_path='branch__business'
        )
    elif request.user.branch:
        # Branch-level users (admin, instructor) see categories in their branch
        categories = CourseCategory.objects.filter(branch=request.user.branch)
    else:
        # For other roles, return empty queryset for Session
        categories = CourseCategory.objects.none()
    
    paginator = Paginator(categories, 10)  # Show 10 categories per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Categories', 'icon': 'fa-tags'}
    ]
    
    context = {
        'categories': page_obj,
        'total_categories': categories.count(),
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'categories/category_list.html', context)

@login_required
def check_slug_exists(request):
    """
    Check if a slug already exists in the database.
    Used for AJAX validation in the category creation form.
    """
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        slug = request.GET.get('slug', '').strip()
        exists = CourseCategory.objects.filter(slug=slug).exists()
        return JsonResponse({'exists': exists})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def category_create(request):
    # Check if user has permission to create categories
    # Allow instructors, admins, and superusers to create categories
    if not (request.user.is_superuser or 
            request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor'] or
            PermissionManager.user_has_capability(request.user, 'create_categories')):
        messages.error(request, 'You do not have permission to create categories')
        return redirect('categories:category_list')
    if request.method == 'POST':
        form = CourseCategoryForm(request.POST)
        if form.is_valid():
            # Create the category but don't save yet
            category = form.save(commit=False)
            
            # Assign branch based on user role (consistent with ajax_category_create)
            if request.user.role == 'globaladmin' or request.user.is_superuser:
                # Global admin and superuser can create categories without branch restrictions
                category.branch = None
            elif request.user.role == 'superadmin':
                # Superadmin can create categories with optional branch assignment
                category.branch = request.user.branch if hasattr(request.user, 'branch') else None
            elif request.user.role in ['admin', 'instructor']:
                # Branch-level users must create categories for their branch
                category.branch = request.user.branch
            
            # Now save the category
            category.save()
            
            # Check if this is an AJAX request
            if request.POST.get('is_ajax') == '1':
                return JsonResponse({
                    'status': 'success',
                    'id': category.id,
                    'name': category.name,
                    'description': category.description,
                    'slug': category.slug
                })
            
            messages.success(request, 'Category created successfully.')
            return redirect('categories:category_list')
        elif request.POST.get('is_ajax') == '1':
            # Return form errors as JSON
            errors = form.errors.as_json()
            return JsonResponse({
                'status': 'error',
                'message': 'Form validation error',
                'errors': errors
            }, status=400)
    else:
        form = CourseCategoryForm()
    
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/categories/', 'label': 'Categories', 'icon': 'fa-tags'},
        {'label': 'Create Category', 'icon': 'fa-plus'}
    ]
    
    return render(request, 'categories/category_form.html', {
        'form': form,
        'breadcrumbs': breadcrumbs
    })

@login_required
@require_capability('manage_categories')
def category_edit(request, pk):
    category = get_object_or_404(CourseCategory, pk=pk)
    if request.method == 'POST':
        form = CourseCategoryForm(request.POST, instance=category)
        if form.is_valid():
            # Let the model's save() method handle slug uniqueness
            updated_category = form.save()
            messages.success(request, 'Category updated successfully.')
            return redirect('categories:category_list')
    else:
        form = CourseCategoryForm(instance=category)
    
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/categories/', 'label': 'Categories', 'icon': 'fa-tags'},
        {'label': f'Edit {category.name}', 'icon': 'fa-edit'}
    ]
    
    return render(request, 'categories/category_form.html', {
        'form': form,
        'category': category,
        'breadcrumbs': breadcrumbs
    })

@login_required
@require_capability('delete_categories')
def category_delete(request, pk):
    category = get_object_or_404(CourseCategory, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category deleted successfully.')
        return redirect('categories:category_list')
    
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/categories/', 'label': 'Categories', 'icon': 'fa-tags'},
        {'label': f'Delete {category.name}', 'icon': 'fa-trash'}
    ]
    
    return render(request, 'categories/category_confirm_delete.html', {
        'category': category,
        'breadcrumbs': breadcrumbs
    })

@login_required
def ajax_category_create(request):
    """Simple AJAX category creation endpoint"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST requests allowed'}, status=405)
    
    # Check permissions
    if not (request.user.is_superuser or 
            request.user.role in ['globaladmin', 'superadmin', 'admin', 'instructor']):
        return JsonResponse({
            'status': 'error',
            'message': 'Permission denied'
        }, status=403)
    
    # Get form data
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    
    if not name:
        return JsonResponse({
            'status': 'error',
            'message': 'Category name is required'
        }, status=400)
    
    try:
        # Create category
        category = CourseCategory.objects.create(
            name=name,
            description=description,
            is_active=True,
            branch=request.user.branch if hasattr(request.user, 'branch') else None
        )
        
        return JsonResponse({
            'status': 'success',
            'id': category.id,
            'name': category.name,
            'slug': category.slug
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error creating category: {str(e)}'
        }, status=500)


@login_required
@require_capability('view_categories')
def category_api_list(request):
    """API endpoint to list categories for frontend JavaScript"""
    try:
        # Apply same business/branch filtering as the main category_list view
        if PermissionManager.user_has_capability(request.user, 'manage_categories') and (request.user.is_superuser or request.user.role == 'globaladmin'):
            categories = CourseCategory.objects.all()
        elif request.user.role == 'superadmin':
            # Super Admin: CONDITIONAL access (business-scoped categories)
            from core.utils.business_filtering import filter_queryset_by_business
            categories = filter_queryset_by_business(
                CourseCategory.objects.all(), 
                request.user, 
                business_field_path='branch__business'
            )
        elif request.user.branch:
            # Branch-level users see categories in their branch
            categories = CourseCategory.objects.filter(branch=request.user.branch)
        else:
            # For other roles, return empty queryset for Session
            categories = CourseCategory.objects.none()
        
        # Convert to list with id and name
        categories_data = []
        for category in categories.filter(is_active=True).order_by('name'):
            categories_data.append({
                'id': category.id,
                'name': category.name
            })
        
        return JsonResponse({
            'status': 'success',
            'categories': categories_data
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'categories': []
        }, status=500)
