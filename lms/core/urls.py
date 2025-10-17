"""
Core URLs - Base URL patterns for the LMS core functionality
"""

from django.urls import path, include
from . import views
# from .views import csrf_views  # COMMENTED OUT TO FIX ERRORS
# Import calendar API functions from the views module
from .views import api_calendar_activities, api_daily_activities, api_calendar_summary, log_client_error, api_version
# Import monitoring views
from .views.monitoring_dashboard import monitoring_dashboard, api_system_metrics, api_health_check, api_user_engagement
# Import timezone API functions
from .timezone_api import set_user_timezone, get_user_timezone, get_timezone_list
# Import server time API
from .views.server_time import server_time

app_name = 'core'

urlpatterns = [
    # Legal pages
    path('terms-of-service/', views.terms_of_service, name='terms_of_service'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    
    # API endpoints
    path('api/', include([
        # CSRF token management - COMMENTED OUT TO FIX ERRORS
        # path('csrf/', include([
        #     path('refresh/', csrf_views.refresh_csrf_token, name='csrf_refresh'),
        #     path('validate/', csrf_views.validate_csrf_token, name='csrf_validate'),
        #     path('info/', csrf_views.csrf_token_info, name='csrf_info'),
        # ])),
        # Calendar API endpoints
        path('calendar/', include([
            path('activities/', api_calendar_activities, name='api_calendar_activities'),
            path('daily/<str:date_str>/', api_daily_activities, name='api_daily_activities'),
            path('summary/', api_calendar_summary, name='api_calendar_summary'),
        ])),
        # Timezone API endpoints
        path('timezone/', include([
            path('set/', set_user_timezone, name='api_timezone_set'),
            path('get/', get_user_timezone, name='api_timezone_get'),
            path('list/', get_timezone_list, name='api_timezone_list'),
        ])),
        # Error logging API endpoints
        path('log-client-error/', log_client_error, name='api_log_client_error'),
        path('log-error/', log_client_error, name='api_log_error'),  # Alternative endpoint
        # Device time sync API endpoint
        path('sync-device-time/', views.sync_device_time, name='api_sync_device_time'),
        # Server time API endpoint
        path('server-time/', server_time, name='api_server_time'),
        # Version endpoint
        path('version/', api_version, name='api_version'),
        # Monitoring endpoints
        path('monitoring/', include([
            path('dashboard/', monitoring_dashboard, name='monitoring_dashboard'),
            path('metrics/', api_system_metrics, name='api_system_metrics'),
            path('health/', api_health_check, name='api_health_check'),
            path('user-engagement/<int:user_id>/', api_user_engagement, name='api_user_engagement'),
        ])),
    ])),
    
    # Remote login endpoint
    path('remote/login/', views.remote_login, name='remote_login'),
    
    # Security and well-known endpoints
    path('.well-known/security.txt', views.security_txt, name='security_txt'),
]