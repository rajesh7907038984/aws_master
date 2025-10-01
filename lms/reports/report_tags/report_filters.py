from django import template
from django.utils.html import escape

register = template.Library()

@register.filter
def get_report(dictionary, key):
    """Get item from dictionary by key with XSS protection (renamed to avoid conflict)"""
    if dictionary is None:
        return None
    
    value = dictionary.get(key)
    # Escape HTML to prevent XSS if value is a string
    if isinstance(value, str):
        return escape(value)
    return value

@register.simple_tag
def hello():
    return "Hello World" 