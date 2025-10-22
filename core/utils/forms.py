from django import forms
from django.forms import ModelForm
from tinymce_editor.forms import TinyMCEFormField
from tinymce_editor.widgets import TinyMCEWidget
from .fields import TinyMCEField

class CustomTinyMCEFormField(TinyMCEFormField):
    """
    Custom TinyMCE form field with standard configuration 
    for use across application forms.
    """
    def __init__(self, *args, **kwargs):
        # Set default form field configurations
        if 'required' not in kwargs:
            kwargs['required'] = False
            
        # Set custom TinyMCE configuration
        custom_config = {
            'skin': 'oxide',
            'plugins': 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount help aiwriter toolbarfix',
            'toolbar': 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen help aiwriter',
            'toolbar_mode': 'sliding',
            'toolbar_sticky': True,
            'toolbar_location': 'top',
            'branding': False,
            'promotion': False,
            'menubar': 'edit view insert format table',
            'statusbar': True,
            'resize': 'both',
            'elementpath': True,
            'height': 300,
            'placeholder': 'Enter your content here...',
            'setup': '''function(editor) {
                editor.on('init', function() {
                    setTimeout(function() {
                        // Force display of toolbar elements
                        var container = editor.getContainer();
                        var toolbar = container.querySelector('.tox-toolbar__primary');
                        var toolbarGroups = container.querySelectorAll('.tox-toolbar__group');
                        var buttons = container.querySelectorAll('.tox-tbtn');
                        
                        if (toolbar) toolbar.style.display = 'flex';
                        toolbarGroups.forEach(function(group) { group.style.display = 'flex'; });
                        buttons.forEach(function(btn) { btn.style.display = 'flex'; });
                        
                        // Hide overflow button
                        var overflowBtn = container.querySelector('[data-mce-name="overflow-button"]');
                        if (overflowBtn) overflowBtn.style.display = 'none';
                        
                        editor.fire('ResizeEditor');
                    }, 500);
                });
            }''',
            'external_plugins': {
                'aiwriter': '/static/tinymce_editor/js/plugins/aiwriter/plugin.js',
                'toolbarfix': '/static/tinymce_editor/js/plugins/toolbar-fix/plugin.js'
            }
        }
        
        # Create a TinyMCEWidget with the custom configuration
        widget = TinyMCEWidget(config=custom_config)
        
        # Set widget in kwargs
        kwargs['widget'] = widget
            
        super().__init__(*args, **kwargs)
        
class BaseModelFormWithTinyMCE(ModelForm):
    """
    Base model form with support for TinyMCEField.
    Inherit from this class when creating forms for models
    that use TinyMCEField.
    
    Example usage:
    
    class CourseForm(BaseModelFormWithTinyMCE):
        class Meta:
            model = Course
            fields = ['title', 'description', 'course_outcomes', 'course_rubrics']
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Automatically detect and apply custom widget for all TinyMCEFields
        for field_name, field in self.fields.items():
            try:
                model_field = self._meta.model._meta.get_field(field_name)
                if isinstance(model_field, TinyMCEField):
                    self.fields[field_name] = CustomTinyMCEFormField(
                        required=field.required,
                        label=field.label,
                        help_text=field.help_text,
                        initial=field.initial
                    )
            except Exception as e:
                # Skip fields that don't exist in the model
                pass

# Alias for backward compatibility
BaseModelFormWithQuill = BaseModelFormWithTinyMCE 