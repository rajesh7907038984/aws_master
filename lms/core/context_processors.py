from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from datetime import datetime, timedelta

def global_context(request):
    """
    Global context processor for common data across all pages
    """
    context = {}
    
    if request.user.is_authenticated:
        user = request.user
        context['user'] = user
        context['is_authenticated'] = True
    else:
        context['is_authenticated'] = False
    
    return context

def sidebar_context(request):
    """
    Context processor for sidebar data
    """
    context = {}
    
    if request.user.is_authenticated:
        user = request.user
        context['sidebar_user'] = user
        context['sidebar_authenticated'] = True
    else:
        context['sidebar_authenticated'] = False
    
    return context

def order_management_context(request):
    """
    Context processor for order management data
    """
    context = {}
    
    if request.user.is_authenticated:
        user = request.user
        context['order_management_user'] = user
        context['order_management_authenticated'] = True
    else:
        context['order_management_authenticated'] = False
    
    return context

def global_sidebar_context(request):
    """
    Context processor to provide data for global sidebars across all pages
    """
    context = {}
    
    if request.user.is_authenticated:
        user = request.user
        
        # Recent activities (last 5 activities)
        try:
            # This would need to be implemented based on your activity tracking system
            # For now, we'll provide empty data
            context['recent_activities'] = []
        except Exception:
            context['recent_activities'] = []
        
        # Quick stats for authenticated users
        try:
            # Course statistics
            if hasattr(user, 'enrolled_courses'):
                context['total_courses'] = user.enrolled_courses.count()
                context['completed_courses'] = user.enrolled_courses.filter(status='completed').count()
            else:
                context['total_courses'] = 0
                context['completed_courses'] = 0
            
            # Assignment statistics
            if hasattr(user, 'assignments'):
                context['pending_assignments'] = user.assignments.filter(status='pending').count()
            else:
                context['pending_assignments'] = 0
            
            # Certificate statistics
            if hasattr(user, 'certificates'):
                context['certificates_earned'] = user.certificates.count()
            else:
                context['certificates_earned'] = 0
                
        except Exception:
            context['total_courses'] = 0
            context['completed_courses'] = 0
            context['pending_assignments'] = 0
            context['certificates_earned'] = 0
        
        # Today's events/schedule
        try:
            # This would need to be implemented based on your calendar/event system
            # For now, we'll provide empty data
            context['today_events'] = []
        except Exception:
            context['today_events'] = []
    
    return context

def right_sidebar_context(request):
    """
    Context processor specifically for right sidebar data
    """
    context = {}
    
    if request.user.is_authenticated:
        user = request.user
        today = timezone.now().date()
        
        # Calendar data for Activity Calendar section
        try:
            # Generate week days for mini calendar
            week_days = []
            start_of_week = today - timedelta(days=today.weekday())
            
            for i in range(7):
                day_date = start_of_week + timedelta(days=i)
                week_days.append({
                    'day': day_date.day,
                    'date': day_date,
                    'is_today': day_date == today,
                    'has_events': False  # This would be determined by actual events
                })
            
            context['week_days'] = week_days
            
            # Recent calendar activities (mock data for now)
            context['recent_calendar_activities'] = []
            
        except Exception as e:
            context['week_days'] = []
            context['recent_calendar_activities'] = []
        
        # Todo data for Todo List section
        try:
            # Use the existing TodoService to get todos
            from core.services.todo_service import TodoService
            
            todo_service = TodoService(user)
            todos = todo_service.get_todos(limit=5)  # Get recent 5 todos
            
            # Calculate statistics from todos
            total_todos = len(todo_service.get_todos(limit=100))  # Get more for accurate count
            pending_todos = len([todo for todo in todo_service.get_todos(limit=100) if todo['priority'] in ['high', 'critical']])
            completed_today = 0  # This would need to be tracked separately
            
            # Format recent todos for template
            formatted_recent_todos = []
            for todo in todos:
                formatted_recent_todos.append({
                    'id': todo['id'],
                    'title': todo['title'],
                    'type': todo['type'],
                    'priority': todo['priority'],
                    'due_date': todo['due_date'],
                    'status': 'pending',  # All todos from service are pending
                    'url': todo['url'],
                    'metadata': todo['metadata']
                })
            
            context['total_todos'] = total_todos
            context['pending_todos'] = pending_todos
            context['completed_today'] = completed_today
            context['recent_todos'] = formatted_recent_todos
            
        except Exception as e:
            # Fallback if TodoService doesn't work
            context['total_todos'] = 0
            context['pending_todos'] = 0
            context['completed_today'] = 0
            context['recent_todos'] = []
    
    else:
        # Default values for non-authenticated users
        context['week_days'] = []
        context['recent_calendar_activities'] = []
        context['total_todos'] = 0
        context['pending_todos'] = 0
        context['completed_today'] = 0
        context['recent_todos'] = []
    
    return context