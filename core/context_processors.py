"""
Context processors for the LMS application.
"""
from django.urls import resolve
from django.urls.exceptions import Resolver404


def global_context(request):
    """
    Global context processor for common template variables.
    """
    return {
        'site_name': 'Nexsy LMS',
        'site_version': '1.0.0',
    }


def global_sidebar_context(request):
    """
    Global sidebar context processor.
    """
    return {
        'sidebar_collapsed': False,
    }


def sidebar_context(request):
    """
    Sidebar context processor.
    """
    return {
        'sidebar_enabled': True,
    }


def order_management_context(request):
    """
    Order management context processor.
    """
    return {
        'order_management_enabled': False,
    }


def right_sidebar_context(request):
    """
    Right sidebar context processor.
    """
    return {
        'right_sidebar_enabled': True,
        'right_sidebar_content': [],
    }


def breadcrumbs(request):
    """
    Generate breadcrumbs based on the current URL path.
    """
    breadcrumbs_list = []
    
    # Get the current path
    current_path = request.path
    path_parts = [part for part in current_path.split('/') if part]
    
    # Always start with Dashboard
    breadcrumbs_list.append({
        'url': '/',
        'label': 'Dashboard',
        'icon': 'fa-home'
    })
    
    # Build breadcrumbs based on URL patterns
    if path_parts:
        # Handle different URL patterns
        if path_parts[0] == 'courses':
            breadcrumbs_list.append({
                'url': '/courses/',
                'label': 'Courses',
                'icon': 'fa-book'
            })
            
            if len(path_parts) > 1:
                if path_parts[1] == 'create':
                    breadcrumbs_list.append({
                        'label': 'Create Course',
                        'icon': 'fa-plus'
                    })
                elif path_parts[1].isdigit():
                    # Course detail page
                    breadcrumbs_list.append({
                        'label': 'Course Details',
                        'icon': 'fa-info-circle'
                    })
                    
                    if len(path_parts) > 2:
                        if path_parts[2] == 'edit':
                            breadcrumbs_list.append({
                                'label': 'Edit Course',
                                'icon': 'fa-edit'
                            })
                        elif path_parts[2] == 'topics':
                            breadcrumbs_list.append({
                                'label': 'Course Topics',
                                'icon': 'fa-list'
                            })
                            if len(path_parts) > 3 and path_parts[3] == 'create':
                                breadcrumbs_list.append({
                                    'label': 'Create Topic',
                                    'icon': 'fa-plus'
                                })
        
        elif path_parts[0] == 'users':
            breadcrumbs_list.append({
                'url': '/users/',
                'label': 'Users',
                'icon': 'fa-users'
            })
            
            if len(path_parts) > 1:
                if path_parts[1] == 'create':
                    breadcrumbs_list.append({
                        'label': 'Create User',
                        'icon': 'fa-user-plus'
                    })
                elif path_parts[1].isdigit():
                    breadcrumbs_list.append({
                        'label': 'User Profile',
                        'icon': 'fa-user'
                    })
        
        elif path_parts[0] == 'assignments':
            breadcrumbs_list.append({
                'url': '/assignments/',
                'label': 'Assignments',
                'icon': 'fa-tasks'
            })
            
            if len(path_parts) > 1:
                if path_parts[1] == 'create':
                    breadcrumbs_list.append({
                        'label': 'Create Assignment',
                        'icon': 'fa-plus'
                    })
        
        elif path_parts[0] == 'quiz':
            breadcrumbs_list.append({
                'url': '/quiz/',
                'label': 'Quizzes',
                'icon': 'fa-question-circle'
            })
            
            if len(path_parts) > 1:
                if path_parts[1] == 'create':
                    breadcrumbs_list.append({
                        'label': 'Create Quiz',
                        'icon': 'fa-plus'
                    })
        
        elif path_parts[0] == 'reports':
            breadcrumbs_list.append({
                'url': '/reports/',
                'label': 'Reports',
                'icon': 'fa-chart-bar'
            })
        
        elif path_parts[0] == 'admin':
            breadcrumbs_list.append({
                'url': '/admin/',
                'label': 'Admin',
                'icon': 'fa-cog'
            })
        
        elif path_parts[0] == 'notifications':
            breadcrumbs_list.append({
                'url': '/notifications/',
                'label': 'Notifications',
                'icon': 'fa-bell'
            })
        
        elif path_parts[0] == 'messages':
            breadcrumbs_list.append({
                'url': '/messages/',
                'label': 'Messages',
                'icon': 'fa-comments'
            })
    
    return {
        'breadcrumbs': breadcrumbs_list
    }