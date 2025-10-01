from django.urls import path
from . import views

app_name = 'tinymce_editor'

urlpatterns = [
    path('', views.upload_image, name='editor'),  # Main editor endpoint
    path('upload_image/', views.upload_image, name='upload_image'),
    path('upload_media_file/', views.upload_media_file, name='upload_media_file'),
    path('generate_ai_content/', views.generate_ai_content, name='generate_ai_content'),
    path('csrf-test/', views.csrf_test, name='csrf_test'),
    
    # AI Token Management URLs (for Global Admins)
    path('ai-token-dashboard/', views.ai_token_dashboard, name='ai_token_dashboard'),
    path('manage-branch-tokens/<int:branch_id>/', views.manage_branch_tokens, name='manage_branch_tokens'),
    path('manage-branch-tokens/<int:branch_id>/data/', views.get_branch_token_data, name='get_branch_token_data'),
    path('bulk-update-tokens/', views.bulk_update_tokens, name='bulk_update_tokens'),
    path('check-token-status/', views.check_token_status, name='check_token_status'),
] 