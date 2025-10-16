from django import template
from django.urls import resolve, Resolver404

register = template.Library()

@register.filter
def is_dashboard_page(request):
    """
    Check if the current page is a dashboard page that should exclude the right sidebar
    """
    if not request:
        return False
    
    try:
        # Get the current URL path
        current_path = request.path
        
        # List of dashboard URL patterns that should exclude the right sidebar
        dashboard_patterns = [
            '/dashboard/learner/',
            '/dashboard/instructor/',
            '/dashboard/admin/',
            '/dashboard/globaladmin/',
            '/dashboard/superadmin/',
            '/admin_dashboard/',
            '/super-admin/',
        ]
        
        # Check if current path starts with any dashboard pattern
        for pattern in dashboard_patterns:
            if current_path.startswith(pattern):
                return True
        
        # Also check for dashboard in the URL name if available
        try:
            resolved = resolve(current_path)
            if resolved and resolved.url_name:
                dashboard_names = [
                    'dashboard_learner',
                    'dashboard_instructor', 
                    'dashboard_admin',
                    'dashboard_globaladmin',
                    'dashboard_superadmin',
                ]
                if resolved.url_name in dashboard_names:
                    return True
        except Resolver404:
            pass
            
        return False
        
    except Exception:
        # If there's any error, default to not showing sidebar to be safe
        return False

@register.filter
def should_show_right_sidebar(request):
    """
    Determine if the right sidebar should be shown
    Returns True if we should show the sidebar, False if we should hide it
    """
    return not is_dashboard_page(request)
