"""
Fixed SCORM async uploader with robust error handling and proper environment variable inheritance
"""
import os
import json
import time
import logging
import threading
import queue
import traceback
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from scorm_cloud.utils.api import get_scorm_client, SCORMCloudError
from scorm_cloud.utils.redis_fallback import get_robust_fallback

logger = logging.getLogger(__name__)

# CRITICAL FIX: Load environment variables at module level to ensure worker threads inherit them
def _load_environment_variables():
    """Load environment variables from unified .env file at module level"""
    try:
        # Import the unified environment loader
        from core.env_loader import env_loader
        
        # Environment variables are already loaded by the env_loader
        logger.info("✅ Environment variables loaded via unified env_loader for SCORM worker")
        
        # Log the key database variables (without passwords)
        logger.info(f"Database host: {os.environ.get('AWS_DB_HOST', 'Not set')}")
        logger.info(f"Database user: {os.environ.get('AWS_DB_USER', 'Not set')}")
        logger.info(f"Database name: {os.environ.get('AWS_DB_NAME', 'Not set')}")
        logger.info(f"Database password: {'✓ Set' if os.environ.get('AWS_DB_PASSWORD') else '✗ Not set'}")
        
    except Exception as e:
        logger.error(f"Failed to load environment variables for SCORM worker: {str(e)}")

# Load environment variables immediately when module is imported
_load_environment_variables()

# Global upload queue
upload_queue = queue.Queue()
retry_queue = queue.Queue()

# Upload worker thread control
worker_running = False
worker_thread = None
max_retries = 3

class SCORMUploadTask:
    """Represents a SCORM upload task"""
    def __init__(self, file_path, topic_id, course_id=None, title=None, retries=0, user_id=None):
        self.file_path = file_path
        self.topic_id = topic_id
        self.course_id = course_id or f"LMS_{topic_id}_{int(time.time())}"
        self.title = title
        self.retries = retries
        self.created_at = datetime.now()
        self.status = "queued"
        self.result = None
        self.error = None
        self.scorm_id = None
        self.user_id = user_id

def enqueue_upload(file_path, topic_id, title=None, user=None):
    """Add a SCORM package upload task to the queue with robust error handling"""
    try:
        # Check worker health before enqueueing
        restart_worker_if_needed()
        
        if file_path:
            if not os.path.exists(file_path):
                logger.error(f"Cannot enqueue upload - file not found: {file_path}")
                return False
        else:
            logger.error("Cannot enqueue upload - no file path provided")
            return False
        
        # Use robust fallback cache
        fallback_cache = get_robust_fallback()
        
        # Check for duplicate processing
        cache_key = f"scorm_processing_{topic_id}"
        if fallback_cache.get(cache_key):
            logger.info(f"Topic {topic_id} is already being processed, skipping duplicate enqueue")
            return False
        
        # Check if this topic is already completed
        try:
            from scorm_cloud.models import SCORMCloudContent
            existing_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic_id)
            ).first()
            
            if existing_content and existing_content.package:
                logger.info(f"SCORM content already exists for topic {topic_id}, skipping upload")
                fallback_cache.set(f"scorm_processed_{topic_id}", True, 3600)
                return False
        except Exception as e:
            logger.warning(f"Could not check for existing SCORM content: {str(e)}")
        
        # Check if this topic is already in the queue
        with upload_queue.mutex:
            for item in list(upload_queue.queue):
                if item.topic_id == topic_id:
                    logger.info(f"Topic {topic_id} already in upload queue, skipping duplicate")
                    return False
        
        # Also check the retry queue
        with retry_queue.mutex:
            for item in list(retry_queue.queue):
                if item.topic_id == topic_id:
                    logger.info(f"Topic {topic_id} already in retry queue, skipping duplicate")
                    return False
        
        user_id = user.id if user else None
        logger.info(f"enqueue_upload: Creating task with user_id={user_id} for topic {topic_id}")
        task = SCORMUploadTask(file_path, topic_id, title=title, user_id=user_id)
        upload_queue.put(task)
        logger.info(f"Queued SCORM upload for topic {topic_id}: {file_path}")
        
        # Start the worker thread if not already running
        try:
            worker_started = ensure_worker_running()
            if not worker_started:
                logger.warning("Worker thread failed to start, attempting synchronous upload")
                return process_upload_synchronously(task)
        except Exception as e:
            logger.error(f"Failed to start upload worker: {str(e)}")
            logger.info("Attempting synchronous upload as fallback")
            return process_upload_synchronously(task)
        
        return True
        
    except Exception as e:
        logger.error(f"Error in enqueue_upload: {str(e)}")
        logger.exception("enqueue_upload error details:")
        return False

