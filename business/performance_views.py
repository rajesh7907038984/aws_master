"""
Global Business Performance Dashboard Views
Views for business performance statistics and analytics
"""

from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.utils import timezone
from django.core.cache import cache
from django.contrib import messages
from django.urls import reverse
import json
import logging

from .models import Business
from .statistics_utils import BusinessStatisticsManager

logger = logging.getLogger(__name__)

class GlobalBusinessPerformanceView(UserPassesTestMixin, TemplateView):
    """
    Global business performance dashboard for global admins
    """
    template_name = 'business/global_performance_dashboard.html'
    
    def test_func(self):
        """Only global admins can access this view"""
        return (self.request.user.is_authenticated and 
                hasattr(self.request.user, 'role') and 
                self.request.user.role == 'globaladmin')
    
    def get_context_data(self, **kwargs):
        """Get context data for the performance dashboard"""
        context = super().get_context_data(**kwargs)
        
        # Initialize statistics manager
        stats_manager = BusinessStatisticsManager(self.request.user)
        
        # Get selected business and timeframe from request
        selected_business_id = self.request.GET.get('business_id')
        timeframe = self.request.GET.get('timeframe', 'month')
        
        # Get all businesses for dropdown
        context['businesses'] = Business.objects.filter(is_active=True).order_by('name')
        context['selected_business_id'] = selected_business_id
        context['selected_timeframe'] = timeframe
        
        # Get business overview statistics
        context['overview_stats'] = stats_manager.get_business_overview_statistics(selected_business_id)
        
        # Get login statistics
        context['login_stats'] = stats_manager.get_login_statistics(timeframe, selected_business_id)
        
        # Get course completion statistics
        context['completion_stats'] = stats_manager.get_course_completion_statistics(timeframe, selected_business_id)
        
        # Get business comparison data
        context['business_comparison'] = stats_manager.get_business_comparison_data()
        
        # Add breadcrumbs
        context['breadcrumbs'] = [
            {'url': reverse('role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'label': 'Global Business Performance', 'icon': 'fa-chart-line'}
        ]
        
        # Add chart data as JSON for JavaScript
        context['chart_data'] = {
            'login_trend': json.dumps(stats_manager.get_chart_data('login_trend', timeframe, selected_business_id)),
            'completion_trend': json.dumps(stats_manager.get_chart_data('completion_trend', timeframe, selected_business_id)),
            'business_comparison': json.dumps(stats_manager.get_chart_data('business_comparison'))
        }
        
        # Add real-time data refresh settings
        context['refresh_interval'] = 30000  # 30 seconds
        context['api_endpoints'] = {
            'login_trend': reverse('business:api_chart_data') + '?type=chart_data&chart_type=login_trend',
            'completion_trend': reverse('business:api_chart_data') + '?type=chart_data&chart_type=completion_trend',
            'business_comparison': reverse('business:api_chart_data') + '?type=chart_data&chart_type=business_comparison'
        }
        
        return context

class BusinessPerformanceAPIView(UserPassesTestMixin, TemplateView):
    """
    API endpoint for business performance data (AJAX requests)
    """
    
    def test_func(self):
        """Only global admins can access this view"""
        return (self.request.user.is_authenticated and 
                hasattr(self.request.user, 'role') and 
                self.request.user.role == 'globaladmin')
    
    def get(self, request, *args, **kwargs):
        """Handle AJAX requests for performance data"""
        try:
            # Get parameters
            data_type = request.GET.get('type', 'overview')
            business_id = request.GET.get('business_id')
            timeframe = request.GET.get('timeframe', 'month')
            
            # Initialize statistics manager
            stats_manager = BusinessStatisticsManager(self.request.user)
            
            # Get requested data
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
                'data': data
            })
            
        except Exception as e:
            logger.error(f"Error in BusinessPerformanceAPIView: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

class BusinessDetailPerformanceView(UserPassesTestMixin, TemplateView):
    """
    Detailed performance view for a specific business
    """
    template_name = 'business/business_detail_performance.html'
    
    def test_func(self):
        """Only global admins can access this view"""
        return (self.request.user.is_authenticated and 
                hasattr(self.request.user, 'role') and 
                self.request.user.role == 'globaladmin')
    
    def get_context_data(self, **kwargs):
        """Get context data for business detail performance"""
        context = super().get_context_data(**kwargs)
        
        # Get business
        business_id = kwargs.get('business_id')
        business = get_object_or_404(Business, id=business_id)
        context['business'] = business
        
        # Get timeframe
        timeframe = self.request.GET.get('timeframe', 'month')
        context['selected_timeframe'] = timeframe
        
        # Initialize statistics manager
        stats_manager = BusinessStatisticsManager(self.request.user)
        
        # Get business-specific statistics
        context['overview_stats'] = stats_manager.get_business_overview_statistics(business_id)
        context['login_stats'] = stats_manager.get_login_statistics(timeframe, business_id)
        context['completion_stats'] = stats_manager.get_course_completion_statistics(timeframe, business_id)
        
        # Add chart data
        context['chart_data'] = {
            'login_trend': json.dumps(stats_manager.get_chart_data('login_trend', timeframe, business_id)),
            'completion_trend': json.dumps(stats_manager.get_chart_data('completion_trend', timeframe, business_id))
        }
        
        # Add breadcrumbs
        context['breadcrumbs'] = [
            {'url': reverse('role_based_redirect'), 'label': 'Dashboard', 'icon': 'fa-home'},
            {'url': reverse('business:global_performance'), 'label': 'Global Performance', 'icon': 'fa-chart-line'},
            {'label': f'{business.name} Performance', 'icon': 'fa-building'}
        ]
        
        return context

class PerformanceExportView(UserPassesTestMixin, TemplateView):
    """
    Export performance data to various formats
    """
    
    def test_func(self):
        """Only global admins can access this view"""
        return (self.request.user.is_authenticated and 
                hasattr(self.request.user, 'role') and 
                self.request.user.role == 'globaladmin')
    
    def get(self, request, *args, **kwargs):
        """Handle export requests"""
        try:
            export_format = request.GET.get('format', 'json')
            business_id = request.GET.get('business_id')
            timeframe = request.GET.get('timeframe', 'month')
            
            # Initialize statistics manager
            stats_manager = BusinessStatisticsManager(self.request.user)
            
            # Get all performance data
            data = {
                'export_info': {
                    'exported_at': timezone.now().isoformat(),
                    'exported_by': request.user.username,
                    'timeframe': timeframe,
                    'business_id': business_id
                },
                'overview_stats': stats_manager.get_business_overview_statistics(business_id),
                'login_stats': stats_manager.get_login_statistics(timeframe, business_id),
                'completion_stats': stats_manager.get_course_completion_statistics(timeframe, business_id),
                'business_comparison': stats_manager.get_business_comparison_data()
            }
            
            if export_format == 'json':
                response = JsonResponse(data, json_dumps_params={'indent': 2})
                response['Content-Disposition'] = f'attachment; filename="business_performance_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
                return response
            
            elif export_format == 'csv':
                # For CSV export, you would need to implement CSV formatting
                # Future implementation
                messages.warning(request, 'CSV export not yet implemented')
                return JsonResponse({'error': 'CSV export not implemented'}, status=501)
            
            else:
                return JsonResponse({'error': 'Invalid export format'}, status=400)
                
        except Exception as e:
            logger.error(f"Error in PerformanceExportView: {str(e)}")
            messages.error(request, f'Export failed: {str(e)}')
            return JsonResponse({'error': str(e)}, status=500)

class PerformanceCacheManagementView(UserPassesTestMixin, TemplateView):
    """
    Cache management for performance data
    """
    
    def test_func(self):
        """Only global admins can access this view"""
        return (self.request.user.is_authenticated and 
                hasattr(self.request.user, 'role') and 
                self.request.user.role == 'globaladmin')
    
    def post(self, request, *args, **kwargs):
        """Handle cache management requests"""
        try:
            action = request.POST.get('action')
            
            if action == 'clear_all':
                # Clear all business statistics cache
                stats_manager = BusinessStatisticsManager(self.request.user)
                stats_manager.clear_cache()
                messages.success(request, 'All performance data cache cleared successfully')
                
            elif action == 'clear_business':
                business_id = request.POST.get('business_id')
                if business_id:
                    # Clear cache for specific business
                    stats_manager = BusinessStatisticsManager(self.request.user)
                    stats_manager.clear_cache('business_overview')
                    messages.success(request, f'Cache cleared for business {business_id}')
                else:
                    messages.error(request, 'Business ID required for business-specific cache clearing')
            
            else:
                messages.error(request, 'Invalid cache management action')
                
        except Exception as e:
            logger.error(f"Error in PerformanceCacheManagementView: {str(e)}")
            messages.error(request, f'Cache management failed: {str(e)}')
        
        return JsonResponse({'success': True})
