from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.db.models import Q, Count, Sum, F, ExpressionWrapper, DecimalField
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import json
from decimal import Decimal

from branches.models import Branch
from courses.models import Course
from categories.models import CourseCategory
from .models import (
    BranchPortal, Cart, CartItem, Order, OrderItem,
    MainContentSection, FeatureGridSection, FeatureGridItem,
    PreFooterSection, CustomMenuLink, SocialMediaIcon
)
from users.views import get_or_assign_branch_for_global_admin

def marketing_landing_page(request):
    """Display the marketing landing page (without authentication)"""
    # Get featured courses
    featured_courses = Course.objects.filter(
        is_active=True,
        catalog_visibility='visible'
    ).order_by('-created_at')[:3]
    
    # Ensure price is a Decimal for each course
    for course in featured_courses:
        course.price = Decimal(str(course.price)) if course.price else Decimal('0.00')
        
        # Calculate discounted price if applicable
        if course.discount_percentage > 0:
            discount_factor = Decimal(1) - (Decimal(course.discount_percentage) / Decimal(100))
            course.discounted_price = (course.price * discount_factor).quantize(Decimal('0.01'))
        else:
            course.discounted_price = course.price
    
    context = {
        'featured_courses': featured_courses,
    }
    
    return render(request, 'branch_portal/landing_page.html', context)

def portal_landing(request, slug):
    """Display the branch landing page"""
    portal = get_object_or_404(BranchPortal, slug=slug, is_active=True)
    branch = portal.branch
    
    # Check if order management is enabled for this branch
    order_management_enabled = getattr(branch, 'order_management_enabled', False)
    
    # Check global order management settings
    from account_settings.models import GlobalAdminSettings
    global_settings = GlobalAdminSettings.get_settings()
    order_management_globally_enabled = global_settings.order_management_enabled if global_settings else False
    
    # Get branch courses - ensure we include courses with price or discount_percentage
    courses = Course.objects.filter(
        branch=branch,
        is_active=True,
        catalog_visibility='visible'
    ).order_by('-created_at')
    
    # Calculate discounted prices for courses with discounts
    for course in courses:
        # Ensure price is a Decimal type for proper comparison
        course.price = Decimal(str(course.price)) if course.price else Decimal('0.00')
        
        if course.discount_percentage > 0:
            discount_factor = Decimal(1) - (Decimal(course.discount_percentage) / Decimal(100))
            course.discounted_price = (course.price * discount_factor).quantize(Decimal('0.01'))
        else:
            course.discounted_price = course.price
    
    # Get categories for branch courses
    categories = CourseCategory.objects.filter(
        courses__branch=branch,
        courses__is_active=True,
        courses__catalog_visibility='visible',
        is_active=True
    ).distinct().annotate(course_count=Count('courses'))
    
    # Get portal sections
    main_content_sections = MainContentSection.objects.filter(
        portal=portal,
        is_active=True
    ).order_by('order')
    
    feature_grid_sections = FeatureGridSection.objects.filter(
        portal=portal,
        is_active=True
    ).prefetch_related('items').order_by('order')
    
    # Get pre-footer section
    try:
        pre_footer = PreFooterSection.objects.get(
            portal=portal,
            is_active=True
        )
        pre_footer_menu_links = pre_footer.menu_links.filter(is_active=True).order_by('order')
        pre_footer_social_icons = pre_footer.social_icons.filter(is_active=True).order_by('order')
    except PreFooterSection.DoesNotExist:
        pre_footer = None
        pre_footer_menu_links = []
        pre_footer_social_icons = []
    
    context = {
        'portal': portal,
        'branch': branch,
        'courses': courses,
        'categories': categories,
        'main_content_sections': main_content_sections,
        'feature_grid_sections': feature_grid_sections,
        'pre_footer': pre_footer,
        'pre_footer_menu_links': pre_footer_menu_links,
        'pre_footer_social_icons': pre_footer_social_icons,
        'order_management_enabled': order_management_enabled and order_management_globally_enabled,
        'show_pricing': order_management_enabled and order_management_globally_enabled,
        'show_cart': order_management_enabled and order_management_globally_enabled,
    }
    
    return render(request, 'branch_portal/landing_page.html', context)

@login_required
def manage_portal(request, branch_id=None):
    """Portal management page for superadmins and global admins"""
    # Check if user has permission to manage portal - ONLY Super Admin and Global Admin
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to manage this portal")
    
    # Super Admins need access to business-scoped branches, Global Admins have full access
    # Branch Admins are no longer allowed to manage portals
    
    # If a specific branch_id is provided, use that branch (with permission validation)
    if branch_id:
        try:
            target_branch = Branch.objects.get(id=branch_id)
            
            # Validate permissions for the target branch
            if request.user.is_superuser or request.user.role == 'globaladmin':
                # Global admin can access any branch
                branch = target_branch
            elif request.user.role == 'superadmin':
                # Super Admin: Validate the target branch is within their business scope
                from core.utils.business_filtering import filter_branches_by_business
                accessible_branches = filter_branches_by_business(request.user)
                
                if target_branch in accessible_branches:
                    branch = target_branch
                else:
                    messages.error(request, f"You don't have access to manage the portal for '{target_branch.name}'. You can only manage portals for branches within your assigned businesses.")
                    return redirect('branch_portal:branch_dashboard')
            else:
                # Other roles don't have portal management access
                return HttpResponseForbidden("You don't have permission to manage this portal")
                
        except Branch.DoesNotExist:
            messages.error(request, "The specified branch does not exist")
            return redirect('branch_portal:branch_dashboard')
    else:
        # No specific branch provided, use existing logic for default branch selection
        if request.user.is_superuser or request.user.role == 'globaladmin':
            if not request.user.branch:
                # For global admin, use the branch assignment utility
                branch = get_or_assign_branch_for_global_admin(request)
                if not branch:
                    messages.error(request, "No branches exist in the system")
                    return redirect('users:role_based_redirect')
            else:
                branch = request.user.branch
        elif request.user.role == 'superadmin':
            # Super Admin: CONDITIONAL access (business-scoped branches only)
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            
            if not request.user.branch:
                # If super admin has no assigned branch, use the first accessible branch
                if accessible_branches.exists():
                    branch = accessible_branches.first()
                else:
                    messages.error(request, "You don't have access to any branches within your assigned businesses")
                    return redirect('users:role_based_redirect')
            else:
                # Validate that their assigned branch is within their business scope
                if request.user.branch in accessible_branches:
                    branch = request.user.branch
                else:
                    messages.error(request, f"You don't have access to your assigned branch. You can only access branches within your assigned businesses.")
                    # Use the first accessible branch instead
                    if accessible_branches.exists():
                        branch = accessible_branches.first()
                    else:
                        return redirect('users:role_based_redirect')
        else:
            branch = request.user.branch
    
    # Get or create portal for user's branch
    portal, created = BranchPortal.objects.get_or_create(
        branch=branch,
        defaults={'business_name': branch.name}
    )
    
    # Get branch courses
    courses = Course.objects.filter(
        branch=branch,
        is_active=True
    ).order_by('-created_at')
    
    # Ensure price is a Decimal for each course
    for course in courses:
        course.price = Decimal(str(course.price)) if course.price else Decimal('0.00')
    
    # Get categories for branch courses
    categories = CourseCategory.objects.filter(
        courses__branch=branch,
        courses__is_active=True,
        is_active=True
    ).distinct().annotate(course_count=Count('courses'))
    
    # Define breadcrumbs for this view
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Portal Management', 'icon': 'fa-globe'}
    ]
    
    context = {
        'portal': portal,
        'branch': branch,
        'courses': courses,
        'categories': categories,
        'breadcrumbs': breadcrumbs,
        'active_tab': 'portal',
    }
    
    return render(request, 'branch_portal/manage_portal.html', context)

