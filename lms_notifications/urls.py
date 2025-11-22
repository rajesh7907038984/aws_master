from django.urls import path
from . import views

app_name = 'lms_notifications'

urlpatterns = [
    # Main notification views
    path('', views.notification_center, name='notification_center'),
    path('', views.notification_center, name='notification_list'),  # Alias for consistency
    path('unread/', views.unread_notifications, name='unread_notifications'),
    path('all/', views.all_notifications, name='all_notifications'),
    
    # Individual notification actions
    path('<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('delete-all-read/', views.delete_all_read, name='delete_all_read'),
    
    # Settings
    path('settings/', views.notification_settings, name='settings'),
    path('settings/type/<int:type_id>/', views.notification_type_settings, name='type_settings'),
    path('settings/test-email/', views.send_test_email, name='send_test_email'),
    path('admin-settings/', views.notification_admin_settings, name='admin_settings'),
    # Branch settings disabled - using main notification settings instead
    # path('branch-settings/', views.branch_notification_settings, name='branch_settings'),
    
    # Bulk notifications (admin/instructor only)
    path('bulk/', views.bulk_notification_list, name='bulk_notification_list'),
    path('bulk/create/', views.bulk_notification_create, name='bulk_notification_create'),
    path('bulk/<int:bulk_id>/edit/', views.bulk_notification_edit, name='bulk_notification_edit'),
    path('bulk/<int:bulk_id>/send/', views.bulk_notification_send, name='bulk_notification_send'),
    path('bulk/<int:bulk_id>/preview/', views.bulk_notification_preview, name='bulk_notification_preview'),
    path('bulk/<int:bulk_id>/delete/', views.bulk_notification_delete, name='bulk_notification_delete'),
    
    # Templates (admin only)
    path('templates/', views.notification_template_list, name='template_list'),
    path('templates/create/', views.notification_template_create, name='template_create'),
    path('templates/<int:template_id>/edit/', views.notification_template_edit, name='template_edit'),
    path('templates/<int:template_id>/delete/', views.notification_template_delete, name='template_delete'),
    
    # AJAX endpoints
    path('api/count/', views.notification_count_api, name='notification_count_api'),
    path('api/recent/', views.recent_notifications_api, name='recent_notifications_api'),
    path('api/mark-read/<int:notification_id>/', views.mark_read_api, name='mark_read_api'),
    path('api/bulk-preview/', views.bulk_preview_api, name='bulk_preview_api'),
    
    # Reports and analytics (admin only)
    path('reports/', views.notification_reports, name='reports'),
    path('reports/analytics/', views.notification_analytics, name='analytics'),
] 