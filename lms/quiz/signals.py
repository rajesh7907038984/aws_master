from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import QuizAttempt
from courses.models import Topic

# Import TopicProgress dynamically
try:
    from courses.models import TopicProgress
except ImportError:
    TopicProgress = None
from quiz.models import Quiz


@receiver(post_save, sender=QuizAttempt)
def update_topic_progress_on_quiz_completion(sender, instance, **kwargs):
    """Update topic progress when quiz attempt is completed"""
    # Only process when quiz is completed
    if not instance.is_completed or not instance.end_time:
        return
    
    try:
        # Find topics that contain this quiz
        topics = Topic.objects.filter(quiz=instance.quiz)
        
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
            
            # Update progress data with quiz info
            topic_progress.progress_data.update({
                'quiz_attempt_id': instance.id,
                'quiz_score': float(instance.score),
                'quiz_passed': instance.passed,
                'quiz_completed_at': instance.end_time.isoformat(),
                'quiz_passing_score': float(instance.quiz.passing_score) if instance.quiz.passing_score else 70.0
            })
            
            # Update scores
            topic_progress.last_score = instance.score
            if topic_progress.best_score is None or instance.score > topic_progress.best_score:
                topic_progress.best_score = instance.score
            
            # Mark as completed if quiz passed
            if instance.passed:
                if not topic_progress.completed:
                    topic_progress.completed = True
                    topic_progress.completed_at = instance.end_time
                    topic_progress.completion_method = 'auto'
                    
                    # Add completion info to progress data
                    topic_progress.progress_data['completed'] = True
                    topic_progress.progress_data['completed_at'] = instance.end_time.isoformat()
                    topic_progress.progress_data['completion_method'] = 'auto'
                    
                    # Log the completion
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Quiz completion auto-marked topic {topic.id} as complete for user {instance.user.username}")
            
            topic_progress.save()
            
            # Check if course is now completed as a result of this topic completion
            if topic_progress.completed:
                topic_progress._check_course_completion()
                
    except Exception as e:
        # Log error but don't fail the save operation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating topic progress for quiz completion: {e}")
