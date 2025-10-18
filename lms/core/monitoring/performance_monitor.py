"""
Performance Monitoring System
Comprehensive performance monitoring and optimization for LMS
"""

import time
import psutil
import logging
import threading
from typing import Dict, List, Optional
from django.conf import settings
from django.db import connection
from django.core.cache import cache

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Advanced performance monitoring system"""
    
    def __init__(self):
        self.metrics = {
            'response_times': [],
            'memory_usage': [],
            'cpu_usage': [],
            'db_queries': [],
            'cache_hits': 0,
            'cache_misses': 0,
            'error_count': 0,
            'request_count': 0
        }
        self.monitoring = False
        self.monitor_thread = None
        self.start_time = time.time()
    
    def start_monitoring(self):
        """Start performance monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Performance monitoring started")
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")
    
    def record_request(self, response_time: float, memory_usage: float, db_queries: int):
        """Record request metrics"""
        self.metrics['request_count'] += 1
        self.metrics['response_times'].append(response_time)
        self.metrics['memory_usage'].append(memory_usage)
        self.metrics['db_queries'].append(db_queries)
        
        # Keep only last 1000 records to prevent memory issues
        if len(self.metrics['response_times']) > 1000:
            self.metrics['response_times'] = self.metrics['response_times'][-1000:]
            self.metrics['memory_usage'] = self.metrics['memory_usage'][-1000:]
            self.metrics['db_queries'] = self.metrics['db_queries'][-1000:]
    
    def record_error(self):
        """Record error occurrence"""
        self.metrics['error_count'] += 1
    
    def record_cache_hit(self):
        """Record cache hit"""
        self.metrics['cache_hits'] += 1
    
    def record_cache_miss(self):
        """Record cache miss"""
        self.metrics['cache_misses'] += 1
    
    def get_performance_stats(self) -> Dict:
        """Get comprehensive performance statistics"""
        if not self.metrics['response_times']:
            return {'status': 'No data available'}
        
        # Calculate averages
        avg_response_time = sum(self.metrics['response_times']) / len(self.metrics['response_times'])
        avg_memory_usage = sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage'])
        avg_db_queries = sum(self.metrics['db_queries']) / len(self.metrics['db_queries'])
        
        # Calculate percentiles
        sorted_response_times = sorted(self.metrics['response_times'])
        p95_response_time = sorted_response_times[int(len(sorted_response_times) * 0.95)]
        p99_response_time = sorted_response_times[int(len(sorted_response_times) * 0.99)]
        
        # Cache hit rate
        total_cache_operations = self.metrics['cache_hits'] + self.metrics['cache_misses']
        cache_hit_rate = (self.metrics['cache_hits'] / total_cache_operations * 100) if total_cache_operations > 0 else 0
        
        # Error rate
        error_rate = (self.metrics['error_count'] / self.metrics['request_count'] * 100) if self.metrics['request_count'] > 0 else 0
        
        # System metrics
        system_metrics = self._get_system_metrics()
        
        return {
            'uptime_seconds': time.time() - self.start_time,
            'total_requests': self.metrics['request_count'],
            'total_errors': self.metrics['error_count'],
            'error_rate_percent': error_rate,
            'avg_response_time_ms': avg_response_time * 1000,
            'p95_response_time_ms': p95_response_time * 1000,
            'p99_response_time_ms': p99_response_time * 1000,
            'avg_memory_usage_mb': avg_memory_usage,
            'avg_db_queries_per_request': avg_db_queries,
            'cache_hit_rate_percent': cache_hit_rate,
            'system_metrics': system_metrics,
            'performance_score': self._calculate_performance_score(avg_response_time, error_rate, cache_hit_rate)
        }
    
    def _get_system_metrics(self) -> Dict:
        """Get system-level metrics"""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage_percent': psutil.disk_usage('/').percent,
                'load_average': psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def _calculate_performance_score(self, avg_response_time: float, error_rate: float, cache_hit_rate: float) -> int:
        """Calculate overall performance score (0-100)"""
        score = 100
        
        # Response time penalty
        if avg_response_time > 2.0:  # > 2 seconds
            score -= 30
        elif avg_response_time > 1.0:  # > 1 second
            score -= 15
        elif avg_response_time > 0.5:  # > 500ms
            score -= 5
        
        # Error rate penalty
        if error_rate > 10:  # > 10% error rate
            score -= 40
        elif error_rate > 5:  # > 5% error rate
            score -= 20
        elif error_rate > 1:  # > 1% error rate
            score -= 10
        
        # Cache hit rate bonus
        if cache_hit_rate > 80:  # > 80% cache hit rate
            score += 10
        elif cache_hit_rate < 50:  # < 50% cache hit rate
            score -= 10
        
        return max(0, min(100, score))
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.monitoring:
            try:
                # Record system metrics
                cpu_usage = psutil.cpu_percent()
                memory_usage = psutil.virtual_memory().percent
                
                self.metrics['cpu_usage'].append(cpu_usage)
                self.metrics['memory_usage'].append(memory_usage)
                
                # Keep only last 100 records
                if len(self.metrics['cpu_usage']) > 100:
                    self.metrics['cpu_usage'] = self.metrics['cpu_usage'][-100:]
                
                # Log performance warnings
                if cpu_usage > 80:
                    logger.warning(f"High CPU usage: {cpu_usage}%")
                if memory_usage > 80:
                    logger.warning(f"High memory usage: {memory_usage}%")
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in performance monitoring loop: {e}")
                time.sleep(60)
    
    def get_recommendations(self) -> List[str]:
        """Get performance optimization recommendations"""
        recommendations = []
        stats = self.get_performance_stats()
        
        if stats.get('avg_response_time_ms', 0) > 1000:
            recommendations.append("Consider optimizing database queries - average response time is high")
        
        if stats.get('error_rate_percent', 0) > 5:
            recommendations.append("High error rate detected - investigate error logs")
        
        if stats.get('cache_hit_rate_percent', 0) < 50:
            recommendations.append("Low cache hit rate - consider implementing more caching")
        
        if stats.get('avg_db_queries_per_request', 0) > 10:
            recommendations.append("High number of database queries per request - consider query optimization")
        
        system_metrics = stats.get('system_metrics', {})
        if system_metrics.get('cpu_percent', 0) > 80:
            recommendations.append("High CPU usage - consider scaling or optimization")
        
        if system_metrics.get('memory_percent', 0) > 80:
            recommendations.append("High memory usage - consider memory optimization")
        
        return recommendations

# Global performance monitor instance
performance_monitor = PerformanceMonitor()

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance"""
    return performance_monitor

def start_performance_monitoring():
    """Start performance monitoring if enabled"""
    if getattr(settings, 'ENABLE_PERFORMANCE_MONITORING', True):
        performance_monitor.start_monitoring()
