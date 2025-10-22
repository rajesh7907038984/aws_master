from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Q
from django.core.cache import cache
from django.conf import settings
import logging
import time

logger = logging.getLogger(__name__)

def sidebar_context(request):
    """
    Add sidebar todo data and calendar data to the global template context.
    This provides dynamic todo items and calendar events for the right sidebar component.
    Optimized with caching and error handling.
    """
    # Return empty context for unauthenticated users or AJAX requests
    if (not hasattr(request, 'user') or 
        not request.user.is_authenticated or 
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.path.startswith('/api/')):
        return {
            'sidebar_todo_all': [],
            'sidebar_todo_courses': [],
            'sidebar_todo_assignments': [],
            'sidebar_todo_discussions': [],
            'sidebar_calendar_events': [],
            'sidebar_current_month': '',
            # New dashboard fields
            'week_days': [],
            'recent_calendar_activities': [],
            'total_todos': 0,
            'pending_todos': 0,
            'completed_today': 0,
            'recent_todos': [],
        }

    user = request.user
    
    # Cache key based on user and current hour (refresh hourly)
    cache_key = f"sidebar_context_{user.id}_{timezone.now().hour}"
    
    # Try to get cached data first
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    # Generate fresh data
    try:
        context_data = _generate_sidebar_context(user)
        
        # Cache for 1 hour, or 5 minutes in development
        cache_timeout = 300 if settings.DEBUG else 3600  # 5 minutes in debug, 1 hour in production
        cache.set(cache_key, context_data, cache_timeout)
        
        return context_data
        
    except Exception as e:
        # Log the error but don't crash the page
        logger.error(f"Error in sidebar_context for user {user.id}: {str(e)}", exc_info=True)
        
        # Return empty context to prevent template crashes
        return {
            'sidebar_todo_all': [],
            'sidebar_todo_courses': [],
            'sidebar_todo_assignments': [],
            'sidebar_todo_discussions': [],
            'sidebar_calendar_events': [],
            'sidebar_current_month': timezone.now().strftime('%B %Y'),
            # New dashboard fields
            'week_days': [],
            'recent_calendar_activities': [],
            'total_todos': 0,
            'pending_todos': 0,
            'completed_today': 0,
            'recent_todos': [],
        }

