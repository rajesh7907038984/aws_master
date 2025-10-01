"""
Celery tasks for SharePoint integration

These tasks handle asynchronous SharePoint synchronization operations
to avoid blocking the main application.
"""

from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging
import time

from .utils.sync_services import (
    UserSyncService,
    EnrollmentSyncService,
    ProgressSyncService,
    CertificateSyncService,
    ReportsSyncService
)

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=5, default_retry_delay=60, exponential_backoff=True)
def sync_sharepoint_data(self, integration_id, sync_type='all', direction='to_sharepoint'):
    """
    Asynchronous task to sync data with SharePoint
    
    Args:
        integration_id: SharePoint integration ID
        sync_type: Type of data to sync ('all', 'users', 'enrollments', etc.)
        direction: Direction of sync ('to_sharepoint', 'from_sharepoint', 'bidirectional')
    """
    try:
        from account_settings.models import SharePointIntegration
        
        # Get integration
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        logger.info(f"Starting async SharePoint sync for integration {integration.name}")
        
        # Check if integration is active
        if not integration.is_active:
            logger.warning(f"SharePoint integration {integration.name} is not active")
            return {
                'success': False,
                'message': 'Integration is not active'
            }
        
        results = {
            'success': True,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'error_messages': []
        }
        
        # User synchronization
        if sync_type in ['all', 'users']:
            logger.info("Starting user synchronization...")
            user_service = UserSyncService(integration)
            
            if direction in ['to_sharepoint', 'bidirectional']:
                user_results = user_service.sync_users_to_sharepoint()
                _merge_task_results(results, user_results)
            
            if direction in ['from_sharepoint', 'bidirectional']:
                user_results = user_service.sync_users_from_sharepoint()
                _merge_task_results(results, user_results)
        
        # Enrollment synchronization
        if sync_type in ['all', 'enrollments']:
            logger.info("Starting enrollment synchronization...")
            enrollment_service = EnrollmentSyncService(integration)
            enrollment_results = enrollment_service.sync_enrollments_to_sharepoint()
            _merge_task_results(results, enrollment_results)
        
        # Progress synchronization
        if sync_type in ['all', 'progress']:
            logger.info("Starting progress synchronization...")
            progress_service = ProgressSyncService(integration)
            progress_results = progress_service.sync_progress_to_sharepoint()
            _merge_task_results(results, progress_results)
        
        # Certificate synchronization
        if sync_type in ['all', 'certificates']:
            logger.info("Starting certificate synchronization...")
            cert_service = CertificateSyncService(integration)
            cert_results = cert_service.sync_certificates_to_sharepoint()
            _merge_task_results(results, cert_results)
        
        # Reports synchronization
        if sync_type in ['all', 'reports']:
            logger.info("Starting reports synchronization...")
            reports_service = ReportsSyncService(integration)
            reports_results = reports_service.sync_reports_to_powerbi()
            _merge_task_results(results, reports_results)
        
        results['success'] = results['errors'] == 0
        
        logger.info(f"SharePoint sync completed for integration {integration.name}: {results}")
        
        return results
        
    except Exception as exc:
        logger.error(f"SharePoint sync task failed: {str(exc)}")
        
        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying SharePoint sync task in 60 seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60, exc=exc)
        
        return {
            'success': False,
            'message': f'Task failed after {self.max_retries} retries: {str(exc)}'
        }


