"""
LMS Project Main URL Configuration

This is the root URL configuration for the Learning Management System.
It includes all app URL patterns, authentication routes, admin interface,
and system-level endpoints.

Key features:
- Multi-tenant branch-based authentication
- Role-based dashboard routing
- Static and media file serving
- Custom error handling
- Health monitoring
- API endpoints from all apps

URL Structure:
- / : Home page
- /auth/<branch>/ : Branch-specific authentication
- /dashboard/<role>/ : Role-based dashboards
- /<app>/ : Individual app URLs
- /admin/ : Django admin interface
- /health/ : System health check
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from users.views import role_based_redirect, home, learner_dashboard, instructor_dashboard, admin_dashboard, global_admin_dashboard, users_admin_dashboard, custom_login, register, forgot_password
from core.views import health_check
from admin_dashboard.views import SuperAdminDashboardView
from django.views.generic.base import RedirectView
from branch_portal.views import marketing_landing_page

# Custom error handlers
from core.views import custom_404_view, custom_500_view, custom_403_view

# Configure custom error handlers
handler404 = custom_404_view
handler500 = custom_500_view
handler403 = custom_403_view

# Redirect helper for accounts login
def redirect_accounts_login(request):
    """Redirect to custom login"""
    next_url = request.GET.get('next', '/')
    return redirect(f'/login/?next={next_url}')

urlpatterns = [
    path('', home, name='home'),
    path('landing/', marketing_landing_page, name='marketing_landing'),
    
    # Custom Users Admin Dashboard (replaces Django admin for users)
    path('admin/users/', users_admin_dashboard, name='users_admin_dashboard'),
    path('admin/users/customuser/', lambda request: redirect('/admin/users/')),
    
    path('admin/', admin.site.urls),
    
    # Favicon handling
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'core/img/favicon.png', permanent=True)),
    path('favicon.ico/', RedirectView.as_view(url=settings.STATIC_URL + 'core/img/favicon.png', permanent=True)),
    
    # Standard web files
    path('robots.txt', RedirectView.as_view(url=settings.STATIC_URL + 'robots.txt', permanent=True)),
    path('Session.txt', RedirectView.as_view(url=settings.STATIC_URL + 'Session.txt', permanent=True)),
    path('.well-known/Session.txt', RedirectView.as_view(url=settings.STATIC_URL + 'Session.txt', permanent=True)),
    
    # Security monitoring for .env file access attempts
    path('.env', custom_404_view, name='security_monitor_env'),
    
    # Static files redirect (fix 404 for /static/ without trailing slash)
    path('static', RedirectView.as_view(url=settings.STATIC_URL, permanent=True)),
    path('static/', RedirectView.as_view(url=settings.STATIC_URL, permanent=True)),
    path('', include('core.urls')),  # Include core URLs at root level for session management
    path('admin_dashboard/', include('admin_dashboard.urls', namespace='admin_dashboard')),
    path('super-admin/', include('admin_dashboard.urls', namespace='admin_dashboard_legacy')),
    path('dashboard/globaladmin/', global_admin_dashboard, name='dashboard_globaladmin'),
    path('dashboard/superadmin/', SuperAdminDashboardView.as_view(), name='dashboard_superadmin'),
    path('dashboard/learner/', learner_dashboard, name='dashboard_learner'),
    path('dashboard/instructor/', instructor_dashboard, name='dashboard_instructor'),
    path('dashboard/admin/', admin_dashboard, name='dashboard_admin'),
    path('health/', health_check, name='health_check'),
    
    # Global authentication URLs (fallback)
    path('login/', custom_login, name='login'),
    path('branch-login/', custom_login, name='branch_login'),
    path('logout/', auth_views.LogoutView.as_view(
        template_name='registration/logout.html',
        next_page='login'
    ), name='logout'),
    path('register/', register, name='register'),  # Direct registration view
    path('forgot-password/', forgot_password, name='forgot_password'),
    path('resend-verification/', register, name='resend_verification'),  # Reuse register view for resend
    path('custom-users-admin/', users_admin_dashboard, name='custom_users_admin'),
    
    # Branch-specific authentication URLs
    path('auth/<slug:branch_slug>/', include('users.urls_auth')),
    path('auth/', include('users.urls_auth')),  # Global auth URLs
    
    path('users/', include('users.urls', namespace='users')),
    path('courses/', include('courses.urls', namespace='courses')),
    path('groups/', include('groups.urls', namespace='groups')),
    path('branches/', include('branches.urls', namespace='branches')),
    path('business/', include('business.urls', namespace='business')),
    path('branch-portal/', include('branch_portal.urls', namespace='branch_portal')),
    path('redirect/', role_based_redirect, name='role_based_redirect'),
    path('scorm/', include('scorm.urls', namespace='scorm')),  # Native SCORM support
    path('messages/', include('lms_messages.urls', namespace='lms_messages')),
    path('discussions/', include('discussions.urls', namespace='discussions')),
    path('conferences/', include('conferences.urls', namespace='conferences')),
    path('categories/', include('categories.urls', namespace='categories')),
    path('quiz/', include('quiz.urls', namespace='quiz')),
    path('assignments/', include('assignments.urls', namespace='assignments')),
    path('gradebook/', include('gradebook.urls', namespace='gradebook')),
    path('calendar/', include('calendar_app.urls', namespace='calendar')),
    path('reports/', include('reports.urls', namespace='reports')),
    path('rubrics/', include('lms_rubrics.urls', namespace='lms_rubrics')),
    path('outcomes/', include('lms_outcomes.urls', namespace='lms_outcomes')),
    path('certificates/', include('certificates.urls', namespace='certificates')),
    path('notifications/', include('lms_notifications.urls', namespace='lms_notifications')),
    path('account/', include('account_settings.urls', namespace='account_settings')),
    path('teams-integration/', include('teams_integration.urls', namespace='teams_integration')),
    path('individual-learning-plan/', include('individual_learning_plan.urls', namespace='individual_learning_plan')),
    path('role-management/', include('role_management.urls', namespace='role_management')),
    path('course-reviews/', include('course_reviews.urls', namespace='course_reviews')),
    # path('media/', include('lms_media.urls', namespace='lms_media')),  # Commented out - lms_media module doesn't exist
    path('tinymce/', include('tinymce_editor.urls')),
    path('accounts/login/', redirect_accounts_login, name='accounts_login_redirect'),
    
    
    # API fallback endpoints for common AJAX requests
    path('api/health/', health_check, name='api_health_check'),
    
    # Calendar API endpoints are already included via core.urls at root level
]

# Add Django Debug Toolbar URLs when DEBUG is enabled
from django.conf import settings
if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    except ImportError:
        # Debug toolbar not installed, continue without it
        pass

# Custom 404 handling - Fixed to avoid redirect loops
# Only catch specific patterns that are definitely not valid URLs
urlpatterns += [
    # Catch common invalid patterns but avoid interfering with valid app URLs
    re_path(r'^[a-zA-Z0-9-_]+\.php$', custom_404_view, name='catch_php_404'),
    re_path(r'^wp-admin/', custom_404_view, name='catch_wp_404'),
    re_path(r'^wp-content/', custom_404_view, name='catch_wp_content_404'),
    re_path(r'^wordpress/', custom_404_view, name='catch_wordpress_404'),
]

# Add media and static file handling
if settings.DEBUG:
    # In development, serve static and media files through Django
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
# In production, WhiteNoise middleware handles static files automatically
# Media files are served via S3, no URL patterns needed

