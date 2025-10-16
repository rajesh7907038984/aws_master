"""
Signal handlers for gradebook cache invalidation
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from courses.models import TopicProgress
from scorm.models import ELearningTracking
import logging

logger = logging.getLogger(__name__)

#         
#     except Exception as e:

@receiver(post_save, sender=TopicProgress)
def invalidate_gradebook_cache_on_topic_progress_update(sender, instance, **kwargs):
    """
    Clear gradebook cache when TopicProgress is updated
    """
    try:
        # Clear all gradebook caches - topics are linked to courses via M2M so clear all
        cache.clear()
        logger.info(f"Cleared all caches after TopicProgress {instance.id} update")
        
    except Exception as e:
        logger.error(f"Error clearing gradebook cache after TopicProgress update: {str(e)}")

@receiver(post_save, sender=ELearningTracking)
def invalidate_gradebook_cache_on_scorm_tracking_update(sender, instance, **kwargs):
    """
    Clear gradebook cache when SCORM tracking is updated
    """
    try:
        # Clear all gradebook caches - SCORM packages are linked to courses via topics
        cache.clear()
        logger.info(f"Cleared all caches after SCORM tracking {instance.id} update for user {instance.user.id}")
        
    except Exception as e:
        logger.error(f"Error clearing gradebook cache after SCORM tracking update: {str(e)}")
