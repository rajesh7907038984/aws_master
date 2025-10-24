"""
Teams Integration Signals

Signal handlers for Teams integration events.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(post_save, sender='conferences.Conference')
def handle_conference_created(sender, instance, created, **kwargs):
    """Handle conference creation for Teams integration"""
    if created and instance.meeting_platform == 'teams':
        try:
            from .models import TeamsMeetingSync
            
            # Create Teams meeting sync record
            TeamsMeetingSync.objects.create(
                conference=instance,
                teams_meeting_id=instance.meeting_id or '',
                teams_meeting_url=instance.meeting_link,
                meeting_status='scheduled'
            )
            
            logger.info(f"Created Teams meeting sync record for conference {instance.id}")
            
        except Exception as e:
            logger.error(f"Error creating Teams meeting sync record: {str(e)}")


@receiver(post_save, sender='groups.GroupMembership')
def handle_group_membership_changed(sender, instance, created, **kwargs):
    """Handle group membership changes for Teams integration"""
    if created and instance.is_active:
        try:
            from .utils.entra_sync import EntraSyncService
            from account_settings.models import TeamsIntegration
            
            # Find Teams integration for the user's branch
            integration = TeamsIntegration.objects.filter(
                branch=instance.user.branch,
                is_active=True
            ).first()
            
            if integration:
                # Sync user to Teams
                entra_sync = EntraSyncService(integration)
                result = entra_sync.sync_user_groups(instance.user)
                
                if result['success']:
                    logger.info(f"Synced user {instance.user.username} to Teams groups")
                else:
                    logger.warning(f"Failed to sync user {instance.user.username} to Teams: {result.get('error')}")
            
        except Exception as e:
            logger.error(f"Error syncing user to Teams after group membership change: {str(e)}")


@receiver(post_save, sender='account_settings.TeamsIntegration')
def handle_teams_integration_created(sender, instance, created, **kwargs):
    """Handle Teams integration creation"""
    if created:
        try:
            from .tasks import health_check_teams_integrations
            
            # Start health check for the new integration
            health_check_teams_integrations.delay()
            
            logger.info(f"Started health check for new Teams integration: {instance.name}")
            
        except Exception as e:
            logger.error(f"Error starting health check for Teams integration: {str(e)}")
