from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core Features'
    
    def ready(self):
        """Import signal handlers when the app is ready"""
        try:
            from core.utils import cache_signals
        except ImportError:
            pass
        