from django import template
from django.conf import settings
from django.utils import timezone
from conferences.models import Conference
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key"""
    if dictionary and key is not None:
        return dictionary.get(key)
    return None

@register.filter 
def sum_points(evaluations, field=None):
    """
    Sum the points from a collection of evaluations.
    Handles both nested dictionaries and simple querysets/lists.
    """
    if not evaluations:
        return 0
    
    total = 0
    
    # Handle dictionary with nested structure (criterion_id -> evaluation)
    if hasattr(evaluations, 'values'):
        for item in evaluations.values():
            # Check if item is a nested dictionary (criterion_id -> evaluation)
            if isinstance(item, dict):
                # If it's a nested dictionary, sum points from its values
                for evaluation in item.values():
                    if hasattr(evaluation, 'points'):
                        total += evaluation.points
            elif hasattr(item, 'points'):
                # If it's a direct evaluation object
                total += item.points
    else:
        # Handle list/queryset of evaluations
        try:
            for evaluation in evaluations:
                if field and hasattr(evaluation, field):
                    total += getattr(evaluation, field, 0)
                elif hasattr(evaluation, 'points'):
                    total += evaluation.points
        except (AttributeError, TypeError):
            pass
    
    return total

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces in a string."""
    if value:
        return str(value).replace('_', ' ')
    return value

@register.simple_tag
def get_conference_rubric_evaluations(conference):
    """Get all conference rubric evaluations for timeline display"""
    try:
        from conferences.models import ConferenceRubricEvaluation
        evaluations = ConferenceRubricEvaluation.objects.filter(
            conference=conference
        ).select_related(
            'attendance', 
            'attendance__user', 
            'criterion', 
            'rating', 
            'evaluated_by'
        ).order_by('attendance__user__last_name', 'criterion__position', '-created_at')
        return evaluations
    except Exception as e:
        return []

 