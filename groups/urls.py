from django.urls import path
from . import views

app_name = 'groups'

urlpatterns = [
    path('', views.group_list, name='group_list'),
    path('<int:group_id>/', views.group_detail, name='group_detail'),
    path('create/', views.group_create, name='group_create'),
    path('<int:group_id>/edit/', views.group_edit, name='group_edit'),
    path('<int:group_id>/delete/', views.group_delete, name='group_delete'),
    path('bulk-delete/', views.group_bulk_delete, name='group_bulk_delete'),
    path('<int:group_id>/members/add/', views.member_add, name='member_add'),
    path('<int:group_id>/members/<int:membership_id>/delete/', views.member_delete, name='member_delete'),
    path('<int:group_id>/courses/', views.course_access_manage, 
         name='course_access_manage'),
    path('<int:group_id>/courses/<int:course_id>/remove/', 
         views.remove_course_access, name='remove_course_access'),
    # Access Control URLs
    path('access-control/create/', views.role_create, name='role_create'),
    path('access-control/<int:role_id>/edit/', views.role_edit, name='role_edit'),
    path('access-control/<int:role_id>/delete/', views.role_delete, name='role_delete'),
    path('<int:group_id>/access-control/edit/', views.access_control_edit, name='access_control_edit'),
    # Azure AD Group Import URLs
    path('azure/list/', views.azure_groups_list, name='azure_groups_list'),
    path('azure/import/', views.azure_group_import, name='azure_group_import'),
    path('azure/sync/', views.azure_group_sync, name='azure_group_sync'),
]
