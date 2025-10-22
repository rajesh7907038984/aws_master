"""
Course and Topic Deletion Signals
Automatically clean up related data when courses or topics are deleted.
Also handles enrollment notifications.
"""

from django.db.models.signals import pre_delete, post_delete, post_save
from django.dispatch import receiver
from django.db import transaction, DatabaseError, IntegrityError
from django.utils import timezone
import logging

from .models import Course, Topic, CourseEnrollment

# Import TopicProgress and CourseTopic dynamically  
try:
    from .models import TopicProgress
except ImportError:
    TopicProgress = None

try:
    from .models import CourseTopic
except ImportError:
    # CourseTopic is a through model, get it dynamically
    CourseTopic = Course.topics.through if hasattr(Course, 'topics') else None

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
            
            logger.info(f"Course {course_id} cleanup completed successfully")
            
    except (DatabaseError, IntegrityError) as e:
        logger.error(f"Database error during course {instance.id} cleanup: {str(e)}")
        # Don't raise the exception to prevent deletion failure
        # Log the error and continue with deletion
    except Exception as e:
        logger.error(f"Unexpected error during course {instance.id} cleanup: {str(e)}")
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
            
            # 1. Delete SCORM-related data if this is a SCORM topic
            if instance.content_type == 'SCORM':
                try:
                    from scorm.models import ScormPackage, ScormAttempt
                    
                    # Check if SCORM package exists
                    if hasattr(instance, 'scorm_package'):
                        scorm_package = instance.scorm_package
                        
                        # Delete all attempts first
                        attempts_count = ScormAttempt.objects.filter(scorm_package=scorm_package).count()
                        if attempts_count > 0:
                            ScormAttempt.objects.filter(scorm_package=scorm_package).delete()
                            logger.info(f"Deleted {attempts_count} SCORM attempts for topic {topic_id}")
                        
                        # Delete the package (this will cascade to files if configured)
                        scorm_package.delete()
                        logger.info(f"Deleted SCORM package for topic {topic_id}")
                        
                except Exception as scorm_error:
                    logger.error(f"Error cleaning up SCORM data for topic {topic_id}: {str(scorm_error)}")
            
            # 2. Delete all progress records for this topic
            progress_records = TopicProgress.objects.filter(topic=instance)
            progress_count = progress_records.count()
            if progress_count > 0:
                progress_records.delete()
                logger.info(f"Deleted {progress_count} progress records for topic {topic_id}")
            
            # 3. Delete all course-topic relationships for this topic
            relationships = CourseTopic.objects.filter(topic=instance)
            relationship_count = relationships.count()
            if relationship_count > 0:
                relationships.delete()
                logger.info(f"Deleted {relationship_count} course-topic relationships for topic {topic_id}")
            
            logger.info(f"Topic {topic_id} cleanup completed successfully")
            
    except (DatabaseError, IntegrityError) as e:
        logger.error(f"Database error during topic {instance.id} cleanup: {str(e)}")
        # Don't raise the exception to prevent deletion failure
        # Log the error and continue with deletion
    except Exception as e:
        logger.error(f"Unexpected error during topic {instance.id} cleanup: {str(e)}")
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
        
        total_cleaned = orphaned_count
        logger.info(f"Orphaned data cleanup completed: {total_cleaned} records cleaned")
        
        return total_cleaned
        
    except Exception as e:
        logger.error(f"Error during orphaned data cleanup: {str(e)}")
        return 0


