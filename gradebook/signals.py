"""
Signal handlers for gradebook cache invalidation
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from courses.models import TopicProgress
from scorm.models import ELearningTracking
import logging

logger = logging.getLogger(__name__)

#         
#     except Exception as e:

@receiver(post_save, sender=TopicProgress)
def invalidate_gradebook_cache_on_topic_progress_update(sender, instance, **kwargs):
    """
    Handle TopicProgress updates (cache functionality removed)
    """
    try:
        logger.info("TopicProgress {{instance.id}} updated")
        
    except Exception as e:
        logger.error("Error handling TopicProgress update: {{str(e)}}")

@receiver(post_save, sender=ELearningTracking)
def invalidate_gradebook_cache_on_scorm_tracking_update(sender, instance, **kwargs):
    """
    Handle SCORM tracking updates (cache functionality removed)
    """
    try:
        logger.info("SCORM tracking {{instance.id}} updated for user {{instance.user.id}}")
        
    except Exception as e:
        logger.error("Error handling SCORM tracking update: {{str(e)}}")
