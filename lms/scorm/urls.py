from django.urls import path
from . import views, validation_views

app_name = 'scorm'

urlpatterns = [
    # SCORM Content Viewing
    path('view/<int:topic_id>/', views.scorm_view, name='view'),
    path('player/<int:topic_id>/', views.scorm_view, name='player'),  # Legacy URL support
    path('content/<int:topic_id>/<path:path>', views.scorm_content, name='content'),
    
    # SCORM Content with attempt_id (for backward compatibility)
    path('content/<int:attempt_id>/<path:path>', views.scorm_content, name='content_by_attempt'),
    
    # SCORM API (for tracking)
    path('api/<int:attempt_id>/', views.scorm_api, name='api'),
    path('status/<int:attempt_id>/', views.scorm_status, name='status'),
    path('debug/<int:attempt_id>/', views.scorm_debug, name='debug'),
    path('tracking-report/<int:attempt_id>/', views.scorm_tracking_report, name='tracking_report'),
    
    # SCORM validation endpoints
    path('validate/', validation_views.validate_scorm_ajax, name='validate'),
    path('validation-test/', validation_views.validation_test_page, name='validation_test'),
    path('help/', validation_views.scorm_help, name='help'),
]

