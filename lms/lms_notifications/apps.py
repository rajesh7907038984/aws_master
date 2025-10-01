from django.apps import AppConfig


class LmsNotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lms_notifications"
    verbose_name = "LMS Notifications"

    def ready(self):
        import lms_notifications.signals
