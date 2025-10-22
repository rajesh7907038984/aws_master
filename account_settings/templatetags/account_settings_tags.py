from django import template
from ..models import GlobalAdminSettings

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0 

@register.simple_tag
def is_google_oauth_enabled():
    """Check if Google OAuth is enabled - now always enabled when credentials are available"""
    try:
        global_settings = GlobalAdminSettings.get_settings()
        # Always return True if credentials are available, since OAuth should always be enabled
        return bool(global_settings.google_client_id and global_settings.google_client_secret)
    except:
        return False

@register.simple_tag
def is_microsoft_oauth_enabled():
    """Check if Microsoft OAuth is enabled - always enabled when credentials are available"""
    try:
        global_settings = GlobalAdminSettings.get_settings()
        # Always return True if credentials are available, since OAuth should always be enabled
        return bool(global_settings.microsoft_client_id and global_settings.microsoft_client_secret)
    except:
        return False 