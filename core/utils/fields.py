from django.db import models


class TinyMCEField(models.TextField):
    """
    TinyMCE rich text field - stores content as HTML in a TextField.
    
    This field is used to replace the old Quill editor fields with TinyMCE editor.
    Content is stored as HTML in the database.
    """
    
    def __init__(self, *args, **kwargs):
        # Set default configurations if not provided
        if 'blank' not in kwargs:
            kwargs['blank'] = True
        if 'default' not in kwargs:
            kwargs['default'] = ''
            
        super().__init__(*args, **kwargs)


# CustomQuillField has been completely replaced with TinyMCEField
# All migration files have been updated to use TinyMCEField directly