def _generate_sidebar_context(user):
    """Generate the sidebar context data with optimized queries"""
    now = timezone.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)

    # Initialize empty lists
    all_tasks = []
    course_tasks = []
    assignment_tasks = []
    discussion_tasks = []
    calendar_events = []

    # Calendar month setup
    current_month = now.strftime('%B %Y')
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.get_current_timezone())
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.get_current_timezone())

    try:
        # Import models when needed with error handling
        try:
            from courses.models import CourseEnrollment, Course
            from assignments.models import Assignment, AssignmentSubmission
            from conferences.models import Conference
            from calendar_app.models import CalendarEvent
        except ImportError as e:
            logger.error(f"Model import error in sidebar_context: {e}")
            return _get_empty_sidebar_context()
        
        if user.role == 'learner':
            # Get learner's enrolled courses with optimized query [[memory:3584318]]
            try:
                enrolled_courses_ids = list(CourseEnrollment.objects.filter(
                    user=user
                ).select_related('course').values_list('course_id', flat=True))
            except Exception as e:
                logger.error(f"Error getting enrolled courses for user {user.id}: {e}")
                enrolled_courses_ids = []

            if enrolled_courses_ids:
                # Get course objects in a single query
                accessible_courses = Course.objects.filter(
                    id__in=enrolled_courses_ids,
                    is_active=True
                ).select_related('instructor')

                # Get pending assignments with optimized query [[memory:3584318]]
                try:
                    pending_assignments = Assignment.objects.filter(
                        Q(course__in=enrolled_courses_ids) |
                        Q(courses__in=enrolled_courses_ids) |
                        Q(topics__courses__in=enrolled_courses_ids),
                        is_active=True,
                        due_date__gte=now
                    ).exclude(
                        submissions__user=user,
                        submissions__status__in=['submitted', 'graded', 'not_graded']
                    ).distinct().select_related('course').order_by('due_date')[:5]  # Limit to 5
                except Exception as e:
                    logger.error(f"Error getting pending assignments for user {user.id}: {e}")
                    pending_assignments = []

                # Process assignments
                for assignment in pending_assignments:
                    due_date = assignment.due_date.date() if assignment.due_date else None
                    if due_date:
                        if due_date == today:
                            due_text, priority = "Today", 'high'
                        elif due_date == tomorrow:
                            due_text, priority = "Tomorrow", 'high'
                        elif due_date <= next_week:
                            due_text, priority = due_date.strftime('%a %b %d'), 'medium'
                        else:
                            due_text, priority = due_date.strftime('%b %d'), 'medium'
                    else:
                        due_text, priority = "No due date", 'low'

                    course_name = assignment.course.title if assignment.course else 'General Assignment'

                    task = {
                        'title': assignment.title,
                        'description': course_name,
                        'due_text': due_text,
                        'icon': 'file-alt',
                        'icon_color': 'orange-600',
                        'icon_bg': 'orange-100',
                        'type': 'assignment',
                        'url': f'/assignments/{assignment.id}/',
                        'priority': priority
                    }
                    
                    all_tasks.append(task)
                    assignment_tasks.append(task)

                # Get course progress efficiently - only courses with actual topic completion
                incomplete_enrollments = CourseEnrollment.objects.filter(
                    user=user,
                    course__in=enrolled_courses_ids,
                    completed=False
                ).select_related('course')
                
                # Filter to only those with actual progress (completed topics)
                in_progress_enrollments = []
                for enrollment in incomplete_enrollments:
                    try:
                        if enrollment.get_progress() > 0:
                            in_progress_enrollments.append(enrollment)
                    except Exception:
                        continue
                
                # Sort by last_accessed and limit to 3
                in_progress_enrollments = sorted(
                    in_progress_enrollments, 
                    key=lambda x: x.last_accessed, 
                    reverse=True
                )[:3]

                for enrollment in in_progress_enrollments:
                    progress_percentage = enrollment.progress_percentage
                    
                    task = {
                        'title': f'Continue: {enrollment.course.title}',
                        'description': f'{progress_percentage}% complete',
                        'due_text': 'In Progress',
                        'icon': 'book-open',
                        'icon_color': 'blue-600',
                        'icon_bg': 'blue-100',
                        'type': 'course',
                        'url': f'/courses/{enrollment.course.id}/view/',
                        'priority': 'low'
                    }
                    
                    all_tasks.append(task)
                    course_tasks.append(task)

                # Calendar events - limit queries
                assignments_due = Assignment.objects.filter(
                    Q(course__in=enrolled_courses_ids),
                    is_active=True,
                    due_date__gte=month_start,
                    due_date__lt=month_end
                ).exclude(
                    submissions__user=user,
                    submissions__status__in=['submitted', 'graded', 'not_graded']
                ).distinct().select_related('course')[:10]  # Limit calendar events

                for assignment in assignments_due:
                    calendar_events.append({
                        'day': assignment.due_date.day,
                        'title': assignment.title,
                        'type': 'assignment',
                        'color': '#ef4444',
                        'course': assignment.course.title if assignment.course else 'General',
                        'date': assignment.due_date,
                        'url': f'/assignments/{assignment.id}/'
                    })

        elif user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']:
            # For instructors/admins - get accessible courses efficiently
            if user.role == 'globaladmin':
                accessible_courses_ids = list(Course.objects.filter(
                    is_active=True
                ).values_list('id', flat=True)[:20])  # Limit for performance
            elif user.role == 'admin' and user.branch:
                accessible_courses_ids = list(Course.objects.filter(
                    branch=user.branch, 
                    is_active=True
                ).values_list('id', flat=True)[:20])
            elif user.role == 'instructor' and user.branch:
                accessible_courses_ids = list(Course.objects.filter(
                    Q(instructor=user) | 
                    Q(accessible_groups__memberships__user=user,
                      accessible_groups__memberships__is_active=True),
                    branch=user.branch,
                    is_active=True
                ).distinct().values_list('id', flat=True)[:20])
            else:
                accessible_courses_ids = []

            if accessible_courses_ids:
                # Get submissions pending grading [[memory:3584318]]
                pending_submissions = AssignmentSubmission.objects.filter(
                    assignment__course__in=accessible_courses_ids,
                    status='submitted'
                ).select_related('assignment', 'assignment__course', 'user').order_by('submitted_at')[:5]  # Limit to 5

                for submission in pending_submissions:
                    days_since = (now.date() - submission.submitted_at.date()).days
                    if days_since == 0:
                        due_text, priority = "Today", 'high'
                    elif days_since == 1:
                        due_text, priority = "Yesterday", 'high'
                    else:
                        due_text, priority = f"{days_since} days ago", 'medium'

                    course_name = submission.assignment.course.title if submission.assignment.course else 'Assignment'
                    
                    task = {
                        'title': f'Grade: {submission.assignment.title}',
                        'description': f'{submission.user.get_full_name()} - {course_name}',
                        'due_text': due_text,
                        'icon': 'check-circle',
                        'icon_color': 'purple-600',
                        'icon_bg': 'purple-100',
                        'type': 'grading',
                        'url': f'/assignments/{submission.assignment.id}/',
                        'priority': priority
                    }
                    
                    all_tasks.append(task)
                    assignment_tasks.append(task)

        # Sort and limit results
        priority_order = {'high': 1, 'medium': 2, 'low': 3}
        all_tasks.sort(key=lambda x: priority_order.get(x['priority'], 4))
        
        # Limit final results
        all_tasks = all_tasks[:6]
        assignment_tasks = assignment_tasks[:4]
        course_tasks = course_tasks[:4]
        discussion_tasks = discussion_tasks[:3]
        
        # Sort calendar events
        calendar_events.sort(key=lambda x: x['day'])

    except Exception as e:
        logger.error(f"Error generating sidebar context for user {user.id}: {str(e)}")
        # Return minimal data on error
        all_tasks = []
        course_tasks = []
        assignment_tasks = []
        discussion_tasks = []
        calendar_events = []

    # Generate week days for mini calendar
    week_days = _generate_week_days()
    
    # Generate recent calendar activities (upcoming this week)
    recent_calendar_activities = _generate_recent_calendar_activities(calendar_events, all_tasks)
    
    # Calculate todo stats
    total_todos = len(all_tasks)
    pending_todos = len([task for task in all_tasks if task['priority'] in ['high', 'medium']])
    completed_today = 0  # This would need to be calculated from actual completion data
    
    # Recent todos (same as all_tasks but with different formatting)
    recent_todos = [{
        'title': task['title'],
        'type': task['type'].title(),
        'priority': task['priority'],
        'due_date': None,  # You might want to parse this from due_text
        'url': task['url']
    } for task in all_tasks]

    return {
        # Template context variables
        'sidebar_todo_all': all_tasks,
        'sidebar_todo_courses': course_tasks,
        'sidebar_todo_assignments': assignment_tasks,
        'sidebar_todo_discussions': discussion_tasks,
        'sidebar_calendar_events': calendar_events,
        'sidebar_current_month': current_month,
        
        # New dashboard data
        'week_days': week_days,
        'recent_calendar_activities': recent_calendar_activities,
        'total_todos': total_todos,
        'pending_todos': pending_todos,
        'completed_today': completed_today,
        'recent_todos': recent_todos,
    }

