from django.urls import path, include
from . import views

app_name = 'lrs'

urlpatterns = [
    # CRITICAL FIX: Add compatibility routes for CMI5 content FIRST (more specific patterns)
    path('xapi/statements/statements/', views.StatementsView.as_view(), name='statements_statements'),
    path('xapi/statements/statements', views.StatementsView.as_view(), name='statements_statements_noslash'),
    # CRITICAL FIX: Add compatibility route for CMI5 content that requests /xapi/statements/activities/
    # MUST be BEFORE the parameterized statement_id route to match correctly
    path('xapi/statements/activities/', views.ActivitiesView.as_view(), name='statements_activities'),
    path('xapi/statements/activities/<str:activity_id>/', views.ActivitiesView.as_view(), name='statements_activity_detail'),
    # CRITICAL FIX: Move parameterized route AFTER specific routes to avoid conflicts
    path('xapi/statements/<str:statement_id>/', views.StatementsView.as_view(), name='statement_detail'),
    # xAPI endpoints
    path('xapi/statements/', views.StatementsView.as_view(), name='statements'),
    path('xapi/activities/', views.ActivitiesView.as_view(), name='activities'),
    path('xapi/activities/<str:activity_id>/', views.ActivitiesView.as_view(), name='activity_detail'),
    path('xapi/activities/<str:activity_id>/profile/', views.ActivityProfilesView.as_view(), name='activity_profiles'),
    # CRITICAL FIX: Add compatibility routes for CMI5 content that requests /xapi/statements/activities/state
    path('xapi/statements/activities/state/', views.StateRootView.as_view(), name='statements_activity_state_root'),
    path('xapi/statements/activities/state', views.StateRootView.as_view(), name='statements_activity_state_root_noslash'),
    # Compatibility: AUs that call /xapi/activities/state (no activity_id) with activityId query param
    # Must be BEFORE the parameterized state route so it matches first
    path('xapi/activities/state/', views.StateRootView.as_view(), name='activity_state_root'),
    # No-slash variant to avoid potential redirects from some AU POSTs
    path('xapi/activities/state', views.StateRootView.as_view(), name='activity_state_root_noslash'),
    path('xapi/activities/<str:activity_id>/state/', views.StateView.as_view(), name='activity_state'),
    path('xapi/activities/<str:activity_id>/resume/', views.StateView.as_view(), name='activity_resume'),
    path('xapi/agents/profile/', views.AgentProfilesView.as_view(), name='agent_profiles'),
    
    # CMI5 endpoints
    path('cmi5/launch/', views.CMI5LaunchView.as_view(), name='cmi5_launch'),
    path('cmi5/fetch/', views.CMI5FetchView.as_view(), name='cmi5_fetch'),
    
    # SCORM 2004 endpoints
    path('scorm2004/sequencing/<str:activity_id>/', views.SCORM2004SequencingView.as_view(), name='scorm2004_sequencing'),
]
