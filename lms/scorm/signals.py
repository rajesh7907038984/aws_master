"""
SCORM Signals
Handle post-save and other signals for SCORM models
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage
import logging

from .models import SCORMPackage, SCORMAttempt

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=SCORMPackage)
def delete_package_files(sender, instance, **kwargs):
    """
    Delete associated files when a SCORM package is deleted
    """
    try:
        # Delete package file
        if instance.package_file:
            if default_storage.exists(instance.package_file.name):
                default_storage.delete(instance.package_file.name)
                logger.info(f"Deleted package file: {instance.package_file.name}")
        
        # Delete extracted content directory
        if instance.extracted_path:
            # List and delete all files in the directory
            try:
                dirs, files = default_storage.listdir(instance.extracted_path)
                
                # Delete all files
                for file in files:
                    file_path = f"{instance.extracted_path}/{file}"
                    if default_storage.exists(file_path):
                        default_storage.delete(file_path)
                
                # Delete all subdirectories (recursively)
                for dir_name in dirs:
                    dir_path = f"{instance.extracted_path}/{dir_name}"
                    delete_directory_recursive(dir_path)
                
                logger.info(f"Deleted extracted content: {instance.extracted_path}")
            except Exception as e:
                logger.error(f"Error deleting extracted content: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error in delete_package_files signal: {str(e)}")


def delete_directory_recursive(directory_path):
    """
    Recursively delete a directory and its contents in S3
    """
    try:
        dirs, files = default_storage.listdir(directory_path)
        
        # Delete all files
        for file in files:
            file_path = f"{directory_path}/{file}"
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
        
        # Delete all subdirectories (recursively)
        for dir_name in dirs:
            dir_path = f"{directory_path}/{dir_name}"
            delete_directory_recursive(dir_path)
    
    except Exception as e:
        logger.error(f"Error deleting directory {directory_path}: {str(e)}")


@receiver(post_save, sender=SCORMAttempt)
def sync_topic_progress(sender, instance, created, **kwargs):
    """
    Sync SCORM attempt completion with topic progress
    """
    if not created and instance.topic and instance.is_completed():
        try:
            from courses.models import TopicProgress
            
            topic_progress, tp_created = TopicProgress.objects.get_or_create(
                user=instance.user,
                topic=instance.topic
            )
            
            # Update completion status
            if not topic_progress.completed:
                topic_progress.completed = True
                topic_progress.completion_date = instance.completed_at
                
                # Update score if available
                if instance.score_raw is not None:
                    topic_progress.score = instance.score_raw
                
                topic_progress.save()
                logger.info(f"Synced SCORM completion to topic progress: {instance}")
        
        except Exception as e:
            logger.error(f"Error syncing topic progress: {str(e)}")