def ensure_worker_running():
    """Ensure the upload worker thread is running with robust error handling and auto-recovery"""
    global worker_running, worker_thread
    
    try:
        # CRITICAL FIX: Check if worker is already running and alive
        if worker_running and worker_thread and worker_thread.is_alive():
            logger.info("SCORM upload worker is already running")
            return True
        
        # Additional check to prevent multiple workers in Gunicorn
        import os
        if os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn'):
            logger.info("Skipping SCORM worker start in Gunicorn worker process")
            return True
        
        # Reset state if thread is dead
        if worker_thread and not worker_thread.is_alive():
            logger.warning("Previous SCORM worker thread was dead, resetting state")
            worker_running = False
            worker_thread = None
        
        # Start the worker thread with proper error handling
        worker_thread = threading.Thread(
            target=upload_worker, 
            daemon=True, 
            name="SCORMUploadWorker"
        )
        worker_thread.start()
        
        # Give the thread time to start and initialize
        time.sleep(2)
        
        # Verify the thread started successfully
        if worker_thread and worker_thread.is_alive():
            logger.info("SCORM upload worker thread started successfully")
            return True
        else:
            logger.error("SCORM upload worker thread failed to start")
            worker_running = False
            return False
            
    except Exception as e:
        logger.error(f"Failed to start SCORM upload worker thread: {str(e)}")
        logger.exception("Worker thread startup error details:")
        worker_running = False
        worker_thread = None
        return False

def restart_worker_if_needed():
    """Check and restart worker thread if it's dead - called periodically"""
    global worker_running, worker_thread
    
    try:
        # Check if worker thread is dead
        if worker_thread and not worker_thread.is_alive():
            logger.warning("SCORM worker thread detected as dead, attempting restart")
            worker_running = False
            worker_thread = None
            
            # Attempt to restart the worker
            if ensure_worker_running():
                logger.info("SCORM worker thread successfully restarted")
                return True
            else:
                logger.error("Failed to restart SCORM worker thread")
                return False
        elif not worker_thread:
            # No worker thread exists, try to start one
            logger.info("No SCORM worker thread exists, attempting to start")
            return ensure_worker_running()
        else:
            # Worker is alive and running
            return True
            
    except Exception as e:
        logger.error(f"Error checking/restarting SCORM worker thread: {str(e)}")
        return False

def get_worker_status():
    """Get the current status of the SCORM upload worker"""
    global worker_running, worker_thread
    
    status = {
        'worker_running': worker_running,
        'worker_thread_alive': worker_thread.is_alive() if worker_thread else False,
        'queue_size': upload_queue.qsize(),
        'retry_queue_size': retry_queue.qsize(),
        'worker_thread_name': worker_thread.name if worker_thread else None
    }
    
    return status

def health_check():
    """Perform a health check on the SCORM upload worker and restart if needed"""
    try:
        status = get_worker_status()
        logger.info(f"SCORM worker health check: {status}")
        
        # Check if worker needs restart
        if not status['worker_running'] or not status['worker_thread_alive']:
            logger.warning("SCORM worker is not running, attempting restart")
            return restart_worker_if_needed()
        
        return True
        
    except Exception as e:
        logger.error(f"Error in SCORM worker health check: {str(e)}")
        return False

