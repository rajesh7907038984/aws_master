from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Comment
from courses.models import Topic

# Import TopicProgress dynamically
try:
    from courses.models import TopicProgress
except ImportError:
    TopicProgress = None
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Comment)
def update_topic_progress_on_discussion_participation(sender, instance, **kwargs):
    """Update topic progress when user participates in a discussion by commenting"""
    # Only process when comment is created (not updated)
    if kwargs.get('created', False):
        try:
            # Import CourseTopic to get course context
            from courses.models import CourseTopic
            
            # Find topics that contain this discussion
            topics = Topic.objects.filter(discussion=instance.discussion)
            
            for topic in topics:
                # Get all courses this topic belongs to
                course_topics = CourseTopic.objects.filter(topic=topic).select_related('course')
                
                # Update progress for each course-topic combination
                for course_topic in course_topics:
                    # Get or create topic progress
                    topic_progress, created = TopicProgress.objects.get_or_create(
                        user=instance.user,
                        topic=topic,
                        course=course_topic.course,
                        defaults={
                            'completed': False,
                            'progress_data': {}
                        }
                    )
                    
                    # Initialize progress_data if not exists
                    if not topic_progress.progress_data:
                        topic_progress.progress_data = {}
                    
                    # Update progress data with discussion info
                    topic_progress.progress_data.update({
                        'discussion_comment_id': instance.id,
                        'discussion_participated_at': timezone.now().isoformat(),
                        'discussion_title': instance.discussion.title,
                        'comment_text': instance.content[:100] + '...' if len(instance.content) > 100 else instance.content
                    })
                    
                    # Add estimated time for discussion participation
                    # Estimate: 2 minutes (120 seconds) per comment as base time
                    # Add additional time based on comment length (1 second per 10 characters, max 5 minutes)
                    base_time = 120  # 2 minutes in seconds
                    content_length_time = min(len(instance.content) // 10, 300)  # Max 5 additional minutes
                    estimated_time = base_time + content_length_time
                    
                    topic_progress.total_time_spent += estimated_time
                    topic_progress.progress_data['discussion_estimated_time_seconds'] = estimated_time
                    
                    # Mark as completed when user participates in discussion
                    if not topic_progress.completed:
                        topic_progress.mark_complete('auto')
                        
                        # Add discussion-specific completion info to progress data
                        topic_progress.progress_data.update({
                            'discussion_completed': True,
                            'discussion_completed_at': timezone.now().isoformat(),
                            'discussion_completion_method': 'auto'
                        })
                        
                        # Log the completion
                        logger.info(f"Discussion participation auto-marked topic {topic.id} as complete for user {instance.user.username}")
                    
                    topic_progress.save()
                    
                    # Check if course is now completed as a result of this topic completion
                    if topic_progress.completed:
                        topic_progress._check_course_completion()
                    
        except Exception as e:
            # Log error but don't fail the save operation
            logger.error(f"Error updating topic progress for discussion participation: {e}")
