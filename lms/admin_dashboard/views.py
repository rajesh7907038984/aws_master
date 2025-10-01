from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from courses.models import Course, CourseEnrollment
from users.models import CustomUser
from branches.models import Branch
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import ContentType as AuthContentType
from django.urls import reverse
from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
import json
import logging
import psutil
import gc

# Memory monitoring
logger = logging.getLogger(__name__)

def get_memory_usage():
    """Get current memory usage in MB"""
    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # Convert to MB
    except:
        return 0

def monitor_memory_usage(func_name, initial_memory=None):
    """Log memory usage for debugging"""
    current_memory = get_memory_usage()
    if initial_memory:
        memory_diff = current_memory - initial_memory
        logger.info(f"{func_name}: Memory usage {current_memory:.1f}MB (diff: {memory_diff:+.1f}MB)")
    else:
        logger.info(f"{func_name}: Memory usage {current_memory:.1f}MB")
    return current_memory

def cleanup_memory():
    """Force garbage collection and cleanup"""
    gc.collect()
    
# Cache keys
CACHE_KEY_PORTAL_ACTIVITY = "admin_dashboard_portal_activity_{}_v2"
CACHE_KEY_DASHBOARD_DATA = "admin_dashboard_data_{}_v2"
CACHE_TIMEOUT = 300  # 5 minutes

# Create your views here.

