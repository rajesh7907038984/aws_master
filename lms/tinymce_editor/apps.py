from django.apps import AppConfig


class TinymceEditorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tinymce_editor"
    verbose_name = "TinyMCE Editor"
    
    def ready(self):
        """Initialize any app-specific functionality."""
        pass
