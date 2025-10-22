from django.apps import AppConfig


class LmsMessagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lms_messages"
    verbose_name = "LMS Messages"
    
    def ready(self):
        """Import signals when app is ready"""
        import lms_messages.signals