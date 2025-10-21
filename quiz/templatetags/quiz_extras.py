from django import template

register = template.Library()

@register.filter
def get_item(obj, key):
    """
    Template filter to get an item from a dictionary by key or an attribute from an object
    Usage: {{ dictionary|get_item:key }} or {{ object|get_item:attribute }}
    """
    if obj is None:
        return None
    
    # Handle dictionary access
    if isinstance(obj, dict):
        return obj.get(key)
    
    # Handle object attribute access
    try:
        return getattr(obj, key)
    except (AttributeError, TypeError):
        # For safety, return None if attribute doesn't exist
        return None

@register.filter
def get_rating_id(evaluation):
    """
    Template filter to get the rating ID from an evaluation object
    Usage: {{ evaluation|get_rating_id }}
    """
    if evaluation is None:
        return None
    
    if hasattr(evaluation, 'rating') and evaluation.rating:
        return evaluation.rating.id
    
    return None

@register.filter
def sum_rubric_points(evaluations):
    """
    Template filter to sum up all points from a queryset of rubric evaluations
    Usage: {{ evaluations|sum_rubric_points }}
    """
    if not evaluations:
        return 0
    
    total_points = 0
    for evaluation in evaluations:
        if hasattr(evaluation, 'points'):
            total_points += evaluation.points
    
    return total_points 