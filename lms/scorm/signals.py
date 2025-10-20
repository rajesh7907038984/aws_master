"""
SCORM Signals
Automatically handle SCORM package lifecycle:
- Auto-extract packages when uploaded
- Clean up SCORM content from S3 and database when deleted
"""

from django.db.models.signals import pre_delete, post_delete, post_save
from django.dispatch import receiver
from django.db import transaction
import logging
from .models import ELearningPackage, ELearningTracking
from courses.models import Topic, Course

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ELearningPackage)
def auto_extract_package(sender, instance, created, **kwargs):
    """
    Automatically extract SCORM/CMI5 package to S3 when uploaded.
    This ensures packages are always ready to use immediately after upload.
    """
    try:
        # Only auto-extract if:
        # 1. Package has a file
        # 2. Package is not already extracted
        # 3. Avoid re-extraction loops
        if instance.package_file and not instance.is_extracted:
            logger.info(f"Auto-extracting package {instance.id} for topic {instance.topic_id}")
            
            # Ensure package_type is set (auto-detect if needed)
            if not instance.package_type:
                logger.info(f"Package type not set, attempting auto-detection...")
                detected_type = instance.detect_package_type()
                if detected_type:
                    instance.package_type = detected_type
                    instance.save(update_fields=['package_type'])
                    logger.info(f"Auto-detected package type: {detected_type}")
                else:
                    # Default to SCORM_1_2 if detection fails
                    instance.package_type = 'SCORM_1_2'
                    instance.save(update_fields=['package_type'])
                    logger.warning(f"Could not detect package type, using default: SCORM_1_2")
            
            # Check if file actually exists in storage
            if instance.package_file.storage.exists(instance.package_file.name):
                # Extract the package directly to S3
                success = instance.extract_package()
                
                if success:
                    logger.info(f"✅ Successfully auto-extracted package {instance.id} to S3")
                    logger.info(f"   Package type: {instance.package_type}")
                    logger.info(f"   Extracted path: {instance.extracted_path}")
                else:
                    logger.error(f"❌ Failed to auto-extract package {instance.id}")
                    if instance.extraction_error:
                        logger.error(f"   Error: {instance.extraction_error}")
            else:
                logger.warning(f"Package file {instance.package_file.name} not found in storage")
                
    except Exception as e:
        logger.error(f"Error during auto-extraction for package {instance.id}: {str(e)}", exc_info=True)

@receiver(pre_delete, sender=Topic)
def cleanup_scorm_topic_data(sender, instance, **kwargs):
    """
    Clean up SCORM data when a topic is deleted.
    This runs before the topic is actually deleted.
    """
    try:
        with transaction.atomic():
            topic_id = instance.id
            topic_title = instance.title
            
            logger.info(f"Starting SCORM cleanup for topic {topic_id}: {topic_title}")
            
            # 1. Delete all SCORM tracking records for this topic
            tracking_records = ELearningTracking.objects.filter(
                elearning_package__topic=instance
            )
            tracking_count = tracking_records.count()
            if tracking_count > 0:
                tracking_records.delete()
                logger.info(f"Deleted {tracking_count} SCORM tracking records for topic {topic_id}")
            
            # 2. Delete SCORM package and clean up S3 files
            try:
                scorm_package = ELearningPackage.objects.get(topic=instance)
                # Delete S3 files
                cleanup_scorm_s3_files(scorm_package)
                # Delete the package record
                scorm_package.delete()
                logger.info(f"Deleted SCORM package and S3 files for topic {topic_id}")
            except ELearningPackage.DoesNotExist:
                logger.info(f"No SCORM package found for topic {topic_id}")
            
            logger.info(f"SCORM cleanup completed for topic {topic_id}")
            
    except Exception as e:
        logger.error(f"Error during SCORM cleanup for topic {instance.id}: {str(e)}")

