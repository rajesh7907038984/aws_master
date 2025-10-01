from django.urls import path
from . import views

app_name = 'role_management'

urlpatterns = [
    path('', views.role_list, name='role_list'),
    path('create/', views.role_create, name='role_create'),
    path('<int:role_id>/', views.role_detail, name='role_detail'),
    path('<int:role_id>/edit/', views.role_edit, name='role_edit'),
    path('<int:role_id>/delete/', views.role_delete, name='role_delete'),
    path('<int:role_id>/audit/', views.role_audit_log, name='role_audit_log'),
    path('assign/', views.assign_role, name='assign_role'),
    path('unassign/', views.unassign_role, name='unassign_role'),
    path('bulk-action/', views.bulk_role_action, name='bulk_role_action'),
] 