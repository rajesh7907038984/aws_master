"""
Celery tasks for automated conference sync maintenance
"""
from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from conferences.models import Conference, ConferenceSyncLog
from conferences.utils.sync_resilience import SyncHealthChecker, SyncRecoveryManager
from conferences.views import sync_zoom_meeting_data, rematch_unmatched_chat_messages
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def automated_sync_maintenance(self):
    """
    Automated maintenance task that runs daily to:
    1. Check sync health of recent conferences
    2. Auto-fix issues where possible
    3. Send alerts for critical issues
    """
    try:
        logger.info("Starting automated sync maintenance...")
        
        # Get conferences from last 7 days that might need attention
        recent_conferences = Conference.objects.filter(
            date__gte=timezone.now().date() - timezone.timedelta(days=7)
        ).order_by('-date')
        
        maintenance_report = {
            'total_checked': 0,
            'issues_found': 0,
            'auto_fixed': 0,
            'critical_alerts': 0,
            'conferences_processed': []
        }
        
        for conference in recent_conferences:
            try:
                maintenance_report['total_checked'] += 1
                
                # Check health
                health = SyncHealthChecker.check_conference_sync_health(conference.id)
                
                conf_result = {
                    'conference_id': conference.id,
                    'conference_title': conference.title,
                    'status': health['overall_status'],
                    'issues': health.get('issues', []),
                    'actions_taken': []
                }
                
                if health['issues']:
                    maintenance_report['issues_found'] += 1
                    
                    # Attempt auto-recovery
                    recovery_result = SyncRecoveryManager.auto_recover_conference(conference.id)
                    
                    conf_result['actions_taken'] = recovery_result.get('actions_taken', [])
                    
                    if recovery_result.get('success'):
                        maintenance_report['auto_fixed'] += 1
                        logger.info(f"Auto-fixed issues for conference {conference.id}: {conference.title}")
                    
                    # If still critical after recovery, flag for alert
                    if health['overall_status'] == 'critical':
                        maintenance_report['critical_alerts'] += 1
                
                maintenance_report['conferences_processed'].append(conf_result)
                
            except Exception as e:
                logger.error(f"Error processing conference {conference.id}: {str(e)}")
                continue
        
        # Send summary email to admins
        send_maintenance_summary.delay(maintenance_report)
        
        logger.info(f"Automated maintenance complete: {maintenance_report['auto_fixed']} fixes applied")
        return maintenance_report
        
    except Exception as exc:
        logger.error(f"Automated sync maintenance failed: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)

@shared_task
def send_maintenance_summary(maintenance_report):
    """Send maintenance summary email to administrators"""
    try:
        if not hasattr(settings, 'EMAIL_HOST') or not settings.EMAIL_HOST:
            logger.warning("Email not configured, skipping maintenance summary")
            return
        
        subject = f"Conference Sync Maintenance Report - {maintenance_report['auto_fixed']} Fixes Applied"
        
        message = "Automated Conference Sync Maintenance Report\n"
        message += "="*50 + "\n\n"
        message += f"Summary:\n"
        message += f"• Total conferences checked: {maintenance_report['total_checked']}\n"
        message += f"• Issues found: {maintenance_report['issues_found']}\n"
        message += f"• Auto-fixed: {maintenance_report['auto_fixed']}\n"
        message += f"• Critical alerts: {maintenance_report['critical_alerts']}\n\n"
        
        if maintenance_report['auto_fixed'] > 0:
            message += "Auto-Fixed Conferences:\n"
            for conf in maintenance_report['conferences_processed']:
                if conf['actions_taken']:
                    message += f"• {conf['conference_title']} (ID: {conf['conference_id']})\n"
                    for action in conf['actions_taken']:
                        message += f"  - {action}\n"
            message += "\n"
        
        if maintenance_report['critical_alerts'] > 0:
            message += "Critical Issues Requiring Attention:\n"
            for conf in maintenance_report['conferences_processed']:
                if conf['status'] == 'critical':
                    message += f"• {conf['conference_title']} (ID: {conf['conference_id']})\n"
                    for issue in conf['issues']:
                        message += f"  - {issue}\n"
            message += "\n"
        
        message += f"Report generated at: {timezone.now()}\n"
        
        # Send to admins
        admin_emails = [email for name, email in getattr(settings, 'ADMINS', [])]
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=True,
            )
            logger.info(f"Maintenance summary sent to {len(admin_emails)} admins")
        
    except Exception as e:
        logger.error(f"Failed to send maintenance summary: {str(e)}")

@shared_task(bind=True, max_retries=2)
def sync_conference_data_task(self, conference_id):
    """
    Background task for syncing conference data with enhanced resilience
    """
    try:
        conference = Conference.objects.get(id=conference_id)
        logger.info(f"Starting background sync for conference {conference_id}: {conference.title}")
        
        # Use the enhanced sync function
        sync_result = sync_zoom_meeting_data(conference)
        
        if sync_result.get('success'):
            logger.info(f"Background sync successful for conference {conference_id}")
            return {
                'success': True,
                'conference_id': conference_id,
                'sync_result': sync_result
            }
        else:
            logger.error(f"Background sync failed for conference {conference_id}: {sync_result.get('error')}")
            return {
                'success': False,
                'conference_id': conference_id,
                'error': sync_result.get('error')
            }
            
    except Conference.DoesNotExist:
        logger.error(f"Conference {conference_id} not found for background sync")
        return {
            'success': False,
            'conference_id': conference_id,
            'error': 'Conference not found'
        }
    except Exception as exc:
        logger.error(f"Background sync task failed for conference {conference_id}: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)

@shared_task
def rematch_chat_messages_task(conference_id):
    """
    Background task for re-matching chat messages
    """
    try:
        conference = Conference.objects.get(id=conference_id)
        logger.info(f"Starting chat re-matching for conference {conference_id}: {conference.title}")
        
        matched_count = rematch_unmatched_chat_messages(conference)
        
        logger.info(f"Chat re-matching complete for conference {conference_id}: {matched_count} messages matched")
        return {
            'success': True,
            'conference_id': conference_id,
            'matched_count': matched_count
        }
        
    except Conference.DoesNotExist:
        logger.error(f"Conference {conference_id} not found for chat re-matching")
        return {
            'success': False,
            'conference_id': conference_id,
            'error': 'Conference not found'
        }
    except Exception as e:
        logger.error(f"Chat re-matching task failed for conference {conference_id}: {str(e)}")
        return {
            'success': False,
            'conference_id': conference_id,
            'error': str(e)
        }

@shared_task
def cleanup_old_sync_logs():
    """
    Clean up old sync logs to prevent database bloat
    """
    try:
        # Keep logs for last 30 days
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        
        deleted_count = ConferenceSyncLog.objects.filter(
            sync_started_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old sync logs")
        return {
            'success': True,
            'deleted_count': deleted_count
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old sync logs: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

@shared_task
def health_check_system():
    """
    System-wide health check task that can be triggered externally
    """
    try:
        system_health = SyncHealthChecker.get_system_wide_health()
        
        # Determine if action is needed
        action_needed = (
            system_health['critical'] > 0 or 
            system_health['warning'] > system_health['total_conferences'] * 0.3
        )
        
        if action_needed:
            logger.warning(
                f"System health check: {system_health['critical']} critical, "
                f"{system_health['warning']} warnings out of {system_health['total_conferences']} conferences"
            )
        
        return {
            'success': True,
            'system_health': system_health,
            'action_needed': action_needed
        }
        
    except Exception as e:
        logger.error(f"System health check failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        } 