"""
URL routing for SCORM app
"""
from django.urls import path
from . import views
from . import views_enrollment

app_name = 'scorm'

urlpatterns = [
    # SCORM launcher (wrapper page with API)
    path('launch/<int:topic_id>/', views.scorm_launcher, name='launcher'),
    
    # SCORM player proxy endpoint (same-origin)
    path('player/<int:package_id>/<path:file_path>', views.scorm_player, name='player'),
    
    # SCORM package status endpoint
    path('package/<int:package_id>/status/', views.package_status, name='package_status'),
    
    # Enhanced SCORM progress tracking with enrollment/attempt models
    path('progress/<int:topic_id>/', views_enrollment.update_scorm_progress_with_enrollment, name='update_progress'),
]

