import functools
import logging
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)

def check_scorm_configuration(view_func):
    """
    Decorator to check if SCORM Cloud is properly configured for the user's branch
    before allowing access to SCORM-related views.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from scorm_cloud.utils.api import has_branch_scorm_enabled
        
        # Check if SCORM is enabled for the user's branch
        if not has_branch_scorm_enabled(user=request.user):
            logger.error(f"SCORM Cloud configuration is not available for user {request.user.username}")
            messages.error(
                request, 
                "SCORM Cloud integration is not configured for your branch. "
                "Please contact your branch administrator to set up SCORM Cloud integration."
            )
            # Redirect to dashboard or appropriate view
            if request.user.is_authenticated:
                return redirect('users:role_based_redirect')
            return redirect('users:login')
            
        # If everything is configured correctly, proceed to the view
        return view_func(request, *args, **kwargs)
    
    return wrapper
