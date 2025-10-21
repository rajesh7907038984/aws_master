from django.apps import AppConfig


class SharepointIntegrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sharepoint_integration'
    verbose_name = 'SharePoint Integration'
    
    def ready(self):
        """Initialize app when Django starts"""
        # Import signals if any
        try:
            from . import signals
        except ImportError:
            pass
