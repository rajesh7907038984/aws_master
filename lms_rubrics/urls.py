from django.urls import path
from . import views

app_name = 'lms_rubrics'

urlpatterns = [
    path('', views.rubric_list, name='list'),
    path('create/', views.create_rubric, name='create'),
    path('<int:rubric_id>/', views.rubric_detail, name='detail'),
    path('<int:rubric_id>/edit/', views.edit_rubric, name='edit'),
    path('<int:rubric_id>/delete/', views.delete_rubric, name='delete'),
    path('add_criterion/<int:rubric_id>/', views.add_criterion, name='add_criterion'),
    path('criterion/<int:criterion_id>/delete/', views.delete_criterion, name='delete_criterion'),
    path('criterion/<int:criterion_id>/edit/', views.edit_criterion, name='edit_criterion'),
    path('criterion/<int:criterion_id>/add_rating/', views.add_rating, name='add_rating'),
    path('rating/<int:rating_id>/delete/', views.delete_rating, name='delete_rating'),
    path('rating/<int:rating_id>/edit/', views.edit_rating, name='edit_rating'),
    path('update_criterion_range/<int:criterion_id>/', views.update_criterion_range, name='update_criterion_range'),
] 