@login_required
@require_POST
def update_portal(request):
    """Update branch portal settings"""
    # Check if user is a superadmin or global admin - ONLY Super Admin and Global Admin
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to update this portal")
    
    # Get the target branch based on user role and permissions
    if request.user.is_superuser or request.user.role == 'globaladmin':
        # Global admin can update any branch portal
        branch_id = request.POST.get('branch_id')
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id)
        elif request.user.branch:
            branch = request.user.branch
        else:
            branch = Branch.objects.first()
            if not branch:
                return JsonResponse({'success': False, 'message': "No branches exist in the system"})
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped branches only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        
        branch_id = request.POST.get('branch_id')
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id)
            # Validate that the target branch is within their assigned businesses
            if branch not in accessible_branches:
                return JsonResponse({
                    'success': False, 
                    'message': f"Access denied: You can only manage portals for branches within your assigned businesses"
                })
        elif request.user.branch:
            # Validate that their assigned branch is within their business scope
            if request.user.branch in accessible_branches:
                branch = request.user.branch
            else:
                return JsonResponse({
                    'success': False, 
                    'message': "Access denied: Your assigned branch is not within your business scope"
                })
        else:
            # Use the first accessible branch
            if accessible_branches.exists():
                branch = accessible_branches.first()
            else:
                return JsonResponse({
                    'success': False, 
                    'message': "You don't have access to any branches within your assigned businesses"
                })
    else:
        # This should not be reached as only superadmin and globaladmin are allowed
        return JsonResponse({'success': False, 'message': "Invalid role for portal management"})
    
    # Get portal for branch
    portal = get_object_or_404(BranchPortal, branch=branch)
    
    # Update basic information
    portal.business_name = request.POST.get('business_name', portal.business_name)
    portal.slug = request.POST.get('slug', portal.slug)
    
    # Update contact information
    portal.address_line1 = request.POST.get('address_line1', portal.address_line1)
    portal.address_line2 = request.POST.get('address_line2', portal.address_line2)
    portal.city = request.POST.get('city', portal.city)
    portal.state_province = request.POST.get('state_province', portal.state_province)
    portal.postal_code = request.POST.get('postal_code', portal.postal_code)
    portal.country = request.POST.get('country', portal.country)
    portal.phone = request.POST.get('phone', portal.phone)
    portal.email = request.POST.get('email', portal.email)
    
    # Update theme settings
    portal.primary_color = request.POST.get('primary_color', portal.primary_color)
    portal.secondary_color = request.POST.get('secondary_color', portal.secondary_color)
    portal.font_family = request.POST.get('font_family', portal.font_family)
    
    # Update content
    portal.welcome_message = request.POST.get('welcome_message', portal.welcome_message)
    portal.about_text = request.POST.get('about_text', portal.about_text)
    portal.banner_text = request.POST.get('banner_text', portal.banner_text)
    
    # Update social media links
    portal.facebook_url = request.POST.get('facebook_url', portal.facebook_url)
    portal.twitter_url = request.POST.get('twitter_url', portal.twitter_url)
    portal.instagram_url = request.POST.get('instagram_url', portal.instagram_url)
    portal.linkedin_url = request.POST.get('linkedin_url', portal.linkedin_url)
    
    # Handle file uploads
    if 'logo' in request.FILES:
        portal.logo = request.FILES['logo']
    
    if 'banner_image' in request.FILES:
        portal.banner_image = request.FILES['banner_image']
    
    portal.save()
    
    messages.success(request, "Portal settings updated successfully")
    
    # Redirect back to the specific branch management page
    # Use the branch.id since the branch object has already been validated
    return redirect('branch_portal:manage_portal_for_branch', branch_id=branch.id)

@login_required
def add_to_cart(request, course_id):
    """Add a course to the cart"""
    course = get_object_or_404(Course, id=course_id, is_active=True)
    
    # Check if order management is enabled for the course's branch
    if course.branch:
        branch_order_enabled = getattr(course.branch, 'order_management_enabled', False)
        from account_settings.models import GlobalAdminSettings
        global_settings = GlobalAdminSettings.get_settings()
        global_order_enabled = global_settings.order_management_enabled if global_settings else False
        
        if not (branch_order_enabled and global_order_enabled):
            messages.error(request, "Order management is not enabled for this course.")
            return redirect('branch_portal:portal_landing', slug=course.branch.portal.slug if hasattr(course.branch, 'portal') else 'default')
    
    # Get or create user's cart
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    # Add course to cart
    cart_item = cart.add_item(course)
    
    messages.success(request, f"{course.title} added to your cart")
    
    # Always redirect to cart page
    return redirect('branch_portal:view_cart')

@login_required
def remove_from_cart(request, course_id):
    """Remove a course from the cart"""
    course = get_object_or_404(Course, id=course_id)
    
    # Get user's cart
    try:
        cart = Cart.objects.get(user=request.user)
        removed = cart.remove_item(course)
        
        if removed:
            messages.success(request, f"{course.title} removed from your cart")
        else:
            messages.warning(request, f"{course.title} is not in your cart")
    except Cart.DoesNotExist:
        messages.warning(request, "Your cart is empty")
    
    # Return to cart
    return redirect('branch_portal:view_cart')

