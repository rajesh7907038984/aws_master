from django.urls import path
from . import views

app_name = 'course_reviews'

urlpatterns = [
    # Survey Management (Admin/Instructor)
    path('surveys/', views.survey_list, name='survey_list'),
    path('surveys/create/', views.survey_create, name='survey_create'),
    path('surveys/<int:survey_id>/edit/', views.survey_edit, name='survey_edit'),
    path('surveys/<int:survey_id>/delete/', views.survey_delete, name='survey_delete'),
    path('surveys/<int:survey_id>/preview/', views.survey_preview, name='survey_preview'),
    
    # Survey Field Management
    path('surveys/<int:survey_id>/fields/add/', views.survey_field_add, name='survey_field_add'),
    path('surveys/<int:survey_id>/fields/<int:field_id>/edit/', views.survey_field_edit, name='survey_field_edit'),
    path('surveys/<int:survey_id>/fields/<int:field_id>/delete/', views.survey_field_delete, name='survey_field_delete'),
    
    # Survey Submission (Learner)
    path('course/<int:course_id>/survey/', views.submit_course_survey, name='submit_course_survey'),
    
    # Course Reviews Display
    path('course/<int:course_id>/reviews/', views.course_reviews_list, name='course_reviews_list'),
    path('course/<int:course_id>/reviews/<int:review_id>/', views.course_review_detail, name='course_review_detail'),
    
    # API Endpoints
    path('api/course/<int:course_id>/average-rating/', views.get_course_average_rating, name='get_course_average_rating'),
    path('api/surveys/<int:survey_id>/responses/', views.survey_responses, name='survey_responses'),
]
