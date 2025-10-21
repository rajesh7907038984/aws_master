from django.urls import path
from . import views
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
    
    # API endpoints
    path('api/overview/', api_views.get_business_overview_api, name='api_business_overview'),
    path('api/login-stats/', api_views.get_login_statistics_api, name='api_login_statistics'),
    path('api/completion-stats/', api_views.get_completion_statistics_api, name='api_completion_statistics'),
    path('api/business-comparison/', api_views.get_business_comparison_api, name='api_business_comparison'),
    path('api/chart-data/', api_views.get_chart_data_api, name='api_chart_data'),
    path('api/real-time-stats/', api_views.get_real_time_stats_api, name='api_real_time_stats'),
] 