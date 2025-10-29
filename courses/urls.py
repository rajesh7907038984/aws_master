from django.urls import path, include
from . import views
from . import views_simple
from .topic_views import topic_view, topic_content, topic_url_embed

app_name = 'courses'

urlpatterns = [
    # Video Streaming - bypass authentication
    path('video/<path:path>', views.stream_video, name='stream_video'),
    path('<int:course_id>/check-video/', views.check_video_status, name='check_video_status'),
    
    # Course List and Management Views
    path('', views.course_list, name='course_list'),
    path('create/', views.course_manage, name='course_manage'),
    path('create/', views.course_manage, name='course_create'),  # Alias for consistency
    path('admin/', views.admin_manage_courses, name='admin_courses'),
    path('superadmin/', views.super_admin_manage_courses, name='superadmin_courses'),
    
    # Course CRUD Operations
    path('<int:course_id>/details/', views.course_details, name='course_details'),
    path('<int:course_id>/edit/', views.course_edit, name='course_edit'),
    path('<int:course_id>/view/', views.course_view, name='course_view'),
    path('<int:course_id>/delete/', views.course_delete, name='course_delete'),
    path('<int:course_id>/settings/', views.course_settings, name='course_settings'),
    path('<int:course_id>/debug-permissions/', views.debug_course_permissions, name='debug_course_permissions'),
    # path('course/<int:course_id>/settings/update/', views.update_course_title_api, name='update_course_title'),
    
    # API endpoints
    path('api/branch/<int:branch_id>/courses/', views.get_branch_courses, name='get_branch_courses'),
    path('<int:course_id>/progress/api/', views.get_course_progress, name='get_course_progress_api'),
    
    # Claude AI proxy endpoint
    path('api/claude-ai-proxy/', views.claude_ai_proxy, name='claude_ai_proxy'),
    
    # Section Management
    path('section/<int:course_id>/create/', views.section_create, name='section_create'),
    path('move_topic_to_section/', views.move_topic_to_section, name='move_topic_to_section'),
    
    # Enrollment Management
    path('<int:course_id>/enrollment-toggle/', views.course_enrollment_toggle, name='course_enrollment_toggle'),
    path('<int:course_id>/enroll/<int:user_id>/', views.enroll_learner, name='enroll_learner'),
    path('<int:course_id>/unenroll/<int:user_id>/', views.unenroll_learner, name='unenroll_learner'),
    path('<int:course_id>/users/', views.course_users, name='course_users'),
    path('<int:course_id>/users/add/', views.course_add_users, name='course_add_users'),
    path('<int:course_id>/users/create/', views.course_create_user, name='course_create_user'),
    path('<int:course_id>/api/enrolled-learners/', views.api_enrolled_learners, name='api_enrolled_learners'),
    path('<int:course_id>/progress/', views.course_progress_view, name='course_progress'),
    path('<int:course_id>/progress/<int:user_id>/', views.user_course_progress_view, name='user_course_progress'),
    path('<int:course_id>/bulk-enroll/', views.course_bulk_enroll, name='course_bulk_enroll'),
    
    # Group Management
    path('<int:course_id>/groups/add/', views.course_add_groups, name='course_add_groups'),
    path('<int:course_id>/groups/add/<int:group_id>/', views.add_group_to_course, name='add_group_to_course'),
    path('<int:course_id>/groups/remove/<int:group_id>/', views.remove_group_from_course, name='remove_group_from_course'),
    
    # Topic Management
    path('<int:course_id>/topic/create/', views.topic_create, name='topic_create'),
    path('topic/<int:topic_id>/edit/', views.topic_edit, name='topic_edit'),
    path('topic/<int:topic_id>/section/<int:section_id>/edit/', views.topic_edit, name='topic_section_edit'),
    path('topic/<int:topic_id>/delete/', views.topic_delete, name='topic_delete'),
    path('topic/<int:topic_id>/content/', topic_content, name='topic_content'),
    path('topic/<int:topic_id>/view/', topic_view, name='topic_view'),
    path('topic/<int:topic_id>/embed/', topic_url_embed, name='topic_url_embed'),
    path('topic/<int:topic_id>/discussion/', views.topic_discussion_view, name='topic_discussion_view'),
    path('topic/<int:topic_id>/complete/', views.mark_topic_complete, name='mark_topic_complete'),
    
    
    path('topic/<int:topic_id>/incomplete/', views.mark_topic_incomplete, name='mark_topic_incomplete'),
    
    path('api/update_audio_progress/<int:topic_id>/', views.update_audio_progress, name='update_audio_progress'),
    path('topic/<int:topic_id>/like/<str:item_type>/<int:item_id>/', views.like_item, name='like_item'),
    path('topic/<int:topic_id>/toggle-status/', views.toggle_topic_status, name='toggle_topic_status'),
    path('api/update_video_progress/<int:topic_id>/', views.update_video_progress, name='update_video_progress'),
    path('api/update_scorm_progress/<int:topic_id>/', views.update_scorm_progress, name='update_scorm_progress'),
    
    # Comment Management
    path('topic/<int:topic_id>/comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('topic/<int:topic_id>/comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('topic/<int:topic_id>/comment/<int:comment_id>/reply/', views.add_reply, name='add_reply'),
    path('topic/<int:topic_id>/reply/<int:reply_id>/delete/', views.delete_reply, name='delete_reply'),
    path('topic/<int:topic_id>/reply/<int:reply_id>/edit/', views.edit_reply, name='edit_reply'),
    
    # API endpoints with consistent naming pattern
    path('api/topics/reorder/', views.api_topic_reorder, name='api_topic_reorder'),
    path('api/topics/move/', views.api_topic_move, name='api_topic_move'),
    path('api/sections/reorder/', views.api_section_reorder, name='api_section_reorder'),
    path('api/sections/create/', views.section_create, name='section_create'),
    path('api/sections/<int:section_id>/update/', views.section_update, name='section_update'),
    path('api/sections/<int:section_id>/delete/', views.section_delete, name='section_delete'),
    path('api/sections/<int:section_id>/simple-delete/', views_simple.simple_section_delete, name='simple_section_delete'),
    path('api/sections/<int:section_id>/rename/', views.update_section_name, name='update_section_name'),
    
   
    # Category management - use categories app instead
    
    # Course progress and completion
    path('courses/<int:course_id>/generate-certificate/', views.generate_certificate, name='generate_certificate'),
    
    # Certificate URLs
    path('course/<int:course_id>/certificate/', views.generate_certificate, name='get_certificate'),
    path('certificates/<str:uuid>/', views.certificate_view, name='certificate_view'),
    
    # Editor image upload endpoint
    path('upload-editor-image/', views.upload_editor_image, name='upload_editor_image'),
    
    # Editor video upload endpoint
    path('upload-editor-video/', views.upload_editor_video, name='upload_editor_video'),
]
# Direct S3 Upload endpoints
from courses.s3_direct_upload import get_presigned_upload_url, confirm_upload
urlpatterns += [
    path('api/get-upload-url/', get_presigned_upload_url, name='get_upload_url'),
    path('api/confirm-upload/', confirm_upload, name='confirm_upload'),
]
