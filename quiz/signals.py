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
    import logging
    logger = logging.getLogger(__name__)
    
    # Only process when quiz is completed
    if not instance.is_completed or not instance.end_time:
        return
    
    # Log quiz completion details
    logger.info(f"Processing quiz completion signal - Quiz: {instance.quiz.title}, User: {instance.user.username}, Score: {instance.score}%, Passed: {instance.passed}")
    
    try:
        # Find topics that contain this quiz
        topics = Topic.objects.filter(quiz=instance.quiz)
        
        if not topics.exists():
            logger.warning(f"No topics found for quiz {instance.quiz.id} ({instance.quiz.title})")
        
        # Import CourseTopic to get course context
        from courses.models import CourseTopic
        
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
                
                # Sync quiz active time to topic progress
                if instance.active_time_seconds > 0:
                    # Add quiz time to total_time_spent
                    topic_progress.total_time_spent += instance.active_time_seconds
                    topic_progress.progress_data['quiz_active_time_seconds'] = instance.active_time_seconds
                
                # Determine if topic should be auto-completed
                # VAK Tests and Initial Assessments complete on any attempt (for classification purposes)
                # Regular quizzes only complete if passed
                should_complete = False
                completion_reason = ""
                
                if instance.quiz.is_vak_test:
                    should_complete = True
                    completion_reason = "VAK test completed (classification quiz)"
                elif instance.quiz.is_initial_assessment:
                    should_complete = True
                    completion_reason = "Initial assessment completed (classification quiz)"
                elif instance.passed:
                    should_complete = True
                    completion_reason = f"Quiz passed with {instance.score}%"
                else:
                    completion_reason = f"Quiz not passed (score: {instance.score}%, required: {instance.quiz.passing_score}%)"
                
                # Mark as completed if conditions met
                if should_complete:
                    if not topic_progress.completed:
                        topic_progress.completed = True
                        topic_progress.completed_at = instance.end_time
                        topic_progress.completion_method = 'auto'
                        
                        # Add completion info to progress data
                        topic_progress.progress_data['completed'] = True
                        topic_progress.progress_data['completed_at'] = instance.end_time.isoformat()
                        topic_progress.progress_data['completion_method'] = 'auto'
                        
                        # Log the completion
                        logger.info(f"✓ Quiz completion auto-marked topic {topic.id} ({topic.title}) as complete for user {instance.user.username} - Reason: {completion_reason}")
                    else:
                        logger.info(f"Topic {topic.id} ({topic.title}) already marked as completed for user {instance.user.username}")
                else:
                    logger.info(f"Topic {topic.id} not auto-completed for user {instance.user.username} - Reason: {completion_reason}")
                
                topic_progress.save()
                
                # Check if course is now completed as a result of this topic completion
                if topic_progress.completed:
                    topic_progress._check_course_completion()
                
    except Exception as e:
        # Log error but don't fail the save operation
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating topic progress for quiz completion: {e}")
