from django.apps import AppConfig


class ScormConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scorm'
    
    def ready(self):
        import scorm.signals  # This will register the signals