"""
Activity Monitor for LMS
=======================

This module provides comprehensive user activity tracking,
performance monitoring, and analytics for the LMS system.
"""

import logging
import json
import time
from typing import Dict, Any, List, Optional
from django.utils import timezone
from django.http import HttpRequest
from django.contrib.auth.models import User
from django.db import models
from datetime import datetime, timedelta
import psutil

logger = logging.getLogger(__name__)

class ActivityTracker:
    """Track user activities and system performance"""
    
    def __init__(self):
        self.max_activities = 1000  # Max activities to store per user
    
    def track_user_activity(self, user_id: int, activity_type: str, 
                           details: Dict[str, Any] = None, request: HttpRequest = None):
        """Track user activity"""
        activity = {
            'user_id': user_id,
            'activity_type': activity_type,
            'timestamp': timezone.now().isoformat(),
            'details': details or {},
            'ip_address': request.META.get('REMOTE_ADDR') if request else None,
            'user_agent': request.META.get('HTTP_USER_AGENT') if request else None,
            'path': request.path if request else None,
            'method': request.method if request else None
        }
        
        # Store activity (simplified without cache)
        # In a real implementation, you might want to store this in the database
        pass
        
        # Log important activities
        if activity_type in ['login', 'logout', 'course_enroll', 'course_complete']:
            logger.info(f"User {user_id} performed {activity_type}: {details}")
    
    def get_user_activities(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get user activities (simplified without cache)"""
        # In a real implementation, you might want to query the database
        return []
    
    def track_page_view(self, user_id: int, page_path: str, request: HttpRequest):
        """Track page views"""
        self.track_user_activity(
            user_id=user_id,
            activity_type='page_view',
            details={
                'page_path': page_path,
                'referrer': request.META.get('HTTP_REFERER'),
                'session_id': request.session.session_key
            },
            request=request
        )
    
    def track_search(self, user_id: int, search_query: str, results_count: int, 
                    search_type: str = 'general', request: HttpRequest = None):
        """Track search activities"""
        self.track_user_activity(
            user_id=user_id,
            activity_type='search',
            details={
                'query': search_query,
                'results_count': results_count,
                'search_type': search_type
            },
            request=request
        )
    
    def track_course_interaction(self, user_id: int, course_id: int, 
                                interaction_type: str, details: Dict[str, Any] = None):
        """Track course interactions"""
        self.track_user_activity(
            user_id=user_id,
            activity_type='course_interaction',
            details={
                'course_id': course_id,
                'interaction_type': interaction_type,
                **(details or {})
            }
        )

class PerformanceMonitor:
    """Monitor system performance and resource usage"""
    
    def __init__(self):
        pass
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network I/O
            network = psutil.net_io_counters()
            
            metrics = {
                'timestamp': timezone.now().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': psutil.cpu_count()
                },
                'memory': {
                    'total': memory.total,
                    'available': memory.available,
                    'percent': memory.percent,
                    'used': memory.used
                },
                'disk': {
                    'total': disk.total,
                    'used': disk.used,
                    'free': disk.free,
                    'percent': (disk.used / disk.total) * 100
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                }
            }
            
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def get_cached_metrics(self) -> Dict[str, Any]:
        """Get cached system metrics (simplified without cache)"""
        return {}
    
    def track_request_performance(self, request: HttpRequest, response_time: float, 
                                query_count: int, memory_usage: float):
        """Track request performance"""
        performance_data = {
            'path': request.path,
            'method': request.method,
            'response_time': response_time,
            'query_count': query_count,
            'memory_usage': memory_usage,
            'timestamp': timezone.now().isoformat(),
            'user_id': request.user.id if request.user.is_authenticated else None
        }
        
        # Store performance data (simplified without cache)
        # In a real implementation, you might want to store this in the database
        
        # Log slow requests
        if response_time > 2.0:  # More than 2 seconds
            logger.warning(f"Slow request: {request.path} took {response_time:.2f}s")
        
        if query_count > 50:  # More than 50 queries
            logger.warning(f"High query count: {request.path} used {query_count} queries")

class AnalyticsEngine:
    """Generate analytics and insights from tracked data"""
    
    def __init__(self):
        self.activity_tracker = ActivityTracker()
        self.performance_monitor = PerformanceMonitor()
    
    def get_user_engagement_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get user engagement statistics"""
        activities = self.activity_tracker.get_user_activities(user_id, limit=1000)
        
        # Filter activities by date range
        cutoff_date = timezone.now() - timedelta(days=days)
        recent_activities = [
            activity for activity in activities
            if datetime.fromisoformat(activity['timestamp'].replace('Z', '+00:00')) > cutoff_date
        ]
        
        # Calculate engagement metrics
        total_activities = len(recent_activities)
        unique_days = len(set(
            activity['timestamp'][:10] for activity in recent_activities
        ))
        
        # Activity type breakdown
        activity_types = {}
        for activity in recent_activities:
            activity_type = activity['activity_type']
            activity_types[activity_type] = activity_types.get(activity_type, 0) + 1
        
        return {
            'total_activities': total_activities,
            'active_days': unique_days,
            'activity_types': activity_types,
            'engagement_score': min(100, (total_activities / days) * 10),  # Simple engagement score
            'period_days': days
        }
    
    def get_system_health_score(self) -> Dict[str, Any]:
        """Calculate system health score"""
        metrics = self.performance_monitor.get_cached_metrics()
        
        if not metrics:
            return {'health_score': 0, 'status': 'unknown'}
        
        # Calculate health score based on metrics
        cpu_score = max(0, 100 - metrics.get('cpu', {}).get('percent', 0))
        memory_score = max(0, 100 - metrics.get('memory', {}).get('percent', 0))
        disk_score = max(0, 100 - metrics.get('disk', {}).get('percent', 0))
        
        health_score = (cpu_score + memory_score + disk_score) / 3
        
        # Determine status
        if health_score >= 80:
            status = 'excellent'
        elif health_score >= 60:
            status = 'good'
        elif health_score >= 40:
            status = 'fair'
        else:
            status = 'poor'
        
        return {
            'health_score': round(health_score, 2),
            'status': status,
            'cpu_score': round(cpu_score, 2),
            'memory_score': round(memory_score, 2),
            'disk_score': round(disk_score, 2),
            'timestamp': metrics.get('timestamp')
        }
    
    def get_popular_pages(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get most popular pages"""
        # This would need to be implemented based on your data storage
        # For now, return mock data
        return [
            {'path': '/courses/', 'views': 150, 'unique_users': 45},
            {'path': '/dashboard/', 'views': 120, 'unique_users': 40},
            {'path': '/users/', 'views': 80, 'unique_users': 25}
        ]
    
    def get_search_analytics(self, days: int = 7) -> Dict[str, Any]:
        """Get search analytics"""
        # This would analyze search patterns
        return {
            'total_searches': 0,
            'popular_queries': [],
            'zero_result_searches': 0,
            'average_results_per_search': 0
        }

# Global instances
activity_tracker = ActivityTracker()
performance_monitor = PerformanceMonitor()
analytics_engine = AnalyticsEngine()

def track_user_activity(user_id: int, activity_type: str, details: Dict[str, Any] = None, 
                        request: HttpRequest = None):
    """Convenience function for tracking user activity"""
    activity_tracker.track_user_activity(user_id, activity_type, details, request)

def track_page_view(user_id: int, page_path: str, request: HttpRequest):
    """Convenience function for tracking page views"""
    activity_tracker.track_page_view(user_id, page_path, request)

def track_search(user_id: int, search_query: str, results_count: int, 
                search_type: str = 'general', request: HttpRequest = None):
    """Convenience function for tracking searches"""
    activity_tracker.track_search(user_id, search_query, results_count, search_type, request)
