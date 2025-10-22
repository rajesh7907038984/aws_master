# SharePoint integration utilities package 
# Enhanced Auto-sync signals for comprehensive SharePoint integration
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
import logging
import json
from typing import Optional, Dict, Any
from celery import current_app
import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def is_celery_available():
    """
    Check if Celery is available and properly configured
    
    Returns:
        dict: Status information about Celery availability
    """
    try:
        # Check if Celery app is configured
        if not hasattr(current_app, 'control'):
            return {
                'available': False,
                'status': 'not_configured',
                'message': 'Celery is not configured'
            }
        
        # Check if Redis is accessible
        try:
            redis_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
            if redis_url.startswith('redis://'):
                # Extract Redis connection details
                import urllib.parse
                parsed = urllib.parse.urlparse(redis_url)
                redis_client = redis.Redis(
                    host=parsed.hostname or '127.0.0.1'  # Redis fallback,
                    port=parsed.port or 6379,
                    db=int(parsed.path.lstrip('/')) if parsed.path and parsed.path != '/' else 0
                )
                redis_client.ping()
            else:
                # For other brokers, assume they're working if configured
                pass
        except Exception as e:
            return {
                'available': False,
                'status': 'redis_unavailable', 
                'message': f'Redis broker not accessible: {str(e)}'
            }
        
        # Check if workers are active
        try:
            inspect = current_app.control.inspect()
            active_workers = inspect.active()
            if not active_workers:
                return {
                    'available': False,
                    'status': 'no_workers',
                    'message': 'No active Celery workers found'
                }
        except Exception as e:
            return {
                'available': False,
                'status': 'workers_check_failed',
                'message': f'Unable to check worker status: {str(e)}'
            }
        
        return {
            'available': True,
            'status': 'ready',
            'message': 'Celery is available and ready',
            'worker_count': len(active_workers) if active_workers else 0
        }
        
    except Exception as e:
        return {
            'available': False,
            'status': 'error',
            'message': f'Error checking Celery availability: {str(e)}'
        }


def get_sync_mode():
    """
    Determine the current sync mode based on Celery availability
    
    Returns:
        dict: Information about current sync mode
    """
    celery_status = is_celery_available()
    
    if celery_status['available']:
        return {
            'mode': 'async',
            'description': 'Background processing with Celery',
            'performance': 'Optimal - operations run in background',
            'celery_status': celery_status
        }
    else:
        return {
            'mode': 'sync', 
            'description': 'Synchronous processing',
            'performance': 'Standard - operations run immediately',
            'celery_status': celery_status
        }

def get_sharepoint_integration(branch=None, user=None):
    """
    Get active SharePoint integration for a branch or user
    
    Args:
        branch: Branch instance
        user: User instance (fallback to user's branch if branch not provided)
        
    Returns:
        SharePointIntegration instance or None
    """
    try:
        from account_settings.models import SharePointIntegration
        
        target_branch = branch
        if not target_branch and user and hasattr(user, 'branch'):
            target_branch = user.branch
            
        if target_branch:
            return SharePointIntegration.objects.filter(
                branch=target_branch,
                is_active=True
            ).first()
    except Exception as e:
        logger.error(f"Error getting SharePoint integration: {str(e)}")
    return None

def safe_sync_to_sharepoint(sync_function, instance, operation_type="update", async_task=None):
    """
    Safely execute SharePoint sync with error handling and logging.
    Automatically chooses between async (Celery) and sync execution.
    
    Args:
        sync_function: Function to execute for sync (used for sync mode)
        instance: Model instance being synced
        operation_type: Type of operation (create, update, delete)
        async_task: Celery task to execute (used for async mode)
    """
    try:
        sync_mode = get_sync_mode()
        
        if sync_mode['mode'] == 'async' and async_task:
            # Use Celery for background processing
            try:
                async_task.delay(instance.id)
                logger.info(f"Queued async sync for {instance._meta.label} {getattr(instance, 'id', 'unknown')} ({operation_type})")
                return True
            except Exception as celery_error:
                logger.warning(f"Failed to queue async sync for {instance._meta.label}, falling back to sync: {str(celery_error)}")
                # Fall back to synchronous execution
        
        # Execute sync synchronously
        with transaction.atomic():
            success = sync_function()
            
            if success:
                mode_info = "sync" if sync_mode['mode'] == 'sync' else "sync (fallback)"
                logger.info(f"Auto-synced {instance._meta.label} {getattr(instance, 'id', 'unknown')} to SharePoint ({operation_type}, {mode_info})")
                return True
            else:
                logger.warning(f"Failed to auto-sync {instance._meta.label} {getattr(instance, 'id', 'unknown')} to SharePoint ({operation_type})")
                return False
                
    except Exception as e:
        logger.error(f"Error in auto-sync signal for {instance._meta.label}: {str(e)}")
        return False

# ============================================================================
# USER SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='users.CustomUser')
def sync_user_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync user changes to SharePoint"""
    integration = get_sharepoint_integration(user=instance)
    
    if integration and integration.enable_user_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_lms_user_to_sharepoint(instance),
            instance,
            operation
        )

@receiver(post_delete, sender='users.CustomUser')
def handle_user_deletion_sharepoint(sender, instance, **kwargs):
    """Handle user deletion in SharePoint"""
    integration = get_sharepoint_integration(user=instance)
    
    if integration and integration.enable_user_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        
        # Mark user as deleted in SharePoint instead of actual deletion
        safe_sync_to_sharepoint(
            lambda: sync_service.mark_user_inactive_in_sharepoint(instance.email),
            instance,
            "delete"
        )

# ============================================================================
# COURSE SYNC SIGNALS  
# ============================================================================

@receiver(post_save, sender='courses.Course')
def sync_course_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync course changes to SharePoint"""
    integration = get_sharepoint_integration(branch=instance.branch)
    
    if integration:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_course_to_sharepoint(instance),
            instance,
            operation
        )

