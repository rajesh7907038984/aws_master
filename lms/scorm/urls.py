from django.urls import path
from . import views

app_name = 'scorm'

urlpatterns = [
    # SCORM Launch and Content
    path('launch/<int:topic_id>/', views.scorm_launch, name='launch'),
    path('content/<int:topic_id>/<path:file_path>', views.scorm_content, name='content'),
    
    # SCORM API
    path('api/<int:topic_id>/', views.scorm_api, name='api'),
    path('log/', views.scorm_log, name='log'),
    
    # Reports
    path('reports/<int:course_id>/', views.scorm_reports, name='reports'),
    path('reports/<int:course_id>/learner/<int:user_id>/', views.scorm_learner_progress, name='learner_progress'),
]
