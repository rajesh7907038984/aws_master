from django import forms
from .widgets import TinyMCEWidget, TinyMCEAdvancedWidget, TinyMCESimpleWidget


class TinyMCEFormField(forms.CharField):
    """
    Base TinyMCE form field with default widget.
    """
    
    def __init__(self, config=None, widget=None, *args, **kwargs):
        if widget is None:
            widget = TinyMCEWidget(config=config)
        elif isinstance(widget, type) and issubclass(widget, TinyMCEWidget):
            widget = widget(config=config)
        
        kwargs['widget'] = widget
        super().__init__(*args, **kwargs)


class TinyMCEAdvancedFormField(TinyMCEFormField):
    """
    Advanced TinyMCE form field with all features enabled.
    """
    
    def __init__(self, config=None, *args, **kwargs):
        widget = TinyMCEAdvancedWidget(config=config)
        super().__init__(widget=widget, *args, **kwargs)


class TinyMCESimpleFormField(TinyMCEFormField):
    """
    Simple TinyMCE form field with minimal features.
    """
    
    def __init__(self, config=None, *args, **kwargs):
        widget = TinyMCESimpleWidget(config=config)
        super().__init__(widget=widget, *args, **kwargs)


class TinyMCETextarea(forms.Textarea):
    """
    Simple textarea replacement that becomes a TinyMCE editor.
    Use this as a direct replacement for forms.Textarea.
    """
    
    def __init__(self, attrs=None, config=None):
        if attrs is None:
            attrs = {}
        attrs['class'] = attrs.get('class', '') + ' tinymce-editor'
        if config:
            import json
            attrs['data-tinymce-config'] = json.dumps(config)
        super().__init__(attrs)


# Example form mixins for common use cases
class TinyMCEFormMixin:
    """
    Mixin for Django forms to easily add TinyMCE fields.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tinymce_to_fields()
    
    def apply_tinymce_to_fields(self):
        """
        Apply TinyMCE widget to specified fields.
        Override tinymce_fields in your form to specify which fields to convert.
        """
        tinymce_fields = getattr(self, 'tinymce_fields', [])
        for field_name in tinymce_fields:
            if field_name in self.fields:
                field = self.fields[field_name]
                if isinstance(field, forms.CharField):
                    field.widget = TinyMCEWidget()


class TinyMCEModelFormMixin:
    """
    Mixin for Django ModelForms to easily add TinyMCE fields.
    """
    
    class Meta:
        abstract = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_tinymce_to_text_fields()
    
    def apply_tinymce_to_text_fields(self):
        """
        Apply TinyMCE widget to TextField fields.
        """
        for field_name, field in self.fields.items():
            if (isinstance(field, forms.CharField) and 
                hasattr(self._meta.model, field_name)):
                model_field = self._meta.model._meta.get_field(field_name)
                # Apply to TextField and TextField subclasses
                if (hasattr(model_field, 'max_length') and 
                    (model_field.max_length is None or model_field.max_length > 500)):
                    field.widget = TinyMCEWidget() 