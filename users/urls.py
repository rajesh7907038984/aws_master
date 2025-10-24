from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import api_views
from django.shortcuts import redirect

app_name = 'users'

urlpatterns = [
    # Default route for /users/
    path('', views.role_based_redirect, name='users_home'),

    # Authentication URLs
    # Note: logout is handled at the global level in main urls.py
    path('register/', views.register, name='register'),
    path('branch-register/', views.branch_register, name='branch_register'),
    path('branch-register/<str:branch_slug>/', views.branch_register, name='branch_register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('branch-login/', views.custom_login, name='branch_login'),
    path('redirect/', views.role_based_redirect, name='role_based_redirect'),
    
    # Google OAuth URLs
    path('auth/google/', views.google_login, name='google_login'),
    path('auth/google/callback/', views.google_callback, name='google_callback'),
    
    # Microsoft OAuth URLs
    path('auth/microsoft/', views.microsoft_login, name='microsoft_login'),
    path('auth/microsoft/callback/', views.microsoft_callback, name='microsoft_callback'),

    # User Management URLs
    path('admin/', views.users_admin_dashboard, name='users_admin_dashboard'),
    path('list/', views.user_list, name='user_list'),
    path('create/', views.user_create, name='user_create'),
    path('create/', views.user_create, name='add_user'),
    path('<int:user_id>/', views.user_detail, name='user_profile'),
    path('<int:user_id>/', views.user_detail, name='user_view'),
    path('<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('<int:user_id>/password/', views.password_change, name='password_change'),
    path('<int:user_id>/send-forgot-password/', views.admin_send_forgot_password, name='admin_send_forgot_password'),
    path('send-self-password-reset/', views.send_self_password_reset, name='send_self_password_reset'),
    
        # API endpoints for group selection
        path('api/branches/<int:branch_id>/groups/', api_views.get_branch_groups, name='api_branch_groups'),
    path('api/groups/<int:group_id>/courses/', api_views.get_group_courses, name='api_group_courses'),
    path('api/users/<int:user_id>/groups/', api_views.update_user_groups, name='api_update_user_groups'),
    path('settings/', views.user_settings, name='user_settings'),

    # Dashboard URLs moved to main urls.py for direct access

    # Dashboard API Endpoints
    path('api/dashboard-overview/', views.get_dashboard_overview_data, name='api_dashboard_overview'),
    path('api/dashboard-activity-data/', views.get_dashboard_activity_data, name='api_dashboard_activity'),
    path('api/admin-course-progress/', views.get_admin_course_progress_data, name='api_admin_course_progress'),
    path('api/course-progress-data/', views.get_course_progress_data, name='api_course_progress_data'),
    
    # Auto-timezone detection endpoints
    path('api/auto-timezone/set/', views.auto_timezone_set, name='api_auto_timezone_set'),
    path('api/auto-timezone/status/', views.auto_timezone_status, name='api_auto_timezone_status'),
    path('api/timezone/update/', views.timezone_update, name='api_timezone_update'),
    path('api/instructor-dashboard-stats/', views.get_instructor_dashboard_stats, name='api_instructor_dashboard_stats'),
    path('api/recent-activities/', views.get_recent_activities, name='api_recent_activities'),

    # Todo API Endpoints
    path('api/todos/', views.get_user_todos, name='api_user_todos'),
    path('api/todo-counts/', views.get_todo_counts, name='api_todo_counts'),
    path('todos/', views.get_user_todos, name='todo_list'),

    
    # Search URL
    path('search/', views.search, name='search'),
    
    # Download User Template URL
    path('template/download/', views.download_user_template, name='download_user_template'),
    
    # Bulk Import URLs
    path('validate-bulk-import/', views.validate_bulk_import, name='validate_bulk_import'),
    path('validate-bulk-data/', views.validate_bulk_data, name='validate_bulk_data'),
    path('bulk-import/', views.bulk_import, name='bulk_import'),
    
    # CV Data Extraction API
    path('api/extract-cv-data/', views.extract_cv_data, name='extract_cv_data'),
    
    # Duplicate User Role Check API
    path('api/check-duplicate-user-role/', views.check_duplicate_user_role, name='check_duplicate_user_role'),
    
    # Postcode Lookup API
    path('api/lookup-postcode/', views.lookup_postcode, name='lookup_postcode'),
    
    # Public Postcode Lookup API (for testing only)
    path('api/public/lookup-postcode/', views.lookup_postcode_public, name='lookup_postcode_public'),
    
    # Postcode Addresses Lookup API (returns multiple addresses for selection)
    path('api/public/lookup-postcode-addresses/', views.lookup_postcode_addresses, name='lookup_postcode_addresses'),
    
    # Quiz Assignment Management URLs
    path('add-quiz-assignment/', views.add_quiz_assignment, name='add_quiz_assignment'),
    path('edit-quiz-assignment/<int:assignment_id>/', views.edit_quiz_assignment, name='edit_quiz_assignment'),
    path('delete-quiz-assignment/<int:assignment_id>/', views.delete_quiz_assignment, name='delete_quiz_assignment'),
    path('get-available-quizzes/', views.get_available_quizzes, name='get_available_quizzes'),
    
    # Manual VAK Scores Management - integrated into main user form
    # Session management endpoints
    path('keep-alive/', views.keep_alive_view, name='keep_alive'),
    path('ping/', views.ping_view, name='ping'),
    
    # Bulk user operations
    path('bulk-delete/', views.bulk_delete_users, name='bulk_delete_users'),
    path('test-simple/', views.bulk_delete_users, name='test_simple'),
]