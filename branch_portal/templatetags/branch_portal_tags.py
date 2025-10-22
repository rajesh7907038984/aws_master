from django import template

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract the arg from the value."""
    try:
        return value - arg
    except (ValueError, TypeError):
        try:
            return int(value) - int(arg)
        except (ValueError, TypeError):
            return 0 