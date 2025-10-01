"""
Celery configuration for automated sync maintenance
"""
# Conditional celery import to avoid import errors during deployment
try:
    from celery.schedules import crontab
except ImportError:
    # Fallback when celery is not available
    crontab = None

# Celery periodic tasks configuration
if crontab is not None:
    CELERY_BEAT_SCHEDULE = {
        # Conference tasks
        'automated-sync-maintenance': {
            'task': 'conferences.tasks.automated_sync_maintenance',
            'schedule': crontab(hour=2, minute=0),  # 2:00 AM daily
            'options': {
                'queue': 'maintenance',
                'expires': 3600,  # 1 hour expiry
            }
        },
        
        # Weekly cleanup of old sync logs on Sundays at 3 AM
        'cleanup-old-sync-logs': {
            'task': 'conferences.tasks.cleanup_old_sync_logs',
            'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3:00 AM
            'options': {
                'queue': 'maintenance',
            }
        },
        
        # System health check every 6 hours
        'system-health-check': {
            'task': 'conferences.tasks.health_check_system',
            'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
            'options': {
                'queue': 'monitoring',
                'expires': 300,  # 5 minute expiry
            }
        },
        
        # SharePoint tasks
        'monitor-sharepoint-changes': {
            'task': 'sharepoint_integration.tasks.monitor_sharepoint_changes',
            'schedule': crontab(minute='*/15'),  # Every 15 minutes
            'options': {
                'queue': 'sync',
                'expires': 900,  # 15 minute expiry
            }
        },
        
        'sync-sharepoint-hourly': {
            'task': 'sharepoint_integration.tasks.scheduled_sharepoint_sync',
            'schedule': crontab(minute=0),  # Every hour
            'options': {
                'queue': 'sync',
                'expires': 3600,  # 1 hour expiry
            }
        },
        
        'sharepoint-health-check': {
            'task': 'sharepoint_integration.tasks.health_check_sharepoint_integrations',
            'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
            'options': {
                'queue': 'monitoring',
                'expires': 3600,  # 1 hour expiry
            }
        },
    }
else:
    # Fallback when celery is not available
    CELERY_BEAT_SCHEDULE = {}

# Celery queue configuration
CELERY_TASK_ROUTES = {
    # Conference tasks
    'conferences.tasks.automated_sync_maintenance': {'queue': 'maintenance'},
    'conferences.tasks.send_maintenance_summary': {'queue': 'emails'},
    'conferences.tasks.sync_conference_data_task': {'queue': 'sync'},
    'conferences.tasks.rematch_chat_messages_task': {'queue': 'sync'},
    'conferences.tasks.cleanup_old_sync_logs': {'queue': 'maintenance'},
    'conferences.tasks.health_check_system': {'queue': 'monitoring'},
    
    # SharePoint tasks
    'sharepoint_integration.tasks.sync_sharepoint_data': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_user_data_to_sharepoint': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_enrollment_data_to_sharepoint': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_progress_data_to_sharepoint': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_certificate_data_to_sharepoint': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_reports_to_powerbi': {'queue': 'sync'},
    'sharepoint_integration.tasks.scheduled_sharepoint_sync': {'queue': 'sync'},
    'sharepoint_integration.tasks.monitor_sharepoint_changes': {'queue': 'sync'},
    'sharepoint_integration.tasks.batch_sync_users': {'queue': 'sync'},
    'sharepoint_integration.tasks.batch_sync_enrollments': {'queue': 'sync'},
    'sharepoint_integration.tasks.sync_single_record': {'queue': 'sync'},
    'sharepoint_integration.tasks.health_check_sharepoint_integrations': {'queue': 'monitoring'},
}

# Task settings
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Retry settings
CELERY_TASK_SOFT_TIME_LIMIT = 300  # 5 minutes
CELERY_TASK_TIME_LIMIT = 600  # 10 minutes
CELERY_TASK_MAX_RETRIES = 3

# Enable task events for monitoring
CELERY_SEND_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

# Queue priority settings
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUES = {
    'default': {'routing_key': 'default'},
    'sync': {'routing_key': 'sync'},
    'maintenance': {'routing_key': 'maintenance'},
    'monitoring': {'routing_key': 'monitoring'},
    'emails': {'routing_key': 'emails'},
}

# Worker settings for conference sync
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100 