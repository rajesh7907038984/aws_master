"""
Auto-sync Views for SCORM
Dynamic API endpoints that trigger automatic score synchronization
"""
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .dynamic_score_processor import auto_process_scorm_score
from .real_time_validator import ScormScoreValidator
from .models import ScormAttempt
from courses.models import TopicProgress, CourseTopic

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def trigger_score_sync(request):
    """
    API endpoint to trigger score synchronization for the current user
    Called automatically by frontend when user visits gradebook or course views
    """
    try:
        user = request.user
        
        # Find recent SCORM attempts that might need processing
        since = timezone.now() - timedelta(hours=24)
        recent_attempts = ScormAttempt.objects.filter(
            user=user,
            last_accessed__gte=since,
            suspend_data__isnull=False
        ).exclude(suspend_data='')
        
        processed = 0
        fixed = 0
        
        for attempt in recent_attempts:
            # Quick check if this attempt needs processing
            needs_processing = (
                (attempt.suspend_data and len(attempt.suspend_data) > 50 and not attempt.score_raw) or
                (attempt.score_raw and attempt.lesson_status == 'not_attempted')
            )
            
            if needs_processing:
                processed += 1
                if auto_process_scorm_score(attempt):
                    fixed += 1
        
        return JsonResponse({
            'success': True,
            'processed': processed,
            'fixed': fixed,
            'message': f'Processed {processed} attempts, fixed {fixed} issues'
        })
        
    except Exception as e:
        logger.error(f"Score sync trigger error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def check_scorm_health(request):
    """
    Health check endpoint for SCORM score synchronization
    Returns status of user's SCORM attempts
    """
    try:
        user = request.user
        
        # Get user's SCORM attempts from last week
        since = timezone.now() - timedelta(days=7)
        attempts = ScormAttempt.objects.filter(
            user=user,
            last_accessed__gte=since
        ).select_related('scorm_package__topic')
        
        health_data = {
            'total_attempts': attempts.count(),
            'completed_attempts': attempts.filter(lesson_status__in=['completed', 'passed']).count(),
            'attempts_with_scores': attempts.filter(score_raw__isnull=False).count(),
            'sync_issues': 0,
            'last_check': timezone.now().isoformat()
        }
        
        # Check for sync issues
        for attempt in attempts:
            if attempt.score_raw:
                # Check if TopicProgress is in sync
                topic_progress = TopicProgress.objects.filter(
                    user=user,
                    topic=attempt.scorm_package.topic
                ).first()
                
                if not topic_progress or topic_progress.last_score != float(attempt.score_raw):
                    health_data['sync_issues'] += 1
        
        # Determine overall health
        if health_data['sync_issues'] == 0:
            health_data['status'] = 'healthy'
        elif health_data['sync_issues'] < 3:
            health_data['status'] = 'minor_issues'
        else:
            health_data['status'] = 'needs_attention'
        
        return JsonResponse({
            'success': True,
            'health': health_data
        })
        
    except Exception as e:
        logger.error(f"SCORM health check error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def auto_fix_course_scores(request, course_id):
    """
    Endpoint to automatically fix all SCORM scores in a specific course
    Can be called by instructors or administrators
    """
    try:
        # Check permissions (instructor/admin only)
        if not (hasattr(request.user, 'role') and 
                request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']):
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
        # Get all SCORM topics in this course
        course_topics = CourseTopic.objects.filter(
            course_id=course_id,
            topic__scorm_package__isnull=False
        ).select_related('topic__scorm_package')
        
        total_attempts = 0
        processed = 0
        fixed = 0
        
        for course_topic in course_topics:
            topic = course_topic.topic
            
            # Get all attempts for this topic
            topic_attempts = ScormAttempt.objects.filter(
                scorm_package__topic=topic,
                last_accessed__gte=timezone.now() - timedelta(days=30)  # Last 30 days
            )
            
            total_attempts += topic_attempts.count()
            
            for attempt in topic_attempts:
                # Check if needs processing
                if ((attempt.suspend_data and len(attempt.suspend_data) > 50) and
                    (not attempt.score_raw or attempt.lesson_status == 'not_attempted')):
                    
                    processed += 1
                    if auto_process_scorm_score(attempt):
                        fixed += 1
        
        # Clear course-related caches
        from django.core.cache import cache
        cache.delete_pattern(f'course_{course_id}_*')
        cache.delete_pattern(f'gradebook_{course_id}_*')
        
        logger.info(f"Course {course_id} auto-fix: {total_attempts} total, {processed} processed, {fixed} fixed")
        
        return JsonResponse({
            'success': True,
            'course_id': course_id,
            'total_attempts': total_attempts,
            'processed': processed,
            'fixed': fixed,
            'message': f'Auto-fixed {fixed} SCORM score issues in course'
        })
        
    except Exception as e:
        logger.error(f"Course auto-fix error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
