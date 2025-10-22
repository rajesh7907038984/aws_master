from django import template
import os
import html
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def get_filename(value):
    """Returns the filename from a file path."""
    if value:
        return os.path.basename(str(value))
    return '' 

@register.filter
def basename(value):
    """Returns the filename from a file path."""
    if value:
        return os.path.basename(str(value))
    return ''

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces in a string."""
    if value:
        return str(value).replace('_', ' ')
    return value

@register.filter
def get_item(dictionary, key):
    """Returns the value from a dictionary for the given key."""
    if dictionary and key in dictionary:
        return dictionary[key]
    return None

@register.filter
def filter_by_user(queryset, user):
    """Filter queryset by a specific user."""
    if queryset and user:
        return queryset.filter(created_by=user)
    return queryset.none() if queryset else []

@register.filter
def has_rubric_evaluation(student, discussion):
    """Check if a student has been graded for a specific discussion."""
    if not student or not discussion:
        return False
    
    # Import here to avoid circular imports
    from lms_rubrics.models import RubricEvaluation
    
    return RubricEvaluation.objects.filter(
        discussion=discussion,
        student=student
    ).exists() 

@register.filter
def get_rubric_evaluation_score(student, discussion):
    """Get the student's total rubric evaluation score for a discussion."""
    if not student or not discussion or not discussion.rubric:
        return None
    
    # Import here to avoid circular imports
    from lms_rubrics.models import RubricEvaluation
    
    evaluations = RubricEvaluation.objects.filter(
        discussion=discussion,
        student=student
    )
    
    if evaluations.exists():
        total_points = sum(eval.points for eval in evaluations)
        max_points = discussion.rubric.total_points
        return {
            'total_points': total_points,
            'max_points': max_points,
            'percentage': round((total_points / max_points * 100), 1) if max_points > 0 else 0
        }
    
    return None


@register.filter
def safe_file_size(file_field):
    """
    Safely get file size without raising FileNotFoundError.
    Returns 0 if file doesn't exist or can't be accessed.
    
    Args:
        file_field: Django FileField instance
    
    Returns:
        File size in bytes or 0 if not accessible
    """
    try:
        if file_field and hasattr(file_field, 'size') and file_field.name:
            return file_field.size
    except (FileNotFoundError, OSError, ValueError):
        # File doesn't exist on disk or other file access error
        pass
    return 0

@register.filter
def decode_html(value):
    """
    Decode HTML entities that might be double-encoded in discussion content.
    This helps fix existing content that shows HTML tags instead of rendered content.
    
    Args:
        value: String that might contain HTML entities
    
    Returns:
        Decoded HTML string safe for rendering
    """
    if not value:
        return ""
    
    try:
        # First decode any HTML entities (like &lt; to <)
        decoded = html.unescape(str(value))
        # Return as safe HTML for rendering
        return mark_safe(decoded)
    except (ValueError, TypeError, AttributeError):
        # If decoding fails, return the original value as safe
        # Import html here to avoid scoping issues
        import html as html_module
        escaped_value = html_module.escape(str(value))
        return mark_safe(escaped_value) 