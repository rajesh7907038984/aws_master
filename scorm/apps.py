from django.apps import AppConfig


class ScormConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scorm'
    verbose_name = 'SCORM Packages'
    
    def ready(self):
        """Import signals when app is ready"""
        import scorm.signals  # noqa

