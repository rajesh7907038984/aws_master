from django.apps import AppConfig


class ConferencesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'conferences'
    
    def ready(self):
        # Import signals to ensure they're registered
        import conferences.models  # This will import the signal handlers
        import conferences.signals  # Import our custom signals
