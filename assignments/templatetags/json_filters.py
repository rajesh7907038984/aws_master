from django import template
from django.utils.safestring import mark_safe
import json
import html

register = template.Library()

@register.filter
def get_json_content(text_content):
    """
    Parse a JSON string and return the 'html' content from it
    If it's not JSON, just return the original text
    """
    if not text_content:
        return ""
        
    # Handle field object formats
    if hasattr(text_content, 'json_string'):
        # Extract the json_string attribute from field
        return get_json_content(text_content.json_string)
        
    # Handle case where input is already a dict
    if isinstance(text_content, dict):
        if 'html' in text_content:
            return mark_safe(text_content['html'])
        return str(text_content)
        
    # Try to parse as JSON string
    try:
        # Only try to parse as JSON if it looks like JSON
        if isinstance(text_content, str) and text_content.strip().startswith('{'):
            data = json.loads(text_content)
            if isinstance(data, dict) and 'html' in data:
                return mark_safe(data['html'])
    except (json.JSONDecodeError, TypeError):
        pass
        
    # Return original if it's not valid JSON or doesn't look like JSON
    return text_content

@register.filter
def render_rich_content(content):
    """
    Smart filter to render rich content properly.
    Handles JSON content, HTML content with escaped entities, and plain text.
    """
    if not content:
        return ""
    
    # First try to get JSON content
    json_content = get_json_content(content)
    
    # If it's different from original, it was JSON, so return as safe HTML
    if json_content != content:
        return json_content  # Already marked safe by get_json_content
    
    # Check if content contains HTML entities that need unescaping
    if isinstance(content, str) and ('&lt;' in content or '&gt;' in content or '&amp;' in content or 
                                     '&quot;' in content or '&#x27;' in content or '&#' in content or
                                     '&nbsp;' in content or '&apos;' in content):
        # Content appears to have escaped HTML entities, unescape them
        return unescape_html(content)
    
    # Check if content looks like HTML (contains HTML tags)
    if isinstance(content, str) and ('<' in content and '>' in content):
        # Content appears to be HTML, check if it contains common HTML tags
        import re
        html_tag_pattern = r'</?[a-zA-Z][^>]*>'
        if re.search(html_tag_pattern, content):
            # Content contains HTML tags, assume it's safe HTML from TinyMCE
            return mark_safe(content)
    
    # Otherwise, treat as plain text and escape for safety
    import html as html_module
    content = html_module.escape(content, quote=False)  # Escape HTML entities
    return mark_safe(content)

@register.filter
def unescape_html(content):
    """
    Unescape HTML entities and mark as safe for rendering.
    Useful for content stored with escaped HTML entities.
    """
    if not content:
        return ""
    
    # Unescape HTML entities like &lt; &gt; &amp; etc.
    unescaped_content = html.unescape(str(content))
    return mark_safe(unescaped_content) 