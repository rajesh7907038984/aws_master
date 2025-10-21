from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('superadmin/', views.OptimizedSuperAdminDashboardView.as_view(), name='superadmin_dashboard'),
]