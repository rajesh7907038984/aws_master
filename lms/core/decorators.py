"""
Core decorators for consistent access control and security
"""

from functools import wraps
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(required_roles):
    """
    Decorator to require specific roles for access
    
    Args:
        required_roles: Single role string or list/tuple of roles
    
    Usage:
        @role_required('admin')
        @role_required(['admin', 'superadmin'])
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden("Authentication required")
            
            # Convert single role to list for consistent handling
            if isinstance(required_roles, str):
                allowed_roles = [required_roles]
            else:
                allowed_roles = list(required_roles)
            
            # Check if user has required role
            user_role = getattr(request.user, 'role', None)
            if user_role not in allowed_roles:
                # For API requests, return JSON response
                if request.path.startswith('/api/') or request.content_type == 'application/json':
                    return JsonResponse({
                        'error': 'Access Denied',
                        'message': f'Required roles: {", ".join(allowed_roles)}',
                        'current_role': user_role
                    }, status=403)
                
                # For regular requests, return HTML response
                return HttpResponseForbidden(
                    f"Access Denied. Required roles: {', '.join(allowed_roles)}. "
                    f"Your current role: {user_role}"
                )
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    """Decorator to require admin, superadmin, or globaladmin role"""
    return role_required(['admin', 'superadmin', 'globaladmin'])(view_func)


def instructor_required(view_func):
    """Decorator to require instructor role"""
    return role_required('instructor')(view_func)


def learner_required(view_func):
    """Decorator to require learner role"""
    return role_required('learner')(view_func)


def superadmin_required(view_func):
    """Decorator to require superadmin or globaladmin role"""
    return role_required(['superadmin', 'globaladmin'])(view_func)


def globaladmin_required(view_func):
    """Decorator to require globaladmin role"""
    return role_required('globaladmin')(view_func)


def api_role_required(required_roles):
    """
    Decorator specifically for API endpoints with consistent JSON responses
    
    Args:
        required_roles: Single role string or list/tuple of roles
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'error': 'Authentication required',
                    'message': 'Please log in to access this resource'
                }, status=401)
            
            # Convert single role to list for consistent handling
            if isinstance(required_roles, str):
                allowed_roles = [required_roles]
            else:
                allowed_roles = list(required_roles)
            
            # Check if user has required role
            user_role = getattr(request.user, 'role', None)
            if user_role not in allowed_roles:
                return JsonResponse({
                    'error': 'Access Denied',
                    'message': f'Required roles: {", ".join(allowed_roles)}',
                    'current_role': user_role
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def check_permissions(required_roles, allow_self=False):
    """
    Utility function to check permissions with optional self-access
    
    Args:
        required_roles: Single role string or list/tuple of roles
        allow_self: If True, allow users to access their own resources regardless of role
    
    Returns:
        tuple: (has_permission, error_response)
    """
    if not isinstance(required_roles, (list, tuple)):
        required_roles = [required_roles]
    
    user_role = getattr(request.user, 'role', None)
    
    # Check if user has required role
    if user_role in required_roles:
        return True, None
    
    # Check if self-access is allowed and user is accessing their own resource
    if allow_self and hasattr(request, 'user_id') and request.user.id == request.user_id:
        return True, None
    
    # Create error response
    error_response = JsonResponse({
        'error': 'Access Denied',
        'message': f'Required roles: {", ".join(required_roles)}',
        'current_role': user_role
    }, status=403)
    
    return False, error_response
