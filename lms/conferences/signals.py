from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ConferenceParticipant
from courses.models import TopicProgress, Topic
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ConferenceParticipant)
def update_topic_progress_on_conference_participation(sender, instance, **kwargs):
    """Update topic progress when user participates in a conference"""
    # Only process when user has joined the meeting or is active
    if instance.participation_status not in ['joined_meeting', 'active_in_meeting', 'meeting_ended', 'sync_completed']:
        return
    
    # Skip if no user (guest participants)
    if not instance.user:
        return
    
    try:
        # Find topics that contain this conference
        topics = Topic.objects.filter(conference=instance.conference)
        
        for topic in topics:
            # Get or create topic progress
            topic_progress, created = TopicProgress.objects.get_or_create(
                user=instance.user,
                topic=topic,
                defaults={
                    'completed': False,
                    'progress_data': {}
                }
            )
            
            # Initialize progress_data if not exists
            if not topic_progress.progress_data:
                topic_progress.progress_data = {}
            
            # Update progress data with conference info
            topic_progress.progress_data.update({
                'conference_participant_id': instance.id,
                'conference_participation_status': instance.participation_status,
                'conference_join_method': instance.join_method,
                'conference_participated_at': timezone.now().isoformat(),
                'conference_title': instance.conference.title
            })
            
            # Mark as completed when user has joined the meeting or is active
            if instance.participation_status in ['joined_meeting', 'active_in_meeting', 'meeting_ended', 'sync_completed']:
                if not topic_progress.completed:
                    topic_progress.mark_complete('auto')
                    
                    # Add conference-specific completion info to progress data
                    topic_progress.progress_data.update({
                        'conference_completed': True,
                        'conference_completed_at': timezone.now().isoformat(),
                        'conference_completion_method': 'auto'
                    })
                    
                    # Log the completion
                    logger.info(f"Conference participation auto-marked topic {topic.id} as complete for user {instance.user.username}")
            
            topic_progress.save()
            
            # Check if course is now completed as a result of this topic completion
            if topic_progress.completed:
                topic_progress._check_course_completion()
                
    except Exception as e:
        # Log error but don't fail the save operation
        logger.error(f"Error updating topic progress for conference participation: {e}")
