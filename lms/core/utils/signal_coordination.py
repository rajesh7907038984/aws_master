"""
Signal coordination utilities to prevent signal conflicts and improve performance
"""

import logging
from functools import wraps
from django.db import transaction

logger = logging.getLogger(__name__)

class SignalCoordinator:
    """Coordinates signals to prevent conflicts and improve performance"""
    
    _signal_registry = {}
    _signal_priority = {}
    
    @classmethod
    def register_signal(cls, signal_name, priority=0):
        """Register a signal with a priority level"""
        cls._signal_registry[signal_name] = priority
        cls._signal_priority[priority] = signal_name
    
    @classmethod
    def should_process_signal(cls, signal_name, instance, created):
        """Determine if a signal should be processed based on context"""
        # Skip processing for certain enrollment sources to prevent loops
        if hasattr(instance, 'enrollment_source'):
            skip_sources = ['auto_group', 'auto_prerequisite', 'auto_dependent']
            if instance.enrollment_source in skip_sources and not created:
                return False
        
        # Skip processing for bulk operations
        if hasattr(instance, '_bulk_operation'):
            return False
            
        return True
    
    @classmethod
    def coordinate_signal(cls, signal_name):
        """Decorator to coordinate signal processing"""
        def decorator(func):
            @wraps(func)
            def wrapper(sender, instance, created, **kwargs):
                if not cls.should_process_signal(signal_name, instance, created):
                    logger.debug(f"Skipping {signal_name} for {instance}")
                    return
                
                try:
                    with transaction.atomic():
                        return func(sender, instance, created, **kwargs)
                except Exception as e:
                    logger.error(f"Error in {signal_name}: {e}")
                    # Don't re-raise to prevent breaking the main operation
            return wrapper
        return decorator

# Register signal priorities
SignalCoordinator.register_signal('cache_invalidation', priority=1)
SignalCoordinator.register_signal('logging', priority=2)
SignalCoordinator.register_signal('notifications', priority=3)
SignalCoordinator.register_signal('sharepoint_sync', priority=5)
