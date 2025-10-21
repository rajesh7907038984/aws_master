"""
Security template filters for XSS protection and content sanitization
"""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import bleach
import re

register = template.Library()


@register.filter
def safe_html(value):
    """
    Safely render HTML content with XSS protection
    """
    if not value:
        return ''
    
    # Allowed HTML tags
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'u', 'b', 'i', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'a', 'img', 'div', 'span',
        'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption'
    ]
    
    # Allowed attributes
    allowed_attributes = {
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'table': ['border', 'cellpadding', 'cellspacing'],
        'div': ['class', 'id'],
        'span': ['class', 'id'],
        'p': ['class'],
        'h1': ['class'], 'h2': ['class'], 'h3': ['class'], 'h4': ['class'], 'h5': ['class'], 'h6': ['class']
    }
    
    # Clean the HTML
    cleaned = bleach.clean(
        value,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )
    
    return mark_safe(cleaned)


@register.filter
def escape_html(value):
    """
    Escape HTML content to prevent XSS
    """
    if not value:
        return ''
    return escape(value)


@register.filter
def safe_url(value):
    """
    Validate and sanitize URLs
    """
    if not value:
        return ''
    
    # Remove dangerous protocols
    dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'onload=', 'onerror=']
    for protocol in dangerous_protocols:
        if protocol in value.lower():
            return '#'
    
    # Only allow http, https, and relative URLs
    if not (value.startswith('http://') or value.startswith('https://') or value.startswith('/')):
        return '#'
    
    return value


@register.filter
def sanitize_filename(value):
    """
    Sanitize filename to prevent directory traversal
    """
    if not value:
        return ''
    
    # Remove dangerous characters
    value = re.sub(r'[^\w\-_\.]', '', value)
    
    # Remove multiple dots
    value = re.sub(r'\.{2,}', '.', value)
    
    # Remove leading/trailing dots
    value = value.strip('.')
    
    return value


@register.filter
def safe_json(value):
    """
    Safely encode value as JSON
    """
    import json
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return 'null'