@login_required
def view_cart(request):
    """Display the user's cart"""
    # Check global order management settings
    from account_settings.models import GlobalAdminSettings
    global_settings = GlobalAdminSettings.get_settings()
    global_order_enabled = global_settings.order_management_enabled if global_settings else False
    
    if not global_order_enabled:
        messages.error(request, "Order management is currently disabled.")
        return redirect('users:role_based_redirect')
    
    # Get or create user's cart
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    # Get cart items with related courses
    cart_items = cart.items.all().select_related('course')
    
    # Get portal data for header/footer (similar to landing page)
    try:
        portal = BranchPortal.objects.first()
    except BranchPortal.DoesNotExist:
        portal = None
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Shopping Cart', 'icon': 'fa-shopping-cart'}
    ]
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
        'breadcrumbs': breadcrumbs,
        'portal': portal,  # Add portal data for header
    }
    
    return render(request, 'branch_portal/cart.html', context)

@login_required
def clear_cart(request):
    """Clear all items from the cart"""
    # Get user's cart
    try:
        cart = Cart.objects.get(user=request.user)
        cart.clear()
        messages.success(request, "Your cart has been cleared")
    except Cart.DoesNotExist:
        messages.warning(request, "Your cart is already empty")
    
    # Return to cart
    return redirect('branch_portal:view_cart')

@login_required
def checkout(request, branch_id):
    """Checkout process for the cart"""
    branch = get_object_or_404(Branch, id=branch_id)
    
    # Check if order management is enabled for this branch
    branch_order_enabled = getattr(branch, 'order_management_enabled', False)
    from account_settings.models import GlobalAdminSettings
    global_settings = GlobalAdminSettings.get_settings()
    global_order_enabled = global_settings.order_management_enabled if global_settings else False
    
    if not (branch_order_enabled and global_order_enabled):
        messages.error(request, "Order management is not enabled for this branch.")
        return redirect('users:role_based_redirect')
    
    # Get user's cart
    try:
        cart = Cart.objects.get(user=request.user)
        
        # Check if cart is empty
        if not cart.items.exists():
            messages.warning(request, "Your cart is empty")
            return redirect('branch_portal:view_cart')
        
        # Handle form submission
        if request.method == 'POST':
            # Create order from cart
            order = cart.create_order(branch)
            
            # Add any notes from the user
            if 'user_notes' in request.POST:
                order.user_notes = request.POST['user_notes']
                order.save()
            
            messages.success(request, f"Your order has been submitted. Order number: {order.order_number}")
            return redirect('branch_portal:order_success', order_number=order.order_number)
    
    except Cart.DoesNotExist:
        messages.warning(request, "Your cart is empty")
        return redirect('branch_portal:view_cart')
    
    # Get portal data for header/footer (similar to landing page)
    try:
        portal = BranchPortal.objects.first()
    except BranchPortal.DoesNotExist:
        portal = None
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('branch_portal:view_cart'), 'label': 'Shopping Cart', 'icon': 'fa-shopping-cart'},
        {'label': 'Checkout', 'icon': 'fa-credit-card'}
    ]
    
    context = {
        'cart': cart,
        'branch': branch,
        'breadcrumbs': breadcrumbs,
        'portal': portal,  # Add portal data for header
    }
    
    return render(request, 'branch_portal/checkout.html', context)

@login_required
def order_success(request, order_number):
    """Display order success page"""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    # Get portal data for header/footer (similar to landing page)
    try:
        portal = BranchPortal.objects.first()
    except BranchPortal.DoesNotExist:
        portal = None
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('branch_portal:view_cart'), 'label': 'Shopping Cart', 'icon': 'fa-shopping-cart'},
        {'label': 'Order Success', 'icon': 'fa-check-circle'}
    ]
    
    context = {
        'order': order,
        'breadcrumbs': breadcrumbs,
        'portal': portal,  # Add portal data for header
    }
    
    return render(request, 'branch_portal/order_success.html', context)

@login_required
def branch_orders(request):
    """Display orders for a branch admin, superadmin, or globaladmin"""
    # Check if user has permission to view orders
    if request.user.role not in ['globaladmin', 'superadmin', 'admin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to view orders")
    
    # Check if order management is enabled globally
    from account_settings.models import GlobalAdminSettings
    try:
        global_settings = GlobalAdminSettings.get_settings()
        global_order_management_enabled = global_settings.order_management_enabled if global_settings else False
    except:
        global_order_management_enabled = False
    
    if not global_order_management_enabled:
        messages.error(request, "Order management is currently disabled system-wide. Please contact your administrator.")
        return redirect('branch_portal:branch_dashboard')
    
    user_branch = None
    # Get branch filter with proper business scoping for Super Admin
    if request.user.is_superuser or request.user.role == 'globaladmin':
        # Global admin can see all orders or filter by branch
        branch_id = request.GET.get('branch')
        if branch_id:
            orders = Order.objects.filter(branch_id=branch_id)
            user_branch = get_object_or_404(Branch, id=branch_id)
        else:
            # For global admin, if no specific branch is requested, use their utility function
            default_branch = get_or_assign_branch_for_global_admin(request)
            if default_branch:
                orders = Order.objects.filter(branch=default_branch)
                user_branch = default_branch
            else:
                orders = Order.objects.all()
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped orders only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        
        branch_id = request.GET.get('branch')
        if branch_id:
            # Validate that the requested branch is within their assigned businesses
            user_branch = get_object_or_404(Branch, id=branch_id)
            if user_branch not in accessible_branches:
                messages.error(request, f"You don't have access to orders for branch '{user_branch.name}'. You can only access branches within your assigned businesses.")
                return redirect('branch_portal:branch_orders')
            
            # Check if order management is enabled for this branch
            branch_order_management_enabled = getattr(user_branch, 'order_management_enabled', False)
            if not branch_order_management_enabled:
                messages.error(request, f"Order management is not enabled for branch '{user_branch.name}'. Please contact your administrator.")
                return redirect('branch_portal:branch_orders')
            
            orders = Order.objects.filter(branch=user_branch)
        else:
            # Show orders from all branches within their assigned businesses that have order management enabled
            enabled_branches = accessible_branches.filter(order_management_enabled=True)
            orders = Order.objects.filter(branch__in=enabled_branches)
    else:
        # Branch admin can only see orders for their branch
        if not request.user.branch:
            messages.error(request, "You need to be assigned to a branch to view orders")
            return redirect('users:role_based_redirect')
        
        user_branch = request.user.branch
        
        # Check if order management is enabled for this branch
        branch_order_management_enabled = getattr(user_branch, 'order_management_enabled', False)
        if not branch_order_management_enabled:
            messages.error(request, f"Order management is not enabled for your branch '{user_branch.name}'. Please contact your administrator.")
            return redirect('branch_portal:branch_dashboard')
        
        orders = Order.objects.filter(branch=user_branch)
    
    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    payment_status_filter = request.GET.get('payment_status')
    if payment_status_filter:
        orders = orders.filter(payment_status=payment_status_filter)
    
    search_query = request.GET.get('q')
    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    # Sort orders
    sort_by = request.GET.get('sort', '-created_at')
    orders = orders.order_by(sort_by)
    
    # Paginate results
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get branch list for superadmin filter with business scoping
    branches = None
    if request.user.is_superuser or request.user.role == 'globaladmin':
        branches = Branch.objects.all()
    elif request.user.role == 'superadmin':
        # Super Admin: Show only branches within their assigned businesses
        from core.utils.business_filtering import filter_branches_by_business
        branches = filter_branches_by_business(request.user)
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Orders', 'icon': 'fa-shopping-bag'}
    ]
    
    context = {
        'orders': page_obj,
        'branches': branches,
        'user_branch': user_branch,
        'status_filter': status_filter,
        'payment_status_filter': payment_status_filter,
        'search_query': search_query,
        'sort_by': sort_by,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'branch_portal/branch_orders.html', context)

