from django.urls import path
from . import views
from . import source_map_handler
from . import error_handler

app_name = 'scorm'

urlpatterns = [
    # SCORM Launch and Content
    path('launch/<int:topic_id>/', views.scorm_launch, name='launch'),
    path('content/<int:topic_id>/<path:file_path>', views.scorm_content, name='content'),
    
    
    
    # SCORM API
    path('api/<int:topic_id>/', views.scorm_api, name='api'),
    path('log/', views.scorm_log, name='log'),
    
    # SCORM Result and Retake
    path('result/<int:topic_id>/', views.scorm_result, name='result'),
    path('retake/<int:topic_id>/', views.scorm_retake, name='retake'),
    path('resume/<int:topic_id>/', views.scorm_resume, name='resume'),
    path('progress/<int:topic_id>/', views.scorm_progress, name='progress'),
    path('debug/<int:topic_id>/', views.scorm_debug, name='debug'),
    
    # Preview URLs for instructors/admins
    path('preview/<int:topic_id>/', views.scorm_preview, name='preview'),
    
    # Package Validation and Progress
    path('validate/<int:topic_id>/', views.validate_elearning_package_endpoint, name='validate'),
    path('extraction-progress/<int:topic_id>/', views.extraction_progress, name='extraction_progress'),
    
    # Reports
    path('reports/<int:course_id>/', views.scorm_reports, name='reports'),
    path('reports/<int:course_id>/learner/<int:user_id>/', views.scorm_learner_progress, name='learner_progress'),
    
    # Analytics
    path('analytics/', views.scorm_analytics_dashboard, name='analytics_dashboard'),
    path('analytics/api/', views.scorm_analytics_api, name='analytics_api'),
    
    # Source Map Handlers (to prevent 404 errors)
    path('source-maps/<str:filename>', source_map_handler.handle_source_map, name='source_map'),
    path('desktop.min.css.map', source_map_handler.handle_desktop_css_map, name='desktop_css_map'),
    
    # Error Handlers (to fix SCORM content errors)
    path('error-fixes.js', error_handler.scorm_error_fixes, name='error_fixes'),
    path('console-cleaner.js', error_handler.scorm_console_cleaner, name='console_cleaner'),
    path('string-table-fix.js', error_handler.string_table_fix, name='string_table_fix'),
]
