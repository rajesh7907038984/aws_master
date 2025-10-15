from django.urls import path
from . import views, validation_views

app_name = 'scorm'

urlpatterns = [
    # SCORM Content Viewing - Now using dedicated player only
    path('view/<int:topic_id>/', views.dedicated_scorm_player, name='view'),
    path('player/<int:topic_id>/', views.dedicated_scorm_player, name='player'),  # Legacy URL support
    path('content/<int:topic_id>/<path:path>', views.scorm_content, name='content'),
    
    # SCORM API (for tracking)
    path('api/<int:attempt_id>/', views.scorm_api, name='api'),
    path('debug/<int:attempt_id>/', views.scorm_debug, name='debug'),
    
    # SCORM validation endpoints
    path('validate/', validation_views.validate_scorm_ajax, name='validate'),
    path('validation-test/', validation_views.validation_test_page, name='validation_test'),
    path('help/', validation_views.scorm_help, name='help'),
]

