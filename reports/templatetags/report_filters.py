from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using a key with XSS protection."""
    if hasattr(dictionary, 'get'):
        value = dictionary.get(key)
        # Escape HTML to prevent XSS if value is a string
        if isinstance(value, str):
            return escape(value)
        return value
    return None

@register.filter
def get(dictionary, key):
    """Get an item from a dictionary using a key with XSS protection (alias for get_item)."""
    if hasattr(dictionary, 'get'):
        value = dictionary.get(key)
        # Escape HTML to prevent XSS if value is a string
        if isinstance(value, str):
            return escape(value)
        return value
    return None

@register.filter
def replace(value, arg):
    """Replace underscores with spaces in the value with XSS protection."""
    if not isinstance(value, str) or not isinstance(arg, str):
        return value
    
    # Escape input to prevent XSS
    safe_value = escape(value)
    safe_arg = escape(arg)
    
    if safe_arg == "_":
        return safe_value.replace("_", " ")
    return safe_value

@register.filter
def title_with_spaces(value):
    """Convert field names to title case with spaces instead of underscores with XSS protection."""
    if not isinstance(value, str):
        return value
    
    # Escape input to prevent XSS
    safe_value = escape(value)
    return safe_value.replace("_", " ").title()

@register.simple_tag
def hello():
    return "Hello World" 