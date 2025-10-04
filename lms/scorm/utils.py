"""
SCORM Utility Functions
Helper functions for SCORM integration with gradebook and reports
"""
import logging
from django.db.models import Avg, Max, Count
from decimal import Decimal

logger = logging.getLogger(__name__)


def get_scorm_data_for_gradebook(user, topic):
    """
    Get SCORM attempt data formatted for gradebook display
    
    Args:
        user: User instance
        topic: Topic instance with SCORM content
        
    Returns:
        dict: SCORM data for gradebook including score, status, time spent
    """
    try:
        from .models import ScormAttempt, ScormPackage
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return None
        
        # Get all attempts for this user and package
        attempts = ScormAttempt.objects.filter(
            user=user,
            scorm_package=scorm_package
        ).order_by('-attempt_number')
        
        if not attempts.exists():
            return {
                'attempted': False,
                'score': None,
                'status': 'Not Attempted',
                'time_spent': 0,
                'attempts_count': 0
            }
        
        # Get the best attempt (highest score)
        best_attempt = attempts.order_by('-score_raw').first()
        latest_attempt = attempts.first()
        
        # Parse time from SCORM format (hhhh:mm:ss.ss) to seconds
        def parse_time(time_str):
            try:
                if not time_str:
                    return 0
                parts = time_str.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
                return 0
            except:
                return 0
        
        # Calculate total time across all attempts
        total_time = sum(parse_time(att.total_time) for att in attempts)
        
        return {
            'attempted': True,
            'score': float(best_attempt.score_raw) if best_attempt.score_raw else None,
            'max_score': float(scorm_package.mastery_score) if scorm_package.mastery_score else 100,
            'status': latest_attempt.lesson_status.title() if scorm_package.version == '1.2' else latest_attempt.completion_status.title(),
            'completion_status': latest_attempt.lesson_status if scorm_package.version == '1.2' else latest_attempt.completion_status,
            'time_spent': int(total_time),
            'attempts_count': attempts.count(),
            'last_accessed': latest_attempt.last_accessed,
            'completed_at': latest_attempt.completed_at,
            'best_attempt_number': best_attempt.attempt_number,
            'version': scorm_package.version
        }
        
    except Exception as e:
        logger.error(f"Error getting SCORM data for gradebook: {str(e)}")
        return None


def get_scorm_report_data(course=None, user=None, topic=None):
    """
    Get comprehensive SCORM report data
    
    Args:
        course: Optional Course instance to filter by
        user: Optional User instance to filter by
        topic: Optional Topic instance to filter by
        
    Returns:
        list: List of dictionaries containing SCORM attempt data
    """
    try:
        from .models import ScormAttempt, ScormPackage
        from courses.models import Topic, CourseTopic
        
        # Build query
        attempts = ScormAttempt.objects.select_related(
            'user', 
            'scorm_package',
            'scorm_package__topic'
        ).all()
        
        # Apply filters
        if user:
            attempts = attempts.filter(user=user)
        
        if topic:
            attempts = attempts.filter(scorm_package__topic=topic)
        
        if course:
            # Get topics for this course
            course_topics = CourseTopic.objects.filter(course=course).values_list('topic_id', flat=True)
            attempts = attempts.filter(scorm_package__topic_id__in=course_topics)
        
        # Format data
        report_data = []
        for attempt in attempts:
            # Parse time
            try:
                parts = attempt.total_time.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    time_seconds = hours * 3600 + minutes * 60 + seconds
                else:
                    time_seconds = 0
            except:
                time_seconds = 0
            
            report_data.append({
                'user': attempt.user,
                'user_name': attempt.user.get_full_name() or attempt.user.username,
                'user_email': attempt.user.email,
                'topic': attempt.scorm_package.topic,
                'topic_title': attempt.scorm_package.topic.title,
                'scorm_title': attempt.scorm_package.title,
                'scorm_version': attempt.scorm_package.version,
                'attempt_number': attempt.attempt_number,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_max': float(attempt.score_max) if attempt.score_max else 100,
                'score_percentage': float(attempt.score_raw / attempt.score_max * 100) if attempt.score_raw and attempt.score_max else None,
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'time_spent': time_seconds,
                'time_spent_formatted': format_time(time_seconds),
                'started_at': attempt.started_at,
                'last_accessed': attempt.last_accessed,
                'completed_at': attempt.completed_at,
                'is_passed': attempt.is_passed(),
            })
        
        return report_data
        
    except Exception as e:
        logger.error(f"Error getting SCORM report data: {str(e)}")
        return []


def get_scorm_course_statistics(course):
    """
    Get aggregated SCORM statistics for a course
    
    Args:
        course: Course instance
        
    Returns:
        dict: Aggregated statistics
    """
    try:
        from .models import ScormAttempt, ScormPackage
        from courses.models import CourseTopic
        
        # Get all SCORM topics in the course
        course_topics = CourseTopic.objects.filter(
            course=course,
            topic__content_type='SCORM'
        ).values_list('topic_id', flat=True)
        
        if not course_topics:
            return {
                'total_scorm_topics': 0,
                'total_attempts': 0,
                'avg_score': None,
                'completion_rate': 0,
            }
        
        # Get all attempts for these topics
        attempts = ScormAttempt.objects.filter(
            scorm_package__topic_id__in=course_topics
        )
        
        total_attempts = attempts.count()
        completed_attempts = attempts.filter(
            lesson_status__in=['completed', 'passed']
        ).count()
        
        # Calculate average score
        avg_score = attempts.filter(score_raw__isnull=False).aggregate(
            avg=Avg('score_raw')
        )['avg']
        
        return {
            'total_scorm_topics': len(course_topics),
            'total_attempts': total_attempts,
            'avg_score': float(avg_score) if avg_score else None,
            'completion_rate': (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0,
            'unique_users': attempts.values('user').distinct().count(),
        }
        
    except Exception as e:
        logger.error(f"Error getting SCORM course statistics: {str(e)}")
        return {}


def format_time(seconds):
    """Format seconds to human readable time"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

