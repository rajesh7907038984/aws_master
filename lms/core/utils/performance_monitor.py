"""
Performance Monitor Utility
Provides system performance monitoring and metrics collection
"""

import time
import psutil
from django.conf import settings
from django.db import connection
from django.utils import timezone


def get_performance_stats():
    """
    Get current system performance statistics
    """
    try:
        # Basic system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Database connection count
        db_connections = len(connection.queries) if hasattr(connection, 'queries') else 0
        
        # Cache status (removed - no longer using cache)
        cache_status = 'disabled'
        
        return {
            'timestamp': timezone.now().isoformat(),
            'cpu_percent': cpu_percent,
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
            'database': {
                'connections': db_connections,
                'status': 'connected'
            },
            'cache': {
                'status': cache_status
            }
        }
    except Exception as e:
        return {
            'timestamp': timezone.now().isoformat(),
            'error': str(e),
            'status': 'error'
        }


def get_system_health():
    """
    Get overall system health status
    """
    try:
        stats = get_performance_stats()
        
        # Determine health status based on metrics
        health_score = 100
        
        # CPU usage penalty
        if stats.get('cpu_percent', 0) > 80:
            health_score -= 20
        elif stats.get('cpu_percent', 0) > 60:
            health_score -= 10
        
        # Memory usage penalty
        memory_percent = stats.get('memory', {}).get('percent', 0)
        if memory_percent > 90:
            health_score -= 30
        elif memory_percent > 80:
            health_score -= 15
        
        # Disk usage penalty
        disk_percent = stats.get('disk', {}).get('percent', 0)
        if disk_percent > 90:
            health_score -= 25
        elif disk_percent > 80:
            health_score -= 10
        
        # Determine status
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 70:
            status = 'good'
        elif health_score >= 50:
            status = 'fair'
        else:
            status = 'poor'
        
        return {
            'status': status,
            'score': max(0, health_score),
            'timestamp': timezone.now().isoformat(),
            'metrics': stats
        }
    except Exception as e:
        return {
            'status': 'error',
            'score': 0,
            'timestamp': timezone.now().isoformat(),
            'error': str(e)
        }
