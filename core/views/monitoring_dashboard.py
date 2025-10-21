"""
Monitoring Dashboard Views
========================

This module provides views for system monitoring and analytics.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from core.utils.activity_monitor import analytics_engine, performance_monitor
import logging

logger = logging.getLogger(__name__)

def is_admin_user(user):
    """Check if user is admin or superuser"""
    return user.is_authenticated and user.role in ['globaladmin', 'superadmin', 'admin']

@login_required
@user_passes_test(is_admin_user)
def monitoring_dashboard(request):
    """Main monitoring dashboard"""
    try:
        # Get system health
        health_data = analytics_engine.get_system_health_score()
        
        # Get performance stats
        performance_stats = performance_monitor.get_system_metrics() if hasattr(performance_monitor, 'get_system_metrics') else {}
        
        # Cache stats (removed - no longer using cache)
        cache_stats = {'status': 'disabled'}
        
        # Get popular pages
        popular_pages = analytics_engine.get_popular_pages()
        
        # Get search analytics
        search_analytics = analytics_engine.get_search_analytics()
        
        context = {
            'health_data': health_data,
            'performance_stats': performance_stats,
            'cache_stats': cache_stats,
            'popular_pages': popular_pages,
            'search_analytics': search_analytics,
            'timestamp': timezone.now().isoformat()
        }
        
        return render(request, 'core/monitoring_dashboard.html', context)
        
    except Exception as e:
        logger.error("Error in monitoring dashboard: {{e}}")
        return render(request, 'core/monitoring_dashboard.html', {
            'error': 'Unable to load monitoring data'
        })

@login_required
@user_passes_test(is_admin_user)
def api_system_metrics(request):
    """API endpoint for system metrics"""
    try:
        metrics = performance_monitor.get_system_metrics()
        return JsonResponse(metrics)
    except Exception as e:
        logger.error("Error getting system metrics: {{e}}")
        return JsonResponse({'error': 'Unable to get metrics'}, status=500)

@login_required
@user_passes_test(is_admin_user)
def api_user_engagement(request, user_id):
    """API endpoint for user engagement stats"""
    try:
        days = int(request.GET.get('days', 30))
        engagement_stats = analytics_engine.get_user_engagement_stats(user_id, days)
        return JsonResponse(engagement_stats)
    except Exception as e:
        logger.error("Error getting user engagement: {{e}}")
        return JsonResponse({'error': 'Unable to get engagement stats'}, status=500)

@login_required
@user_passes_test(is_admin_user)
def api_health_check(request):
    """API endpoint for system health check"""
    try:
        health_data = analytics_engine.get_system_health_score()
        return JsonResponse(health_data)
    except Exception as e:
        logger.error("Error in health check: {{e}}")
        return JsonResponse({'error': 'Health check failed'}, status=500)
