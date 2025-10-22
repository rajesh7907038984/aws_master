from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import CalendarEvent
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
import json

@login_required
def calendar_view(request):
    """Main calendar view showing the calendar interface."""
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'label': 'Calendar', 'icon': 'fa-calendar'}
    ]
    context = {
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'calendar/calendar.html', context)

@login_required
def add_event_view(request):
    """Add event page with form."""
    breadcrumbs = [
        {'url': '/', 'label': 'Dashboard', 'icon': 'fa-home'},
        {'url': '/calendar/', 'label': 'Calendar', 'icon': 'fa-calendar'},
        {'label': 'Add Event', 'icon': 'fa-plus'}
    ]
    context = {
        'breadcrumbs': breadcrumbs
    }
    return render(request, 'calendar/add_event.html', context)

@login_required
def get_events(request):
    """API endpoint to get calendar events."""
    start = request.GET.get('start')
    end = request.GET.get('end')
    
    events = CalendarEvent.objects.filter(created_by=request.user)
    if start:
        events = events.filter(start_date__gte=start)
    if end:
        events = events.filter(end_date__lte=end)
    
    event_list = []
    for event in events:
        event_list.append({
            'id': event.id,
            'title': event.title,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'allDay': event.is_all_day,
            'color': event.color,
        })
    return JsonResponse(event_list, safe=False)

@login_required
@require_http_methods(['POST'])
def create_event(request):
    """Create a new calendar event."""
    try:
        data = json.loads(request.body)
        
        # Convert ISO format strings to datetime objects
        start_date = timezone.datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        end_date = timezone.datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
        
        event = CalendarEvent.objects.create(
            title=data['title'],
            description=data.get('description', ''),
            start_date=start_date,
            end_date=end_date,
            is_all_day=data.get('allDay', False),
            color=data.get('color', '#3498db'),
            is_recurring=data.get('is_recurring', False),
            notification=data.get('notification', 'none'),
            tags=data.get('tags', ''),
            created_by=request.user
        )
        
        return JsonResponse({
            'id': event.id,
            'title': event.title,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'allDay': event.is_all_day,
            'color': event.color,
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except KeyError as e:
        return JsonResponse({'error': f'Missing required field: {str(e)}'}, status=400)
    except ValueError as e:
        return JsonResponse({'error': f'Invalid date format: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error creating event: {str(e)}'}, status=500)

@login_required
@require_http_methods(['PUT', 'DELETE'])
def update_event(request, event_id):
    """Update or delete an existing calendar event."""
    event = get_object_or_404(CalendarEvent, id=event_id, created_by=request.user)
    
    if request.method == 'DELETE':
        event.delete()
        return JsonResponse({'status': 'success'})
    
    try:
        data = json.loads(request.body)
        
        # Update basic fields
        event.title = data.get('title', event.title)
        event.description = data.get('description', event.description)
        
        # Convert ISO format strings to datetime objects if provided
        if 'start' in data:
            event.start_date = timezone.datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        if 'end' in data:
            event.end_date = timezone.datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
            
        event.is_all_day = data.get('allDay', event.is_all_day)
        event.color = data.get('color', event.color)
        event.save()
        
        return JsonResponse({
            'id': event.id,
            'title': event.title,
            'start': event.start_date.isoformat(),
            'end': event.end_date.isoformat(),
            'allDay': event.is_all_day,
            'color': event.color,
        })
    except (json.JSONDecodeError, ValueError) as e:
        return JsonResponse({'error': f'Invalid data format: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Error updating event: {str(e)}'}, status=500)

@login_required
def get_activities(request):
    """API endpoint to get activities for dashboard calendar."""
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Get user's calendar events
        events = CalendarEvent.objects.filter(created_by=request.user)
        
        if start_date:
            start_date = parse_date(start_date)
            events = events.filter(start_date__gte=start_date)
        if end_date:
            end_date = parse_date(end_date)
            events = events.filter(end_date__lte=end_date)
        
        activities = []
        for event in events:
            activities.append({
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'date': event.start_date.strftime('%Y-%m-%d'),
                'type': 'calendar_event',
                'priority': 'medium',
                'url': f'/calendar/events/{event.id}/',
                'color': event.color
            })
        
        return JsonResponse({
            'success': True,
            'activities': activities
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error fetching activities: {str(e)}'
        }, status=500)

@login_required
def get_daily_activities(request, date):
    """API endpoint to get activities for a specific date."""
    try:
        # Parse the date string (format: YYYY-MM-DD)
        target_date = parse_date(date)
        if not target_date:
            return JsonResponse({
                'success': False,
                'error': 'Invalid date format'
            }, status=400)
        
        # Get events for the specific date
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        events = CalendarEvent.objects.filter(
            created_by=request.user,
            start_date__date=target_date
        )
        
        activities = []
        for event in events:
            activities.append({
                'id': event.id,
                'title': event.title,
                'description': event.description,
                'date': event.start_date.strftime('%Y-%m-%d'),
                'type': 'calendar_event',
                'priority': 'medium',
                'url': f'/calendar/events/{event.id}/',
                'color': event.color
            })
        
        return JsonResponse({
            'success': True,
            'activities': activities
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error fetching daily activities: {str(e)}'
        }, status=500) 