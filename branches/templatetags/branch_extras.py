from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """
    Custom template filter to look up dictionary values by key.
    Usage: {{ dict|lookup:key }}
    """
    if dictionary and key:
        return dictionary.get(key)
    return None
