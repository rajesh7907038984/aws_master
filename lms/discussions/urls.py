"""
Discussions URL Configuration

This module defines URL patterns for the discussions application, which handles
forum-style discussions, comments, replies, and social features within the LMS.

Key features:
- Discussion creation and management
- Threaded comments and replies
- Social interactions (likes)
- Rubric-based evaluation
- Bulk evaluation tools
- Image uploads for rich content
"""

from django.urls import path
from . import views

app_name = 'discussions'

# API endpoints - maintain consistent patterns
urlpatterns = [
    # ============================================================================
    # DISCUSSION MANAGEMENT
    # ============================================================================
    path('', views.discussion_list, name='discussion_list'),               # List all discussions
    path('new/', views.new_discussion, name='new_discussion'),             # Create new discussion
    path('new/course/', views.new_discussion, name='new_discussion_with_course'),  # Create with course context
    path('new/<int:course_id>/', views.new_discussion, name='new_discussion_with_course'),  # Create for specific course
    
    # ============================================================================
    # DISCUSSION TOPICS (ALTERNATIVE CREATE FLOW)
    # ============================================================================
    path('add-topic/', views.add_topic, name='add_topic'),                 # Add discussion topic
    path('add-topic/<int:course_id>/', views.add_topic, name='add_topic_with_course'),  # Add topic for course
    
    # ============================================================================
    # INDIVIDUAL DISCUSSION OPERATIONS
    # ============================================================================
    path('<int:discussion_id>/', views.discussion_detail, name='discussion_detail'),        # View discussion
    path('<int:discussion_id>/edit/', views.edit_discussion, name='edit_discussion'),       # Edit discussion
    path('<int:discussion_id>/clone/', views.clone_discussion, name='clone_discussion'),    # Clone discussion
    path('<int:discussion_id>/delete/', views.delete_discussion, name='delete_discussion'), # Delete discussion
    
    # ============================================================================
    # COMMENT SYSTEM
    # ============================================================================
    path('<int:discussion_id>/comment/', views.add_comment, name='add_comment'),             # Add comment
    path('<int:discussion_id>/comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),      # Edit comment
    path('<int:discussion_id>/comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'), # Delete comment
    path('<int:discussion_id>/comment/<int:comment_id>/reply/', views.add_reply, name='add_reply'),            # Reply to comment
    
    # ============================================================================
    # SOCIAL FEATURES
    # ============================================================================
    path('discussion/<int:discussion_id>/like/', views.toggle_discussion_like, name='toggle_discussion_like'), # Like discussion
    path('comment/<int:comment_id>/like/', views.toggle_comment_like, name='toggle_comment_like'),              # Like comment
    
    # ============================================================================
    # EVALUATION & ASSESSMENT
    # ============================================================================
    path('<int:discussion_id>/evaluate-rubric/', views.evaluate_discussion_rubric, name='evaluate_rubric'),   # Rubric evaluation
    path('<int:discussion_id>/scores/', views.discussion_scores, name='discussion_scores'),                   # View scores
    path('<int:discussion_id>/detailed-report/', views.discussion_detailed_report, name='discussion_detailed_report'), # Detailed report
    path('<int:discussion_id>/detailed-report/print/', views.discussion_detailed_report_print, name='discussion_detailed_report_print'), # Print view report
    path('<int:discussion_id>/bulk-evaluate/', views.bulk_evaluate_discussion, name='bulk_evaluate'),         # Bulk evaluation
    path('<int:discussion_id>/student/<int:student_id>/evaluation-data/', views.get_student_evaluation_data, name='get_student_evaluation_data'), # Student evaluation API
    
    # ============================================================================
    # MEDIA UPLOADS & API ENDPOINTS
    # ============================================================================
    path('upload_image/', views.upload_image, name='upload_image'),        # Image upload for rich content
    path('api/users/', views.user_autocomplete_api, name='user_autocomplete_api'), # User autocomplete for @mentions
]