@receiver(post_save, sender=CourseEnrollment)
def send_enrollment_notification(sender, instance, created, **kwargs):
    """
    Send email notification when a user is enrolled in a course
    """
    if created and instance.user and instance.course:
        try:
            # Import here to avoid circular imports
            from lms_notifications.utils import send_notification
            from django.urls import reverse
            
            # Prepare enrollment message
            enrollment_message = f"""
            <h2>Course Enrollment Confirmation</h2>
            <p>Dear {instance.user.first_name or instance.user.username},</p>
            <p>You have been successfully enrolled in the following course:</p>
            <p><strong>Course Details:</strong></p>
            <ul>
                <li><strong>Course Name:</strong> {instance.course.title}</li>
                {f'<li><strong>Description:</strong> {instance.course.description[:200]}...</li>' if instance.course.description else ''}
                <li><strong>Enrollment Date:</strong> {instance.enrolled_at.strftime('%B %d, %Y')}</li>
                <li><strong>Enrollment Type:</strong> {instance.get_enrollment_source_display()}</li>
            </ul>
            <p>You can now access the course materials and start learning.</p>
            <p>Good luck with your studies!</p>
            <p>Best regards,<br>The LMS Team</p>
            """
            
            # Send notification
            notification = send_notification(
                recipient=instance.user,
                notification_type_name='course_enrollment',
                title=f"Enrolled in: {instance.course.title}",
                message=enrollment_message,
                short_message=f"You have been enrolled in {instance.course.title}",
                priority='normal',
                action_url=f"/courses/{instance.course.id}/",
                action_text="View Course",
                related_course=instance.course,
                send_email=True
            )
            
            if notification:
                logger.info(f"Enrollment notification sent to user: {instance.user.username} for course: {instance.course.title}")
            else:
                logger.warning(f"Enrollment notification created but email may not have been sent for user: {instance.user.username}")
                
        except Exception as e:
            logger.error(f"Error sending enrollment notification to {instance.user.username} for course {instance.course.title}: {str(e)}")


@receiver(post_save, sender=Topic)
def process_scorm_package(sender, instance, created, **kwargs):
    """
    Process SCORM package after Topic is saved with SCORM content.
    This handler extracts and parses SCORM packages automatically.
    """
    # Only process if this is a SCORM topic with a content file
    if instance.content_type != 'SCORM' or not instance.content_file:
        return
    
    try:
        # Import SCORM models
        from scorm.models import ScormPackage
        
        # Check if ScormPackage already exists for this topic
        if hasattr(instance, 'scorm_package') and ScormPackage.objects.filter(topic=instance).exists():
            logger.info(f"SCORM package already exists for topic {instance.id}, skipping processing")
            return
        
        # Import parser and validators
        from scorm.parser import ScormParser
        from scorm.validators import validate_scorm_package, ScormValidationError
        
        logger.info(f"🎯 Processing SCORM package for topic {instance.id}: {instance.title}")
        
        # Simple SCORM processing - no complex validation
        logger.info(f" Simple SCORM processing for topic {instance.id}")
        
        # Open and parse the SCORM package
        try:
            instance.content_file.open('rb')
            parser = ScormParser(instance.content_file)
            package_data = parser.parse(skip_validation=True)  # Skip validation since we already did it
            instance.content_file.close()
        except Exception as parse_error:
            logger.error(f" Error parsing SCORM package for topic {instance.id}: {str(parse_error)}")
            try:
                instance.content_file.close()
            except:
                pass
            # Don't raise the exception - log the error and return to prevent topic creation failure
            logger.warning(f" SCORM processing failed for topic {instance.id} - topic will be created without SCORM package")
            return
        
        # Create ScormPackage record
        try:
            scorm_package = ScormPackage.objects.create(
                topic=instance,
                version=package_data['version'],
                identifier=package_data['identifier'],
                title=package_data.get('title', instance.title),
                description=package_data.get('description', ''),
                package_file=instance.content_file,
                extracted_path=package_data['extracted_path'],
                launch_url=package_data['launch_url'],
                manifest_data=package_data['manifest_data'],
                mastery_score=package_data.get('mastery_score')
            )
            
            logger.info(f" SCORM package created successfully for topic {instance.id}")
            logger.info(f"   📦 Package ID: {scorm_package.id}")
            logger.info(f"   📌 Version: SCORM {scorm_package.version}")
            logger.info(f"    Launch URL: {scorm_package.launch_url}")
            logger.info(f"   📂 Extracted to: {scorm_package.extracted_path}")
            logger.info(f"   🎯 Mastery Score: {scorm_package.mastery_score or 'Not set'}")
            logger.info(f"    Title: {scorm_package.title}")
            
        except Exception as create_error:
            logger.error(f" Error creating SCORM package record for topic {instance.id}: {str(create_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't raise - topic creation should still succeed
        
    except Exception as e:
        logger.error(f" Unexpected error processing SCORM package for topic {instance.id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Don't raise the exception to prevent topic creation failure
        # The topic will be created but SCORM package won't be available