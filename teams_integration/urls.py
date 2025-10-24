"""
Teams Integration URL Configuration
"""

from django.urls import path, include
from . import views

app_name = 'teams_integration'

urlpatterns = [
    # Dashboard and main views
    path('', views.teams_integration_dashboard, name='dashboard'),
    path('sync-logs/', views.sync_logs, name='sync_logs'),
    path('sync-logs/<int:log_id>/', views.sync_log_detail, name='sync_log_detail'),
    path('meeting-syncs/', views.meeting_syncs, name='meeting_syncs'),
    path('entra-mappings/', views.entra_group_mappings, name='entra_mappings'),
    
    # API endpoints
    path('test-connection/<int:integration_id>/', views.test_teams_connection, name='test_connection'),
    path('sync-entra-groups/<int:integration_id>/', views.sync_entra_groups_manual, name='sync_entra_groups'),
    path('sync-meeting-data/<int:conference_id>/', views.sync_meeting_data_manual, name='sync_meeting_data'),
    path('toggle-mapping/<int:mapping_id>/', views.toggle_group_mapping, name='toggle_mapping'),
    path('health-check/', views.health_check, name='health_check'),
]