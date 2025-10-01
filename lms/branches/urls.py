from django.urls import path
from . import views

app_name = 'branches'

urlpatterns = [
    # Branch management URLs
    path('', views.manage_branches, name='branch_list'),
    path('create/', views.create_branch, name='create_branch'),
    path('create/', views.create_branch, name='branch_create'),  # Alias for consistency
    path('<int:branch_id>/edit/', views.edit_branch, name='edit_branch'),
    path('<int:branch_id>/delete/', views.delete_branch, name='delete_branch'),
    
    # Admin branch switching URLs
    path('switch/', views.switch_branch, name='switch_branch'),
    path('reset/', views.reset_to_primary_branch, name='reset_to_primary'),
    path('api/user-branches/', views.get_user_branches, name='get_user_branches'),
    
    # Super admin branch management URLs
    path('manage-admin-assignments/', views.manage_admin_branches, name='manage_admin_branches'),
    path('assign-admin/', views.assign_admin_to_branch, name='assign_admin_to_branch'),
    path('remove-admin/', views.remove_admin_from_branch, name='remove_admin_from_branch'),
    path('api/admin-assignments/<int:admin_user_id>/', views.get_admin_branch_assignments, name='get_admin_assignments'),
] 