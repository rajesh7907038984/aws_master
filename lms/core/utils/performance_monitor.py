"""
Performance Monitoring Utility for LMS
=====================================

This module provides performance monitoring and optimization tools
for database queries, memory usage, and response times.
"""

import time
import psutil
import logging
from functools import wraps
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Monitor and optimize system performance"""
    
    def __init__(self):
        self.metrics = {
            'query_count': 0,
            'query_time': 0,
            'memory_usage': 0,
            'response_times': []
        }
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    def get_query_count(self) -> int:
        """Get current database query count"""
        return len(connection.queries)
    
    def get_query_time(self) -> float:
        """Get total query execution time"""
        return sum(float(query['time']) for query in connection.queries)
    
    def log_performance_metrics(self, view_name: str, response_time: float):
        """Log performance metrics for a view"""
        memory_usage = self.get_memory_usage()
        query_count = self.get_query_count()
        query_time = self.get_query_time()
        
        metrics = {
            'view': view_name,
            'response_time': response_time,
            'memory_mb': memory_usage,
            'query_count': query_count,
            'query_time': query_time,
            'timestamp': timezone.now().isoformat()
        }
        
        # Log slow queries
        if query_time > 1.0:  # More than 1 second
            logger.warning(f"Slow query detected in {view_name}: {query_time:.2f}s")
        
        # Log high memory usage
        if memory_usage > 500:  # More than 500MB
            logger.warning(f"High memory usage in {view_name}: {memory_usage:.2f}MB")
        
        # Store metrics in cache for dashboard
        cache_key = f"performance_metrics_{view_name}"
        cache.set(cache_key, metrics, 300)  # 5 minutes
        
        return metrics

def monitor_performance(view_name: str = None):
    """Decorator to monitor view performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            start_time = time.time()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            start_queries = len(connection.queries)
            
            try:
                response = func(request, *args, **kwargs)
                return response
            finally:
                end_time = time.time()
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                end_queries = len(connection.queries)
                
                response_time = end_time - start_time
                memory_delta = end_memory - start_memory
                query_count = end_queries - start_queries
                
                # Log performance metrics
                monitor = PerformanceMonitor()
                monitor.log_performance_metrics(
                    view_name or func.__name__, 
                    response_time
                )
                
                # Log if performance is poor
                if response_time > 2.0:  # More than 2 seconds
                    logger.warning(
                        f"Slow response in {view_name or func.__name__}: "
                        f"{response_time:.2f}s, {query_count} queries, "
                        f"{memory_delta:.2f}MB memory"
                    )
        
        return wrapper
    return decorator

def optimize_queryset(queryset, max_results: int = 1000):
    """Optimize queryset for better performance"""
    # Add select_related for foreign keys
    if hasattr(queryset.model, '_meta'):
        related_fields = [
            field.name for field in queryset.model._meta.get_fields()
            if field.many_to_one and not field.null
        ]
        if related_fields:
            queryset = queryset.select_related(*related_fields[:5])  # Limit to 5 relations
    
    # Add prefetch_related for many-to-many fields
    many_to_many_fields = [
        field.name for field in queryset.model._meta.get_fields()
        if field.many_to_many
    ]
    if many_to_many_fields:
        queryset = queryset.prefetch_related(*many_to_many_fields[:3])  # Limit to 3 relations
    
    # Limit results
    return queryset[:max_results]

def get_performance_stats() -> Dict[str, Any]:
    """Get current performance statistics"""
    monitor = PerformanceMonitor()
    
    return {
        'memory_usage_mb': monitor.get_memory_usage(),
        'query_count': monitor.get_query_count(),
        'query_time': monitor.get_query_time(),
        'cpu_percent': psutil.cpu_percent(),
        'disk_usage': psutil.disk_usage('/').percent,
        'timestamp': timezone.now().isoformat()
    }

def clear_performance_cache():
    """Clear performance-related cache"""
    cache.delete_many([
        key for key in cache._cache.keys() 
        if key.startswith('performance_metrics_')
    ])
