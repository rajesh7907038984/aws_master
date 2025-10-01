"""
Business Performance API Views
REST API endpoints for business performance data
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.views import View
import json
import logging

from .statistics_utils import BusinessStatisticsManager

logger = logging.getLogger(__name__)

def is_global_admin(user):
    """Check if user is a global admin"""
    return user.is_authenticated and user.role == 'globaladmin'

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_business_overview_api(request):
    """
    API endpoint to get business overview statistics
    """
    try:
        business_id = request.GET.get('business_id')
        stats_manager = BusinessStatisticsManager(request.user)
        
        data = stats_manager.get_business_overview_statistics(business_id)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error in get_business_overview_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_login_statistics_api(request):
    """
    API endpoint to get login statistics
    """
    try:
        business_id = request.GET.get('business_id')
        timeframe = request.GET.get('timeframe', 'month')
        stats_manager = BusinessStatisticsManager(request.user)
        
        data = stats_manager.get_login_statistics(timeframe, business_id)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error in get_login_statistics_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_completion_statistics_api(request):
    """
    API endpoint to get course completion statistics
    """
    try:
        business_id = request.GET.get('business_id')
        timeframe = request.GET.get('timeframe', 'month')
        stats_manager = BusinessStatisticsManager(request.user)
        
        data = stats_manager.get_course_completion_statistics(timeframe, business_id)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error in get_completion_statistics_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_business_comparison_api(request):
    """
    API endpoint to get business comparison data
    """
    try:
        stats_manager = BusinessStatisticsManager(request.user)
        data = stats_manager.get_business_comparison_data()
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error in get_business_comparison_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_chart_data_api(request):
    """
    API endpoint to get formatted chart data
    """
    try:
        chart_type = request.GET.get('chart_type', 'login_trend')
        timeframe = request.GET.get('timeframe', 'month')
        business_id = request.GET.get('business_id')
        
        stats_manager = BusinessStatisticsManager(request.user)
        data = stats_manager.get_chart_data(chart_type, timeframe, business_id)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        logger.error(f"Error in get_chart_data_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
@user_passes_test(is_global_admin)
@csrf_protect
def clear_cache_api(request):
    """
    API endpoint to clear performance data cache
    """
    try:
        data = json.loads(request.body)
        method_name = data.get('method_name')
        
        stats_manager = BusinessStatisticsManager(request.user)
        stats_manager.clear_cache(method_name)
        
        return JsonResponse({
            'success': True,
            'message': 'Cache cleared successfully'
        })
    except Exception as e:
        logger.error(f"Error in clear_cache_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@user_passes_test(is_global_admin)
def get_real_time_stats_api(request):
    """
    API endpoint to get real-time statistics (bypasses cache)
    """
    try:
        business_id = request.GET.get('business_id')
        timeframe = request.GET.get('timeframe', 'month')
        
        # Create stats manager with cache disabled
        stats_manager = BusinessStatisticsManager(request.user)
        stats_manager.cache_enabled = False
        
        # Get all statistics
        overview = stats_manager.get_business_overview_statistics(business_id)
        login_stats = stats_manager.get_login_statistics(timeframe, business_id)
        completion_stats = stats_manager.get_course_completion_statistics(timeframe, business_id)
        comparison = stats_manager.get_business_comparison_data()
        
        return JsonResponse({
            'success': True,
            'data': {
                'overview': overview,
                'login_stats': login_stats,
                'completion_stats': completion_stats,
                'business_comparison': comparison,
                'timestamp': timezone.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Error in get_real_time_stats_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

class BusinessPerformanceAPIView(View):
    """
    Class-based API view for business performance data
    """
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'globaladmin':
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        """Handle GET requests for performance data"""
        try:
            data_type = request.GET.get('type', 'overview')
            business_id = request.GET.get('business_id')
            timeframe = request.GET.get('timeframe', 'month')
            
            stats_manager = BusinessStatisticsManager(request.user)
            
            if data_type == 'overview':
                data = stats_manager.get_business_overview_statistics(business_id)
            elif data_type == 'login_stats':
                data = stats_manager.get_login_statistics(timeframe, business_id)
            elif data_type == 'completion_stats':
                data = stats_manager.get_course_completion_statistics(timeframe, business_id)
            elif data_type == 'business_comparison':
                data = stats_manager.get_business_comparison_data()
            elif data_type == 'chart_data':
                chart_type = request.GET.get('chart_type', 'login_trend')
                data = stats_manager.get_chart_data(chart_type, timeframe, business_id)
            else:
                return JsonResponse({'error': 'Invalid data type'}, status=400)
            
            return JsonResponse({
                'success': True,
                'data': data,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error in BusinessPerformanceAPIView: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def post(self, request, *args, **kwargs):
        """Handle POST requests for cache management"""
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            stats_manager = BusinessStatisticsManager(request.user)
            
            if action == 'clear_cache':
                method_name = data.get('method_name')
                stats_manager.clear_cache(method_name)
                return JsonResponse({
                    'success': True,
                    'message': 'Cache cleared successfully'
                })
            elif action == 'refresh_data':
                # Force refresh by clearing cache and getting fresh data
                stats_manager.clear_cache()
                return JsonResponse({
                    'success': True,
                    'message': 'Data refreshed successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid action'
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error in BusinessPerformanceAPIView POST: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
