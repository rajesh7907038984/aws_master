from django.urls import path
from . import views

app_name = 'scorm'

urlpatterns = [
    # SCORM player
    path('player/<int:topic_id>/', views.scorm_player, name='player'),
    
    # SCORM API endpoint
    path('api/<int:attempt_id>/', views.scorm_api, name='api'),
    
    # SCORM content proxy
    path('content/<int:attempt_id>/<path:path>', views.scorm_content, name='content'),
    
    # SCORM status
    path('status/<int:attempt_id>/', views.scorm_status, name='status'),
]

