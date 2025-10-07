from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def star_rating_display(rating, max_rating=5, show_number=True):
    """
    Display star rating with filled and empty stars
    Usage: {% star_rating_display course.average_rating %}
    """
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0.0
    
    full_stars = int(rating)
    half_star = (rating - full_stars) >= 0.5
    empty_stars = max_rating - full_stars - (1 if half_star else 0)
    
    html = '<span class="star-rating-display">'
    
    # Full stars
    for i in range(full_stars):
        html += '<i class="fas fa-star text-warning"></i>'
    
    # Half star
    if half_star:
        html += '<i class="fas fa-star-half-alt text-warning"></i>'
    
    # Empty stars
    for i in range(empty_stars):
        html += '<i class="far fa-star text-warning"></i>'
    
    if show_number:
        html += f' <span class="rating-number">({rating:.1f})</span>'
    
    html += '</span>'
    
    return mark_safe(html)


@register.simple_tag
def star_rating_compact(rating, total_reviews=None):
    """
    Compact star rating display for course cards
    Usage: {% star_rating_compact course.average_rating course.total_reviews %}
    """
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0.0
    
    html = '<div class="star-rating-compact d-flex align-items-center gap-1">'
    html += '<i class="fas fa-star" style="color: #fbbf24;"></i>'
    html += f'<span class="fw-bold">{rating:.1f}</span>'
    
    if total_reviews is not None:
        html += f'<span class="text-muted">({total_reviews})</span>'
    
    html += '</div>'
    
    return mark_safe(html)


@register.filter
def get_item(dictionary, key):
    """
    Get item from dictionary in template
    Usage: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.simple_tag
def rating_stars_simple(rating):
    """
    Simple star rating display (just stars, no numbers)
    Usage: {% rating_stars_simple 4.5 %}
    """
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0.0
    
    html = '<span class="stars-simple">'
    
    for i in range(1, 6):
        if i <= rating:
            html += '★'
        elif i - 0.5 <= rating:
            html += '★'  # You could use a half-star character here if available
        else:
            html += '☆'
    
    html += '</span>'
    
    return mark_safe(html)