@login_required
def order_detail(request, order_number):
    """Display order details"""
    # Check if order management is enabled globally
    from account_settings.models import GlobalAdminSettings
    try:
        global_settings = GlobalAdminSettings.get_settings()
        global_order_management_enabled = global_settings.order_management_enabled if global_settings else False
    except:
        global_order_management_enabled = False
    
    if not global_order_management_enabled and request.user.role in ['globaladmin', 'superadmin', 'admin']:
        messages.error(request, "Order management is currently disabled system-wide. Please contact your administrator.")
        return redirect('branch_portal:branch_dashboard')
    
    # Check permissions with proper business scoping for Super Admin
    if request.user.is_superuser or request.user.role == 'globaladmin':
        order = get_object_or_404(Order, order_number=order_number)
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped orders only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        order = get_object_or_404(Order, order_number=order_number, branch__in=accessible_branches)
    elif request.user.role == 'admin':
        # Branch admin can only see orders for their branch
        if not request.user.branch:
            messages.error(request, "You need to be assigned to a branch to view orders")
            return redirect('users:role_based_redirect')
        
        # Check if order management is enabled for this branch
        branch_order_management_enabled = getattr(request.user.branch, 'order_management_enabled', False)
        if not branch_order_management_enabled:
            messages.error(request, f"Order management is not enabled for your branch '{request.user.branch.name}'. Please contact your administrator.")
            return redirect('branch_portal:branch_dashboard')
        
        order = get_object_or_404(Order, order_number=order_number, branch=request.user.branch)
    else:
        # Regular users can only see their own orders
        order = get_object_or_404(Order, order_number=order_number, user=request.user)
    
    # Get order items with related courses
    order_items = order.items.all().select_related('course')
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': reverse('branch_portal:branch_orders'), 'label': 'Orders', 'icon': 'fa-shopping-bag'},
        {'label': f'Order #{order.order_number}', 'icon': 'fa-file-invoice'}
    ]
    
    context = {
        'order': order,
        'order_items': order_items,
        'breadcrumbs': breadcrumbs,
    }
    
    return render(request, 'branch_portal/order_detail.html', context)

@login_required
@require_POST
def update_order_status(request, order_number):
    """Update order status"""
    # Check permissions with proper business scoping for Super Admin
    if request.user.is_superuser or request.user.role == 'globaladmin':
        order = get_object_or_404(Order, order_number=order_number)
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped orders only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        order = get_object_or_404(Order, order_number=order_number, branch__in=accessible_branches)
    elif request.user.role == 'admin':
        # Branch admin can only update orders for their branch
        if not request.user.branch:
            return JsonResponse({'success': False, 'message': "You need to be assigned to a branch"})
        
        order = get_object_or_404(Order, order_number=order_number, branch=request.user.branch)
    else:
        return HttpResponseForbidden("You don't have permission to update this order")
    
    # Update status
    new_status = request.POST.get('status')
    if new_status in dict(Order.ORDER_STATUS_CHOICES):
        order.status = new_status
        
        # If marking as completed, also update completed_at
        if new_status == 'completed' and not order.completed_at:
            order.completed_at = timezone.now()
            
            # Also process course enrollments
            order.mark_as_completed()
        
        order.save()
        
        # Add admin note if provided
        admin_note = request.POST.get('admin_note')
        if admin_note:
            if order.admin_notes:
                order.admin_notes += f"\n\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {admin_note}"
            else:
                order.admin_notes = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {admin_note}"
            order.save()
        
        messages.success(request, f"Order status updated to {dict(Order.ORDER_STATUS_CHOICES)[new_status]}")
    else:
        messages.error(request, "Invalid status")
    
    return redirect('branch_portal:order_detail', order_number=order_number)

@login_required
@require_POST
def delete_order(request, order_number):
    """Delete an order"""
    # Check permissions with proper business scoping for Super Admin
    if request.user.is_superuser or request.user.role == 'globaladmin':
        order = get_object_or_404(Order, order_number=order_number)
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped orders only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        order = get_object_or_404(Order, order_number=order_number, branch__in=accessible_branches)
    elif request.user.role == 'admin':
        # Branch admin can only delete orders for their branch
        if not request.user.branch:
            messages.error(request, "You need to be assigned to a branch")
            return redirect('branch_portal:branch_orders')
        
        order = get_object_or_404(Order, order_number=order_number, branch=request.user.branch)
    else:
        return HttpResponseForbidden("You don't have permission to delete this order")
    
    # Only allow deletion of pending, rejected, or cancelled orders
    if order.status not in ['pending', 'rejected', 'cancelled']:
        messages.error(request, f"Cannot delete order with status '{order.get_status_display()}'. Only pending, rejected, or cancelled orders can be deleted.")
        return redirect('branch_portal:order_detail', order_number=order_number)
    
    # Store order number for success message
    order_num = order.order_number
    
    # Delete the order
    order.delete()
    
    messages.success(request, f"Order #{order_num} has been successfully deleted.")
    return redirect('branch_portal:branch_orders')

