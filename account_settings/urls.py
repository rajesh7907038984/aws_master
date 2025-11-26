from django.urls import path, re_path
from . import views, storage_views

app_name = 'account_settings'

urlpatterns = [
    path('', views.account_settings, name='settings'),
    path('toggle-2fa/', views.toggle_2fa, name='toggle_2fa'),
    path('toggle-oauth-2fa/', views.toggle_oauth_2fa, name='toggle_oauth_2fa'),
    path('setup-totp/', views.setup_totp, name='setup_totp'),
    path('toggle-totp-2fa/', views.toggle_totp_2fa, name='toggle_totp_2fa'),
    path('totp-backup-codes/', views.totp_backup_codes, name='totp_backup_codes'),
    path('branch-integrations/', views.manage_branch_integrations, name='manage_branch_integrations'),
    re_path(r'integrations/(?P<integration_type>[^/]+)/(?P<integration_id>-?\d+)/delete/', views.delete_integration, name='delete_integration'),
    re_path(r'integrations/(?P<integration_type>[^/]+)/(?P<integration_id>-?\d+)/toggle/', views.toggle_integration, name='toggle_integration'),
    re_path(r'integrations/(?P<integration_type>[^/]+)/(?P<integration_id>-?\d+)/edit/', views.edit_integration, name='edit_integration'),
    path('branch-limits/<int:branch_id>/update/', views.update_branch_limits, name='update_branch_limits'),
    path('business-limits/<int:business_id>/update/', views.update_business_limits, name='update_business_limits'),
    
    # Data Export/Import URLs
    path('export/start/', views.start_export, name='start_export'),
    path('import/start/', views.start_import, name='start_import'),
    path('export/status/<int:job_id>/', views.export_status, name='export_status'),
    path('import/status/<int:job_id>/', views.import_status, name='import_status'),
    path('export/download/<int:job_id>/', views.download_export, name='download_export'),
    path('export/jobs/', views.get_export_jobs, name='get_export_jobs'),
    path('import/jobs/', views.get_import_jobs, name='get_import_jobs'),
    
    # Backup Management URLs
    path('backup/create/', views.create_backup, name='create_backup'),
    path('backup/list/', views.get_backups, name='get_backups'),
    path('backup/download/<int:backup_id>/', views.download_backup, name='download_backup'),
    path('backup/delete/<int:backup_id>/', views.delete_backup, name='delete_backup'),
    
    # Integration Test URLs
    path('test-teams-connection/', views.test_teams_connection, name='test_teams_connection'),
    path('validate-teams-permissions/', views.validate_teams_permissions, name='validate_teams_permissions'),
    path('test-zoom-connection/', views.test_zoom_connection, name='test_zoom_connection'),
    path('test-sharepoint-connection/', views.test_sharepoint_connection, name='test_sharepoint_connection'),
    path('sharepoint-manual-setup-guide/', views.sharepoint_manual_setup_guide, name='sharepoint_manual_setup_guide'),
    
    # SharePoint Sync URLs
    path('sharepoint-sync/', views.manual_sharepoint_sync, name='manual_sharepoint_sync'),
    path('sharepoint-sync-status/<str:task_id>/', views.sharepoint_sync_status, name='sharepoint_sync_status'),
    
    # AJAX Data Loading URLs
    path('load-business-data/', views.load_business_data, name='load_business_data'),
    path('load-branches-data/', views.load_branches_data, name='load_branches_data'),
    path('load-order-management-branches/', views.load_order_management_branches, name='load_order_management_branches'),
    
    # AJAX endpoints for lazy loading
    path('ajax/load-business-data/', views.load_business_data, name='load_business_data'),
    path('ajax/load-branches-data/', views.load_branches_data, name='load_branches_data'),
    path('ajax/load-integrations-data/', views.load_integrations_data, name='load_integrations_data'),
    
    # Storage Management URLs
    path('storage/manage/<int:branch_id>/', storage_views.manage_branch_storage, name='manage_branch_storage'),
    path('storage/analytics/', storage_views.storage_analytics, name='storage_analytics'),
    path('storage/info/', storage_views.get_storage_info, name='get_storage_info'),
    path('storage/check-upload/', storage_views.check_upload_permission, name='check_upload_permission'),
    path('storage/report/<int:branch_id>/', storage_views.branch_storage_report, name='branch_storage_report'),
    path('storage/report/', storage_views.branch_storage_report, name='branch_storage_report_own'),
    
] 