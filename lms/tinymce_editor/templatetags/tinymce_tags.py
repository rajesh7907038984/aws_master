from django import template
from django.utils.safestring import mark_safe
from django.templatetags.static import static
import json

register = template.Library()


@register.simple_tag
def tinymce_media():
    """
    Include TinyMCE media files (CSS and JS).
    Usage: {% tinymce_media %}
    """
    html = f'''
    <!-- TinyMCE ES5 compatibility script -->
    <script src="{static('core/js/tinymce-es5-compat.js')}"></script>
    <script src="{static('tinymce_editor/tinymce/tinymce.min.js')}"></script>
    <script src="{static('tinymce_editor/js/tinymce-widget.js')}"></script>
    <link rel="stylesheet" href="{static('tinymce_editor/css/tinymce-widget.css')}">
    
    <!-- Browser compatibility detection -->
    <script>
        window.browserHasES6Support = false;
        try {{
            // Test for ES6 features without using eval()
            Function('const test = () => {{}};')();
            window.browserHasES6Support = true;
        }} catch (e) {{
            console.warn('Browser does not support ES6 features, using ES5 compatible scripts for TinyMCE');
            window.browserHasES6Support = false;
        }}
    </script>
    '''
    return mark_safe(html)


@register.simple_tag
def tinymce_js():
    """
    Include only TinyMCE JavaScript files.
    Usage: {% tinymce_js %}
    """
    html = f'''
    <script src="{static('tinymce_editor/tinymce/tinymce.min.js')}"></script>
    <script src="{static('tinymce_editor/js/tinymce-widget.js')}"></script>
    '''
    return mark_safe(html)


@register.simple_tag
def tinymce_css():
    """
    Include only TinyMCE CSS files.
    Usage: {% tinymce_css %}
    """
    html = f'''
    <link rel="stylesheet" href="{static('tinymce_editor/css/tinymce-widget.css')}">
    '''
    return mark_safe(html)


@register.simple_tag
def tinymce_init(selector='textarea.tinymce-editor', config=None):
    """
    Initialize TinyMCE with custom configuration.
    
    Args:
        selector: CSS selector for textareas to convert
        config: Dictionary of TinyMCE configuration options
    
    Usage: 
        {% tinymce_init %}
        {% tinymce_init "textarea.my-editor" %}
        {% tinymce_init config='{"height": 400, "menubar": false}' %}
    """
    default_config = {
        'selector': selector,
        'base_url': static('tinymce_editor/tinymce/'),
        'height': 400,
        'menubar': True,
        'plugins': [
            'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
            'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
            'insertdatetime', 'media', 'table', 'help', 'wordcount'
        ],
        'toolbar': 'undo redo | blocks | ' +
                  'bold italic forecolor | alignleft aligncenter ' +
                  'alignright alignjustify | bullist numlist outdent indent | ' +
                  'removeformat | help',
        'content_style': 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
        'branding': False,
        'promotion': False,
    }
    
    if config:
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        if isinstance(config, dict):
            default_config.update(config)
    
    config_json = json.dumps(default_config)
    
    html = f'''
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            if (typeof tinymce !== 'undefined') {{
                tinymce.init({config_json});
            }}
        }});
    </script>
    '''
    return mark_safe(html)


@register.filter
def add_tinymce_class(field):
    """
    Add tinymce-editor class to a form field.
    Usage: {{ form.content|add_tinymce_class }}
    """
    if hasattr(field.field.widget, 'attrs'):
        current_class = field.field.widget.attrs.get('class', '')
        if 'tinymce-editor' not in current_class:
            field.field.widget.attrs['class'] = f'{current_class} tinymce-editor'.strip()
    return field


@register.inclusion_tag('tinymce_editor/tinymce_field.html')
def tinymce_field(field, **kwargs):
    """
    Render a TinyMCE enabled form field.
    Usage: {% tinymce_field form.content %}
    
    Additional options can be provided as keyword arguments:
    {% tinymce_field form.content height=500 plugins="code table" %}
    """
    # Get field ID
    field_id = field.auto_id if hasattr(field, 'auto_id') else f'id_{field.name}'
    
    # Basic configuration
    config = {
        'height': 300,
        'menubar': 'edit view insert format tools table',
        'plugins': 'lists advlist autolink link image charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table paste code help wordcount',
        'toolbar': 'undo redo | formatselect | bold italic backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | help'
    }
    
    # Update with any provided kwargs
    config.update(kwargs)
    
    # Convert the config to JSON for passing to the template
    config_json = json.dumps(config)
    
    return {
        'field': field,
        'field_id': field_id,
        'config': config_json,
    }


@register.inclusion_tag('tinymce_editor/tinymce_field_es5.html')
def tinymce_field_es5(field, **kwargs):
    """
    Render a TinyMCE enabled form field with ES5 compatibility.
    Usage: {% tinymce_field_es5 form.content %}
    
    Additional options can be provided as keyword arguments:
    {% tinymce_field_es5 form.content height=500 plugins="code table" %}
    """
    # Get field ID
    field_id = field.auto_id if hasattr(field, 'auto_id') else f'id_{field.name}'
    
    # Basic configuration - simpler for ES5 compatibility
    config = {
        'height': 300,
        'menubar': 'edit view insert format tools table',
        'plugins': 'lists advlist autolink link image charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table paste code help wordcount',
        'toolbar': 'undo redo | formatselect | bold italic | alignleft aligncenter alignright | bullist numlist | link image | code',
        'statusbar': False,
        'resize': False,
        'browser_spellcheck': True
    }
    
    # Update with any provided kwargs
    config.update(kwargs)
    
    # Convert the config to JSON for passing to the template
    config_json = json.dumps(config)
    
    return {
        'field': field,
        'field_id': field_id,
        'config': config_json,
    }


@register.inclusion_tag('tinymce_editor/tinymce_field_inline.html')
def tinymce_inline(field_id, **kwargs):
    """
    Create an inline TinyMCE editor.
    Usage: {% tinymce_inline "my-editable-div" %}
    """
    # Basic configuration
    config = {
        'inline': True,
        'menubar': False,
        'toolbar': 'undo redo | formatselect | bold italic | alignleft aligncenter alignright | bullist numlist | link image',
        'plugins': 'lists link image'
    }
    
    # Update with any provided kwargs
    config.update(kwargs)
    
    # Convert the config to JSON for passing to the template
    config_json = json.dumps(config)
    
    return {
        'field_id': field_id,
        'config': config_json,
    }


@register.inclusion_tag('tinymce_editor/tinymce_browser_compat.html')
def tinymce_browser_compat():
    """
    Render a TinyMCE browser compatibility check that will include the right
    version of the editor based on browser capability.
    
    Usage: {% tinymce_browser_compat %}
    """
    return {} 