from django import template
from datetime import timedelta

register = template.Library()

@register.filter
def format_time_spent(timedelta_obj):
    """Format timedelta object to human readable time format"""
    if not timedelta_obj:
        return "N/A"
    
    total_seconds = int(timedelta_obj.total_seconds())
    
    if total_seconds >= 3600:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{hours}h"
    elif total_seconds >= 60:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if seconds > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{minutes}m"
    else:
        return f"{total_seconds}s"

@register.filter
def scorm_time_format(timedelta_obj):
    """Convert timedelta to SCORM PT format"""
    if not timedelta_obj:
        return 'PT0S'
    
    total_seconds = int(timedelta_obj.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"PT{hours}H{minutes}M{seconds}S"
    elif minutes > 0:
        return f"PT{minutes}M{seconds}S"
    else:
        return f"PT{seconds}S"
