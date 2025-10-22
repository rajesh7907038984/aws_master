from django.urls import path
from . import views

app_name = 'assignments'

# API endpoints - maintain consistent patterns
urlpatterns = [
    path('', views.assignment_list, name='assignment_list'),
    path('manage/', views.assignment_management, name='assignment_management'),
    path('create/', views.create_assignment, name='create_assignment'),
    path('create/', views.create_assignment, name='assignment_create'),  # Alias for consistency
    path('create/<int:course_id>/', views.create_assignment, name='create_assignment'),
    path('<int:assignment_id>/', views.assignment_detail, name='assignment_detail'),
    path('<int:assignment_id>/edit/', views.edit_assignment, name='edit_assignment'),
    path('<int:assignment_id>/clone/', views.clone_assignment, name='clone_assignment'),
    path('<int:assignment_id>/delete/', views.delete_assignment, name='delete_assignment'),
    path('<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('<int:assignment_id>/submit-iteration/', views.submit_iteration, name='submit_iteration'),
    path('<int:assignment_id>/feedback/', views.view_assignment_feedback, name='view_feedback'),
    path('submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
    path('submission/<int:submission_id>/grade-history/', views.submission_grade_history, name='submission_grade_history'),
    path('submission/<int:submission_id>/view-pdf/', views.view_pdf_inline, name='view_pdf_inline'),
    path('submission/<int:submission_id>/test-pdf/', views.test_pdf_viewer, name='test_pdf_viewer'),
    path('download/<str:file_type>/<int:file_id>/', views.download_file, name='download_file'),
    path('question/<int:question_id>/delete/', views.question_delete, name='question_delete'),
    path('question/create/<int:quiz_id>/', views.question_create, name='question_create'),
    
    # Text questions URLs
    path('<int:assignment_id>/add_question/', views.text_question_create, name='add_text_question'),
    path('<int:assignment_id>/edit_question/<int:question_id>/', views.text_question_edit, name='edit_text_question'),
    path('<int:assignment_id>/delete_question/<int:question_id>/', views.text_question_delete, name='delete_text_question'),
    path('<int:assignment_id>/delete_question/<int:question_id>/', views.text_question_delete, name='text_question_delete'),
    path('<int:assignment_id>/reorder_questions/', views.update_text_question_order, name='reorder_text_questions'),
    
    
    # Detailed Report URLs
    path('<int:assignment_id>/detailed-report/', views.assignment_detailed_report, name='assignment_detailed_report'),
    path('<int:assignment_id>/detailed-report/admin-approve/', views.admin_approve_report, name='admin_approve_report'),
    path('<int:assignment_id>/detailed-report/confirm/', views.confirm_detailed_report, name='confirm_detailed_report'),
    path('<int:assignment_id>/detailed-report/download/', views.download_detailed_report, name='download_detailed_report'),
    
    # Editor image upload endpoint
    path('upload-editor-image/', views.upload_editor_image, name='upload_editor_image'),
    
    # Editor video upload endpoint
    path('upload-editor-video/', views.upload_editor_video, name='upload_editor_video'),
    
    # API endpoints
    path('api/list/', views.assignment_api_list, name='assignment_api_list'),
    
    # Comment management URLs
    path('<int:assignment_id>/add-comment/', views.add_comment, name='add_comment'),
    path('comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
] 