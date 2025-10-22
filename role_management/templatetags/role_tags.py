from django import template

register = template.Library()

@register.filter
def format_capability(value):
    """Format capability name by replacing underscores with spaces and capitalizing each word"""
    return value.replace('_', ' ').title() 

@register.filter
def split(value, delimiter=','):
    """Split a string into a list using the specified delimiter."""
    return value.split(delimiter) 