@shared_task
def sync_user_data_to_sharepoint(integration_id, user_id=None):
    """
    Sync specific user data to SharePoint
    
    Args:
        integration_id: SharePoint integration ID
        user_id: Specific user ID to sync (optional, syncs all if None)
    """
    try:
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_user_sync:
            return {'success': False, 'message': 'User sync not enabled'}
        
        user_service = UserSyncService(integration)
        
        if user_id:
            # Sync specific user (would need additional implementation)
            logger.info(f"Syncing specific user {user_id} to SharePoint")
            # This would require modifying the service to handle single user sync
            results = user_service.sync_users_to_sharepoint()
        else:
            # Sync all users
            results = user_service.sync_users_to_sharepoint()
        
        logger.info(f"User sync to SharePoint completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"User sync task failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def sync_enrollment_data_to_sharepoint(integration_id, course_id=None):
    """
    Sync enrollment data to SharePoint
    
    Args:
        integration_id: SharePoint integration ID
        course_id: Specific course ID to sync enrollments for (optional)
    """
    try:
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_enrollment_sync:
            return {'success': False, 'message': 'Enrollment sync not enabled'}
        
        enrollment_service = EnrollmentSyncService(integration)
        results = enrollment_service.sync_enrollments_to_sharepoint()
        
        logger.info(f"Enrollment sync to SharePoint completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Enrollment sync task failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def sync_progress_data_to_sharepoint(integration_id):
    """
    Sync progress data to SharePoint
    
    Args:
        integration_id: SharePoint integration ID
    """
    try:
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_progress_sync:
            return {'success': False, 'message': 'Progress sync not enabled'}
        
        progress_service = ProgressSyncService(integration)
        results = progress_service.sync_progress_to_sharepoint()
        
        logger.info(f"Progress sync to SharePoint completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Progress sync task failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def sync_certificates_to_sharepoint(integration_id):
    """
    Sync certificates to SharePoint document library
    
    Args:
        integration_id: SharePoint integration ID
    """
    try:
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_certificate_sync:
            return {'success': False, 'message': 'Certificate sync not enabled'}
        
        cert_service = CertificateSyncService(integration)
        results = cert_service.sync_certificates_to_sharepoint()
        
        logger.info(f"Certificate sync to SharePoint completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Certificate sync task failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def sync_reports_to_powerbi(integration_id):
    """
    Sync LMS analytics to Power BI via SharePoint
    
    Args:
        integration_id: SharePoint integration ID
    """
    try:
        from account_settings.models import SharePointIntegration
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_reports_sync:
            return {'success': False, 'message': 'Reports sync not enabled'}
        
        reports_service = ReportsSyncService(integration)
        results = reports_service.sync_reports_to_powerbi()
        
        logger.info(f"Reports sync to Power BI completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Reports sync task failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def scheduled_sharepoint_sync():
    """
    Scheduled task to sync all active SharePoint integrations
    This task should be run periodically via Celery Beat
    """
    try:
        from account_settings.models import SharePointIntegration, GlobalAdminSettings
        
        # Check if SharePoint integration is globally enabled
        try:
            global_settings = GlobalAdminSettings.objects.first()
            if not global_settings or not global_settings.sharepoint_integration_enabled:
                logger.info("SharePoint integration is globally disabled")
                return {'success': False, 'message': 'SharePoint integration globally disabled'}
        except:
            logger.warning("Could not check global SharePoint settings")
        
        # Get all active integrations
        integrations = SharePointIntegration.objects.filter(is_active=True)
        
        if not integrations.exists():
            logger.info("No active SharePoint integrations found")
            return {'success': True, 'message': 'No active integrations'}
        
        results = {
            'total_integrations': integrations.count(),
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for integration in integrations:
            try:
                # Start async sync for each integration
                task_result = sync_sharepoint_data.delay(
                    integration.id,
                    sync_type='all',
                    direction='to_sharepoint'
                )
                
                results['successful'] += 1
                results['details'].append({
                    'integration_id': integration.id,
                    'integration_name': integration.name,
                    'task_id': task_result.id,
                    'status': 'started'
                })
                
                logger.info(f"Started scheduled sync for integration {integration.name}")
                
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'integration_id': integration.id,
                    'integration_name': integration.name,
                    'error': str(e),
                    'status': 'failed'
                })
                
                logger.error(f"Failed to start scheduled sync for integration {integration.name}: {str(e)}")
        
        logger.info(f"Scheduled SharePoint sync completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Scheduled SharePoint sync failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def monitor_sharepoint_changes(self, integration_id=None):
    """
    Monitor SharePoint for changes and sync them to LMS
    
    Args:
        integration_id: Specific integration ID (optional, monitors all if None)
    """
    try:
        from account_settings.models import SharePointIntegration
        from .utils.sharepoint_monitor import start_sharepoint_monitoring, SharePointChangeMonitor
        
        if integration_id:
            # Monitor specific integration
            integration = SharePointIntegration.objects.get(id=integration_id)
            if not integration.is_active:
                return {'success': False, 'message': 'Integration is not active'}
            
            monitor = SharePointChangeMonitor(integration)
            results = monitor.start_monitoring()
            
            logger.info(f"SharePoint monitoring completed for {integration.name}: {results}")
            return results
        else:
            # Monitor all active integrations
            results = start_sharepoint_monitoring()
            logger.info(f"SharePoint monitoring completed for all integrations: {results}")
            return results
            
    except Exception as exc:
        logger.error(f"SharePoint monitoring task failed: {str(exc)}")
        
        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying SharePoint monitoring task in {30 * (2 ** self.request.retries)} seconds")
            raise self.retry(countdown=30 * (2 ** self.request.retries), exc=exc)
        
        return {'success': False, 'message': f'Monitoring failed after {self.max_retries} retries: {str(exc)}'}


@shared_task(bind=True, max_retries=3)
def batch_sync_users(self, integration_id, user_ids, batch_size=50):
    """
    Batch sync multiple users to SharePoint
    
    Args:
        integration_id: SharePoint integration ID
        user_ids: List of user IDs to sync
        batch_size: Number of users to process per batch
    """
    try:
        from account_settings.models import SharePointIntegration
        from .utils.sync_services import SharePointBidirectionalSync
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active or not integration.enable_user_sync:
            return {'success': False, 'message': 'User sync not enabled'}
        
        sync_service = SharePointBidirectionalSync(integration)
        
        results = {
            'total_users': len(user_ids),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        # Process users in batches
        for i in range(0, len(user_ids), batch_size):
            batch_ids = user_ids[i:i + batch_size]
            users = User.objects.filter(id__in=batch_ids)
            
            for user in users:
                try:
                    success = sync_service.sync_lms_user_to_sharepoint(user)
                    results['processed'] += 1
                    
                    if success:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append(f"Failed to sync user {user.email}")
                        
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(f"Error syncing user {user.email}: {str(e)}")
                    logger.error(f"Error syncing user {user.email}: {str(e)}")
            
            # Small delay between batches to avoid overwhelming SharePoint
            if i + batch_size < len(user_ids):
                time.sleep(1)
        
        logger.info(f"Batch user sync completed: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Batch user sync task failed: {str(exc)}")
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying batch user sync task in 60 seconds")
            raise self.retry(countdown=60, exc=exc)
        
        return {'success': False, 'message': f'Batch sync failed: {str(exc)}'}


@shared_task(bind=True, max_retries=2)
def resolve_sync_conflicts(self, integration_id):
    """
    Resolve synchronization conflicts between LMS and SharePoint
    
    Args:
        integration_id: SharePoint integration ID
    """
    try:
        from account_settings.models import SharePointIntegration
        from .utils.conflict_resolver import SharePointConflictResolver
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active:
            return {'success': False, 'message': 'Integration is not active'}
        
        resolver = SharePointConflictResolver(integration)
        results = resolver.resolve_all_conflicts()
        
        logger.info(f"Conflict resolution completed for {integration.name}: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Conflict resolution task failed: {str(exc)}")
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying conflict resolution task in 120 seconds")
            raise self.retry(countdown=120, exc=exc)
        
        return {'success': False, 'message': f'Conflict resolution failed: {str(exc)}'}


@shared_task
def sync_single_record(integration_id, record_type, record_id, direction='to_sharepoint'):
    """
    Sync a single record to/from SharePoint
    
    Args:
        integration_id: SharePoint integration ID
        record_type: Type of record ('user', 'course', 'enrollment', etc.)
        record_id: ID of the record to sync
        direction: Direction of sync
    """
    try:
        from account_settings.models import SharePointIntegration
        from .utils.sync_services import SharePointBidirectionalSync
        
        integration = SharePointIntegration.objects.get(id=integration_id)
        
        if not integration.is_active:
            return {'success': False, 'message': 'Integration is not active'}
        
        sync_service = SharePointBidirectionalSync(integration)
        
        # Route to appropriate sync method based on record type
        if record_type == 'user':
            from django.contrib.auth import get_user_model
            User = get_user_model()
            record = User.objects.get(id=record_id)
            
            if direction == 'to_sharepoint':
                success = sync_service.sync_lms_user_to_sharepoint(record)
            else:
                # Would need SharePoint user data for reverse sync
                success = False
                
        elif record_type == 'enrollment':
            from courses.models import CourseEnrollment
            record = CourseEnrollment.objects.get(id=record_id)
            
            if direction == 'to_sharepoint':
                from .utils.sync_services import EnrollmentSyncService
                enrollment_service = EnrollmentSyncService(integration)
                success = enrollment_service.sync_single_enrollment_to_sharepoint(record)
            else:
                success = False
                
        else:
            return {'success': False, 'message': f'Unsupported record type: {record_type}'}
        
        result = {
            'success': success,
            'record_type': record_type,
            'record_id': record_id,
            'direction': direction
        }
        
        logger.info(f"Single record sync completed: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Single record sync failed: {str(e)}")
        return {'success': False, 'message': str(e)}


@shared_task
def health_check_sharepoint_integrations():
    """
    Health check for all SharePoint integrations
    """
    try:
        from account_settings.models import SharePointIntegration
        from .utils.sharepoint_api import SharePointAPI
        
        integrations = SharePointIntegration.objects.filter(is_active=True)
        
        results = {
            'total_integrations': integrations.count(),
            'healthy': 0,
            'unhealthy': 0,
            'details': []
        }
        
        for integration in integrations:
            try:
                api = SharePointAPI(integration)
                success, message = api.test_connection()
                
                status = 'healthy' if success else 'unhealthy'
                results[status] += 1
                
                results['details'].append({
                    'integration_id': integration.id,
                    'name': integration.name,
                    'status': status,
                    'message': message,
                    'last_sync': integration.last_sync_datetime.isoformat() if integration.last_sync_datetime else None
                })
                
            except Exception as e:
                results['unhealthy'] += 1
                results['details'].append({
                    'integration_id': integration.id,
                    'name': integration.name,
                    'status': 'unhealthy',
                    'message': str(e),
                    'last_sync': integration.last_sync_datetime.isoformat() if integration.last_sync_datetime else None
                })
        
        logger.info(f"SharePoint health check completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"SharePoint health check failed: {str(e)}")
        return {'success': False, 'message': str(e)}


def _merge_task_results(main_results, service_results):
    """Helper function to merge service results into main task results"""
    main_results['processed'] += service_results.get('processed', 0)
    main_results['created'] += service_results.get('created', 0)
    main_results['updated'] += service_results.get('updated', 0)
    main_results['errors'] += service_results.get('errors', 0)
    
    if service_results.get('error_messages'):
        main_results['error_messages'].extend(service_results['error_messages'])


# Enhanced Celery Beat schedule configuration for periodic tasks
# Add this to your Celery configuration:
"""
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Bidirectional sync every 15 minutes
    'monitor-sharepoint-changes': {
        'task': 'sharepoint_integration.tasks.monitor_sharepoint_changes',
        'schedule': crontab(minute='*/15'),  # Run every 15 minutes
    },
    
    # Full sync every hour
    'sync-sharepoint-hourly': {
        'task': 'sharepoint_integration.tasks.scheduled_sharepoint_sync',
        'schedule': crontab(minute=0),  # Run every hour
    },
    
    # Daily reports sync
    'sync-sharepoint-reports-daily': {
        'task': 'sharepoint_integration.tasks.sync_reports_to_powerbi',
        'schedule': crontab(hour=2, minute=0),  # Run daily at 2 AM
    },
    
    # Health check every 6 hours
    'sharepoint-health-check': {
        'task': 'sharepoint_integration.tasks.health_check_sharepoint_integrations',
        'schedule': crontab(minute=0, hour='*/6'),  # Run every 6 hours
    },
    
    # Conflict resolution daily
    'resolve-sync-conflicts-daily': {
        'task': 'sharepoint_integration.tasks.resolve_sync_conflicts',
        'schedule': crontab(hour=3, minute=0),  # Run daily at 3 AM
    },
}
""" 