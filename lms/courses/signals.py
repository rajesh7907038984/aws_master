"""
Course and Topic Deletion Signals
Automatically clean up related data when courses or topics are deleted.
"""

from django.db.models.signals import pre_delete, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone
import logging

from .models import Course, Topic, TopicProgress, CourseTopic
# SCORM imports removed - functionality no longer supported

logger = logging.getLogger(__name__)

@receiver(pre_delete, sender=Course)
def cleanup_course_data(sender, instance, **kwargs):
    """
    Clean up all related data when a course is deleted.
    This runs before the course is actually deleted.
    """
    try:
        with transaction.atomic():
            course_id = instance.id
            course_title = instance.title
            
            logger.info(f"Starting cleanup for course {course_id}: {course_title}")
            
            # 1. Get all topics related to this course
            topics = Topic.objects.filter(coursetopic__course=instance)
            topic_ids = [t.id for t in topics]
            
            # 2. Delete all progress records for topics in this course
            progress_records = TopicProgress.objects.filter(topic__in=topics)
            progress_count = progress_records.count()
            if progress_count > 0:
                progress_records.delete()
                logger.info(f"Deleted {progress_count} progress records for course {course_id}")
            
            # 3. Delete all course-topic relationships
            relationships = CourseTopic.objects.filter(course=instance)
            relationship_count = relationships.count()
            if relationship_count > 0:
                relationships.delete()
                logger.info(f"Deleted {relationship_count} course-topic relationships for course {course_id}")
            
            # 4. Keep SCORM content in SCORM Cloud - only remove local database references
            scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id__in=[str(tid) for tid in topic_ids]
            )
            scorm_content_count = scorm_content.count()
            if scorm_content_count > 0:
                # Only delete local database references, keep SCORM content in SCORM Cloud
                scorm_content.delete()
                logger.info(f"Removed {scorm_content_count} local SCORM content references for course {course_id} (SCORM content preserved in SCORM Cloud)")
            
            # 5. Keep SCORM registrations in SCORM Cloud - only remove local database references
            scorm_registrations = []
            for topic in topics:
                if topic.content_type in ['SCORM', 'scorm']:
                    registrations = SCORMRegistration.objects.filter(
                        package__scormcloudcontent__content_type='topic',
                        package__scormcloudcontent__content_id=str(topic.id)
                    )
                    scorm_registrations.extend(registrations)
            
            if scorm_registrations:
                for reg in scorm_registrations:
                    # Only delete local database references, keep registrations in SCORM Cloud
                    reg.delete()
                logger.info(f"Removed {len(scorm_registrations)} local SCORM registration references for course {course_id} (registrations preserved in SCORM Cloud)")
            
            logger.info(f"Course {course_id} cleanup completed successfully")
            
    except Exception as e:
        logger.error(f"Error during course {instance.id} cleanup: {str(e)}")
        # Don't raise the exception to prevent deletion failure
        # Log the error and continue with deletion

