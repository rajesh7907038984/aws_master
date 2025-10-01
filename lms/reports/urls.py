from django.urls import path
from . import views
from .views import BranchReportView, CourseReportView, GroupReportView, CustomReportsView

app_name = 'reports'

urlpatterns = [
    path('overview/', views.overview, name='overview'),
    # path('overview/activity-data/', views.get_activity_data, name='get_activity_data'),
    path('training-matrix/', views.training_matrix, name='training_matrix'),
    path('timeline/', views.timeline, name='timeline'),
    path('subgroups/', views.subgroup_report, name='subgroup_report'),
    path('subgroups/<int:subgroup_id>/', views.subgroup_detail, name='subgroup_detail'),
    path('subgroups/<int:subgroup_id>/excel/', views.subgroup_detail_excel, name='subgroup_detail_excel'),
    path('', views.reports_view, name='reports'),
    path('new/', views.new_report, name='new_report'),
    path('<int:report_id>/', views.report_detail, name='report_detail'),
    path('<int:report_id>/edit/', views.edit_report, name='edit_report'),
    path('<int:report_id>/delete/', views.delete_report, name='delete_report'),
    path('upload-attachment/', views.upload_attachment, name='upload_attachment'),
    path('users/', views.user_reports_list, name='user_reports'),
    path('users/<int:user_id>/', views.user_detail_report, name='user_detail_report'),
    path('users/<int:user_id>/load-more-activities/', views.load_more_activities, name='load_more_activities'),
    
    # User report sections as separate pages
    path('users/<int:user_id>/overview/', views.user_report_overview, name='user_report_overview'),
    path('users/<int:user_id>/courses/', views.user_report_courses, name='user_report_courses'),
    path('users/<int:user_id>/learning-activities/', views.user_report_activities, name='user_report_activities'),
    path('users/<int:user_id>/initial-assessments/', views.user_report_assessments, name='user_report_assessments'),
    path('users/<int:user_id>/certificates/', views.user_report_certificates, name='user_report_certificates'),
    path('users/<int:user_id>/timeline/', views.user_report_timeline, name='user_report_timeline'),
    
    # My learning report sections
    path('my-learning-report/', views.my_report, name='my_learning_report'),
    path('my-learning-report/overview/', views.my_report_overview, name='my_report_overview'),
    path('my-learning-report/courses/', views.my_report_courses, name='my_report_courses'),
    path('my-learning-report/learning-activities/', views.my_report_activities, name='my_report_activities'),
    path('my-learning-report/initial-assessments/', views.my_report_assessments, name='my_report_assessments'),
    path('my-learning-report/certificates/', views.my_report_certificates, name='my_report_certificates'),
    path('my-learning-report/timeline/', views.my_report_timeline, name='my_report_timeline'),
    path('my-report/', views.my_report, name='my_report'),
    path('branch/', BranchReportView.as_view(), name='branch_report'),
    path('branch/<int:branch_id>/', views.branch_detail, name='branch_detail'),
    path('branch/<int:branch_id>/excel/', views.branch_detail_excel, name='branch_detail_excel'),
    path('groups/<int:group_id>/', views.group_detail, name='group_detail'),
    path('courses/', views.courses_report, name='courses_report'),
    path('courses/<int:course_id>/', views.course_detail, name='course_detail'),
    path('courses/<int:course_id>/report/', views.course_report_overview, name='course_report'),  # Redirect to overview
    
    # Course report sections as separate pages
    path('courses/<int:course_id>/overview/', views.course_report_overview, name='course_report_overview'),
    path('courses/<int:course_id>/users/', views.course_report_users, name='course_report_users'),
    path('courses/<int:course_id>/learning-activities/', views.course_report_activities, name='course_report_activities'),
    path('courses/<int:course_id>/unit-matrix/', views.course_report_matrix, name='course_report_matrix'),
    path('courses/<int:course_id>/timeline/', views.course_report_timeline, name='course_report_timeline'),
    path('courses/<int:course_id>/timeline/excel/', views.course_timeline_excel, name='course_timeline_excel'),
    # path('courses/<int:course_id>/unit-success-data/', views.unit_success_data_api, name='unit_success_data_api'),
    path('groups/', GroupReportView.as_view(), name='group_report'),
    path('custom/', CustomReportsView.as_view(), name='custom_reports'),
    path('learning-activities/', views.LearningActivitiesView.as_view(), name='learning_activities'),
    path('activity/<int:activity_id>/overview/', views.activity_report_overview, name='activity_report_overview'),
    path('dashboard/', views.reports_dashboard, name='dashboard'),
] 