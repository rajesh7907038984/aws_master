"""
URL routing for SCORM app
"""
from django.urls import path
from . import views

app_name = 'scorm'

urlpatterns = [
    # SCORM player proxy endpoint (same-origin)
    path('player/<int:package_id>/<path:file_path>', views.scorm_player, name='player'),
    
    # SCORM package status endpoint
    path('package/<int:package_id>/status/', views.package_status, name='package_status'),
]

