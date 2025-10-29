"""
Django signals for SCORM package automatic processing
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from .models import ScormPackage
from .tasks import extract_scorm_package

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ScormPackage)
def auto_extract_scorm_package(sender, instance, created, **kwargs):
    """
    Automatically trigger SCORM package extraction when a new package is created
    Also processes packages that are saved with pending status (for retries)
    """
    # Check if file exists - multiple methods to ensure we catch it
    has_file = False
    file_name = None
    
    try:
        # Method 1: Check if package_zip field exists
        if hasattr(instance, 'package_zip') and instance.package_zip:
            # Method 2: Get the name attribute (works for both local and S3 storage)
            file_name = getattr(instance.package_zip, 'name', None)
            if file_name:
                # Remove leading slashes and check if it's not empty
                file_name = file_name.strip('/').strip()
                has_file = bool(file_name)
            
            # Method 3: If name check failed, try checking the field value directly
            if not has_file:
                try:
                    # Access the underlying file object to check if it exists
                    if hasattr(instance.package_zip, 'file') or hasattr(instance.package_zip, 'storage'):
                        has_file = True
                        if not file_name:
                            file_name = str(instance.package_zip)
                except:
                    pass
            
            # Method 4: Check the database field directly (last resort)
            if not has_file:
                try:
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT package_zip FROM scorm_scormpackage WHERE id = %s",
                            [instance.id]
                        )
                        row = cursor.fetchone()
                        if row and row[0]:
                            file_name = row[0]
                            has_file = bool(file_name)
                except Exception as db_error:
                    logger.debug(f"Could not check DB directly for package {instance.id}: {db_error}")
    except Exception as e:
        logger.error(f"Error checking package_zip for package {instance.id}: {e}", exc_info=True)
    
    # Log signal firing for debugging
    logger.info(
        f"SCORM signal fired: package_id={instance.id}, created={created}, "
        f"status={instance.processing_status}, has_file={has_file}, "
        f"file_name={'present' if file_name else 'missing'}, "
        f"update_fields={kwargs.get('update_fields')}"
    )
    
    # Process if:
    # 1. Status is pending AND file exists (created now or set on update)
    # 2. If retrying by setting status back to pending, require file to be present
    should_process = (
        instance.processing_status == 'pending' and has_file
    )
    
    if not should_process:
        logger.info(
            f"Skipping extraction for package {instance.id}: "
            f"status={instance.processing_status}, has_file={has_file}, created={created}"
        )
        return
    
    logger.info(f"Auto-extracting SCORM package {instance.id} (signal triggered, created={created})")
    
    try:
        # Try Celery first (async)
        try:
            zip_path = None
            try:
                if hasattr(instance.package_zip, 'path') and instance.package_zip.path:
                    import os
                    zip_path = instance.package_zip.path if os.path.exists(instance.package_zip.path) else None
            except (NotImplementedError, AttributeError, ValueError):
                # ValueError can be raised if no file associated yet
                zip_path = None  # S3 storage or not yet available; use None
            
            # Check if Celery is actually available
            if hasattr(extract_scorm_package, 'delay'):
                extract_scorm_package.delay(instance.id, zip_path)
                logger.info(f"Queued Celery task for SCORM package {instance.id}")
            else:
                raise AttributeError("Celery delay method not available")
        except (AttributeError, Exception) as celery_error:
            # Celery not available or failed - run synchronously immediately
            logger.info(f"Celery not available for package {instance.id}, running synchronously: {celery_error}")
            try:
                result = extract_scorm_package(None, instance.id, None)
                logger.info(f"Synchronous extraction completed for package {instance.id}: {result}")
                
                # Refresh instance to get updated status
                instance.refresh_from_db()
                
                if instance.processing_status == 'ready':
                    logger.info(f"Package {instance.id} extraction completed successfully")
                elif instance.processing_status == 'failed':
                    logger.error(f"Package {instance.id} extraction failed: {instance.processing_error}")
            except Exception as sync_error:
                logger.error(f"Error in synchronous SCORM extraction for package {instance.id}: {sync_error}", exc_info=True)
                # Update package status to failed
                try:
                    instance.processing_status = 'failed'
                    instance.processing_error = f"Extraction failed: {str(sync_error)}"
                    instance.save(update_fields=['processing_status', 'processing_error'])
                except Exception as save_error:
                    logger.error(f"Could not update package status: {save_error}")
    except Exception as e:
        logger.error(f"Error auto-extracting SCORM package {instance.id}: {e}", exc_info=True)
        # Ensure package status reflects the error
        try:
            if instance:
                instance.processing_status = 'failed'
                instance.processing_error = f"Signal handler error: {str(e)}"
                instance.save(update_fields=['processing_status', 'processing_error'])
        except Exception as save_error:
            logger.error(f"Could not update package status after signal error: {save_error}")