def _get_empty_sidebar_context():
    """Return empty sidebar context when errors occur"""
    return {
        'sidebar_todo_all': [],
        'sidebar_todo_courses': [],
        'sidebar_todo_assignments': [],
        'sidebar_todo_discussions': [],
        'sidebar_calendar_events': [],
        'sidebar_current_month': timezone.now().strftime('%B %Y'),
        'week_days': [],
        'recent_calendar_activities': [],
        'total_todos': 0,
        'pending_todos': 0,
        'completed_today': 0,
        'recent_todos': [],
    }

def _generate_week_days():
    """Generate week days data for mini calendar"""
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday() + 1)  # Start from Sunday
    week_days = []
    
    for i in range(7):
        current_day = week_start + timedelta(days=i)
        week_days.append({
            'day': current_day.day,
            'is_today': current_day == today,
            'has_events': False,  # This could be enhanced to check for actual events
        })
    
    return week_days

def _generate_recent_calendar_activities(calendar_events, all_tasks):
    """Generate recent calendar activities from events and tasks"""
    activities = []
    now = timezone.now()
    week_from_now = now + timedelta(days=7)
    
    # Add calendar events happening this week
    for event in calendar_events:
        if hasattr(event, 'get') and event.get('date'):
            event_date = event['date']
            if now <= event_date <= week_from_now:
                activities.append({
                    'title': event.get('title', 'Event'),
                    'date': event_date,
                    'icon': 'calendar',
                    'type': 'event'
                })
    
    # Add high priority tasks as activities
    for task in all_tasks[:3]:  # Limit to top 3 tasks
        if task['priority'] in ['high', 'medium']:
            activities.append({
                'title': task['title'],
                'date': now,  # Default to now for tasks without specific dates
                'icon': task.get('icon', 'tasks'),
                'type': 'task'
            })
    
    # Sort by date and limit
    activities.sort(key=lambda x: x['date'])
    return activities[:4]