@receiver(pre_delete, sender=Course)
def cleanup_scorm_course_data(sender, instance, **kwargs):
    """
    Clean up SCORM data when a course is deleted.
    This runs before the course is actually deleted.
    """
    try:
        with transaction.atomic():
            course_id = instance.id
            course_title = instance.title
            
            logger.info(f"Starting SCORM cleanup for course {course_id}: {course_title}")
            
            # Get all topics in this course
            topics = Topic.objects.filter(coursetopic__course=instance)
            topic_ids = [t.id for t in topics]
            
            # Delete all SCORM tracking records for topics in this course
            tracking_records = ELearningTracking.objects.filter(
                elearning_package__topic__in=topics
            )
            tracking_count = tracking_records.count()
            if tracking_count > 0:
                tracking_records.delete()
                logger.info(f"Deleted {tracking_count} SCORM tracking records for course {course_id}")
            
            # Delete SCORM packages and clean up S3 files for all topics
            scorm_packages = ELearningPackage.objects.filter(topic__in=topics)
            for package in scorm_packages:
                cleanup_scorm_s3_files(package)
            scorm_packages.delete()
            
            logger.info(f"SCORM cleanup completed for course {course_id}")
            
    except Exception as e:
        logger.error(f"Error during SCORM cleanup for course {instance.id}: {str(e)}")

def cleanup_scorm_s3_files(scorm_package):
    """
    Clean up S3 files for a SCORM package.
    """
    try:
        if scorm_package.package_file:
            # Delete the main package file
            scorm_package.package_file.delete()
            logger.info(f"Deleted SCORM package file: {scorm_package.package_file.name}")
        
        if scorm_package.extracted_path:
            # Delete extracted content directory
            from .storage import SCORMS3Storage
            storage = SCORMS3Storage()
            
            # Delete all files in the extracted directory
            try:
                # List all files in the extracted directory
                files, dirs = storage.listdir(scorm_package.extracted_path)
                
                # Delete all files
                for file in files:
                    file_path = f"{scorm_package.extracted_path}/{file}"
                    storage.delete(file_path)
                    logger.info(f"Deleted SCORM extracted file: {file_path}")
                
                # Delete subdirectories recursively
                for dir_name in dirs:
                    dir_path = f"{scorm_package.extracted_path}/{dir_name}"
                    cleanup_directory_recursive(storage, dir_path)
                
                logger.info(f"Cleaned up SCORM extracted directory: {scorm_package.extracted_path}")
                
            except Exception as e:
                logger.warning(f"Could not clean up extracted directory {scorm_package.extracted_path}: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error cleaning up S3 files for SCORM package {scorm_package.id}: {str(e)}")

def cleanup_directory_recursive(storage, dir_path):
    """
    Recursively delete a directory and all its contents from S3.
    """
    try:
        files, dirs = storage.listdir(dir_path)
        
        # Delete all files in current directory
        for file in files:
            file_path = f"{dir_path}/{file}"
            storage.delete(file_path)
            logger.info(f"Deleted file: {file_path}")
        
        # Recursively delete subdirectories
        for dir_name in dirs:
            subdir_path = f"{dir_path}/{dir_name}"
            cleanup_directory_recursive(storage, subdir_path)
        
    except Exception as e:
        logger.warning(f"Could not clean up directory {dir_path}: {str(e)}")

@receiver(post_delete, sender=ELearningPackage)
def post_scorm_package_deletion(sender, instance, **kwargs):
    """
    Post-deletion cleanup for SCORM packages.
    This runs after the SCORM package is deleted.
    """
    try:
        logger.info(f"SCORM package {instance.id} deleted successfully")
        
        # Additional cleanup if needed
        # This could include clearing cache, updating search indexes, etc.
        
    except Exception as e:
        logger.error(f"Error during post-deletion cleanup for SCORM package {instance.id}: {str(e)}")

@receiver(post_delete, sender=ELearningTracking)
def post_scorm_tracking_deletion(sender, instance, **kwargs):
    """
    Post-deletion cleanup for SCORM tracking records.
    This runs after the tracking record is deleted.
    """
    try:
        logger.info(f"SCORM tracking record for user {instance.user.id} and package {instance.elearning_package.id} deleted successfully")
        
        # Additional cleanup if needed
        # This could include updating user progress, clearing cache, etc.
        
    except Exception as e:
        logger.error(f"Error during post-deletion cleanup for SCORM tracking record: {str(e)}")