@login_required
@require_POST
def delete_pending_orders(request):
    """Delete all pending orders for a branch"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin', 'admin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to delete orders")
    
    # Get branch ID from request
    branch_id = request.POST.get('branch_id')
    if not branch_id:
        messages.error(request, "Branch ID is required")
        return redirect('branch_portal:branch_dashboard')
    
    # Get branch and verify permissions with proper business scoping for Super Admin
    if request.user.is_superuser or request.user.role == 'globaladmin':
        branch = get_object_or_404(Branch, id=branch_id)
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped branches only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        branch = get_object_or_404(Branch, id=branch_id)
        if branch not in accessible_branches:
            messages.error(request, f"You can only delete orders for branches within your assigned businesses")
            return redirect('branch_portal:branch_dashboard')
    elif request.user.role == 'admin':
        # Branch admin can only delete orders for their branch
        if not request.user.branch or str(request.user.branch.id) != branch_id:
            messages.error(request, "You can only delete orders for your assigned branch")
            return redirect('branch_portal:branch_dashboard')
        branch = request.user.branch
    else:
        return HttpResponseForbidden("You don't have permission to delete orders")
    
    # Delete all pending orders for the branch
    pending_orders = Order.objects.filter(branch=branch, status='pending')
    deleted_count = pending_orders.count()
    
    if deleted_count > 0:
        pending_orders.delete()
        messages.success(request, f"Successfully deleted {deleted_count} pending order(s) for {branch.name}.")
    else:
        messages.info(request, f"No pending orders found for {branch.name}.")
    
    return redirect('branch_portal:branch_dashboard')

@login_required
def branch_dashboard(request):
    """Display branch dashboard with portal and order stats"""
    # Check if user has permission to access this dashboard
    if request.user.role not in ['globaladmin', 'superadmin', 'admin'] and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to access this dashboard")
    
    # Get business and branch filters with proper business scoping
    if request.user.is_superuser or request.user.role == 'globaladmin':
        # Global admin can see all branches, with optional business/branch filtering
        business_id = request.GET.get('business')
        branch_id = request.GET.get('branch')
        
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id)
            branches = [branch]
        elif business_id:
            # Filter by business
            from business.models import Business
            business = get_object_or_404(Business, id=business_id)
            branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
        else:
            # For global admin, show ALL branches by default for comprehensive portal view
            branches = Branch.objects.filter(is_active=True).order_by('name')
    elif request.user.role == 'superadmin':
        # Super Admin: CONDITIONAL access (business-scoped branches only)
        from core.utils.business_filtering import filter_branches_by_business
        accessible_branches = filter_branches_by_business(request.user)
        
        branch_id = request.GET.get('branch')
        if branch_id:
            # Validate that the requested branch is within their assigned businesses
            branch = get_object_or_404(Branch, id=branch_id)
            if branch not in accessible_branches:
                messages.error(request, f"You don't have access to branch '{branch.name}'. You can only access branches within your assigned businesses.")
                return redirect('branch_portal:branch_dashboard')
            branches = [branch]
        else:
            # Show all branches within their assigned businesses
            branches = list(accessible_branches)
    else:
        # Branch admin can only see their branch
        if not request.user.branch:
            messages.error(request, "You need to be assigned to a branch to view the dashboard")
            return redirect('users:role_based_redirect')
        
        branches = [request.user.branch]
    
    # Calculate statistics using optimized queries with select_related and prefetch_related
    try:
        # Optimize branches query with related data
        branches = list(branches.select_related('business') if hasattr(branches, 'select_related') else 
                       [b for b in branches])
        
        # Get all branch IDs for efficient querying
        branch_ids = [branch.id for branch in branches]
        
        # Bulk fetch portals for all branches with optimized query
        portals_dict = {portal.branch_id: portal for portal in 
                       BranchPortal.objects.filter(branch_id__in=branch_ids).select_related('branch')}
        
        # Bulk calculate order statistics using aggregation
        from django.db.models import Case, When, IntegerField
        order_stats = Order.objects.filter(branch_id__in=branch_ids).values('branch_id').annotate(
            total_orders=Count('id'),
            pending_orders=Count(Case(
                When(status='pending', then=1),
                output_field=IntegerField()
            )),
            completed_orders=Count(Case(
                When(status='completed', then=1),
                output_field=IntegerField()
            ))
        )
        order_stats_dict = {stat['branch_id']: stat for stat in order_stats}
        
        # Bulk calculate course statistics using aggregation
        course_stats = Course.objects.filter(branch_id__in=branch_ids).values('branch_id').annotate(
            total_courses=Count('id'),
            active_courses=Count(Case(
                When(is_active=True, then=1),
                output_field=IntegerField()
            ))
        )
        course_stats_dict = {stat['branch_id']: stat for stat in course_stats}
        
        # Bulk calculate user statistics using optimized queries
        from users.models import CustomUser
        user_stats = CustomUser.objects.filter(
            branch_id__in=branch_ids, is_active=True
        ).values('branch_id').annotate(
            total_users=Count('id'),
            admins=Count(Case(
                When(role='admin', then=1),
                output_field=IntegerField()
            )),
            instructors=Count(Case(
                When(role='instructor', then=1),
                output_field=IntegerField()
            )),
            learners=Count(Case(
                When(role='learner', then=1),
                output_field=IntegerField()
            ))
        )
        user_stats_dict = {stat['branch_id']: stat for stat in user_stats}
        
        # Build branch stats efficiently
        branch_stats = []
        for branch in branches:
            portal = portals_dict.get(branch.id)
            portal_url = (request.build_absolute_uri(reverse('branch_portal:portal_landing', kwargs={'slug': portal.slug})) 
                         if portal else None)
            
            # Get stats from aggregated data
            order_data = order_stats_dict.get(branch.id, {})
            course_data = course_stats_dict.get(branch.id, {})
            user_data = user_stats_dict.get(branch.id, {})
            
            branch_stats.append({
                'branch': branch,
                'portal': portal,
                'portal_url': portal_url,
                'order_management_enabled': branch.order_management_enabled,
                'total_orders': order_data.get('total_orders', 0),
                'pending_orders': order_data.get('pending_orders', 0),
                'completed_orders': order_data.get('completed_orders', 0),
                'total_courses': course_data.get('total_courses', 0),
                'active_courses': course_data.get('active_courses', 0),
                'user_stats': {
                    'total_users': user_data.get('total_users', 0),
                    'admins': user_data.get('admins', 0),
                    'instructors': user_data.get('instructors', 0),
                    'learners': user_data.get('learners', 0),
                }
            })
            
    except Exception as e:
        # Handle database errors gracefully [[memory:3584318]]
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database error in branch_dashboard: {str(e)}")
        
        # Fallback to empty stats if database fails
        branch_stats = []
        for branch in branches:
            branch_stats.append({
                'branch': branch,
                'portal': None,
                'portal_url': None,
                'total_orders': 0,
                'pending_orders': 0,
                'completed_orders': 0,
                'total_courses': 0,
                'active_courses': 0,
            })
        messages.error(request, "Database timeout occurred. Showing empty statistics.")
    
    # Define breadcrumbs
    breadcrumbs = [
        {'url': reverse('users:role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Branch Dashboard', 'icon': 'fa-chart-bar'}
    ]
    
    # Additional context for global admin business and branch filtering
    all_branches = None
    all_businesses = None
    selected_branch_id = None
    selected_business_id = None
    
    if request.user.is_superuser or request.user.role == 'globaladmin':
        # Global admin can see all businesses and branches
        from business.models import Business
        all_businesses = Business.objects.filter(is_active=True).order_by('name')
        all_branches = Branch.objects.filter(is_active=True).select_related('business').order_by('name')
        selected_branch_id = request.GET.get('branch')
        selected_business_id = request.GET.get('business')
    elif request.user.role == 'superadmin':
        from core.utils.business_filtering import filter_branches_by_business
        all_branches = filter_branches_by_business(request.user).select_related('business').order_by('name')
        selected_branch_id = request.GET.get('branch')
        # Get businesses for super admin (limited to their assigned businesses)
        if hasattr(request.user, 'business_assignments'):
            all_businesses = request.user.business_assignments.filter(is_active=True).values_list('business', flat=True)
            from business.models import Business
            all_businesses = Business.objects.filter(id__in=all_businesses, is_active=True).order_by('name')
    
    context = {
        'branch_stats': branch_stats,
        'breadcrumbs': breadcrumbs,
        'all_branches': all_branches,
        'all_businesses': all_businesses,
        'selected_branch_id': selected_branch_id,
        'selected_business_id': selected_business_id,
        'showing_all_branches': not selected_branch_id and not selected_business_id and (request.user.is_superuser or request.user.role == 'globaladmin'),
        'showing_business_filter': selected_business_id and (request.user.is_superuser or request.user.role == 'globaladmin'),
    }
    
    return render(request, 'branch_portal/branch_dashboard.html', context)


# AJAX Views for Portal Content Management

@login_required
@require_http_methods(["GET", "POST"])
def manage_main_content(request):
    """AJAX view for managing main content sections"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    portal_id = request.GET.get('portal_id') or request.POST.get('portal_id')
    if not portal_id:
        return JsonResponse({'success': False, 'message': 'Portal ID required'})
    
    try:
        portal = BranchPortal.objects.get(id=portal_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        if request.method == 'GET':
            # Return list of main content sections
            sections = MainContentSection.objects.filter(portal=portal).order_by('order')
            sections_data = []
            for section in sections:
                sections_data.append({
                    'id': section.id,
                    'title': section.title,
                    'description': section.description,
                    'order': section.order,
                    'is_active': section.is_active,
                    'has_image': bool(section.image),
                    'has_video': bool(section.video),
                    'has_video_url': bool(section.video_url),
                    'video_url': section.video_url or '',
                    'image_url': section.image.url if section.image else None,
                    'video_file_url': section.video.url if section.video else None,
                })
            
            return JsonResponse({'success': True, 'sections': sections_data})
        
        elif request.method == 'POST':
            # Handle create/update
            section_id = request.POST.get('section_id')
            title = request.POST.get('title', '').strip()
            description = request.POST.get('description', '').strip()
            order = request.POST.get('order', 0)
            is_active = request.POST.get('is_active') == 'on'
            video_url = request.POST.get('video_url', '').strip()
            
            if not title or not description:
                return JsonResponse({'success': False, 'message': 'Title and description are required'})
            
            try:
                order = int(order)
            except (ValueError, TypeError):
                order = 0
            
            if section_id:
                # Update existing section
                try:
                    section = MainContentSection.objects.get(id=section_id, portal=portal)
                    section.title = title
                    section.description = description
                    section.order = order
                    section.is_active = is_active
                    
                    # Handle media type exclusivity based on user selection
                    selected_media_type = request.POST.get('selected_media_type', 'none')
                    has_new_image = 'image' in request.FILES
                    has_new_video = 'video' in request.FILES
                    has_video_url = video_url.strip() != ''
                    
                    if selected_media_type == 'image':
                        # User selected image - clear other media types
                        if has_new_image:
                            section.image = request.FILES['image']
                        # Keep existing image if no new upload, but clear other media
                        section.video = None
                        section.video_url = ''
                    elif selected_media_type == 'video_file':
                        # User selected video file - clear other media types
                        if has_new_video:
                            section.video = request.FILES['video']
                        # Keep existing video if no new upload, but clear other media
                        section.image = None
                        section.video_url = ''
                    elif selected_media_type == 'video_url':
                        # User selected video URL - clear other media types
                        section.video_url = video_url
                        section.image = None
                        section.video = None
                    else:
                        # User selected "none" - clear all media
                        section.image = None
                        section.video = None
                        section.video_url = ''
                    
                    section.save()
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Section updated successfully'})
                    else:
                        messages.success(request, 'Section updated successfully')
                        return redirect('branch_portal:branch_dashboard')
                
                except MainContentSection.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Section not found'})
            else:
                # Create new section
                # Handle media type exclusivity based on user selection
                selected_media_type = request.POST.get('selected_media_type', 'none')
                has_image = 'image' in request.FILES
                has_video = 'video' in request.FILES
                has_video_url = video_url.strip() != ''
                
                # Initialize section with basic fields
                section = MainContentSection.objects.create(
                    portal=portal,
                    title=title,
                    description=description,
                    order=order,
                    is_active=is_active,
                    video_url=''  # Initialize empty
                )
                
                # Set media based on user selection
                if selected_media_type == 'image' and has_image:
                    section.image = request.FILES['image']
                elif selected_media_type == 'video_file' and has_video:
                    section.video = request.FILES['video']
                elif selected_media_type == 'video_url' and has_video_url:
                    section.video_url = video_url
                # If selected_media_type is 'none' or no matching media provided, section remains without media
                
                section.save()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Section created successfully'})
                else:
                    messages.success(request, 'Section created successfully')
                    return redirect('branch_portal:branch_dashboard')
    
    except BranchPortal.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Portal not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_POST
def delete_main_content(request):
    """AJAX view for deleting main content sections"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    section_id = request.POST.get('section_id')
    if not section_id:
        return JsonResponse({'success': False, 'message': 'Section ID required'})
    
    try:
        section = MainContentSection.objects.get(id=section_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if section.portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        section.delete()
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Section deleted successfully'})
        else:
            messages.success(request, 'Section deleted successfully')
            return redirect('branch_portal:branch_dashboard')
    
    except MainContentSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Section not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_http_methods(["GET", "POST"])
def manage_feature_grid(request):
    """AJAX view for managing feature grid sections"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    portal_id = request.GET.get('portal_id') or request.POST.get('portal_id')
    if not portal_id:
        return JsonResponse({'success': False, 'message': 'Portal ID required'})
    
    try:
        portal = BranchPortal.objects.get(id=portal_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        if request.method == 'GET':
            # Return list of feature grid sections with items
            sections = FeatureGridSection.objects.filter(portal=portal).prefetch_related('items').order_by('order')
            sections_data = []
            for section in sections:
                items_data = []
                for item in section.items.all().order_by('order'):
                    items_data.append({
                        'id': item.id,
                        'title': item.title,
                        'description': item.description,
                        'order': item.order,
                        'is_active': item.is_active,
                        'link_url': item.link_url,
                        'link_text': item.link_text,
                        'has_image': bool(item.image),
                        'image_url': item.image.url if item.image else None,
                    })
                
                sections_data.append({
                    'id': section.id,
                    'section_title': section.section_title,
                    'section_description': section.section_description,
                    'order': section.order,
                    'is_active': section.is_active,
                    'items': items_data,
                })
            
            return JsonResponse({'success': True, 'sections': sections_data})
        
        elif request.method == 'POST':
            # Handle create/update feature grid section
            section_id = request.POST.get('section_id')
            section_title = request.POST.get('section_title', '').strip()
            section_description = request.POST.get('section_description', '').strip()
            order = request.POST.get('order', 0)
            is_active = request.POST.get('is_active') == 'on'
            
            try:
                order = int(order)
            except (ValueError, TypeError):
                order = 0
            
            if section_id:
                # Update existing section
                try:
                    section = FeatureGridSection.objects.get(id=section_id, portal=portal)
                    section.section_title = section_title
                    section.section_description = section_description
                    section.order = order
                    section.is_active = is_active
                    section.save()
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Feature grid section updated successfully'})
                    else:
                        messages.success(request, 'Feature grid section updated successfully')
                        return redirect('branch_portal:branch_dashboard')
                
                except FeatureGridSection.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Feature grid section not found'})
            else:
                # Create new section
                section = FeatureGridSection.objects.create(
                    portal=portal,
                    section_title=section_title,
                    section_description=section_description,
                    order=order,
                    is_active=is_active
                )
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Feature grid section created successfully', 'section_id': section.id})
                else:
                    messages.success(request, 'Feature grid section created successfully')
                    return redirect('branch_portal:branch_dashboard')
    
    except BranchPortal.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Portal not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_POST
def delete_feature_grid(request):
    """AJAX view for deleting feature grid sections"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    section_id = request.POST.get('section_id')
    if not section_id:
        return JsonResponse({'success': False, 'message': 'Section ID required'})
    
    try:
        section = FeatureGridSection.objects.get(id=section_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if section.portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        section.delete()
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Feature grid section deleted successfully'})
        else:
            messages.success(request, 'Feature grid section deleted successfully')
            return redirect('branch_portal:branch_dashboard')
    
    except FeatureGridSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Feature grid section not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_http_methods(["GET", "POST"])
def manage_feature_grid_item(request):
    """AJAX view for managing individual feature grid items"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    if request.method == 'POST':
        # Handle create/update feature grid item
        section_id = request.POST.get('section_id')
        item_id = request.POST.get('item_id')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        order = request.POST.get('order', 0)
        is_active = request.POST.get('is_active') == 'on'
        link_url = request.POST.get('link_url', '').strip()
        link_text = request.POST.get('link_text', 'Learn More').strip()
        
        if not title or not description:
            return JsonResponse({'success': False, 'message': 'Title and description are required'})
        
        try:
            order = int(order)
        except (ValueError, TypeError):
            order = 0
        
        try:
            section = FeatureGridSection.objects.get(id=section_id)
            
            # Verify user has access to this portal's branch
            if request.user.role == 'superadmin':
                from core.utils.business_filtering import filter_branches_by_business
                accessible_branches = filter_branches_by_business(request.user)
                if section.portal.branch not in accessible_branches:
                    return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
            
            if item_id:
                # Update existing item
                try:
                    item = FeatureGridItem.objects.get(id=item_id, feature_section=section)
                    item.title = title
                    item.description = description
                    item.order = order
                    item.is_active = is_active
                    item.link_url = link_url
                    item.link_text = link_text
                    
                    # Handle file uploads
                    if 'image' in request.FILES:
                        item.image = request.FILES['image']
                    
                    item.save()
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Feature item updated successfully'})
                    else:
                        messages.success(request, 'Feature item updated successfully')
                        return redirect('branch_portal:branch_dashboard')
                
                except FeatureGridItem.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Feature item not found'})
            else:
                # Create new item
                item = FeatureGridItem.objects.create(
                    feature_section=section,
                    title=title,
                    description=description,
                    order=order,
                    is_active=is_active,
                    link_url=link_url,
                    link_text=link_text
                )
                
                # Handle file uploads
                if 'image' in request.FILES:
                    item.image = request.FILES['image']
                    item.save()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Feature item created successfully'})
                else:
                    messages.success(request, 'Feature item created successfully')
                    return redirect('branch_portal:branch_dashboard')
        
        except FeatureGridSection.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Feature grid section not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
@require_POST
def delete_feature_grid_item(request):
    """AJAX view for deleting feature grid items"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    item_id = request.POST.get('item_id')
    if not item_id:
        return JsonResponse({'success': False, 'message': 'Item ID required'})
    
    try:
        item = FeatureGridItem.objects.get(id=item_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if item.feature_section.portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        item.delete()
        
        # Check if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Feature item deleted successfully'})
        else:
            messages.success(request, 'Feature item deleted successfully')
            return redirect('branch_portal:branch_dashboard')
    
    except FeatureGridItem.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Feature item not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_http_methods(["GET", "POST"])
def manage_pre_footer(request):
    """AJAX view for managing pre-footer section"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    portal_id = request.GET.get('portal_id') or request.POST.get('portal_id')
    if not portal_id:
        return JsonResponse({'success': False, 'message': 'Portal ID required'})
    
    try:
        portal = BranchPortal.objects.get(id=portal_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        if request.method == 'GET':
            # Return pre-footer data with menu links and social icons
            try:
                pre_footer = portal.pre_footer
                menu_links = list(pre_footer.menu_links.all().order_by('order').values(
                    'id', 'title', 'url', 'order', 'is_active'
                ))
                social_icons = list(pre_footer.social_icons.all().order_by('order').values(
                    'id', 'platform_name', 'url', 'order', 'is_active'
                ))
                
                # Add image URLs for social icons
                for icon in social_icons:
                    try:
                        icon_obj = SocialMediaIcon.objects.get(id=icon['id'])
                        icon['image_url'] = icon_obj.icon.url if icon_obj.icon else None
                    except SocialMediaIcon.DoesNotExist:
                        icon['image_url'] = None
                
                pre_footer_data = {
                    'id': pre_footer.id,
                    'description': pre_footer.description,
                    'is_active': pre_footer.is_active,
                    'menu_links': menu_links,
                    'social_icons': social_icons,
                }
                
                return JsonResponse({'success': True, 'pre_footer': pre_footer_data})
            
            except PreFooterSection.DoesNotExist:
                return JsonResponse({'success': True, 'pre_footer': None})
        
        elif request.method == 'POST':
            # Handle create/update pre-footer
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            # Convert empty description to None for consistency with null=True field
            if not description:
                description = None
            
            pre_footer, created = PreFooterSection.objects.get_or_create(
                portal=portal,
                defaults={'description': description, 'is_active': is_active}
            )
            
            if not created:
                pre_footer.description = description
                pre_footer.is_active = is_active
                pre_footer.save()
            
            action = 'created' if created else 'updated'
            message = f'Pre-footer {action} successfully'
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': message})
            else:
                messages.success(request, message)
                return redirect('branch_portal:branch_dashboard')
    
    except BranchPortal.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Portal not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_http_methods(["POST"])
def manage_menu_link(request):
    """AJAX view for managing menu links in pre-footer"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    pre_footer_id = request.POST.get('pre_footer_id')
    link_id = request.POST.get('link_id')
    action = request.POST.get('action')  # create, update, delete
    
    if not pre_footer_id:
        return JsonResponse({'success': False, 'message': 'Pre-footer ID required'})
    
    try:
        pre_footer = PreFooterSection.objects.get(id=pre_footer_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if pre_footer.portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        if action == 'delete':
            if not link_id:
                return JsonResponse({'success': False, 'message': 'Link ID required for deletion'})
            
            try:
                link = CustomMenuLink.objects.get(id=link_id, pre_footer=pre_footer)
                link.delete()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Menu link deleted successfully'})
                else:
                    messages.success(request, 'Menu link deleted successfully')
                    return redirect('branch_portal:branch_dashboard')
            except CustomMenuLink.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Menu link not found'})
        
        else:  # create or update
            title = request.POST.get('title', '').strip()
            url = request.POST.get('url', '').strip()
            order = request.POST.get('order', 0)
            is_active = request.POST.get('is_active') == 'on'
            
            if not title or not url:
                return JsonResponse({'success': False, 'message': 'Title and URL are required'})
            
            try:
                order = int(order)
            except (ValueError, TypeError):
                order = 0
            
            if link_id and action == 'update':
                # Update existing link
                try:
                    link = CustomMenuLink.objects.get(id=link_id, pre_footer=pre_footer)
                    link.title = title
                    link.url = url
                    link.order = order
                    link.is_active = is_active
                    link.save()
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Menu link updated successfully'})
                    else:
                        messages.success(request, 'Menu link updated successfully')
                        return redirect('branch_portal:branch_dashboard')
                except CustomMenuLink.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Menu link not found'})
            else:
                # Create new link
                link = CustomMenuLink.objects.create(
                    pre_footer=pre_footer,
                    title=title,
                    url=url,
                    order=order,
                    is_active=is_active
                )
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Menu link created successfully'})
                else:
                    messages.success(request, 'Menu link created successfully')
                    return redirect('branch_portal:branch_dashboard')
    
    except PreFooterSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Pre-footer section not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})


@login_required
@require_http_methods(["POST"])
def manage_social_icon(request):
    """AJAX view for managing social media icons in pre-footer"""
    # Check permissions
    if request.user.role not in ['globaladmin', 'superadmin'] and not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Permission denied'})
    
    pre_footer_id = request.POST.get('pre_footer_id')
    icon_id = request.POST.get('icon_id')
    action = request.POST.get('action')  # create, update, delete
    
    if not pre_footer_id:
        return JsonResponse({'success': False, 'message': 'Pre-footer ID required'})
    
    try:
        pre_footer = PreFooterSection.objects.get(id=pre_footer_id)
        
        # Verify user has access to this portal's branch
        if request.user.role == 'superadmin':
            from core.utils.business_filtering import filter_branches_by_business
            accessible_branches = filter_branches_by_business(request.user)
            if pre_footer.portal.branch not in accessible_branches:
                return JsonResponse({'success': False, 'message': 'Access denied to this branch'})
        
        if action == 'delete':
            if not icon_id:
                return JsonResponse({'success': False, 'message': 'Icon ID required for deletion'})
            
            try:
                icon = SocialMediaIcon.objects.get(id=icon_id, pre_footer=pre_footer)
                icon.delete()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Social icon deleted successfully'})
                else:
                    messages.success(request, 'Social icon deleted successfully')
                    return redirect('branch_portal:branch_dashboard')
            except SocialMediaIcon.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Social icon not found'})
        
        else:  # create or update
            platform_name = request.POST.get('platform_name', '').strip()
            url = request.POST.get('url', '').strip()
            order = request.POST.get('order', 0)
            is_active = request.POST.get('is_active') == 'on'
            
            if not platform_name or not url:
                return JsonResponse({'success': False, 'message': 'Platform name and URL are required'})
            
            try:
                order = int(order)
            except (ValueError, TypeError):
                order = 0
            
            if icon_id and action == 'update':
                # Update existing icon
                try:
                    icon = SocialMediaIcon.objects.get(id=icon_id, pre_footer=pre_footer)
                    icon.platform_name = platform_name
                    icon.url = url
                    icon.order = order
                    icon.is_active = is_active
                    
                    # Handle file uploads
                    if 'icon' in request.FILES:
                        icon.icon = request.FILES['icon']
                    
                    icon.save()
                    
                    # Check if it's an AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Social icon updated successfully'})
                    else:
                        messages.success(request, 'Social icon updated successfully')
                        return redirect('branch_portal:branch_dashboard')
                except SocialMediaIcon.DoesNotExist:
                    return JsonResponse({'success': False, 'message': 'Social icon not found'})
            else:
                # Create new icon
                icon = SocialMediaIcon.objects.create(
                    pre_footer=pre_footer,
                    platform_name=platform_name,
                    url=url,
                    order=order,
                    is_active=is_active
                )
                
                # Handle file uploads
                if 'icon' in request.FILES:
                    icon.icon = request.FILES['icon']
                    icon.save()
                
                # Check if it's an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Social icon created successfully'})
                else:
                    messages.success(request, 'Social icon created successfully')
                    return redirect('branch_portal:branch_dashboard')
    
    except PreFooterSection.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Pre-footer section not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
