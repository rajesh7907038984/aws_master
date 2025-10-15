"""
SCORM URL Configuration
"""
from django.urls import path
from . import views

app_name = 'scorm'

urlpatterns = [
    # Package Management
    path('upload/', views.SCORMPackageUploadView.as_view(), name='upload'),
    path('packages/', views.SCORMPackageListView.as_view(), name='package_list'),
    
    # Player
    path('player/<uuid:package_id>/', views.SCORMPlayerView.as_view(), name='player'),
    
    # API Endpoints
    path('api/<int:topic_id>/', views.scorm_api_endpoint, name='api_endpoint'),
    
    # Attempt Management
    path('attempts/', views.scorm_user_attempts, name='user_attempts'),
    path('attempt/<uuid:attempt_id>/', views.scorm_attempt_detail, name='attempt_detail'),
]