def order_management_context(request):
    """Context processor to provide order management status for sidebar menus"""
    context = {
        'show_order_management_menu': False,
        'global_order_management_enabled': False,
        'branch_order_management_enabled': False,
    }
    
    if not request.user.is_authenticated:
        return context
    
    # Cache key based on user and current hour (refresh hourly)
    cache_key = f"order_management_context_{request.user.id}_{timezone.now().hour}"
    
    # Try to get cached data first
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    try:
        # Check global order management settings
        from account_settings.models import GlobalAdminSettings
        global_settings = GlobalAdminSettings.get_settings()
        global_enabled = global_settings.order_management_enabled if global_settings else False
        context['global_order_management_enabled'] = global_enabled
        
        # If global is disabled, hide for everyone including global admin
        if not global_enabled:
            context['show_order_management_menu'] = False
            # Cache the result
            cache.set(cache_key, context, 3600)  # Cache for 1 hour
            return context
        
        user_role = request.user.role
        
        # For Global Admin - show only if global is enabled (already checked above)
        if user_role == 'globaladmin':
            context['show_order_management_menu'] = True
        
        # For Branch Admin - show if their branch has it enabled AND global is enabled
        elif user_role == 'admin' and hasattr(request.user, 'branch') and request.user.branch:
            branch_enabled = getattr(request.user.branch, 'order_management_enabled', False)
            context['branch_order_management_enabled'] = branch_enabled
            context['show_order_management_menu'] = branch_enabled
        
        # For Super Admin - show if ANY branch in their business has it enabled AND global is enabled
        elif user_role == 'superadmin':
            if hasattr(request.user, 'business_assignments'):
                # Get businesses assigned to this super admin
                business_assignments = request.user.business_assignments.filter(is_active=True)
                businesses = [assignment.business for assignment in business_assignments]
                
                # Check if any branch in these businesses has order management enabled
                from branches.models import Branch
                enabled_branches = Branch.objects.filter(
                    business__in=businesses,
                    order_management_enabled=True,
                    is_active=True
                ).exists()
                
                context['show_order_management_menu'] = enabled_branches
        
        # Cache the result
        cache.set(cache_key, context, 3600)  # Cache for 1 hour
            
    except Exception as e:
        # Fail silently in case of any errors
        pass
    
    return context

def global_context(request):
    """
    Global context processor that provides common variables to all templates
    """
    context = {}
    
    # Add security status if user is authenticated
    if hasattr(request, 'user') and request.user and request.user.is_authenticated:
        # Get security status from cache or create default
        cache_key = f"security_status_{request.user.id}"
        security_status = cache.get(cache_key, {
            'warning_level': 'none',
            'failure_count': 0,
            'remaining_attempts': 10,
            'max_attempts': 5,
            'lockout_minutes': 0,
            'remaining_time': 0,
            'is_blocked': False,
            'rate_limited': False,
            'rate_limit_type': None,
            'rate_remaining_time': 0,
            'rate_current_count': 0,
            'rate_max_count': 0
        })
        context['security_status'] = security_status
    else:
        # Default security status for anonymous users
        context['security_status'] = {
            'warning_level': 'none',
            'failure_count': 0,
            'remaining_attempts': 10,
            'max_attempts': 5,
            'lockout_minutes': 0,
            'remaining_time': 0,
            'is_blocked': False,
            'rate_limited': False,
            'rate_limit_type': None,
            'rate_remaining_time': 0,
            'rate_current_count': 0,
            'rate_max_count': 0
        }
    
    return context 