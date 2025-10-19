"""
Template tags for safe HTML rendering with XSS protection
"""
from django import template
from django.utils.safestring import mark_safe
import bleach

register = template.Library()

# Allowed HTML tags for user-generated content
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'code', 'pre',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'span', 'div', 'hr', 'sub', 'sup', 'del', 'ins'
]

# Allowed HTML attributes
ALLOWED_ATTRIBUTES = {
    '*': ['class', 'id', 'style'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'table': ['border', 'cellpadding', 'cellspacing'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
}

# Allowed CSS properties
ALLOWED_STYLES = [
    'color', 'background-color', 'font-size', 'font-weight', 'text-align',
    'padding', 'margin', 'border', 'width', 'height'
]


@register.filter(name='safe_html')
def safe_html(value):
    """
    Sanitize HTML content to prevent XSS attacks while preserving formatting
    
    Usage in templates:
        {{ user_content|safe_html }}
    
    This filter:
    - Removes potentially dangerous HTML tags and attributes
    - Preserves safe formatting tags
    - Prevents JavaScript injection
    - Allows safe CSS styling
    """
    if not value:
        return ''
    
    # Sanitize the HTML using bleach
    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        styles=ALLOWED_STYLES,
        strip=True  # Strip disallowed tags instead of escaping
    )
    
    # Mark as safe for Django template rendering
    return mark_safe(cleaned)


@register.filter(name='safe_html_strict')
def safe_html_strict(value):
    """
    Strictly sanitize HTML content with minimal allowed tags
    
    Usage in templates:
        {{ user_content|safe_html_strict }}
    
    Only allows basic formatting: bold, italic, underline, links, paragraphs
    """
    if not value:
        return ''
    
    # Minimal allowed tags for strict mode
    strict_tags = ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li']
    strict_attrs = {
        'a': ['href', 'title', 'rel'],
    }
    
    cleaned = bleach.clean(
        value,
        tags=strict_tags,
        attributes=strict_attrs,
        strip=True
    )
    
    return mark_safe(cleaned)


@register.filter(name='safe_feedback')
def safe_feedback(value):
    """
    Sanitize feedback/comment HTML content
    
    Usage in templates:
        {{ feedback.feedback_text|safe_feedback }}
    
    Designed specifically for instructor/admin feedback with rich formatting
    """
    if not value:
        return ''
    
    # Allow additional formatting for feedback
    feedback_tags = ALLOWED_TAGS + ['mark', 'small', 'abbr']
    
    cleaned = bleach.clean(
        value,
        tags=feedback_tags,
        attributes=ALLOWED_ATTRIBUTES,
        styles=ALLOWED_STYLES,
        strip=True
    )
    
    return mark_safe(cleaned)


@register.filter(name='strip_html')
def strip_html(value):
    """
    Completely strip all HTML tags from content
    
    Usage in templates:
        {{ user_content|strip_html }}
    
    Returns plain text only
    """
    if not value:
        return ''
    
    # Strip all HTML tags
    cleaned = bleach.clean(value, tags=[], strip=True)
    
    return cleaned

