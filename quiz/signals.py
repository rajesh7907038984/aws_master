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
                
                # Sync quiz active time to topic progress using the model method
                # This ensures consistent logic and can be called manually if needed
                if hasattr(instance, 'sync_time_to_topic_progress'):
                    synced = instance.sync_time_to_topic_progress()
                    if synced:
                        # Reload topic_progress to get updated values
                        topic_progress.refresh_from_db()
                        logger.info(f"Synced quiz time from attempt {instance.id} to topic {topic.id} for user {instance.user.username}")
                else:
                    # Fallback to inline logic if method doesn't exist
                    quiz_time_seconds = 0
                    
                    # First, try to use active_time_seconds (preferred method - tracks actual active time)
                    if instance.active_time_seconds > 0:
                        quiz_time_seconds = instance.active_time_seconds
                    # Fallback: calculate time from start_time and end_time if active_time_seconds is 0
                    elif instance.start_time and instance.end_time:
                        time_diff = instance.end_time - instance.start_time
                        quiz_time_seconds = int(time_diff.total_seconds())
                        logger.info(f"Using fallback time calculation for quiz {instance.quiz.id}: {quiz_time_seconds}s (from start_time/end_time, active_time_seconds was 0)")
                    
                    # Only add time if we have a valid time value
                    if quiz_time_seconds > 0:
                        # Check if this attempt's time was already added to avoid double-counting
                        synced_attempts = topic_progress.progress_data.get('synced_quiz_attempts', [])
                        if instance.id not in synced_attempts:
                            # Add quiz time to total_time_spent
                            topic_progress.total_time_spent += quiz_time_seconds
                            topic_progress.progress_data['quiz_active_time_seconds'] = quiz_time_seconds
                            
                            # Track that this attempt has been synced
                            synced_attempts.append(instance.id)
                            topic_progress.progress_data['synced_quiz_attempts'] = synced_attempts
                            
                            logger.info(f"Synced {quiz_time_seconds}s from quiz attempt {instance.id} to topic {topic.id} for user {instance.user.username}")
                        else:
                            logger.info(f"Quiz attempt {instance.id} time already synced for topic {topic.id}, skipping to avoid double-counting")
                    else:
                        logger.warning(f"No valid time found for quiz attempt {instance.id} (active_time_seconds={instance.active_time_seconds}, start_time={instance.start_time}, end_time={instance.end_time})")
                
                # Determine if topic should be auto-completed
                # VAK Test and Initial Assessment auto-complete on any attempt (for classification purposes)
                # Normal quizzes only complete if passed
                should_complete = False
                completion_reason = ""
                
                if instance.quiz.is_vak_test:
                    should_complete = True
                    completion_reason = f"VAK test completed (classification quiz) - Score: {instance.score}%"
                elif instance.quiz.is_initial_assessment:
                    should_complete = True
                    completion_reason = f"Initial assessment completed (classification quiz) - Score: {instance.score}%"
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
