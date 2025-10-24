"""
Teams Integration Utilities

This module provides utility functions and services for Teams integration,
including API clients, sync services, and helper functions.
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Check if required dependencies are available
try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False
    logger.warning("MSAL library not available. Teams integration will have limited functionality.")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.error("Requests library not available. Teams integration will not work.")


def is_teams_integration_available():
    """Check if Teams integration is properly configured"""
    return MSAL_AVAILABLE and REQUESTS_AVAILABLE


def get_teams_integration(branch=None, user=None):
    """
    Get the appropriate Teams integration for a branch or user
    
    Args:
        branch: Branch instance
        user: User instance
        
    Returns:
        TeamsIntegration instance or None
    """
    from account_settings.models import TeamsIntegration
    
    if not is_teams_integration_available():
        return None
    
    try:
        if branch:
            integration = TeamsIntegration.objects.filter(
                branch=branch,
                is_active=True
            ).first()
            return integration
        
        if user and hasattr(user, 'branch') and user.branch:
            integration = TeamsIntegration.objects.filter(
                branch=user.branch,
                is_active=True
            ).first()
            return integration
        
        # Fallback to any active integration
        return TeamsIntegration.objects.filter(is_active=True).first()
        
    except Exception as e:
        logger.error(f"Error getting Teams integration: {str(e)}")
        return None


def safe_sync_to_teams(sync_function, instance, operation_type="update", async_task=None):
    """
    Safely sync data to Teams with error handling
    
    Args:
        sync_function: Function to call for sync
        instance: Instance to sync
        operation_type: Type of operation (create, update, delete)
        async_task: Optional async task to use
    """
    try:
        integration = get_teams_integration()
        if not integration:
            logger.debug("No Teams integration available for sync")
            return
        
        if async_task:
            # Run asynchronously
            async_task.delay(integration.id, instance.id, operation_type)
        else:
            # Run synchronously
            sync_function(integration, instance, operation_type)
            
    except Exception as e:
        logger.error(f"Error in Teams sync for {instance}: {str(e)}")


def get_sync_mode():
    """
    Get the current sync mode configuration
    
    Returns:
        dict: Sync mode configuration
    """
    return {
        'async_enabled': getattr(settings, 'TEAMS_ASYNC_SYNC', True),
        'sync_interval': getattr(settings, 'TEAMS_SYNC_INTERVAL', 60),
        'retry_attempts': getattr(settings, 'TEAMS_RETRY_ATTEMPTS', 3),
        'batch_size': getattr(settings, 'TEAMS_BATCH_SIZE', 100),
    }
