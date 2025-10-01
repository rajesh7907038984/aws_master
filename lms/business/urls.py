from django.urls import path
from . import views
from . import performance_views
from . import api_views

app_name = 'business'

urlpatterns = [
    # Business management URLs
    path('', views.business_list, name='business_list'),
    path('create/', views.business_create, name='business_create'),
    path('<int:business_id>/', views.business_detail, name='business_detail'),
    path('<int:business_id>/edit/', views.business_edit, name='business_edit'),
    path('<int:business_id>/delete/', views.business_delete, name='business_delete'),
    path('<int:business_id>/assign-user/', views.assign_user_to_business, name='assign_user'),
    path('<int:business_id>/unassign-user/<int:user_id>/', views.unassign_user_from_business, name='unassign_user'),
    
    # Performance dashboard URLs
    path('performance/', performance_views.GlobalBusinessPerformanceView.as_view(), name='global_performance'),
    path('performance/<int:business_id>/', performance_views.BusinessDetailPerformanceView.as_view(), name='business_detail_performance'),
    path('performance/api/', performance_views.BusinessPerformanceAPIView.as_view(), name='performance_api'),
    path('performance/export/', performance_views.PerformanceExportView.as_view(), name='performance_export'),
    path('performance/cache/', performance_views.PerformanceCacheManagementView.as_view(), name='performance_cache_management'),
    
    # API endpoints for performance data
    path('api/overview/', api_views.get_business_overview_api, name='api_business_overview'),
    path('api/login-stats/', api_views.get_login_statistics_api, name='api_login_statistics'),
    path('api/completion-stats/', api_views.get_completion_statistics_api, name='api_completion_statistics'),
    path('api/business-comparison/', api_views.get_business_comparison_api, name='api_business_comparison'),
    path('api/chart-data/', api_views.get_chart_data_api, name='api_chart_data'),
    path('api/clear-cache/', api_views.clear_cache_api, name='api_clear_cache'),
    path('api/real-time-stats/', api_views.get_real_time_stats_api, name='api_real_time_stats'),
    path('api/performance/', api_views.BusinessPerformanceAPIView.as_view(), name='api_performance'),
] 