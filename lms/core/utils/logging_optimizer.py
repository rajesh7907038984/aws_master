"""
Logging optimization utilities to prevent log spam and performance issues.

This module addresses the excessive logging that was causing memory issues
and filling up log files with repeated messages.
"""

import logging
import time
from typing import Dict, Set
from django.core.cache import cache

class ThrottledLogger:
    """
    Logger that throttles repeated messages to prevent log spam.
    """
    
    def __init__(self, logger_name: str, throttle_seconds: int = 60):
        self.logger = logging.getLogger(logger_name)
        self.throttle_seconds = throttle_seconds
        self.last_logged: Dict[str, float] = {}
        self.suppressed_count: Dict[str, int] = {}
    
    def _should_log(self, message: str) -> bool:
        """Check if message should be logged based on throttling rules."""
        current_time = time.time()
        message_hash = str(hash(message))
        
        last_time = self.last_logged.get(message_hash, 0)
        if current_time - last_time < self.throttle_seconds:
            # Increment suppressed count
            self.suppressed_count[message_hash] = self.suppressed_count.get(message_hash, 0) + 1
            return False
        
        # Time to log - update timestamp and check for suppressed messages
        self.last_logged[message_hash] = current_time
        return True
    
    def _get_suppressed_suffix(self, message: str) -> str:
        """Get suffix showing how many messages were suppressed."""
        message_hash = str(hash(message))
        suppressed = self.suppressed_count.get(message_hash, 0)
        if suppressed > 0:
            suffix = f" (suppressed {suppressed} similar messages)"
            self.suppressed_count[message_hash] = 0  # Reset counter
            return suffix
        return ""
    
    def info(self, message: str, *args, **kwargs):
        """Log info message with throttling."""
        if self._should_log(message):
            suffix = self._get_suppressed_suffix(message)
            self.logger.info(message + suffix, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message with throttling."""
        if self._should_log(message):
            suffix = self._get_suppressed_suffix(message)
            self.logger.debug(message + suffix, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message with throttling."""
        if self._should_log(message):
            suffix = self._get_suppressed_suffix(message)
            self.logger.warning(message + suffix, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message (errors are always logged)."""
        self.logger.error(message, *args, **kwargs)


class MemoryAwareLogger:
    """
    Logger that reduces verbosity when memory usage is high.
    """
    
    def __init__(self, logger_name: str, memory_threshold: int = 300):
        self.logger = logging.getLogger(logger_name)
        self.memory_threshold = memory_threshold
        self.throttled_logger = ThrottledLogger(logger_name)
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0
    
    def _is_high_memory(self) -> bool:
        """Check if memory usage is high."""
        return self._get_memory_usage() > self.memory_threshold
    
    def info(self, message: str, *args, **kwargs):
        """Log info message, throttled if memory is high."""
        if self._is_high_memory():
            # Use throttled logging when memory is high
            self.throttled_logger.info(message, *args, **kwargs)
        else:
            self.logger.info(message, *args, **kwargs)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message, suppressed if memory is high."""
        if not self._is_high_memory():
            self.logger.debug(message, *args, **kwargs)
        # Suppress debug messages when memory is high
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message with throttling."""
        self.throttled_logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message (always logged)."""
        self.logger.error(message, *args, **kwargs)


# Global logger instances
pdf_logger = MemoryAwareLogger('users.pdf_processing')
dashboard_logger = MemoryAwareLogger('admin_dashboard.performance')
memory_logger = MemoryAwareLogger('core.memory')

def get_optimized_logger(name: str, memory_threshold: int = 300) -> MemoryAwareLogger:
    """
    Get an optimized logger instance for the given module.
    
    Args:
        name: Logger name
        memory_threshold: Memory threshold in MB for switching to throttled mode
        
    Returns:
        MemoryAwareLogger instance
    """
    return MemoryAwareLogger(name, memory_threshold)

def suppress_noisy_loggers():
    """
    Suppress overly verbose loggers that cause performance issues.
    """
    # Suppress noisy third-party loggers
    noisy_loggers = [
        'django.db.backends',
        'django.template',
        'django.utils.autoreload',
        'PIL.PngImagePlugin',
        'urllib3.connectionpool',
    ]
    
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)  # Only show warnings and errors
    
    # Set PDF processing to use optimized logging
    pdf_base_logger = logging.getLogger('users')
    pdf_base_logger.setLevel(logging.INFO)  # Reduce verbosity

def configure_production_logging():
    """
    Configure logging for production to prevent performance issues.
    """
    # Suppress noisy loggers
    suppress_noisy_loggers()
    
    # Configure root logger
    root_logger = logging.getLogger()
    if len(root_logger.handlers) == 0:
        # Only add handler if none exists
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    
    print("Production logging configured - reduced verbosity for performance")