class SuperAdminDashboardView(UserPassesTestMixin, TemplateView):
    template_name = 'users/dashboards/superadmin.html'

    def test_func(self):
        return self.request.user.is_authenticated and hasattr(self.request.user, 'role') and self.request.user.role == 'superadmin'
    
    def get(self, request, *args, **kwargs):
        # Handle AJAX requests for portal activity timeframe changes
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and ('portal_activity_timeframe' in request.GET or 'timeframe' in request.GET):
            timeframe = request.GET.get('timeframe') or request.GET.get('portal_activity_timeframe', 'month')
            portal_activity_data = self.get_portal_activity_data(timeframe)
            return JsonResponse({
                'labels': portal_activity_data['labels'],
                'logins': portal_activity_data['logins'], 
                'completions': portal_activity_data['completions']
            })
        
        return super().get(request, *args, **kwargs)
    
    def get_portal_activity_data(self, timeframe='month'):
        """Calculate portal activity data for different timeframes with caching and memory optimization"""
        # Memory monitoring
        initial_memory = monitor_memory_usage("get_portal_activity_data_start")
        
        # Try to get from cache first
        cache_key = CACHE_KEY_PORTAL_ACTIVITY.format(f"{self.request.user.id}_{timeframe}")
        cached_data = cache.get(cache_key)
        if cached_data:
            monitor_memory_usage("get_portal_activity_data_cached", initial_memory)
            return cached_data
        
        from core.utils.business_filtering import filter_queryset_by_business
        
        now = timezone.now()
        
        # Determine the number of days and labels based on timeframe
        if timeframe == 'day':
            days = 1
            labels = []
            # For hourly data within the day
            daily_logins = []
            daily_completions = []
            
            accessible_enrollments = filter_queryset_by_business(
                CourseEnrollment.objects.all(),
                self.request.user,
                business_field_path='course__branch__business'
            )
            user_ct = ContentType.objects.get_for_model(CustomUser)
            
            for hour in range(24):
                hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                hour_str = hour_start.strftime('%H:%M')
                labels.append(hour_str)
                
                # Count logins for this hour
                login_count = LogEntry.objects.filter(
                    content_type=user_ct,
                    action_time__gte=hour_start,
                    action_time__lt=hour_end
                ).count()
                daily_logins.append(login_count)
                
                # Count course completions for this hour
                completion_count = accessible_enrollments.filter(
                    completion_date__gte=hour_start,
                    completion_date__lt=hour_end
                ).count()
                daily_completions.append(completion_count)
                
        elif timeframe == 'week':
            days = 7
            labels = []
            daily_logins = []
            daily_completions = []
            
            accessible_enrollments = filter_queryset_by_business(
                CourseEnrollment.objects.all(),
                self.request.user,
                business_field_path='course__branch__business'
            )
            user_ct = ContentType.objects.get_for_model(CustomUser)
            
            for i in range(days, 0, -1):
                day = now - timedelta(days=i)
                next_day = now - timedelta(days=i-1)
                day_str = day.strftime('%a %b %d')
                labels.append(day_str)
                
                # Count logins for this day
                login_count = LogEntry.objects.filter(
                    content_type=user_ct,
                    action_time__gte=day,
                    action_time__lt=next_day
                ).count()
                daily_logins.append(login_count)
                
                # Count course completions for this day
                completion_count = accessible_enrollments.filter(
                    completion_date__gte=day,
                    completion_date__lt=next_day
                ).count()
                daily_completions.append(completion_count)
                
        elif timeframe == 'year':
            # Show monthly data for the last 12 months
            labels = []
            daily_logins = []
            daily_completions = []
            
            accessible_enrollments = filter_queryset_by_business(
                CourseEnrollment.objects.all(),
                self.request.user,
                business_field_path='course__branch__business'
            )
            user_ct = ContentType.objects.get_for_model(CustomUser)
            
            for i in range(12, 0, -1):
                # Calculate start and end of each month
                month_start = (now.replace(day=1) - timedelta(days=32 * (i-1))).replace(day=1)
                if i == 1:
                    month_end = now
                else:
                    next_month = (now.replace(day=1) - timedelta(days=32 * (i-2))).replace(day=1)
                    month_end = next_month - timedelta(days=1)
                    month_end = month_end.replace(hour=23, minute=59, second=59)
                
                month_str = month_start.strftime('%b %Y')
                labels.append(month_str)
                
                # Count logins for this month
                login_count = LogEntry.objects.filter(
                    content_type=user_ct,
                    action_time__gte=month_start,
                    action_time__lte=month_end
                ).count()
                daily_logins.append(login_count)
                
                # Count course completions for this month
                completion_count = accessible_enrollments.filter(
                    completion_date__gte=month_start,
                    completion_date__lte=month_end
                ).count()
                daily_completions.append(completion_count)
                
        else:  # month (default) - show daily data for current month
            # Show daily data for the current month
            labels = []
            daily_logins = []
            daily_completions = []
            
            accessible_enrollments = filter_queryset_by_business(
                CourseEnrollment.objects.all(),
                self.request.user,
                business_field_path='course__branch__business'
            )
            user_ct = ContentType.objects.get_for_model(CustomUser)
            
            # Get first day of current month
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Get number of days in current month
            import calendar
            days_in_month = calendar.monthrange(now.year, now.month)[1]
            
            for day_num in range(1, days_in_month + 1):
                day_start = month_start.replace(day=day_num)
                day_end = day_start.replace(hour=23, minute=59, second=59)
                
                # Only process days up to today
                if day_start.date() > now.date():
                    break
                    
                day_str = day_start.strftime('%d')
                labels.append(day_str)
                
                # Count logins for this day
                login_count = LogEntry.objects.filter(
                    content_type=user_ct,
                    action_time__gte=day_start,
                    action_time__lte=day_end
                ).count()
                daily_logins.append(login_count)
                
                # Count course completions for this day
                completion_count = accessible_enrollments.filter(
                    completion_date__gte=day_start,
                    completion_date__lte=day_end
                ).count()
                daily_completions.append(completion_count)
        
        # Prepare data for caching and return
        activity_data = {
            'labels': labels,
            'logins': daily_logins,
            'completions': daily_completions
        }
        
        # Cache the data for 5 minutes
        cache.set(cache_key, activity_data, CACHE_TIMEOUT)
        
        # Memory cleanup and monitoring
        cleanup_memory()
        monitor_memory_usage("get_portal_activity_data_complete", initial_memory)
        
        # Reduced debug logging to prevent memory issues
        logger.debug(f"Activity data for timeframe '{timeframe}': {len(labels)} data points")
        
        return activity_data

    def get_context_data(self, **kwargs):
        """Get context data with memory monitoring and caching"""
        # Memory monitoring
        initial_memory = monitor_memory_usage("get_context_data_start")
        
        context = super().get_context_data(**kwargs)
        
        # Try to get cached dashboard data first
        dashboard_cache_key = CACHE_KEY_DASHBOARD_DATA.format(self.request.user.id)
        cached_dashboard_data = cache.get(dashboard_cache_key)
        
        if cached_dashboard_data:
            context.update(cached_dashboard_data)
            monitor_memory_usage("get_context_data_cached", initial_memory)
            return context
        
        # Use consistent dashboard data provider for 100% consistency across environments
        from core.utils.consistent_dashboard_data import get_consistent_dashboard_context
        
        dashboard_data = get_consistent_dashboard_context(self.request.user)
        
        # Set context variables with consistent data
        context['total_branches'] = dashboard_data['total_branches']
        context['active_users'] = dashboard_data['active_users']
        context['total_courses'] = dashboard_data['total_courses']
        context['completion_rate'] = dashboard_data['completion_rate']
        context['course_progress_data'] = dashboard_data['course_progress_data']
        context['activity_data'] = dashboard_data['activity_data']
        context['user_role'] = dashboard_data['user_role']
        context['business_assignments'] = dashboard_data['business_assignments']
        
        # Legacy compatibility - keep old variable names
        total_enrollments = dashboard_data['total_courses'] * 5  # Estimate based on test data
        completed_enrollments = int(total_enrollments * (dashboard_data['completion_rate'] / 100))
        context['completion_rate'] = round((completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0, 2)
        
        # Add breadcrumbs for the superadmin dashboard
        context['breadcrumbs'] = [
            {'url': reverse('role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Superadmin Dashboard', 'icon': 'fa-tachometer-alt'}
        ]
        
        # Get date range for recent activity
        now = timezone.now()
        start_date = now - timedelta(days=30)  # Default to last 30 days
        context['start_date'] = start_date.strftime('%d/%m/%Y')
        context['end_date'] = now.strftime('%d/%m/%Y')

        # Get recent activities
        context['recent_activities'] = LogEntry.objects.select_related('user').order_by('-action_time')[:10]
        context['total_activities'] = LogEntry.objects.count()

        # Get business-scoped data for superadmin
        from core.utils.business_filtering import (
            filter_users_by_business,
            filter_courses_by_business,
            filter_queryset_by_business
        )
        from courses.models import CourseEnrollment
        
        accessible_users = filter_users_by_business(self.request.user)
        accessible_courses = filter_courses_by_business(self.request.user)
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.all(),
            self.request.user,
            business_field_path='course__branch__business'
        )

        # Get recent instructors (business-scoped)
        context['recent_instructors'] = accessible_users.filter(
            role='instructor',
            is_active=True
        ).order_by('-last_login')[:4]
        
        # Get branch courses with progress calculation for "In Progress" section
        from django.db.models import Count, Case, When, IntegerField
        
        branch_courses_with_progress = []
        courses_with_enrollments = accessible_courses.annotate(
            total_enrollments=Count('courseenrollment'),
            completed_enrollments=Count(
                Case(
                    When(courseenrollment__completed=True, then=1),
                    output_field=IntegerField()
                )
            )
        ).filter(total_enrollments__gt=0)[:6]  # Limit to 6 courses
        
        for course in courses_with_enrollments:
            if course.total_enrollments > 0:
                progress_percentage = round((course.completed_enrollments / course.total_enrollments) * 100)
            else:
                progress_percentage = 0
            
            # Add progress attribute to course object
            course.progress = progress_percentage
            branch_courses_with_progress.append(course)
        
        context['branch_courses'] = branch_courses_with_progress
        
        # Add progress data for the course progress chart (business-scoped)
        # Use the business-scoped enrollments
        all_enrollments = accessible_enrollments
        
        # Check if CourseEnrollment has a 'failed' field
        has_failed_field = hasattr(CourseEnrollment, 'failed')
        
        # Count by status using actual topic completion
        completed_count = all_enrollments.filter(completed=True).count()
        
        # Calculate in_progress and not_started based on actual topic completion
        incomplete_enrollments = all_enrollments.filter(completed=False)
        in_progress_count = 0
        not_started_count = 0
        
        # OPTIMIZED: Calculate progress efficiently using database aggregation
        # This fixes the N+1 query problem that was causing browser hangs
        from courses.models import TopicProgress
        from django.db.models import F
        
        # Count progress more efficiently - avoid N+1 queries
        in_progress_count = incomplete_enrollments.filter(
            course__coursetopic__topic__user_progress__user=F('user'),
            course__coursetopic__topic__user_progress__completed=True
        ).distinct().count()
        
        not_started_count = incomplete_enrollments.count() - in_progress_count
        
        not_passed_count = all_enrollments.filter(completed=False, failed=True).count() if has_failed_field else 0
        
        # Calculate percentages
        total_status_count = all_enrollments.count()
        if total_status_count > 0:
            completed_percentage = round((completed_count / total_status_count) * 100)
            in_progress_percentage = round((in_progress_count / total_status_count) * 100)
            not_started_percentage = round((not_started_count / total_status_count) * 100)
            not_passed_percentage = 100 - (completed_percentage + in_progress_percentage + not_started_percentage)
        else:
            completed_percentage = 0
            in_progress_percentage = 0
            not_started_percentage = 0
            not_passed_percentage = 0
            
        # Ensure non-negative percentages
        not_passed_percentage = max(0, not_passed_percentage)
        
        # Create course_progress object (matching instructor dashboard structure)
        course_progress = {
            'total_courses': accessible_courses.count(),
            'completed_count': completed_count,
            'in_progress_count': in_progress_count,
            'not_started_count': not_started_count,
            'not_passed_count': not_passed_count,
            'completed_percentage': completed_percentage,
            'in_progress_percentage': in_progress_percentage,
            'not_started_percentage': not_started_percentage,
            'not_passed_percentage': not_passed_percentage,
        }
        
        context['course_progress'] = course_progress
        context['progress_data'] = {
            'completed_percentage': completed_percentage,
            'in_progress_percentage': in_progress_percentage,
            'not_started_percentage': not_started_percentage,
            'not_passed_percentage': not_passed_percentage,
        }
        
        # Add individual progress variables for template JavaScript access
        context['completed_percentage'] = completed_percentage
        context['in_progress_percentage'] = in_progress_percentage
        context['not_started_percentage'] = not_started_percentage
        context['not_passed_percentage'] = not_passed_percentage

        # Get portal activity data using the extracted method
        portal_activity_data = self.get_portal_activity_data('month')
        
        # Add portal activity data to context (JSON encode for safe template rendering)
        import json
        context['portal_activity'] = {
            'labels': json.dumps(portal_activity_data['labels']),
            'logins': json.dumps(portal_activity_data['logins']),
            'completions': json.dumps(portal_activity_data['completions'])
        }
        
        # Add individual activity data variables (matching instructor dashboard structure)
        context['activity_dates'] = json.dumps(portal_activity_data['labels'])
        context['login_counts'] = json.dumps(portal_activity_data['logins'])
        context['completion_counts'] = json.dumps(portal_activity_data['completions'])
        
        # Get total LMS users count (business-scoped)
        context['total_users'] = accessible_users.count()
        
        # Get total logins count (last 30 days)
        user_ct = ContentType.objects.get_for_model(CustomUser)
        context['total_logins'] = LogEntry.objects.filter(
            content_type=user_ct,
            action_time__gte=start_date
        ).count()
        
        # Get total course completions (last 30 days, business-scoped)
        context['total_completions'] = accessible_enrollments.filter(
            completion_date__gte=start_date
        ).count()

        # Cache the dashboard data (excluding context items that shouldn't be cached)
        cacheable_data = {
            'total_branches': context['total_branches'],
            'active_users': context['active_users'],
            'total_courses': context['total_courses'],
            'completion_rate': context['completion_rate'],
            'course_progress_data': context['course_progress_data'],
            'activity_data': context['activity_data'],
            'user_role': context['user_role'],
            'business_assignments': context['business_assignments'],
            'recent_instructors': list(context['recent_instructors'].values()),
            'branch_courses': [
                {
                    'id': course.id,
                    'title': course.title,
                    'progress': course.progress,
                    'total_enrollments': course.total_enrollments,
                    'completed_enrollments': course.completed_enrollments
                }
                for course in context['branch_courses']
            ],
            'course_progress': context['course_progress'],
            'progress_data': context['progress_data'],
            'portal_activity': context['portal_activity'],
            'total_users': context['total_users'],
            'total_logins': context['total_logins'],
            'total_completions': context['total_completions'],
        }
        
        # Cache for 2 minutes to balance performance and data freshness
        cache.set(dashboard_cache_key, cacheable_data, 120)
        
        # Memory cleanup and monitoring
        cleanup_memory()
        monitor_memory_usage("get_context_data_complete", initial_memory)

        return context
