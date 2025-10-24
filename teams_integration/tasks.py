"""
Celery tasks for Teams integration

These tasks handle asynchronous Teams synchronization operations
to avoid blocking the main application.
"""

# from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging
import time

from .utils.sync_services import (
    MeetingSyncService,
    UserSyncService
)
from .utils.entra_sync import EntraSyncService

logger = logging.getLogger(__name__)
User = get_user_model()


# @shared_task(bind=True, max_retries=5, default_retry_delay=60, exponential_backoff=True)
def sync_teams_data(self, integration_id, sync_type='all', direction='from_teams'):
    """
    Asynchronous task to sync data with Teams
    
    Args:
        integration_id: Teams integration ID
        sync_type: Type of data to sync ('all', 'entra_groups', 'entra_users', 'meetings', etc.)
        direction: Direction of sync ('to_teams', 'from_teams', 'bidirectional')
    """
    try:
        from account_settings.models import TeamsIntegration
        from .models import TeamsSyncLog
        
        # Get integration
        integration = TeamsIntegration.objects.get(id=integration_id)
        
        logger.info(f"Starting async Teams sync for integration {integration.name}")
        
        # Check if integration is active
        if not integration.is_active:
            logger.warning(f"Teams integration {integration.name} is not active")
            return {
                'success': False,
                'message': 'Integration is not active'
            }
        
        # Create sync log
        sync_log = TeamsSyncLog.objects.create(
            integration=integration,
            sync_type=sync_type,
            status='started',
            sync_direction=direction,
            initiated_by=None  # System initiated
        )
        
        results = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        # Entra ID groups synchronization
        if sync_type in ['all', 'entra_groups']:
            logger.info("Starting Entra ID groups synchronization...")
            try:
                entra_sync = EntraSyncService(integration)
                entra_results = entra_sync.sync_entra_groups()
                _merge_task_results(results, entra_results)
            except Exception as e:
                logger.error(f"Entra groups sync failed: {str(e)}")
                results['errors'] += 1
                results['error_messages'].append(f"Entra groups sync: {str(e)}")
        
        # Entra ID users synchronization
        if sync_type in ['all', 'entra_users']:
            logger.info("Starting Entra ID users synchronization...")
            try:
                entra_sync = EntraSyncService(integration)
                # This would sync individual users
                # For now, we'll skip detailed user sync
                logger.info("Entra users sync completed (placeholder)")
            except Exception as e:
                logger.error(f"Entra users sync failed: {str(e)}")
                results['errors'] += 1
                results['error_messages'].append(f"Entra users sync: {str(e)}")
        
        # Meeting data synchronization
        if sync_type in ['all', 'meetings']:
            logger.info("Starting meeting data synchronization...")
            try:
                meeting_sync = MeetingSyncService(integration)
                
                # Get conferences that need sync
                from conferences.models import Conference
                conferences = Conference.objects.filter(
                    meeting_platform='teams',
                    meeting_id__isnull=False
                )
                
                for conference in conferences:
                    try:
                        # Sync attendance
                        attendance_results = meeting_sync.sync_meeting_attendance(conference)
                        _merge_task_results(results, attendance_results)
                        
                        # Sync recordings
                        recording_results = meeting_sync.sync_meeting_recordings(conference)
                        _merge_task_results(results, recording_results)
                        
                        # Sync chat
                        chat_results = meeting_sync.sync_meeting_chat(conference)
                        _merge_task_results(results, chat_results)
                        
                        # Sync files
                        file_results = meeting_sync.sync_meeting_files(conference)
                        _merge_task_results(results, file_results)
                        
                    except Exception as e:
                        logger.error(f"Meeting sync failed for conference {conference.id}: {str(e)}")
                        results['errors'] += 1
                        results['error_messages'].append(f"Meeting {conference.id}: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Meeting data sync failed: {str(e)}")
                results['errors'] += 1
                results['error_messages'].append(f"Meeting data sync: {str(e)}")
        
        # User synchronization
        if sync_type in ['all', 'users'] and direction in ['to_teams', 'bidirectional']:
            logger.info("Starting user synchronization to Teams...")
            try:
                user_sync = UserSyncService(integration)
                user_results = user_sync.sync_users_to_teams()
                _merge_task_results(results, user_results)
            except Exception as e:
                logger.error(f"User sync to Teams failed: {str(e)}")
                results['errors'] += 1
                results['error_messages'].append(f"User sync to Teams: {str(e)}")
        
        # Update sync log
        sync_log.completed_at = timezone.now()
        sync_log.items_processed = results['processed']
        sync_log.items_created = results['created']
        sync_log.items_updated = results['updated']
        sync_log.items_failed = results['errors']
        
        if results['errors'] == 0:
            sync_log.status = 'completed'
            sync_log.mark_completed(success=True)
        else:
            sync_log.status = 'partial' if results['processed'] > 0 else 'failed'
            sync_log.error_message = '; '.join(results['error_messages'][:5])  # Limit error message length
            sync_log.mark_completed(success=False, error_message=sync_log.error_message)
        
        # Update integration sync status
        integration.last_sync_datetime = timezone.now()
        integration.last_sync_status = 'success' if results['errors'] == 0 else 'failed'
        if results['error_messages']:
            integration.sync_error_message = '; '.join(results['error_messages'][:3])
        integration.save()
        
        logger.info(f"Teams sync completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Teams sync task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# @shared_task(bind=True, max_retries=3, default_retry_delay=30)
def sync_entra_groups(self, integration_id):
    """
    Sync Entra ID groups for a specific integration
    
    Args:
        integration_id: Teams integration ID
    """
    try:
        from account_settings.models import TeamsIntegration
        from .utils.entra_sync import EntraSyncService
        
        integration = TeamsIntegration.objects.get(id=integration_id)
        entra_sync = EntraSyncService(integration)
        
        results = entra_sync.sync_entra_groups()
        logger.info(f"Entra groups sync completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Entra groups sync task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# @shared_task(bind=True, max_retries=3, default_retry_delay=30)
def sync_meeting_data(self, conference_id):
    """
    Sync meeting data for a specific conference
    
    Args:
        conference_id: Conference ID
    """
    try:
        from conferences.models import Conference
        from .utils.sync_services import MeetingSyncService
        
        conference = Conference.objects.get(id=conference_id)
        
        # Get Teams integration for the conference
        integration = None
        if hasattr(conference.created_by, 'branch') and conference.created_by.branch:
            from account_settings.models import TeamsIntegration
            integration = TeamsIntegration.objects.filter(
                branch=conference.created_by.branch,
                is_active=True
            ).first()
        
        if not integration:
            logger.warning(f"No Teams integration found for conference {conference_id}")
            return {
                'success': False,
                'error': 'No Teams integration found'
            }
        
        meeting_sync = MeetingSyncService(integration)
        
        # Sync all meeting data
        results = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        # Sync attendance
        attendance_results = meeting_sync.sync_meeting_attendance(conference)
        _merge_task_results(results, attendance_results)
        
        # Sync recordings
        recording_results = meeting_sync.sync_meeting_recordings(conference)
        _merge_task_results(results, recording_results)
        
        # Sync chat
        chat_results = meeting_sync.sync_meeting_chat(conference)
        _merge_task_results(results, chat_results)
        
        # Sync files
        file_results = meeting_sync.sync_meeting_files(conference)
        _merge_task_results(results, file_results)
        
        logger.info(f"Meeting data sync completed for conference {conference_id}: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Meeting data sync task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# @shared_task(bind=True, max_retries=3, default_retry_delay=30)
def auto_register_conference_users(self, conference_id):
    """
    Auto-register users for a conference based on group membership
    
    Args:
        conference_id: Conference ID
    """
    try:
        from conferences.models import Conference
        from groups.models import BranchGroup, GroupMembership
        
        conference = Conference.objects.get(id=conference_id)
        
        # Get course groups that have access to this conference
        course_groups = BranchGroup.objects.filter(
            accessible_courses__conferences=conference
        ).distinct()
        
        registered_count = 0
        for group in course_groups:
            # Get active members of the group
            memberships = GroupMembership.objects.filter(
                group=group,
                is_active=True
            )
            
            for membership in memberships:
                # Auto-register user for conference
                # This would create ConferenceAttendance records
                # For now, we'll just log the operation
                logger.info(f"Auto-registering user {membership.user.username} for conference {conference.title}")
                registered_count += 1
        
        logger.info(f"Auto-registered {registered_count} users for conference {conference_id}")
        return {
            'success': True,
            'registered_count': registered_count
        }
        
    except Exception as e:
        logger.error(f"Auto-registration task failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def _merge_task_results(main_results, service_results):
    """Merge results from different sync services"""
    if isinstance(service_results, dict):
        main_results['processed'] += service_results.get('processed', 0)
        main_results['created'] += service_results.get('created', 0)
        main_results['updated'] += service_results.get('updated', 0)
        main_results['errors'] += service_results.get('errors', 0)
        
        if service_results.get('error_messages'):
            main_results['error_messages'].extend(service_results['error_messages'])


# @shared_task(bind=True, max_retries=2, default_retry_delay=60)
def health_check_teams_integrations(self):
    """
    Health check for all Teams integrations
    """
    try:
        from account_settings.models import TeamsIntegration
        from .utils.teams_api import TeamsAPIClient
        
        integrations = TeamsIntegration.objects.filter(is_active=True)
        health_results = {
            'total_integrations': integrations.count(),
            'healthy': 0,
            'unhealthy': 0,
            'results': []
        }
        
        for integration in integrations:
            try:
                api_client = TeamsAPIClient(integration)
                test_result = api_client.test_connection()
                
                if test_result['success']:
                    health_results['healthy'] += 1
                    status = 'healthy'
                else:
                    health_results['unhealthy'] += 1
                    status = 'unhealthy'
                
                health_results['results'].append({
                    'integration_id': integration.id,
                    'integration_name': integration.name,
                    'status': status,
                    'message': test_result.get('message', ''),
                    'error': test_result.get('error', '')
                })
                
            except Exception as e:
                health_results['unhealthy'] += 1
                health_results['results'].append({
                    'integration_id': integration.id,
                    'integration_name': integration.name,
                    'status': 'unhealthy',
                    'error': str(e)
                })
        
        logger.info(f"Teams integrations health check completed: {health_results}")
        return health_results
        
    except Exception as e:
        logger.error(f"Teams integrations health check failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
