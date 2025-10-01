from django.urls import path, include
from . import views
from . import enhanced_trackable_launch

app_name = 'scorm_cloud'

# API endpoints - maintain consistent patterns
urlpatterns = [
    # SCORM Package Management
    path('packages/', views.package_list, name='package_list'),
    path('packages/', views.package_list, name='scorm_list'),  # Alias for consistency
    path('packages/upload/', views.package_upload, name='package_upload'),
    path('packages/<uuid:pk>/', views.package_detail, name='package_detail'),
    path('packages/<uuid:pk>/delete/', views.package_delete, name='package_delete'),
    
    # Direct topic SCORM upload (new endpoint)
    path('topic/upload/', views.topic_scorm_upload, name='topic_scorm_upload'),
    
    # Registration Endpoints
    path('registration/create/<int:topic_id>/', views.create_registration,name='create_registration'),
    path('registrations/create/', views.create_registration, name='create_registration'),
    path('registrations/<uuid:pk>/launch/', views.launch_content, name='launch_content'),
    path('registrations/<uuid:pk>/status/', views.registration_status, name='registration_status'),
    path('registration/create/<int:topic_id>/', views.create_registration, name='create_registration'),
    
    # API Endpoints
    path('api/xapi/statements/', views.xapi_statements, name='xapi_statements'),
    path('api/postback/', views.postback_handler, name='postback_handler'),
    
    # Debug/Testing (development only)
    path('debug/test-connection/', views.test_connection, name='test_connection'),

    # Tracking endpoints
    path('tracking/update/<int:topic_id>/', views.scorm_tracking_update, name='tracking_update'),
    path('tracking/status/<int:topic_id>/', views.scorm_tracking_status, name='tracking_status'),
    path('upload/progress/<int:topic_id>/', views.scorm_upload_progress, name='upload_progress'),
    path('auto-sync/', views.auto_sync_scorm_progress, name='auto_sync'),

    path('topic/<int:topic_id>/launch/', views.scorm_launch, name='scorm_launch'),
    path('topic/<int:topic_id>/tracking/update/', views.scorm_tracking_update, name='scorm_tracking_update'),
    path('topic/<int:topic_id>/tracking/status/', views.scorm_tracking_status, name='scorm_tracking_status'),

    # Add debug view
    path('debug-content/', views.debug_scorm_content, name='debug_scorm_content'),

    # SCORM Topic integration
    path('topic/<int:topic_id>/registration/', views.create_registration, name='create_registration'),
    path('topic/<int:topic_id>/launch/', views.scorm_launch, name='scorm_launch'),
    path('topic/<int:topic_id>/tracking/update/', views.scorm_tracking_update, name='scorm_tracking_update'),
    path('topic/<int:topic_id>/tracking/status/', views.scorm_tracking_status, name='scorm_tracking_status'),
    
    # Debug paths
    path('topic/<int:topic_id>/debug/', views.debug_scorm_launch, name='debug_scorm_launch'),
    path('debug/content/', views.debug_scorm_content, name='debug_scorm_content'),
    
    # SCORM Cloud integration
    path('registration/<str:registration_id>/', views.launch_content, name='launch_content'),
    path('registration/<uuid:pk>/status/', views.registration_status, name='registration_status'),
    
    # XAPI and SCORM Cloud postback endpoints
    path('xapi/statements/', views.xapi_statements, name='xapi_statements'),
    path('postback/', views.postback_handler, name='postback_handler'),
    
    # Test connection
    path('test-connection/', views.test_connection, name='test_connection'),
    path('check-connection/', views.check_scorm_connection, name='check_scorm_connection'),
    
    # Direct SCORM launch URL
    path('content/<int:content_id>/direct-launch/', views.direct_scorm_launch, name='direct_scorm_launch'),
    
    # SCORM Package registration
    path('package/<uuid:package_id>/register/', views.register_for_package, name='register_for_package'),
    
    # Worker management endpoints
    path('worker/status/', views.scorm_worker_status, name='worker_status'),
    path('worker/restart/', views.restart_scorm_worker, name='restart_worker'),
    
    # Diagnostic endpoints
    path('topic/<int:topic_id>/diagnostics/', views.scorm_diagnostics, name='scorm_diagnostics'),
    
    # Reporting endpoints
    path('topic/<int:topic_id>/report/', views.scorm_progress_report, name='scorm_progress_report'),
    
    # Enhanced Trackable Launch URLs
    path('topic/<int:topic_id>/trackable-launch/', enhanced_trackable_launch.enhanced_scorm_launch, name='enhanced_scorm_launch'),
    path('topic/<int:topic_id>/completion/', enhanced_trackable_launch.scorm_completion_redirect, name='scorm_completion_redirect'),
    path('api/postback/<str:registration_id>/', enhanced_trackable_launch.scorm_completion_webhook, name='scorm_completion_webhook'),
    path('topic/<int:topic_id>/progress/', enhanced_trackable_launch.scorm_progress_tracking, name='scorm_progress_tracking'),
    path('topic/<int:topic_id>/report-data/', enhanced_trackable_launch.scorm_report_data, name='scorm_report_data'),
    
    # Direct Launch URL Generation API
    path('api/topic/<int:topic_id>/generate-launch-url/', views.generate_scorm_launch_url, name='generate_scorm_launch_url'),
    
    # Local SCORM Player (fallback when SCORM Cloud is not available)
    path('topic/<int:topic_id>/local-launch/', views.local_scorm_launch, name='local_scorm_launch'),
    path('topic/<int:topic_id>/local-completion/', views.local_scorm_completion, name='local_scorm_completion'),
]