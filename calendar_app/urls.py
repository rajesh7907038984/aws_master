from django.urls import path
from . import views

app_name = 'calendar_app'

urlpatterns = [
    path('', views.calendar_view, name='calendar'),
    path('add/', views.add_event_view, name='add_event'),
    path('events/', views.get_events, name='get_events'),
    path('events/create/', views.create_event, name='create_event'),
    path('events/<int:event_id>/', views.update_event, name='update_event'),
    # API endpoints for dashboard calendar
    path('api/activities/', views.get_activities, name='get_activities'),
    path('api/daily/<str:date>/', views.get_daily_activities, name='get_daily_activities'),
] 