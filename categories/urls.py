from django.urls import path
from . import views
from . import views_simple

app_name = 'categories'

urlpatterns = [
    path('', views.category_list, name='category_list'),
    path('list/', views.category_api_list, name='category_api_list'),
    path('create/', views.category_create, name='category_create'),
    path('ajax-create/', views.ajax_category_create, name='ajax_category_create'),
    path('simple-create/', views_simple.simple_category_create, name='simple_category_create'),
    path('check-slug/', views.check_slug_exists, name='check_slug_exists'),
    path('<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('<int:pk>/delete/', views.category_delete, name='category_delete'),
] 