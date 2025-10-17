from django.urls import path
from . import views
from . import source_map_handler
from . import error_handler

app_name = 'scorm'

urlpatterns = [
    # SCORM Launch and Content
    path('launch/<int:topic_id>/', views.scorm_launch, name='launch'),
    path('content/<int:topic_id>/<path:file_path>', views.scorm_content, name='content'),
    
    # xAPI Launch and Content
    path('xapi/launch/<int:topic_id>/', views.xapi_launch, name='xapi_launch'),
    path('xapi/content/<int:topic_id>/<path:file_path>', views.scorm_content, name='xapi_content'),
    path('xapi/resume/<int:topic_id>/', views.xapi_resume, name='xapi_resume'),
    
    # cmi5 Launch and Content
    path('cmi5/launch/<int:topic_id>/', views.cmi5_launch, name='cmi5_launch'),
    path('cmi5/content/<int:topic_id>/<path:file_path>', views.scorm_content, name='cmi5_content'),
    path('cmi5/resume/<int:topic_id>/', views.cmi5_resume, name='cmi5_resume'),
    
    # SCORM API
    path('api/<int:topic_id>/', views.scorm_api, name='api'),
    path('log/', views.scorm_log, name='log'),
    
    # SCORM Result and Retake
    path('result/<int:topic_id>/', views.scorm_result, name='result'),
    path('retake/<int:topic_id>/', views.scorm_retake, name='retake'),
    path('resume/<int:topic_id>/', views.scorm_resume, name='resume'),
    path('progress/<int:topic_id>/', views.scorm_progress, name='progress'),
    path('debug/<int:topic_id>/', views.scorm_debug, name='debug'),
    
    # Package Validation
    path('validate/<int:topic_id>/', views.validate_elearning_package_endpoint, name='validate'),
    
    # Reports
    path('reports/<int:course_id>/', views.scorm_reports, name='reports'),
    path('reports/<int:course_id>/learner/<int:user_id>/', views.scorm_learner_progress, name='learner_progress'),
    
    # Source Map Handlers (to prevent 404 errors)
    path('source-maps/<str:filename>', source_map_handler.handle_source_map, name='source_map'),
    path('desktop.min.css.map', source_map_handler.handle_desktop_css_map, name='desktop_css_map'),
    
    # Error Handlers (to fix SCORM content errors)
    path('error-fixes.js', error_handler.scorm_error_fixes, name='error_fixes'),
    path('console-cleaner.js', error_handler.scorm_console_cleaner, name='console_cleaner'),
]
