from django.urls import path
from . import views

app_name = 'lms_outcomes'

urlpatterns = [
    path('', views.outcomes_index, name='index'),
    path('', views.outcomes_index, name='outcome_list'),  # Alias for consistency
    path('create/', views.create_outcome, name='create_outcome'),
    path('create/', views.create_outcome, name='outcome_create'),  # Alias for consistency
    path('manage/', views.outcomes_manage, name='manage'),
    path('alignments/', views.outcomes_alignments, name='alignments'),
    path('groups/create/', views.create_outcome_group, name='create_group'),
    path('groups/create/ajax/', views.create_outcome_group_ajax, name='create_group_ajax'),
    path('groups/rename/', views.rename_group, name='rename_group'),
    path('groups/delete/', views.delete_group, name='delete_group'),
    path('create/', views.create_outcome, name='create_outcome'),
    path('edit/<int:outcome_id>/', views.edit_outcome, name='edit_outcome'),
    path('import/', views.import_outcomes, name='import_outcomes'),
    path('import/template/', views.download_template, name='download_template'),
    path('import/mappings/', views.import_rubric_outcome_mappings, name='import_mappings'),
    path('recalculate/', views.recalculate_outcome_evaluations, name='recalculate_evaluations'),
    path('delete/', views.delete_outcomes, name='delete_outcomes'),
    path('move/', views.move_outcomes, name='move_outcomes'),
    path('api/outcomes/', views.get_outcomes_api, name='get_outcomes_api'),
    path('api/outcome/<int:outcome_id>/', views.get_outcome_detail_api, name='get_outcome_detail_api'),
    path('api/rubric-connections/', views.manage_rubric_connections_api, name='manage_rubric_connections_api'),
    path('test/<int:outcome_id>/', views.test_outcome_view, name='test_outcome_view'),
] 