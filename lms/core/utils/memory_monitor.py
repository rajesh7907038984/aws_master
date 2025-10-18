"""
Memory Monitoring Utility for LMS
Provides comprehensive memory monitoring and optimization
"""

import gc
import psutil
import logging
import threading
import time
from typing import Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

class MemoryMonitor:
    """Advanced memory monitoring and optimization"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.monitoring = False
        self.cleanup_thread = None
        self.stats = {
            'peak_memory': 0,
            'current_memory': 0,
            'gc_count': 0,
            'cleanup_count': 0
        }
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics"""
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            
            # Update stats
            self.stats['current_memory'] = memory_mb
            if memory_mb > self.stats['peak_memory']:
                self.stats['peak_memory'] = memory_mb
            
            return {
                'rss_mb': memory_mb,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'percent': self.process.memory_percent(),
                'available_mb': psutil.virtual_memory().available / 1024 / 1024,
                'total_mb': psutil.virtual_memory().total / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return {'rss_mb': 0, 'vms_mb': 0, 'percent': 0, 'available_mb': 0, 'total_mb': 0}
    
    def should_trigger_cleanup(self) -> bool:
        """Check if memory cleanup should be triggered"""
        memory_stats = self.get_memory_usage()
        threshold = getattr(settings, 'MEMORY_WARNING_THRESHOLD_MB', 800)
        return memory_stats['rss_mb'] > threshold
    
    def should_trigger_critical_cleanup(self) -> bool:
        """Check if critical memory cleanup should be triggered"""
        memory_stats = self.get_memory_usage()
        threshold = getattr(settings, 'MEMORY_THRESHOLD_MB', 1000)
        return memory_stats['rss_mb'] > threshold
    
    def cleanup_memory(self, force: bool = False) -> Dict[str, any]:
        """Perform memory cleanup operations"""
        if not force and not self.should_trigger_cleanup():
            return {'cleaned': False, 'reason': 'Memory usage within limits'}
        
        try:
            # Get memory before cleanup
            before_stats = self.get_memory_usage()
            
            # Force garbage collection
            collected = gc.collect()
            self.stats['gc_count'] += 1
            
            # Get memory after cleanup
            after_stats = self.get_memory_usage()
            
            # Calculate memory freed
            memory_freed = before_stats['rss_mb'] - after_stats['rss_mb']
            self.stats['cleanup_count'] += 1
            
            logger.info(f"Memory cleanup completed: {memory_freed:.2f}MB freed, {collected} objects collected")
            
            return {
                'cleaned': True,
                'memory_freed_mb': memory_freed,
                'objects_collected': collected,
                'before_mb': before_stats['rss_mb'],
                'after_mb': after_stats['rss_mb']
            }
            
        except Exception as e:
            logger.error(f"Error during memory cleanup: {e}")
            return {'cleaned': False, 'error': str(e)}
    
    def start_monitoring(self):
        """Start background memory monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.cleanup_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.cleanup_thread.start()
        logger.info("Memory monitoring started")
    
    def stop_monitoring(self):
        """Stop background memory monitoring"""
        self.monitoring = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        logger.info("Memory monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        cleanup_interval = getattr(settings, 'MEMORY_CLEANUP_INTERVAL', 300)
        
        while self.monitoring:
            try:
                # Check if cleanup is needed
                if self.should_trigger_critical_cleanup():
                    logger.warning("Critical memory usage detected, performing cleanup")
                    self.cleanup_memory(force=True)
                elif self.should_trigger_cleanup():
                    logger.info("High memory usage detected, performing cleanup")
                    self.cleanup_memory()
                
                # Log memory stats periodically
                memory_stats = self.get_memory_usage()
                if memory_stats['rss_mb'] > 0:
                    logger.debug(f"Memory usage: {memory_stats['rss_mb']:.2f}MB ({memory_stats['percent']:.1f}%)")
                
                time.sleep(cleanup_interval)
                
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    
    def get_stats(self) -> Dict[str, any]:
        """Get comprehensive memory statistics"""
        memory_stats = self.get_memory_usage()
        return {
            **memory_stats,
            **self.stats,
            'monitoring_active': self.monitoring,
            'cleanup_needed': self.should_trigger_cleanup(),
            'critical_cleanup_needed': self.should_trigger_critical_cleanup()
        }

# Global memory monitor instance
memory_monitor = MemoryMonitor()

def get_memory_monitor() -> MemoryMonitor:
    """Get the global memory monitor instance"""
    return memory_monitor

def cleanup_memory_if_needed():
    """Convenience function to cleanup memory if needed"""
    return memory_monitor.cleanup_memory()

def start_memory_monitoring():
    """Start memory monitoring if enabled"""
    if getattr(settings, 'ENABLE_MEMORY_MONITORING', True):
        memory_monitor.start_monitoring()
