from django.urls import path
from . import scorm_handler, validation_views, auto_sync_views
import logging

logger = logging.getLogger(__name__)

app_name = 'scorm'

urlpatterns = [
    # SCORM Content Viewing - Universal Handler
    path('view/<int:topic_id>/', scorm_handler.scorm_view, name='view'),
    path('player/<int:topic_id>/', scorm_handler.scorm_view, name='player'),  # Legacy URL support
    path('content/<int:topic_id>/<path:path>', scorm_handler.scorm_content, name='content'),
    
    # Direct SCORM content access
    path('direct/<int:topic_id>/<path:path>', scorm_handler.scorm_content, name='content_direct'),
    
    # SCORM Content with attempt_id (for backward compatibility) - More specific pattern
    path('content/attempt/<int:attempt_id>/<path:path>', scorm_handler.scorm_content, name='content_by_attempt'),
    
    # SCORM API (for tracking) - Universal API Handler
    path('api/<int:attempt_id>/', scorm_handler.scorm_api, name='api'),
    path('api/emergency-save/', scorm_handler.scorm_emergency_save, name='emergency_save'),
    path('status/<int:attempt_id>/', scorm_handler.scorm_status, name='status'),
    path('debug/<int:attempt_id>/', scorm_handler.scorm_debug, name='debug'),
    path('tracking-report/<int:attempt_id>/', scorm_handler.scorm_tracking_report, name='tracking_report'),
    
    # SCORM validation endpoints
    path('validate/', validation_views.validate_scorm_ajax, name='validate'),
    path('validation-test/', validation_views.validation_test_page, name='validation_test'),
    path('help/', validation_views.scorm_help, name='help'),
    
    # Dynamic Auto-sync endpoints
    path('auto-sync/trigger/', auto_sync_views.trigger_score_sync, name='trigger_sync'),
    path('auto-sync/health/', auto_sync_views.check_scorm_health, name='health_check'),
    path('auto-sync/fix-course/<int:course_id>/', auto_sync_views.auto_fix_course_scores, name='fix_course'),
    path('auto-sync/exit/', auto_sync_views.sync_on_exit, name='sync_on_exit'),
]