@receiver(pre_delete, sender=Topic)
def cleanup_topic_data(sender, instance, **kwargs):
    """
    Clean up all related data when a topic is deleted.
    This runs before the topic is actually deleted.
    """
    try:
        with transaction.atomic():
            topic_id = instance.id
            topic_title = instance.title
            
            logger.info(f"Starting cleanup for topic {topic_id}: {topic_title}")
            
            # 1. Delete all progress records for this topic
            progress_records = TopicProgress.objects.filter(topic=instance)
            progress_count = progress_records.count()
            if progress_count > 0:
                progress_records.delete()
                logger.info(f"Deleted {progress_count} progress records for topic {topic_id}")
            
            # 2. Delete all course-topic relationships for this topic
            relationships = CourseTopic.objects.filter(topic=instance)
            relationship_count = relationships.count()
            if relationship_count > 0:
                relationships.delete()
                logger.info(f"Deleted {relationship_count} course-topic relationships for topic {topic_id}")
            
            # 3. Keep SCORM content in SCORM Cloud - only remove local database references
            scorm_content = SCORMCloudContent.objects.filter(
                content_type='topic',
                content_id=str(topic_id)
            )
            scorm_content_count = scorm_content.count()
            if scorm_content_count > 0:
                # Only delete local database references, keep SCORM content in SCORM Cloud
                scorm_content.delete()
                logger.info(f"Removed {scorm_content_count} local SCORM content references for topic {topic_id} (SCORM content preserved in SCORM Cloud)")
            
            # 4. Keep SCORM registrations in SCORM Cloud - only remove local database references
            if instance.content_type in ['SCORM', 'scorm']:
                try:
                    scorm_registrations = SCORMRegistration.objects.filter(
                        package__scormcloudcontent__content_type='topic',
                        package__scormcloudcontent__content_id=str(topic_id)
                    )
                    reg_count = scorm_registrations.count()
                    if reg_count > 0:
                        # Only delete local database references, keep registrations in SCORM Cloud
                        scorm_registrations.delete()
                        logger.info(f"Removed {reg_count} local SCORM registration references for topic {topic_id} (registrations preserved in SCORM Cloud)")
                except Exception as e:
                    logger.error(f"Error removing local SCORM registration references for topic {topic_id}: {str(e)}")
            
            logger.info(f"Topic {topic_id} cleanup completed successfully")
            
    except Exception as e:
        logger.error(f"Error during topic {instance.id} cleanup: {str(e)}")
        # Don't raise the exception to prevent deletion failure
        # Log the error and continue with deletion

@receiver(post_delete, sender=Course)
def post_course_deletion(sender, instance, **kwargs):
    """
    Post-deletion cleanup for courses.
    This runs after the course is deleted.
    """
    try:
        course_id = instance.id
        course_title = instance.title
        
        logger.info(f"Course {course_id} ({course_title}) deleted successfully")
        
        # Clear any cached data related to this course
        # This could include clearing cache, updating search indexes, etc.
        
    except Exception as e:
        logger.error(f"Error during post-deletion cleanup for course {instance.id}: {str(e)}")

@receiver(post_delete, sender=Topic)
def post_topic_deletion(sender, instance, **kwargs):
    """
    Post-deletion cleanup for topics.
    This runs after the topic is deleted.
    """
    try:
        topic_id = instance.id
        topic_title = instance.title
        
        logger.info(f"Topic {topic_id} ({topic_title}) deleted successfully")
        
        # Clear any cached data related to this topic
        # This could include clearing cache, updating search indexes, etc.
        
    except Exception as e:
        logger.error(f"Error during post-deletion cleanup for topic {instance.id}: {str(e)}")

def cleanup_orphaned_data():
    """
    Clean up any existing orphaned data.
    This can be called manually or via a management command.
    """
    try:
        logger.info("Starting orphaned data cleanup")
        
        # Find orphaned progress records
        orphaned_progress = TopicProgress.objects.filter(topic__isnull=True)
        orphaned_count = orphaned_progress.count()
        if orphaned_count > 0:
            orphaned_progress.delete()
            logger.info(f"Deleted {orphaned_count} orphaned progress records")
        
        # Find orphaned SCORM registrations
        orphaned_registrations = SCORMRegistration.objects.filter(user__isnull=True)
        orphaned_reg_count = orphaned_registrations.count()
        if orphaned_reg_count > 0:
            orphaned_registrations.delete()
            logger.info(f"Deleted {orphaned_reg_count} orphaned SCORM registrations")
        
        # Find orphaned SCORM content
        orphaned_content = SCORMCloudContent.objects.filter(
            content_type='topic'
        ).exclude(
            content_id__in=[str(t.id) for t in Topic.objects.all()]
        )
        orphaned_content_count = orphaned_content.count()
        if orphaned_content_count > 0:
            orphaned_content.delete()
            logger.info(f"Deleted {orphaned_content_count} orphaned SCORM content records")
        
        total_cleaned = orphaned_count + orphaned_reg_count + orphaned_content_count
        logger.info(f"Orphaned data cleanup completed: {total_cleaned} records cleaned")
        
        return total_cleaned
        
    except Exception as e:
        logger.error(f"Error during orphaned data cleanup: {str(e)}")
        return 0