@receiver(post_save, sender='courses.CourseEnrollment') 
def sync_enrollment_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync course enrollment changes to SharePoint"""
    from core.utils.signal_coordination import SignalCoordinator
    
    if not SignalCoordinator.should_process_signal('sharepoint_sync', instance, created):
        return
        
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration and integration.enable_enrollment_sync:
        from .sync_services import EnrollmentSyncService
        
        sync_service = EnrollmentSyncService(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_single_enrollment_to_sharepoint(instance),
            instance,
            operation
        )

@receiver(post_delete, sender='courses.CourseEnrollment')
def handle_enrollment_deletion_sharepoint(sender, instance, **kwargs):
    """Handle enrollment deletion in SharePoint"""
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration and integration.enable_enrollment_sync:
        from .sync_services import EnrollmentSyncService
        
        sync_service = EnrollmentSyncService(integration) 
        
        safe_sync_to_sharepoint(
            lambda: sync_service.mark_enrollment_withdrawn_in_sharepoint(instance),
            instance,
            "delete"
        )

# ============================================================================
# PROGRESS SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='courses.TopicProgress')
def sync_progress_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync topic progress to SharePoint"""
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration and integration.enable_progress_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_topic_progress_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# ASSIGNMENT SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='assignments.AssignmentSubmission')
def sync_assignment_submission_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync assignment submission to SharePoint"""
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration and integration.enable_assessment_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_assignment_submission_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# GRADEBOOK SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='gradebook.Grade')
def sync_grade_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync grade changes to SharePoint"""
    integration = get_sharepoint_integration(user=instance.student)
    
    if integration and integration.enable_assessment_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_grade_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# QUIZ SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='quiz.QuizAttempt')
def sync_quiz_attempt_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync quiz attempt to SharePoint"""
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration and integration.enable_assessment_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_quiz_attempt_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# CERTIFICATE SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='certificates.IssuedCertificate')
def sync_certificate_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync certificate to SharePoint"""
    integration = get_sharepoint_integration(user=instance.recipient)
    
    if integration and integration.enable_certificate_sync:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_certificate_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# GROUP SYNC SIGNALS
# ============================================================================

@receiver(post_save, sender='groups.BranchGroup')
def sync_group_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync group changes to SharePoint"""
    integration = get_sharepoint_integration(branch=instance.branch)
    
    if integration:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_group_to_sharepoint(instance),
            instance,
            operation
        )

@receiver(post_save, sender='groups.GroupMembership')
def sync_group_membership_to_sharepoint(sender, instance, created, **kwargs):
    """Auto-sync group membership changes to SharePoint"""
    integration = get_sharepoint_integration(user=instance.user)
    
    if integration:
        from .sync_services import SharePointBidirectionalSync
        
        sync_service = SharePointBidirectionalSync(integration)
        operation = "create" if created else "update"
        
        safe_sync_to_sharepoint(
            lambda: sync_service.sync_group_membership_to_sharepoint(instance),
            instance,
            operation
        )

# ============================================================================
# SYNC EVENT LOGGING
# ============================================================================

class SharePointSyncEvent:
    """Class for logging detailed sync events"""
    
    @staticmethod
    def log_sync_event(operation: str, model_name: str, instance_id: Any, 
                      success: bool, details: Dict = None, error: str = None):
        """
        Log a detailed sync event
        
        Args:
            operation: Type of operation (create, update, delete)
            model_name: Name of the model being synced
            instance_id: ID of the instance
            success: Whether sync was successful
            details: Additional details about the sync
            error: Error message if sync failed
        """
        try:
            log_data = {
                'operation': operation,
                'model': model_name,
                'instance_id': str(instance_id),
                'success': success,
                'timestamp': timezone.now().isoformat(),
                'details': details or {},
            }
            
            if error:
                log_data['error'] = error
                
            # Log to file and optionally to database
            if success:
                logger.info(f"SharePoint sync event: {json.dumps(log_data)}")
            else:
                logger.error(f"SharePoint sync failed: {json.dumps(log_data)}")
                
        except Exception as e:
            logger.error(f"Error logging sync event: {str(e)}")

def auto_upload_certificate_to_sharepoint(certificate_data: dict, file_content: bytes):
    """
    Function to be called when a certificate is generated
    This should be called from the certificate generation process
    """
    try:
        from account_settings.models import SharePointIntegration
        
        # Get SharePoint integration for student's branch
        student_email = certificate_data.get('student_email')
        if student_email:
            from users.models import CustomUser
            try:
                user = CustomUser.objects.get(email=student_email)
                if user.branch:
                    integration = SharePointIntegration.objects.filter(
                        branch=user.branch,
                        is_active=True,
                        enable_certificate_sync=True
                    ).first()
                    
                    if integration:
                        from sharepoint_integration.utils.sharepoint_api import SharePointAPI
                        api = SharePointAPI(integration)
                        result = api.upload_certificate(file_content, certificate_data.get('filename', 'certificate.pdf'), certificate_data)
                        
                        if result and result.get('success'):
                            logger.info(f"Successfully uploaded certificate for {student_email} to SharePoint")
                            return result
                        else:
                            logger.warning(f"Failed to upload certificate for {student_email} to SharePoint")
                            
            except CustomUser.DoesNotExist:
                logger.warning(f"User with email {student_email} not found for certificate upload")
                
    except Exception as e:
        logger.error(f"Error in certificate auto-upload: {str(e)}")
    
    return None