from django.apps import AppConfig


class BranchPortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "branch_portal"
    verbose_name = "Branch Portals & Orders"

    def ready(self):
        # Import signals
        import branch_portal.signals
