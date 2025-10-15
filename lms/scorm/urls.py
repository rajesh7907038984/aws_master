from django.urls import path
from . import views, validation_views

app_name = 'scorm'

urlpatterns = [
    # Main SCORM Player URLs - Simplified direct S3 embedding
    path('player/<int:topic_id>/', views.scorm_player, name='player'),
    path('view/<int:topic_id>/', views.scorm_view, name='view'),
    
    # Direct content proxy for SCORM files
    path('content/<int:topic_id>/', views.scorm_direct_content, name='content'),
    path('content/<int:topic_id>/<path:path>', views.scorm_direct_content, name='content_path'),
    
    # Lightweight SCORM API (works without authentication)
    path('api/<int:topic_id>/', views.scorm_api_lite, name='api'),
    
    # Validation endpoints (kept for admin use)
    path('validate/', validation_views.validate_scorm_ajax, name='validate'),
    path('validation-test/', validation_views.validation_test_page, name='validation_test'),
    path('help/', validation_views.scorm_help, name='help'),
]