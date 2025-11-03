from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def star_rating_display(rating, max_rating=5, show_number=True, input_scale=10):
    """
    Display star rating with filled and empty stars
    Usage: {% star_rating_display course.average_rating %}
    
    Note: Ratings are stored on a 0-10 scale but displayed as 5 stars
    """
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0.0
    
    # Normalize rating from input_scale to 5-star scale
    if input_scale != 5:
        normalized_rating = (rating / input_scale) * 5
    else:
        normalized_rating = rating
    
    full_stars = int(normalized_rating)
    half_star = (normalized_rating - full_stars) >= 0.5
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
        html += f' <span class="rating-number">({normalized_rating:.1f}/5)</span>'
    
    html += '</span>'
    
    return mark_safe(html)


@register.simple_tag
def star_rating_compact(rating, total_reviews=None, input_scale=10):
    """
    Compact star rating display for course cards
    Usage: {% star_rating_compact course.average_rating course.total_reviews %}
    
    Note: Ratings are stored on a 0-10 scale but displayed as 5 stars
    """
    try:
        rating = float(rating)
    except (ValueError, TypeError):
        rating = 0.0
    
    # Normalize rating from input_scale (10) to 5-star scale
    if input_scale != 5:
        normalized_rating = (rating / input_scale) * 5
    else:
        normalized_rating = rating
    
    html = '<div class="star-rating-compact" style="display: flex; align-items: center; gap: 0.5rem;">'
    
    # Add star icons
    html += '<div style="display: flex; align-items: center; gap: 0.15rem;">'
    full_stars = int(normalized_rating)
    has_half_star = (normalized_rating - full_stars) >= 0.5
    empty_stars = 5 - full_stars - (1 if has_half_star else 0)
    
    # Full stars
    for i in range(full_stars):
        html += '<i class="fas fa-star" style="color: #fbbf24; font-size: 0.875rem;"></i>'
    
    # Half star
    if has_half_star:
        html += '<i class="fas fa-star-half-alt" style="color: #fbbf24; font-size: 0.875rem;"></i>'
    
    # Empty stars
    for i in range(empty_stars):
        html += '<i class="far fa-star" style="color: #fbbf24; font-size: 0.875rem;"></i>'
    
    html += '</div>'
    
    # Rating number (show normalized 5-star rating)
    html += f'<span style="font-weight: 600; font-size: 0.875rem; color: #1f2937;">{normalized_rating:.1f}</span>'
    
    # Review count
    if total_reviews is not None and total_reviews > 0:
        html += f'<span style="font-size: 0.75rem; color: #6b7280;">({total_reviews})</span>'
    
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
