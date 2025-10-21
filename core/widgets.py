import json
from django import forms
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe


class NesxyEditor(forms.Widget):
    """
    A rich text editor widget for use in Django forms.
    Uses a modern editor interface with enhanced features.
    """
    template_name = 'core/widgets/nesxy/editor.html'
    
    class Media:
        css = {
            'all': [
                'core/css/nesxy-editor.css',
            ]
        }
        js = [
            'core/js/nesxy-editor.js',
        ]
    
    def __init__(self, attrs=None, placeholder=None, height='300px', 
                 toolbar_items=None, enable_theme_toggle=True):
        super().__init__(attrs)
        self.placeholder = placeholder
        self.height = height
        self.toolbar_items = toolbar_items
        self.enable_theme_toggle = enable_theme_toggle
    
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context.update({
            'placeholder': self.placeholder,
            'height': self.height,
            'enable_theme_toggle': self.enable_theme_toggle,
        })
        
        # Add toolbar items if provided
        if self.toolbar_items:
            if isinstance(self.toolbar_items, list):
                context['toolbar_items'] = json.dumps(self.toolbar_items)
            else:
                context['toolbar_items'] = self.toolbar_items
        
        return context
    
    def format_value(self, value):
        # Handle multiple possible input formats
        if not value:
            return ""
        
        # If value is already a string, return it
        if isinstance(value, str):
            try:
                # Try to parse as JSON to validate
                json_obj = json.loads(value)
                return value
            except json.JSONDecodeError:
                # Not valid JSON, wrap it as HTML content
                return json.dumps({
                    'delta': None,
                    'html': value
                })
        
        # If value is a dict or other object, convert to JSON string
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            # Fallback for any other type
            return str(value)


class SimpleNesxyEditor(NesxyEditor):
    """
    A simplified version of the Nesxy editor with a basic toolbar
    """
    def __init__(self, attrs=None, placeholder=None, height='200px'):
        toolbar_items = [
            ['bold', 'italic', 'underline'],
            [{'list': 'ordered'}, {'list': 'bullet'}],
            ['link', 'image'],
            ['clean']
        ]
        super().__init__(
            attrs=attrs,
            placeholder=placeholder,
            height=height,
            toolbar_items=toolbar_items,
            enable_theme_toggle=True
        )


class FullNesxyEditor(NesxyEditor):
    """
    An extended version of the Nesxy editor with all features enabled
    """
    def __init__(self, attrs=None, placeholder=None, height='400px'):
        toolbar_items = [
            [{'header': [1, 2, 3, 4, 5, 6, False]}],
            ['bold', 'italic', 'underline', 'strike'],
            ['blockquote', 'code-block'],
            [{'list': 'ordered'}, {'list': 'bullet'}],
            [{'script': 'sub'}, {'script': 'super'}],
            [{'indent': '-1'}, {'indent': '+1'}],
            [{'direction': 'rtl'}],
            [{'color': []}, {'background': []}],
            [{'align': []}],
            ['link', 'image', 'video', 'table'],
            ['clean']
        ]
        super().__init__(
            attrs=attrs,
            placeholder=placeholder,
            height=height,
            toolbar_items=toolbar_items,
            enable_theme_toggle=True
        ) 