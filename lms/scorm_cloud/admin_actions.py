"""
Admin actions for SCORM Cloud content
"""

from django.contrib import admin, messages
import logging

logger = logging.getLogger(__name__)

def sync_all_scorm_content(modeladmin, request, queryset):
    """
    Admin action to sync all SCORM content with SCORM Cloud.
    This will ensure all packages have valid launch URLs and destinations.
    """
    from django.core.management import call_command
    
    try:
        # Use the management command to fix SCORM content
        call_command('fix_scorm_content')
        modeladmin.message_user(
            request,
            "Successfully synced SCORM content with SCORM Cloud",
            level=messages.SUCCESS
        )
    except Exception as e:
        logger.error(f"Error syncing SCORM content: {str(e)}")
        modeladmin.message_user(
            request,
            f"Error syncing SCORM content: {str(e)}",
            level=messages.ERROR
        )
        
sync_all_scorm_content.short_description = "Sync all SCORM content with SCORM Cloud" 