from django.urls import path
from . import views

app_name = 'ilp'

urlpatterns = [
    # Create ILP Components
    path('<int:user_id>/create/<str:component>/', views.create_ilp_component, name='create_component'),
    
    # Edit ILP Components
    path('<int:user_id>/edit/<str:component>/', views.edit_ilp_component, name='edit_component'),
    path('<int:user_id>/edit/<str:component>/<int:component_id>/', views.edit_ilp_component, name='edit_component_id'),
    
    # Delete ILP Components
    path('<int:user_id>/delete/<str:component>/<int:component_id>/', views.delete_ilp_component, name='delete_component'),
    
    # Learning Progress
    path('<int:user_id>/goal/<int:goal_id>/progress/', views.add_learning_progress, name='add_progress'),
    
    # Induction Checklist
    path('<int:user_id>/induction/', views.manage_induction_checklist, name='manage_induction_checklist'),
    path('<int:user_id>/induction/document/<int:document_id>/read/', views.mark_document_read, name='mark_document_read'),
    path('<int:user_id>/induction/document/<int:document_id>/download/', views.download_induction_document, name='download_induction_document'),
    
    # Health & Safety Questionnaire
    path('<int:user_id>/health-safety/', views.manage_health_safety_questionnaire, name='manage_health_safety_questionnaire'),
    path('health-safety-document/<int:document_id>/mark-read/', views.mark_health_safety_document_read, name='mark_health_safety_document_read'),
    path('<int:user_id>/health-safety/document/<int:document_id>/download/', views.download_health_safety_document, name='download_health_safety_document'),
    
    # API Endpoints
    path('api/<int:user_id>/data/', views.ilp_api_data, name='api_data'),
] 