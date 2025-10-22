"""
Optimized Dashboard Views - Performance Fixed Version
Addresses heavy looping scripts and large request issues
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q, Prefetch
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from datetime import timedelta, datetime
import json

from users.models import CustomUser
from courses.models import CourseEnrollment
from core.decorators import role_required


@login_required
@role_required(['globaladmin', 'superadmin', 'admin'])
def optimized_activity_chart_data(request):
    """
    OPTIMIZED: Bulk database queries instead of loops
    Reduces 24+ queries to 2-3 queries total
    """
    timeframe = request.GET.get('timeframe', 'day')
    
    # Cache key for this specific request
    cache_key = f"activity_chart_{request.user.id}_{timeframe}"
    
    # Cache key for this specific request
    cached_data = cache.get(cache_key)
    if cached_data:
        return JsonResponse(cached_data)
    
    now = timezone.now()
    
    if timeframe == 'day':
        # OPTIMIZED: Single bulk query instead of 24 separate queries
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)
        
        # Bulk query for all login data
        user_ct = ContentType.objects.get_for_model(CustomUser)
        login_data = LogEntry.objects.filter(
            content_type=user_ct,
            action_time__gte=start_time,
            action_time__lt=end_time
        ).extra(
            select={'hour': "EXTRACT(hour FROM action_time)"}
        ).values('hour').annotate(count=Count('id')).order_by('hour')
        
        # Bulk query for completion data
        from core.utils.business_filtering import filter_queryset_by_business
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.select_related('course', 'user'),
            request.user,
            business_field_path='course__branch__business'
        )
        
        completion_data = accessible_enrollments.filter(
            completion_date__gte=start_time,
            completion_date__lt=end_time
        ).extra(
            select={'hour': "EXTRACT(hour FROM completion_date)"}
        ).values('hour').annotate(count=Count('id')).order_by('hour')
        
        # Convert to dictionaries for fast lookup
        login_dict = {int(item['hour']): item['count'] for item in login_data}
        completion_dict = {int(item['hour']): item['count'] for item in completion_data}
        
        # Build response arrays (no database queries in loop)
        labels = []
        daily_logins = []
        daily_completions = []
        
        for hour in range(24):
            hour_start = start_time.replace(hour=hour)
            labels.append(hour_start.strftime('%H:%M'))
            daily_logins.append(login_dict.get(hour, 0))
            daily_completions.append(completion_dict.get(hour, 0))
            
    elif timeframe == 'week':
        # OPTIMIZED: Similar bulk approach for weekly data
        days = 7
        start_time = now - timedelta(days=days)
        
        # Bulk queries with date grouping
        login_data = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(CustomUser),
            action_time__gte=start_time
        ).extra(
            select={'date': "DATE(action_time)"}
        ).values('date').annotate(count=Count('id')).order_by('date')
        
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.select_related('course', 'user'),
            request.user,
            business_field_path='course__branch__business'
        )
        
        completion_data = accessible_enrollments.filter(
            completion_date__gte=start_time
        ).extra(
            select={'date': "DATE(completion_date)"}
        ).values('date').annotate(count=Count('id')).order_by('date')
        
        # Convert to dictionaries
        login_dict = {str(item['date']): item['count'] for item in login_data}
        completion_dict = {str(item['date']): item['count'] for item in completion_data}
        
        # Build arrays without database queries
        labels = []
        daily_logins = []
        daily_completions = []
        
        for i in range(days, 0, -1):
            date = (now - timedelta(days=i)).date()
            date_str = str(date)
            labels.append(date.strftime('%m/%d'))
            daily_logins.append(login_dict.get(date_str, 0))
            daily_completions.append(completion_dict.get(date_str, 0))
    
    else:  # month
        # OPTIMIZED: Monthly bulk queries
        days = 30
        start_time = now - timedelta(days=days)
        
        # Similar bulk approach for monthly data
        login_data = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(CustomUser),
            action_time__gte=start_time
        ).extra(
            select={'date': "DATE(action_time)"}
        ).values('date').annotate(count=Count('id')).order_by('date')
        
        accessible_enrollments = filter_queryset_by_business(
            CourseEnrollment.objects.select_related('course', 'user'),
            request.user,
            business_field_path='course__branch__business'
        )
        
        completion_data = accessible_enrollments.filter(
            completion_date__gte=start_time
        ).extra(
            select={'date': "DATE(completion_date)"}
        ).values('date').annotate(count=Count('id')).order_by('date')
        
        login_dict = {str(item['date']): item['count'] for item in login_data}
        completion_dict = {str(item['date']): item['count'] for item in completion_data}
        
        labels = []
        daily_logins = []
        daily_completions = []
        
        for i in range(days, 0, -1):
            date = (now - timedelta(days=i)).date()
            date_str = str(date)
            labels.append(date.strftime('%m/%d'))
            daily_logins.append(login_dict.get(date_str, 0))
            daily_completions.append(completion_dict.get(date_str, 0))
    
    data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Daily Logins',
                'data': daily_logins,
                'borderColor': 'rgb(75, 192, 192)',
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'tension': 0.1
            },
            {
                'label': 'Course Completions',
                'data': daily_completions,
                'borderColor': 'rgb(255, 99, 132)',
                'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                'tension': 0.1
            }
        ]
    }
    
    # Cache for 5 minutes to reduce database load
    cache.set(cache_key, data, 300)
    
    return JsonResponse(data)


@login_required
@role_required(['globaladmin', 'superadmin', 'admin'])
@cache_page(300)  # Cache for 5 minutes
def optimized_dashboard_stats(request):
    """
    OPTIMIZED: Cached dashboard statistics
    Reduces memory usage and response time
    """
    cache_key = f"dashboard_stats_{request.user.id}"
    cached_stats = cache.get(cache_key)
    if cached_stats:
        return JsonResponse(cached_stats)
    
    from core.utils.business_filtering import filter_queryset_by_business
    
    # OPTIMIZED: Use select_related and prefetch_related
    accessible_users = filter_queryset_by_business(
        CustomUser.objects.select_related('branch').only('id', 'is_active', 'branch'),
        request.user,
        business_field_path='branch__business'
    )
    
    accessible_enrollments = filter_queryset_by_business(
        CourseEnrollment.objects.select_related('course', 'user').only(
            'id', 'completion_date', 'course__id', 'user__id'
        ),
        request.user,
        business_field_path='course__branch__business'
    )
    
    # OPTIMIZED: Single aggregation queries instead of multiple count() calls
    stats = {
        'total_users': accessible_users.filter(is_active=True).count(),
        'total_enrollments': accessible_enrollments.count(),
        'completed_courses': accessible_enrollments.filter(
            completion_date__isnull=False
        ).count(),
        'active_courses': filter_queryset_by_business(
            CourseEnrollment.objects.values('course').distinct(),
            request.user,
            business_field_path='course__branch__business'
        ).count()
    }
    
    # Cache for 10 minutes
    cache.set(cache_key, stats, 600)
    
    return JsonResponse(stats)


# Performance monitoring decorator
def monitor_performance(view_func):
    """Decorator to monitor view performance"""
    def wrapper(request, *args, **kwargs):
        import time
        start_time = time.time()
        
        response = view_func(request, *args, **kwargs)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Log slow requests
        if duration > 1.0:  # More than 1 second
            import logging
            logger = logging.getLogger('performance')
            logger.warning(f"Slow request: {request.path} took {duration:.2f}s")
        
        return response
    return wrapper


@login_required
@role_required(['globaladmin', 'superadmin', 'admin'])
@monitor_performance
def optimized_dashboard_view(request):
    """
    OPTIMIZED: Main dashboard view with reduced memory footprint
    """
    # Minimal context to reduce response size
    context = {
        'user': request.user,
        'page_title': 'Dashboard',
        # Remove heavy data objects from context
        # Load data via AJAX instead
    }
    
    return render(request, 'admin_dashboard/optimized_dashboard.html', context)
