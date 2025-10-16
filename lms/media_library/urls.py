from django.urls import path
from . import views

app_name = 'media_library'

urlpatterns = [
    path('', views.media_dashboard, name='dashboard'),
    path('browser/', views.file_browser, name='browser'),
    path('statistics/', views.storage_statistics, name='statistics'),
    path('file/<int:file_id>/', views.file_detail, name='file_detail'),
    path('serve/<int:file_id>/', views.serve_local_file, name='serve_local_file'),
    path('sync/', views.sync_media_files, name='sync_files'),
    path('bulk-delete/', views.bulk_delete_files, name='bulk_delete'),
]