def upload_worker():
    """Main worker loop for processing upload tasks with robust error handling and auto-recovery"""
    global worker_running
    
    # CRITICAL FIX: Load environment variables in the worker thread
    _load_environment_variables()
    
    logger.info("SCORM upload worker started")
    
    # Set worker_running to True at the beginning of the worker thread
    worker_running = True
    
    # Initialize error counters for auto-recovery
    consecutive_errors = 0
    max_consecutive_errors = 5
    error_recovery_delay = 5  # seconds
    
    try:
        # FIXED: Use Django's database connection properly
        from django.db import connection
        
        # CRITICAL FIX: Use Django's database connection with proper error handling
        try:
            # Close any existing connections to ensure fresh connection
            from django.db import connections
            connections.close_all()
            
            # Get a fresh connection
            from django.db import connection
            connection.ensure_connection()
            
            # Verify connection works by running a simple query
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            logger.info("✅ Database connection established successfully for SCORM worker")
            db_connection_established = True
            
        except Exception as db_error:
            # IMPROVED: Only log as INFO instead of WARNING to reduce noise
            logger.info(f"Database connection not available for SCORM worker: {str(db_error)}")
            logger.info("SCORM worker will continue without database operations (this is normal for background processes)")
            db_connection_established = False
        
        if not db_connection_established:
            logger.info("ℹ️ SCORM worker starting without database connection (normal for background processes)")
        
        while worker_running:
            try:
                # Get task from main queue
                try:
                    task = upload_queue.get(timeout=1)
                except queue.Empty:
                    # Check retry queue
                    try:
                        task = retry_queue.get_nowait()
                    except queue.Empty:
                        # Reset error counter on successful idle cycle
                        consecutive_errors = 0
                        continue
                
                # Process the task
                logger.info(f"Processing SCORM upload task for topic {task.topic_id}")
                process_upload_task(task)
                
                # Reset error counter on successful task processing
                consecutive_errors = 0
                
                # Mark task as done
                try:
                    upload_queue.task_done()
                except ValueError:
                    # Task was from retry queue
                    pass
                    
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in upload worker (consecutive errors: {consecutive_errors}): {str(e)}")
                logger.exception("Worker error details:")
                
                # If too many consecutive errors, take a break
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(f"Too many consecutive errors ({consecutive_errors}), taking a {error_recovery_delay}s break")
                    time.sleep(error_recovery_delay)
                    consecutive_errors = 0  # Reset after break
                
                # Continue processing other tasks
                continue
                
    except Exception as e:
        logger.error(f"Fatal error in upload worker: {str(e)}")
        logger.exception("Fatal worker error details:")
    finally:
        logger.info("SCORM upload worker stopped")
        # Reset global state when worker stops
        global worker_thread
        worker_running = False
        worker_thread = None

