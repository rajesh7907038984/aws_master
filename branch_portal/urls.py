from django.urls import path
from . import views

app_name = 'branch_portal'

urlpatterns = [
    # Marketing landing page
    path('landing/', views.marketing_landing_page, name='marketing_landing'),
    
    # Portal management
    path('manage/', views.manage_portal, name='manage_portal'),
    path('manage/<int:branch_id>/', views.manage_portal, name='manage_portal_for_branch'),
    path('update/', views.update_portal, name='update_portal'),
    
    # Cart and checkout
    path('cart/', views.view_cart, name='view_cart'),
    path('cart/add/<int:course_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:course_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    path('checkout/<int:branch_id>/', views.checkout, name='checkout'),
    path('order/success/<str:order_number>/', views.order_success, name='order_success'),
    
    # Order management
    path('orders/', views.branch_orders, name='branch_orders'),
    path('orders/<str:order_number>/', views.order_detail, name='order_detail'),
    path('orders/<str:order_number>/update-status/', views.update_order_status, name='update_order_status'),
    path('orders/<str:order_number>/delete/', views.delete_order, name='delete_order'),
    path('orders/delete-pending/', views.delete_pending_orders, name='delete_pending_orders'),
    
    # Admin dashboard
    path('dashboard/', views.branch_dashboard, name='branch_dashboard'),
    
    # AJAX endpoints for portal content management
    path('ajax/main-content/', views.manage_main_content, name='ajax_manage_main_content'),
    path('ajax/main-content/delete/', views.delete_main_content, name='ajax_delete_main_content'),
    path('ajax/feature-grid/', views.manage_feature_grid, name='ajax_manage_feature_grid'),
    path('ajax/feature-grid/delete/', views.delete_feature_grid, name='ajax_delete_feature_grid'),
    path('ajax/feature-grid-item/', views.manage_feature_grid_item, name='ajax_manage_feature_grid_item'),
    path('ajax/feature-grid-item/delete/', views.delete_feature_grid_item, name='ajax_delete_feature_grid_item'),
    path('ajax/pre-footer/', views.manage_pre_footer, name='ajax_manage_pre_footer'),
    path('ajax/menu-link/', views.manage_menu_link, name='ajax_manage_menu_link'),
    path('ajax/social-icon/', views.manage_social_icon, name='ajax_manage_social_icon'),
    
    # Landing pages (must be last to avoid conflicts with specific patterns)
    path('<slug:slug>/', views.portal_landing, name='portal_landing'),
] 