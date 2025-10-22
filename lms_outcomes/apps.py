from django.apps import AppConfig


class LmsOutcomesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lms_outcomes'
    verbose_name = 'Learning Outcomes'
    
    def ready(self):
        import lms_outcomes.signals 