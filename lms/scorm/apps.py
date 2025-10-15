from django.apps import AppConfig


class ScormConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scorm'
    verbose_name = 'SCORM Management'
    
    def ready(self):
        """Import signals when the app is ready"""
        try:
            import scorm.signals
        except ImportError:
            pass

