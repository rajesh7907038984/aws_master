from django.urls import path, include
from . import views

app_name = 'lrs'

urlpatterns = [
    # xAPI endpoints
    path('xapi/statements/', views.StatementsView.as_view(), name='statements'),
    path('xapi/statements/<str:statement_id>/', views.StatementsView.as_view(), name='statement_detail'),
    path('xapi/activities/', views.ActivitiesView.as_view(), name='activities'),
    path('xapi/activities/<str:activity_id>/', views.ActivitiesView.as_view(), name='activity_detail'),
    path('xapi/activities/<str:activity_id>/profile/', views.ActivityProfilesView.as_view(), name='activity_profiles'),
    path('xapi/activities/<str:activity_id>/state/', views.StateView.as_view(), name='activity_state'),
    path('xapi/activities/<str:activity_id>/resume/', views.StateView.as_view(), name='activity_resume'),
    path('xapi/agents/profile/', views.AgentProfilesView.as_view(), name='agent_profiles'),
    
    # CMI5 endpoints
    path('cmi5/launch/', views.CMI5LaunchView.as_view(), name='cmi5_launch'),
    
    # SCORM 2004 endpoints
    path('scorm2004/sequencing/<str:activity_id>/', views.SCORM2004SequencingView.as_view(), name='scorm2004_sequencing'),
]