def process_upload_task(task):
    """Process a single upload task with robust error handling"""
    try:
        logger.info(f"Processing upload task for topic {task.topic_id}")
        
        # FIXED: Environment variables are already loaded at module level
        # Ensure database connection is available for this task
        from django.db import connection
        db_connection_available = True
        
        try:
            # Test database connection
            connection.ensure_connection()
            
            # Verify connection works
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
                
        except Exception as db_error:
            logger.error(f"Database connection failed for task {task.topic_id}: {str(db_error)}")
            logger.error(f"Database config check - Host: {os.environ.get('AWS_DB_HOST', 'Not set')}")
            logger.error(f"Database config check - Password: {'✓ Set' if os.environ.get('AWS_DB_PASSWORD') else '✗ Not set'}")
            db_connection_available = False
            # Don't raise the exception, just log it and continue without database operations
            logger.warning(f"Task {task.topic_id} will be processed without database operations")
        
        # Use robust fallback cache
        fallback_cache = get_robust_fallback()
        
        # Set processing lock
        cache_key = f"scorm_processing_{task.topic_id}"
        fallback_cache.set(cache_key, True, 3600)
        
        try:
            # Get SCORM client
            user = None
            if task.user_id and db_connection_available:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(id=task.user_id)
                except User.DoesNotExist:
                    logger.warning(f"User {task.user_id} not found, using default client")
                except Exception as user_error:
                    logger.warning(f"Database error getting user {task.user_id}: {str(user_error)}, using default client")
            elif task.user_id and not db_connection_available:
                logger.warning(f"Database unavailable - cannot get user {task.user_id}, using default client")
            
            client = get_scorm_client(user=user)
            if not client:
                raise Exception("Could not get SCORM client")
            
            # Process the upload
            result = client.upload_package(
                file_path=task.file_path,
                course_id=task.course_id,
                title=task.title or f"Course {task.topic_id}"
            )
            
            if result and result.get('id'):
                task.scorm_id = result['id']
                task.status = "completed"
                task.result = result
                logger.info(f"SCORM upload completed for topic {task.topic_id}: {task.scorm_id}")
                
                # Create SCORMCloudContent record to link the package to the topic (only if DB available)
                if db_connection_available:
                    try:
                        from scorm_cloud.models import SCORMCloudContent, SCORMPackage
                        from courses.models import Topic
                        
                        # Get the topic
                        topic = Topic.objects.get(id=task.topic_id)
                        
                        # Create SCORMPackage record first
                        package = SCORMPackage.objects.create(
                            cloud_id=result['id'],
                            title=task.title or topic.title,
                            description=f"SCORM content for topic {task.topic_id}",
                            version='1.2',
                            launch_url=result.get('launch_url', ''),
                            entry_url=result.get('entry_url', ''),
                            use_frameset=True,
                            launch_mode='window'
                        )
                        
                        # Create or update SCORMCloudContent record with the package
                        scorm_content, created = SCORMCloudContent.objects.update_or_create(
                            content_id=str(task.topic_id),
                            content_type='topic',
                            defaults={
                                'package': package,  # Set the package immediately
                                'title': task.title or topic.title,
                                'description': f"SCORM content for topic {task.topic_id}",
                                'registration_prefix': f'LMS_{task.topic_id}_',
                                'passing_score': 80,
                                'requires_passing_score': True
                            }
                        )
                        
                        # If updating existing content, link the package
                        if not created:
                            scorm_content.package = package
                            scorm_content.save()
                        
                        logger.info(f"✅ {'Created' if created else 'Updated'} SCORM content record for topic {task.topic_id}")
                        
                    except Exception as link_error:
                        logger.error(f"❌ Failed to create SCORM content link for topic {task.topic_id}: {str(link_error)}")
                        # Don't fail the entire upload for database issues
                        logger.warning(f"⚠️ SCORM upload succeeded but database record creation failed for topic {task.topic_id}")
                else:
                    logger.warning(f"⚠️ Database unavailable - SCORM upload succeeded but no database record created for topic {task.topic_id}")
                
                # Mark as processed
                fallback_cache.set(f"scorm_processed_{task.topic_id}", True, 3600)
            else:
                raise Exception("Upload result was empty or invalid")
                
        except Exception as e:
            logger.error(f"Upload failed for topic {task.topic_id}: {str(e)}")
            task.error = str(e)
            task.status = "failed"
            
            # Retry logic
            if task.retries < max_retries:
                task.retries += 1
                task.status = "retrying"
                retry_queue.put(task)
                logger.info(f"Queued topic {task.topic_id} for retry {task.retries}/{max_retries}")
            else:
                logger.error(f"Topic {task.topic_id} failed after {max_retries} retries")
                task.status = "failed_permanently"
        
        finally:
            # Clear processing lock
            fallback_cache.delete(cache_key)
            
    except Exception as e:
        logger.error(f"Fatal error processing task for topic {task.topic_id}: {str(e)}")
        logger.exception("Task processing error details:")

def process_upload_synchronously(task):
    """Process upload synchronously as fallback"""
    try:
        logger.info(f"Processing upload synchronously for topic {task.topic_id}")
        process_upload_task(task)
        return True
    except Exception as e:
        logger.error(f"Synchronous upload failed for topic {task.topic_id}: {str(e)}")
        return False

def get_queue_status():
    """Get current queue status"""
    try:
        return {
            'worker_running': worker_running,
            'worker_alive': worker_thread.is_alive() if worker_thread else False,
            'upload_queue_size': upload_queue.qsize(),
            'retry_queue_size': retry_queue.qsize(),
            'active_locks': 0  # This would need to be tracked separately
        }
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        return {
            'worker_running': False,
            'worker_alive': False,
            'upload_queue_size': 0,
            'retry_queue_size': 0,
            'active_locks': 0
        }
