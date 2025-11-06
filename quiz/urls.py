from django.urls import path
from . import views

app_name = 'quiz'


# API endpoints - maintain consistent patterns
urlpatterns = [
    path('', views.quiz_list, name='quiz_list'),  # Main quiz list page
    path('create/', views.create_quiz, name='create_quiz'),  # Create quiz without course_id
    path('create/', views.create_quiz, name='quiz_create'),  # Alias for consistency
    path('create/<int:course_id>/', views.create_quiz, name='create_quiz_for_course'),  # Create quiz for specific course
    
    path('<int:quiz_id>/edit/', views.edit_quiz, name='edit_quiz'),
    path('<int:quiz_id>/clone/', views.clone_quiz, name='clone_quiz'),
    path('<int:quiz_id>/delete/', views.delete_quiz, name='delete_quiz'),
    path('<int:quiz_id>/attempt/', views.attempt_quiz, name='attempt_quiz'),
    path('<int:quiz_id>/clean-stale-attempts/', views.clean_stale_attempts, name='clean_stale_attempts'),
    path('<int:quiz_id>/feedback/', views.view_quiz_feedback, name='view_feedback'),
    path('attempt/<int:attempt_id>/', views.take_quiz, name='take_quiz'),
    path('attempt/<int:attempt_id>/save-progress/', views.save_quiz_progress, name='save_quiz_progress'),
    path('attempt/<int:attempt_id>/submit/', views.submit_quiz, name='submit_quiz'),
    path('<int:quiz_id>/results/', views.quiz_results, name='quiz_results'),
    path('<int:quiz_id>/detailed-report/', views.quiz_detailed_report, name='quiz_detailed_report'),
    path('<int:quiz_id>/preview/', views.preview_quiz, name='preview_quiz'),
    path('<int:quiz_id>/add-question/', views.add_question, name='create_question'),
    path('question/<int:question_id>/edit/', views.edit_question, name='edit_question'),
    path('question/<int:question_id>/delete/', views.delete_question, name='delete_question'),
    # Removed update_question_order - functionality not implemented
    path('<int:quiz_id>/view/', views.quiz_view, name='quiz_view'),
    path('<int:quiz_id>/', views.quiz_view, name='quiz_detail'),
    path('attempt/<int:attempt_id>/view/', views.view_attempt, name='view_attempt'),
    # Active time tracking endpoints
    path('attempt/<int:attempt_id>/remaining-time/', views.get_remaining_time, name='get_remaining_time'),
    path('attempt/<int:attempt_id>/update-active-time/', views.update_active_time, name='update_active_time'),
    path('api/get_answer_texts/<int:question_id>/', views.get_answer_texts, name='get_answer_texts'),
    # Debug endpoint
    path('debug-answers/<int:attempt_id>/', views.debug_user_answer, name='debug_user_answer'),
]
