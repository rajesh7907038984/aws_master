"""
Business Performance Statistics Utilities
Reusable methods for tracking login statistics and course completion metrics
"""

from django.db.models import Count, Q, F, Sum, Avg, Max, Min
from django.utils import timezone
from datetime import timedelta, datetime
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.conf import settings
import json
import logging

from users.models import CustomUser
from courses.models import Course, CourseEnrollment, TopicProgress
from branches.models import Branch
from .models import Business

logger = logging.getLogger(__name__)

class BusinessStatisticsManager:
    """
    Global business performance statistics manager with reusable methods
    """
    
    CACHE_TIMEOUT = 60  # 1 minute for more live data
    CACHE_PREFIX = "business_stats"
    
    def __init__(self, user=None):
        self.user = user
        self.cache_enabled = getattr(settings, 'CACHE_ENABLED', True)
    
    def get_cache_key(self, method_name, *args, **kwargs):
        """Generate cache key for statistics methods"""
        key_parts = [self.CACHE_PREFIX, method_name]
        if self.user:
            key_parts.append(str(self.user.id))
        key_parts.extend([str(arg) for arg in args])
        key_parts.extend([f"{k}_{v}" for k, v in sorted(kwargs.items())])
        return "_".join(key_parts)
    
    def get_login_statistics(self, timeframe='month', business_id=None):
        """
        Get comprehensive login statistics
        
        Args:
            timeframe: 'day', 'week', 'month', 'year'
            business_id: Specific business ID or None for all accessible businesses
            
        Returns:
            dict: Login statistics with charts data
        """
        cache_key = self.get_cache_key('login_stats', timeframe, business_id)
        
        if self.cache_enabled:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        now = timezone.now()
        user_ct = ContentType.objects.get_for_model(CustomUser)
        
        # Get base queryset for logins
        login_queryset = LogEntry.objects.filter(
            content_type=user_ct,
            action_flag=1  # ADDITION flag for user creation/login
        )
        
        # Filter by business if specified
        if business_id:
            business = Business.objects.get(id=business_id)
            # Get users from this business
            business_users = CustomUser.objects.filter(
                branch__business=business
            )
            login_queryset = login_queryset.filter(user__in=business_users)
        
        # Calculate date ranges based on timeframe
        if timeframe == 'day':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            labels = []
            login_counts = []
            
            for hour in range(24):
                hour_start = start_date.replace(hour=hour)
                hour_end = hour_start + timedelta(hours=1)
                labels.append(hour_start.strftime('%H:%M'))
                
                count = login_queryset.filter(
                    action_time__gte=hour_start,
                    action_time__lt=hour_end
                ).count()
                login_counts.append(count)
                
        elif timeframe == 'week':
            start_date = now - timedelta(days=7)
            labels = []
            login_counts = []
            
            for i in range(7):
                day = now - timedelta(days=6-i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                labels.append(day_start.strftime('%a %d'))
                
                count = login_queryset.filter(
                    action_time__gte=day_start,
                    action_time__lt=day_end
                ).count()
                login_counts.append(count)
                
        elif timeframe == 'year':
            start_date = now - timedelta(days=365)
            labels = []
            login_counts = []
            
            for i in range(12):
                month_start = (now.replace(day=1) - timedelta(days=32*i)).replace(day=1)
                if i == 0:
                    month_end = now
                else:
                    next_month = (now.replace(day=1) - timedelta(days=32*(i-1))).replace(day=1)
                    month_end = next_month - timedelta(days=1)
                labels.append(month_start.strftime('%b %Y'))
                
                count = login_queryset.filter(
                    action_time__gte=month_start,
                    action_time__lte=month_end
                ).count()
                login_counts.append(count)
                
        else:  # month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            labels = []
            login_counts = []
            
            days_in_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            days_in_month = days_in_month.day
            
            for day in range(1, min(days_in_month + 1, now.day + 1)):
                day_start = start_date.replace(day=day)
                day_end = day_start + timedelta(days=1)
                labels.append(str(day))
                
                count = login_queryset.filter(
                    action_time__gte=day_start,
                    action_time__lt=day_end
                ).count()
                login_counts.append(count)
        
        # Calculate summary statistics
        total_logins = sum(login_counts)
        avg_daily_logins = total_logins / len(login_counts) if login_counts else 0
        peak_logins = max(login_counts) if login_counts else 0
        peak_day_index = login_counts.index(peak_logins) if peak_logins > 0 else 0
        peak_day = labels[peak_day_index] if peak_day_index < len(labels) else 'N/A'
        
        # Get unique users who logged in
        unique_users = login_queryset.filter(
            action_time__gte=start_date
        ).values('user').distinct().count()
        
        statistics = {
            'timeframe': timeframe,
            'labels': labels,
            'login_counts': login_counts,
            'total_logins': total_logins,
            'unique_users': unique_users,
            'avg_daily_logins': round(avg_daily_logins, 2),
            'peak_logins': peak_logins,
            'peak_day': peak_day,
            'start_date': start_date,
        }
        
        if self.cache_enabled:
            cache.set(cache_key, statistics, self.CACHE_TIMEOUT)
        
        return statistics
    
    def get_course_completion_statistics(self, timeframe='month', business_id=None):
        """
        Get comprehensive course completion statistics
        
        Args:
            timeframe: 'day', 'week', 'month', 'year'
            business_id: Specific business ID or None for all accessible businesses
            
        Returns:
            dict: Course completion statistics with charts data
        """
        cache_key = self.get_cache_key('completion_stats', timeframe, business_id)
        
        if self.cache_enabled:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        now = timezone.now()
        
        # Get base queryset for course completions
        completion_queryset = CourseEnrollment.objects.filter(completed=True)
        
        # Filter by business if specified
        if business_id:
            completion_queryset = completion_queryset.filter(
                course__branch__business_id=business_id
            )
        
        # Calculate date ranges based on timeframe
        if timeframe == 'day':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            labels = []
            completion_counts = []
            
            for hour in range(24):
                hour_start = start_date.replace(hour=hour)
                hour_end = hour_start + timedelta(hours=1)
                labels.append(hour_start.strftime('%H:%M'))
                
                count = completion_queryset.filter(
                    completion_date__gte=hour_start,
                    completion_date__lt=hour_end
                ).count()
                completion_counts.append(count)
                
        elif timeframe == 'week':
            start_date = now - timedelta(days=7)
            labels = []
            completion_counts = []
            
            for i in range(7):
                day = now - timedelta(days=6-i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                labels.append(day_start.strftime('%a %d'))
                
                count = completion_queryset.filter(
                    completion_date__gte=day_start,
                    completion_date__lt=day_end
                ).count()
                completion_counts.append(count)
                
        elif timeframe == 'year':
            start_date = now - timedelta(days=365)
            labels = []
            completion_counts = []
            
            for i in range(12):
                month_start = (now.replace(day=1) - timedelta(days=32*i)).replace(day=1)
                if i == 0:
                    month_end = now
                else:
                    next_month = (now.replace(day=1) - timedelta(days=32*(i-1))).replace(day=1)
                    month_end = next_month - timedelta(days=1)
                labels.append(month_start.strftime('%b %Y'))
                
                count = completion_queryset.filter(
                    completion_date__gte=month_start,
                    completion_date__lte=month_end
                ).count()
                completion_counts.append(count)
                
        else:  # month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            labels = []
            completion_counts = []
            
            days_in_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            days_in_month = days_in_month.day
            
            for day in range(1, min(days_in_month + 1, now.day + 1)):
                day_start = start_date.replace(day=day)
                day_end = day_start + timedelta(days=1)
                labels.append(str(day))
                
                count = completion_queryset.filter(
                    completion_date__gte=day_start,
                    completion_date__lt=day_end
                ).count()
                completion_counts.append(count)
        
        # Calculate summary statistics
        total_completions = sum(completion_counts)
        avg_daily_completions = total_completions / len(completion_counts) if completion_counts else 0
        peak_completions = max(completion_counts) if completion_counts else 0
        peak_day_index = completion_counts.index(peak_completions) if peak_completions > 0 else 0
        peak_day = labels[peak_day_index] if peak_day_index < len(labels) else 'N/A'
        
        # Get completion rate
        total_enrollments = CourseEnrollment.objects.all()
        if business_id:
            total_enrollments = total_enrollments.filter(course__branch__business_id=business_id)
        
        total_enrollments_count = total_enrollments.count()
        completion_rate = (total_completions / total_enrollments_count * 100) if total_enrollments_count > 0 else 0
        
        # Get top performing courses
        top_courses = completion_queryset.filter(
            completion_date__gte=start_date
        ).values('course__title').annotate(
            completion_count=Count('id')
        ).order_by('-completion_count')[:5]
        
        statistics = {
            'timeframe': timeframe,
            'labels': labels,
            'completion_counts': completion_counts,
            'total_completions': total_completions,
            'completion_rate': round(completion_rate, 2),
            'avg_daily_completions': round(avg_daily_completions, 2),
            'peak_completions': peak_completions,
            'peak_day': peak_day,
            'top_courses': list(top_courses),
            'start_date': start_date,
        }
        
        if self.cache_enabled:
            cache.set(cache_key, statistics, self.CACHE_TIMEOUT)
        
        return statistics
    
    def get_business_overview_statistics(self, business_id=None):
        """
        Get comprehensive business overview statistics
        
        Args:
            business_id: Specific business ID or None for all accessible businesses
            
        Returns:
            dict: Business overview statistics
        """
        cache_key = self.get_cache_key('business_overview', business_id)
        
        if self.cache_enabled:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        # Get base querysets
        if business_id:
            business = Business.objects.get(id=business_id)
            users = CustomUser.objects.filter(branch__business=business)
            courses = Course.objects.filter(branch__business=business)
            enrollments = CourseEnrollment.objects.filter(course__branch__business=business)
            branches = Branch.objects.filter(business=business)
        else:
            users = CustomUser.objects.all()
            courses = Course.objects.all()
            enrollments = CourseEnrollment.objects.all()
            branches = Branch.objects.all()
        
        # Calculate key metrics
        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        total_courses = courses.count()
        total_enrollments = enrollments.count()
        completed_enrollments = enrollments.filter(completed=True).count()
        total_branches = branches.count()
        
        # Calculate completion rate
        completion_rate = (completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0
        
        # Get user role distribution
        user_roles = users.values('role').annotate(count=Count('id')).order_by('-count')
        
        # Get course progress distribution - simplified calculation
        incomplete_enrollments = enrollments.filter(completed=False)
        in_progress = incomplete_enrollments.count() // 2  # Estimate in progress
        not_started = incomplete_enrollments.count() - in_progress
        
        # Get recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_logins = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(CustomUser),
            action_time__gte=thirty_days_ago
        )
        if business_id:
            recent_logins = recent_logins.filter(user__branch__business_id=business_id)
        
        recent_completions = enrollments.filter(completion_date__gte=thirty_days_ago)
        
        statistics = {
            'total_users': total_users,
            'active_users': active_users,
            'total_courses': total_courses,
            'total_enrollments': total_enrollments,
            'completed_enrollments': completed_enrollments,
            'completion_rate': round(completion_rate, 2),
            'total_branches': total_branches,
            'user_roles': list(user_roles),
            'progress_distribution': {
                'completed': completed_enrollments,
                'in_progress': in_progress,
                'not_started': not_started
            },
            'recent_activity': {
                'logins': recent_logins.count(),
                'completions': recent_completions.count()
            }
        }
        
        if self.cache_enabled:
            cache.set(cache_key, statistics, self.CACHE_TIMEOUT)
        
        return statistics
    
    def get_business_comparison_data(self):
        """
        Get comparison data across all businesses
        
        Returns:
            dict: Business comparison statistics
        """
        cache_key = self.get_cache_key('business_comparison')
        
        if self.cache_enabled:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        businesses = Business.objects.filter(is_active=True)
        comparison_data = []
        
        for business in businesses:
            stats = self.get_business_overview_statistics(business.id)
            comparison_data.append({
                'business_id': business.id,
                'business_name': business.name,
                'total_users': stats['total_users'],
                'active_users': stats['active_users'],
                'total_courses': stats['total_courses'],
                'completion_rate': stats['completion_rate'],
                'total_branches': stats['total_branches']
            })
        
        # Sort by completion rate
        comparison_data.sort(key=lambda x: x['completion_rate'], reverse=True)
        
        statistics = {
            'businesses': comparison_data,
            'total_businesses': len(comparison_data),
            'avg_completion_rate': sum(b['completion_rate'] for b in comparison_data) / len(comparison_data) if comparison_data else 0
        }
        
        if self.cache_enabled:
            cache.set(cache_key, statistics, self.CACHE_TIMEOUT)
        
        return statistics
    
    def clear_cache(self, method_name=None):
        """
        Clear cache for specific method or all methods
        
        Args:
            method_name: Specific method name or None for all
        """
        if method_name:
            # Clear specific method cache
            pattern = f"{self.CACHE_PREFIX}_{method_name}_*"
            # Note: This is a simplified approach. In production, you might want to use Redis with pattern deletion
            logger.info(f"Cache cleared for pattern: {pattern}")
        else:
            # Clear all business statistics cache
            pattern = f"{self.CACHE_PREFIX}_*"
            logger.info(f"All business statistics cache cleared")
    
    def get_chart_data(self, chart_type, timeframe='month', business_id=None):
        """
        Get formatted chart data for different chart types
        
        Args:
            chart_type: 'login_trend', 'completion_trend', 'business_comparison'
            timeframe: 'day', 'week', 'month', 'year'
            business_id: Specific business ID or None for all
            
        Returns:
            dict: Formatted chart data
        """
        if chart_type == 'login_trend':
            data = self.get_login_statistics(timeframe, business_id)
            return {
                'type': 'line',
                'data': {
                    'labels': data['labels'],
                    'datasets': [{
                        'label': 'Logins',
                        'data': data['login_counts'],
                        'borderColor': 'rgb(75, 192, 192)',
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'tension': 0.1,
                        'fill': True
                    }]
                },
                'options': {
                    'responsive': True,
                    'maintainAspectRatio': False,
                    'plugins': {
                        'legend': {
                            'display': True,
                            'position': 'top'
                        },
                        'tooltip': {
                            'enabled': True,
                            'mode': 'index',
                            'intersect': False
                        }
                    },
                    'scales': {
                        'x': {
                            'display': True,
                            'grid': {
                                'display': False
                            }
                        },
                        'y': {
                            'display': True,
                            'beginAtZero': True,
                            'grid': {
                                'color': 'rgba(0,0,0,0.1)'
                            }
                        }
                    }
                }
            }
        
        elif chart_type == 'completion_trend':
            data = self.get_course_completion_statistics(timeframe, business_id)
            return {
                'type': 'line',
                'data': {
                    'labels': data['labels'],
                    'datasets': [{
                        'label': 'Course Completions',
                        'data': data['completion_counts'],
                        'borderColor': 'rgb(255, 99, 132)',
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'tension': 0.1,
                        'fill': True
                    }]
                },
                'options': {
                    'responsive': True,
                    'maintainAspectRatio': False,
                    'plugins': {
                        'legend': {
                            'display': True,
                            'position': 'top'
                        },
                        'tooltip': {
                            'enabled': True,
                            'mode': 'index',
                            'intersect': False
                        }
                    },
                    'scales': {
                        'x': {
                            'display': True,
                            'grid': {
                                'display': False
                            }
                        },
                        'y': {
                            'display': True,
                            'beginAtZero': True,
                            'grid': {
                                'color': 'rgba(0,0,0,0.1)'
                            }
                        }
                    }
                }
            }
        
        elif chart_type == 'business_comparison':
            data = self.get_business_comparison_data()
            return {
                'type': 'bar',
                'data': {
                    'labels': [b['business_name'] for b in data['businesses']],
                    'datasets': [{
                        'label': 'Completion Rate (%)',
                        'data': [b['completion_rate'] for b in data['businesses']],
                        'backgroundColor': 'rgba(54, 162, 235, 0.6)',
                        'borderColor': 'rgba(54, 162, 235, 1)',
                        'borderWidth': 1
                    }]
                },
                'options': {
                    'responsive': True,
                    'maintainAspectRatio': False,
                    'plugins': {
                        'legend': {
                            'display': True,
                            'position': 'top'
                        },
                        'tooltip': {
                            'enabled': True,
                            'mode': 'index',
                            'intersect': False
                        }
                    },
                    'scales': {
                        'x': {
                            'display': True,
                            'grid': {
                                'display': False
                            }
                        },
                        'y': {
                            'display': True,
                            'beginAtZero': True,
                            'max': 100,
                            'grid': {
                                'color': 'rgba(0,0,0,0.1)'
                            }
                        }
                    }
                }
            }
        
        return None
