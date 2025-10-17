from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('superadmin/', views.SuperAdminDashboardView.as_view(), name='superadmin_dashboard'),
]