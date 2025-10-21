from django import template

register = template.Library()

@register.filter
def lookup(dictionary, key):
    """
    Template filter to lookup a value in a dictionary using a dynamic key.
    Usage: {{ dictionary|lookup:key }}
    """
    if dictionary and key is not None:
        return dictionary.get(key)
    return None

@register.filter
def get_item(dictionary, key):
    """
    Alternative template filter for dictionary lookup.
    Usage: {{ dictionary|get_item:key }}
    """
    return dictionary.get(key) if dictionary else None