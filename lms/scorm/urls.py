from django.urls import path
from . import views, validation_views

app_name = 'scorm'

urlpatterns = [
    # SCORM Content Viewing
    path('view/<int:topic_id>/', views.scorm_view, name='view'),
    path('player/<int:topic_id>/', views.scorm_view, name='player'),  # Legacy URL support
    path('api-test/', views.scorm_api_test, name='api_test'),  # API diagnostic tool
    path('content/<int:topic_id>/<path:path>', views.scorm_content, name='content'),
    
    # SCORM API (for tracking)
    path('api/<int:attempt_id>/', views.scorm_api, name='api'),
    
    # SCORM validation endpoints
    path('validate/', validation_views.validate_scorm_ajax, name='validate'),
    path('validation-test/', validation_views.validation_test_page, name='validation_test'),
    path('help/', validation_views.scorm_help, name='help'),
]

