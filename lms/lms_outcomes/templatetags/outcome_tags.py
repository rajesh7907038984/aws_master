from django import template

register = template.Library()

@register.filter
def times(number):
    """Return a range of numbers from 0 to the specified number.
    
    Used for generating indentation in hierarchical dropdowns.
    Example usage: {% for _ in group.level|times %}—{% endfor %}
    """
    try:
        return range(int(number))
    except (ValueError, TypeError):
        return range(0) 