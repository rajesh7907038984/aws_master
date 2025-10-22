from django.urls import path
from . import views

app_name = 'gradebook'

urlpatterns = [
    path('', views.gradebook_index, name='index'),
    path('', views.gradebook_index, name='gradebook'),  # Alias for consistency
    path('course/<int:course_id>/', views.course_gradebook_detail, name='course_detail'),
    path('export/<int:course_id>/', views.export_gradebook_csv, name='export_csv'),
    path('grade-sidebar/assignment/<int:assignment_id>/<int:student_id>/', views.assignment_grade_sidebar, name='assignment_grade_sidebar'),
    path('grade-sidebar/quiz/<int:quiz_id>/<int:student_id>/', views.quiz_grade_sidebar, name='quiz_grade_sidebar'),
    path('grade-sidebar/discussion/<int:discussion_id>/<int:student_id>/', views.discussion_grade_sidebar, name='discussion_grade_sidebar'),
    path('grade-sidebar/conference/<int:conference_id>/<int:student_id>/', views.conference_grade_sidebar, name='conference_grade_sidebar'),
    path('ajax/save-grade/', views.ajax_save_grade, name='ajax_save_grade'),
] 