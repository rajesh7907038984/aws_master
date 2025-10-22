"""
Template filters for safe file operations
Provides error-resistant file access for templates
"""

from django import template
from django.core.files.storage import default_storage
import logging

register = template.Library()
logger = logging.getLogger('core.templatetags')


@register.filter
def safe_file_url(file_field):
    """
    Safely get the URL of a file field, handling S3 and other storage errors gracefully.
    
    Usage in templates:
    {{ file_field|safe_file_url }}
    
    Returns:
    - File URL if accessible
    - None if file is None or error occurs
    """
    if not file_field:
        return None
    
    try:
        return file_field.url
    except Exception as e:
        logger.warning(f"Error accessing file URL: {e}")
        return None


@register.filter
def safe_file_name(file_field):
    """
    Safely get the name of a file field, handling storage errors gracefully.
    
    Usage in templates:
    {{ file_field|safe_file_name }}
    
    Returns:
    - File name if accessible
    - "Unknown File" if file is None or error occurs
    """
    if not file_field:
        return "No File"
    
    try:
        return file_field.name.split('/')[-1] if file_field.name else "Unknown File"
    except Exception as e:
        logger.warning(f"Error accessing file name: {e}")
        return "Unknown File"


@register.filter
def safe_file_exists(file_field):
    """
    Safely check if a file exists, handling S3 and other storage errors gracefully.
    
    Usage in templates:
    {% if file_field|safe_file_exists %}
    
    Returns:
    - True if file exists and is accessible
    - False if file is None, doesn't exist, or error occurs
    """
    if not file_field:
        return False
    
    try:
        if not file_field.name:
            return False
            
        # Use S3 permission-safe approach - try to open instead of using exists()
        try:
            test_file = default_storage.open(file_field.name)
            test_file.close()
            return True
        except Exception as access_error:
            # Handle different types of errors
            if "403" in str(access_error) or "Forbidden" in str(access_error):
                # Permission denied - log warning but return False (assume file doesn't exist for user)
                logger.debug(f"S3 permission denied for file: {file_field.name}")
                return False
            elif "NoSuchKey" in str(access_error) or "not found" in str(access_error):
                # File doesn't exist
                return False
            else:
                # Other error - log and return False
                logger.debug(f"Error accessing file {file_field.name}: {access_error}")
                return False
    except Exception as e:
        logger.warning(f"Error checking file existence: {e}")
        return False


@register.filter
def safe_file_size(file_field):
    """
    Safely get the size of a file field, handling storage errors gracefully.
    
    Usage in templates:
    {{ file_field|safe_file_size }}
    
    Returns:
    - File size in bytes if accessible
    - 0 if file is None or error occurs
    """
    if not file_field:
        return 0
    
    try:
        return file_field.size if hasattr(file_field, 'size') else 0
    except Exception as e:
        logger.warning(f"Error accessing file size: {e}")
        return 0


@register.filter
def format_file_size(size_bytes):
    """
    Format file size in human-readable format.
    
    Usage in templates:
    {{ file_field|safe_file_size|format_file_size }}
    
    Returns:
    - Formatted size string (e.g., "1.5 MB", "300 KB")
    """
    try:
        if not size_bytes or size_bytes == 0:
            return "0 B"
        
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{round(size_bytes / 1024, 1)} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{round(size_bytes / (1024 * 1024), 1)} MB"
        else:
            return f"{round(size_bytes / (1024 * 1024 * 1024), 1)} GB"
    except Exception as e:
        logger.warning(f"Error formatting file size: {e}")
        return "Unknown Size"


@register.simple_tag
def safe_media_url(file_path):
    """
    Safely generate a media URL from a file path string, handling storage errors.
    
    Usage in templates:
    {% safe_media_url "path/to/file.jpg" %}
    
    Returns:
    - Media URL if accessible
    - Empty string if path is None or error occurs
    """
    if not file_path:
        return ""
    
    try:
        return default_storage.url(file_path)
    except Exception as e:
        logger.warning(f"Error generating media URL for {file_path}: {e}")
        return ""
