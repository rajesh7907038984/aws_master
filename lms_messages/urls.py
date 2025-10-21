from django.urls import path
from . import views

app_name = 'lms_messages'

urlpatterns = [
    path('', views.messages_view, name='messages'),
    path('new/', views.new_message, name='new_message'),
    path('upload-image/', views.upload_image, name='upload_image'),
    path('<int:message_id>/', views.message_detail, name='message_detail'),
    path('<int:message_id>/reply/', views.reply_message, name='reply_message'),
    path('<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('<int:message_id>/mark-read/', views.mark_as_read, name='mark_as_read'),
    path('mark-all-read/', views.mark_all_as_read, name='mark_all_as_read'),
    path('api/count/', views.message_count_api, name='message_count_api'),
] 