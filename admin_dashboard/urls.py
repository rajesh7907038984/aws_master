from django.urls import path
from . import views, performance_views

app_name = 'admin_dashboard'

urlpatterns = [
    path('superadmin/', views.SuperAdminDashboardView.as_view(), name='superadmin_dashboard'),
    path('performance-stats/', performance_views.PerformanceStatsView.as_view(), name='performance_stats'),
    path('performance/', performance_views.PerformanceStatsView.as_view(), name='performance'),
    path('chart-data/', performance_views.PerformanceChartDataView.as_view(), name='chart_data'),
]