"""
SCORM Utility Functions
Helper functions for SCORM integration
"""
import logging
from typing import Optional
from django.core.files.storage import default_storage
from .models import SCORMPackage, SCORMAttempt

logger = logging.getLogger(__name__)


def get_topic_scorm_package(topic) -> Optional[SCORMPackage]:
    """
    Get the active SCORM package for a topic
    """
    try:
        return SCORMPackage.objects.filter(
            topic=topic,
            is_active=True,
            is_processed=True
        ).first()
    except Exception as e:
        logger.error(f"Error getting SCORM package for topic: {str(e)}")
        return None


def get_user_scorm_attempt(user, package) -> Optional[SCORMAttempt]:
    """
    Get the user's latest active SCORM attempt for a package
    """
    try:
        return SCORMAttempt.objects.filter(
            user=user,
            package=package,
            is_active=True
        ).exclude(
            lesson_status__in=['completed', 'passed']
        ).order_by('-started_at').first()
    except Exception as e:
        logger.error(f"Error getting SCORM attempt: {str(e)}")
        return None


def create_scorm_attempt(user, package, topic=None) -> Optional[SCORMAttempt]:
    """
    Create a new SCORM attempt for a user
    """
    try:
        # Count existing attempts
        attempt_count = SCORMAttempt.objects.filter(
            user=user,
            package=package
        ).count()
        
        # Create new attempt
        attempt = SCORMAttempt.objects.create(
            user=user,
            package=package,
            topic=topic or package.topic,
            attempt_number=attempt_count + 1,
            cmi_data={}
        )
        
        logger.info(f"Created SCORM attempt {attempt.id} for user {user.username}")
        return attempt
    
    except Exception as e:
        logger.error(f"Error creating SCORM attempt: {str(e)}", exc_info=True)
        return None


def get_or_create_scorm_attempt(user, package, topic=None) -> Optional[SCORMAttempt]:
    """
    Get existing attempt or create a new one
    """
    # Try to get existing incomplete attempt
    attempt = get_user_scorm_attempt(user, package)
    
    if not attempt:
        # Create new attempt
        attempt = create_scorm_attempt(user, package, topic)
    
    return attempt


def is_topic_scorm_enabled(topic) -> bool:
    """
    Check if a topic has SCORM content enabled
    """
    return SCORMPackage.objects.filter(
        topic=topic,
        is_active=True,
        is_processed=True
    ).exists()


def get_scorm_launch_url(package: SCORMPackage) -> str:
    """
    Get the launch URL for a SCORM package
    """
    if not package.is_processed or not package.launch_file:
        return ""
    
    if package.extracted_path:
        try:
            base_url = default_storage.url(package.extracted_path)
            return f"{base_url}/{package.launch_file}"
        except Exception as e:
            logger.error(f"Error generating launch URL: {str(e)}")
            return ""
    
    return ""


def sync_scorm_to_topic_progress(attempt: SCORMAttempt):
    """
    Sync SCORM attempt completion to topic progress
    """
    if not attempt.topic:
        return
    
    try:
        from courses.models import TopicProgress
        
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=attempt.topic
        )
        
        # Update completion
        if attempt.is_completed():
            topic_progress.completed = True
            topic_progress.completion_date = attempt.completed_at
            
            # Update score if available
            if attempt.score_raw is not None:
                topic_progress.score = attempt.score_raw
            
            topic_progress.save()
            logger.info(f"Synced SCORM completion to topic progress: {attempt}")
    
    except Exception as e:
        logger.error(f"Error syncing SCORM to topic progress: {str(e)}")

