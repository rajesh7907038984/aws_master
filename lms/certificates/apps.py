from django.apps import AppConfig


class CertificatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "certificates"
    verbose_name = "Certificate Management"
    
    def ready(self):
        """Import signals when the app is ready"""
        import certificates.signals