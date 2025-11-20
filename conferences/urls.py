from django.urls import path, include
from . import views

app_name = 'conferences'

urlpatterns = [
    # Existing URLs
    path('', views.conference_list, name='conference_list'),
    path('new/', views.new_conference, name='new_conference'),
    path('new/', views.new_conference, name='conference_create'),  # Alias for consistency
    path('new/<int:course_id>/', views.new_conference, name='new_conference_course'),
    path('<int:conference_id>/', views.conference_detail, name='conference_detail'),
    path('<int:conference_id>/edit/', views.edit_conference, name='edit_conference'),
    path('<int:conference_id>/clone/', views.clone_conference, name='clone_conference'),
    path('<int:conference_id>/delete/', views.delete_conference, name='delete_conference'),
    path('<int:conference_id>/join/', views.join_conference, name='join_conference'),
    path('<int:conference_id>/public/', views.conference_public_access, name='conference_public_access'),
    path('<int:conference_id>/guest-join/', views.guest_join_conference, name='guest_join_conference'),
    path('<int:conference_id>/sync/', views.sync_conference_data, name='sync_conference_data'),
    path('<int:conference_id>/scores/', views.conference_scores, name='conference_scores'),
    path('<int:conference_id>/detailed-report/', views.conference_detailed_report, name='conference_detailed_report'),
    path('<int:conference_id>/evaluate/', views.evaluate_conference_rubric, name='evaluate_rubric'),
    path('<int:conference_id>/bulk-evaluate/', views.bulk_evaluate_conference, name='bulk_evaluate'),
    path('<int:conference_id>/upload-file/', views.upload_conference_file, name='upload_conference_file'),
    path('<int:conference_id>/return/', views.return_from_meeting, name='return_from_meeting'),
    path('<int:conference_id>/redirect/', views.conference_redirect_handler, name='conference_redirect_handler'),
    path('<int:conference_id>/auto-register-join/', views.auto_register_and_join, name='auto_register_and_join'),
    path('<int:conference_id>/recording/<int:recording_id>/download/', views.download_conference_recording, name='download_conference_recording'),
    
    # API endpoints
    path('api/create-meeting/', views.create_meeting_api, name='create_meeting_api'),
    path('api/create-direct-join-meeting/', views.create_direct_join_meeting_api, name='create_direct_join_meeting_api'),
    path('api/generate-simple-zoom-link/', views.generate_simple_zoom_link, name='generate_simple_zoom_link'),
    
    # Health Check and Monitoring APIs - NEW
    path('health-check/', views.health_check_conference_sync, name='health_check_system'),
    path('health-check/<int:conference_id>/', views.health_check_conference_sync, name='health_check_conference'),
    path('auto-recover/<int:conference_id>/', views.auto_recover_conference_api, name='auto_recover_conference'),
    path('sync-status/', views.sync_status_dashboard, name='sync_status_dashboard'),
    
    # Time Slot Management
    path('<int:conference_id>/time-slots/', views.manage_time_slots, name='manage_time_slots'),
    path('<int:conference_id>/time-slots/<int:slot_id>/select/', views.select_time_slot, name='select_time_slot'),
    path('<int:conference_id>/time-slots/unselect/', views.unselect_time_slot, name='unselect_time_slot'),
    path('<int:conference_id>/time-slots/<int:slot_id>/unselect/', views.unselect_time_slot, name='unselect_specific_time_slot'),
    path('<int:conference_id>/time-slots/<int:slot_id>/retry-calendar/', views.retry_calendar_sync, name='retry_calendar_sync'),
]
