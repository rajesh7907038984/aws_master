"""
Error Dashboard Views
Provides monitoring and management of 500 errors
"""

import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from core.utils.error_monitoring import get_error_dashboard_data, error_monitor
from core.utils.database_health import check_db_health
from core.utils.file_processing_handler import file_handler

logger = logging.getLogger(__name__)

@login_required
def error_dashboard(request):
    """Main error dashboard for administrators"""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # Get error summary data
        error_data = get_error_dashboard_data()
        
        # Get database health
        db_health = check_db_health()
        
        # Get file processing stats
        file_stats = {
            'max_file_size': file_handler.max_file_size,
            'allowed_extensions': file_handler.allowed_extensions,
            'allowed_mime_types': file_handler.allowed_mime_types
        }
        
        context = {
            'error_data': error_data,
            'db_health': db_health,
            'file_stats': file_stats,
            'user': request.user
        }
        
        return render(request, 'core/error_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error loading error dashboard: {str(e)}")
        return JsonResponse({
            'error': 'Failed to load error dashboard',
            'details': str(e)
        }, status=500)

@login_required
def error_summary_api(request):
    """API endpoint for error summary data"""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        hours = int(request.GET.get('hours', 24))
        error_data = get_error_dashboard_data()
        
        return JsonResponse({
            'success': True,
            'data': error_data,
            'hours': hours
        })
        
    except Exception as e:
        logger.error(f"Error getting error summary: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to get error summary',
            'details': str(e)
        }, status=500)

@login_required
def clear_old_errors(request):
    """Clear old error logs"""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        hours = int(request.POST.get('hours', 48))
        error_monitor.clear_old_errors(hours)
        
        return JsonResponse({
            'success': True,
            'message': f'Cleared errors older than {hours} hours'
        })
        
    except Exception as e:
        logger.error(f"Error clearing old errors: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to clear old errors',
            'details': str(e)
        }, status=500)

@login_required
def database_health_api(request):
    """API endpoint for database health check"""
    if not request.user.is_staff and request.user.role not in ['superadmin', 'admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        db_health = check_db_health()
        
        return JsonResponse({
            'success': True,
            'data': db_health
        })
        
    except Exception as e:
        logger.error(f"Error checking database health: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to check database health',
            'details': str(e)
        }, status=500)
