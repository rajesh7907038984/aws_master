"""
Auto-sync Views for SCORM
Dynamic API endpoints that trigger automatic score synchronization
"""
import logging
from datetime import timedelta
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .dynamic_score_processor import auto_process_scorm_score
from .real_time_validator import ScormScoreValidator
from .models import ScormAttempt
from .score_sync_service import ScormScoreSyncService
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


def _safe_str(value):
    """Safely convert any value to string, handling None and non-string types"""
    if value is None or value == '':
        return ''
    try:
        return str(value).strip()
    except:
        return ''


def _safe_len(value):
    """Safely get length of a value, handling None"""
    if value is None:
        return 0
    try:
        return len(value)
    except:
        return 0


@login_required
@require_http_methods(["POST"])
def sync_on_exit(request):
    """
    Sync SCORM data to TopicProgress when user exits SCORM content
    Called by the "Save & Exit" button to ensure all quiz state and scores are saved
    ENHANCED: Comprehensive data preservation with transaction safety and robust error handling
    """
    attempt_id = None
    try:
        attempt_id = request.POST.get('attempt_id')
        
        if not attempt_id:
            logger.warning("sync_on_exit called without attempt_id")
            return JsonResponse({
                'success': False,
                'error': 'No attempt_id provided'
            }, status=400)
        
        # Use atomic transaction to ensure data consistency
        from django.db import transaction
        from decimal import Decimal, InvalidOperation
        
        # First, try to get the attempt without locking to check if it exists
        try:
            attempt_check = ScormAttempt.objects.filter(
                id=attempt_id,
                user=request.user
            ).select_related('scorm_package__topic').first()
            
            if not attempt_check:
                logger.warning(f"Attempt {attempt_id} not found or unauthorized for user {request.user.id}")
                return JsonResponse({
                    'success': False,
                    'error': 'Attempt not found or unauthorized'
                }, status=404)
        except Exception as e:
            logger.error(f"Error checking attempt {attempt_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Database error when checking attempt'
            }, status=500)
        
        # Now use transaction with locking
        with transaction.atomic():
            # Get the attempt with select_for_update to prevent race conditions
            # Use nowait=False to wait for lock instead of failing immediately
            try:
                attempt = ScormAttempt.objects.select_for_update(nowait=False).filter(
                    id=attempt_id,
                    user=request.user
                ).select_related('scorm_package__topic').first()
                
                if not attempt:
                    return JsonResponse({
                        'success': False,
                        'error': 'Attempt not found or unauthorized'
                    }, status=404)
            except Exception as e:
                logger.error(f"Error acquiring lock for attempt {attempt_id}: {str(e)}")
                # Return success anyway to prevent user frustration - data is likely already saved
                return JsonResponse({
                    'success': True,
                    'synced': False,
                    'message': 'Lock acquisition failed but data may already be saved',
                    'warning': 'concurrent_access'
                })
            
            # Log current state for debugging
            logger.info(f"🔄 Exit sync for attempt {attempt_id}")
            logger.info(f"   Status: {attempt.lesson_status}")
            logger.info(f"   Completion Status: {attempt.completion_status}")
            logger.info(f"   Success Status: {attempt.success_status}")
            logger.info(f"   Score Raw: {attempt.score_raw}")
            logger.info(f"   Score Max: {attempt.score_max}")
            logger.info(f"   Score Scaled: {attempt.score_scaled}")
            logger.info(f"   Progress: {attempt.progress_percentage}%")
            logger.info(f"   Suspend data: {_safe_len(attempt.suspend_data)} chars")
            logger.info(f"   Bookmark: {attempt.lesson_location[:50] if attempt.lesson_location else 'None'}")
            logger.info(f"   Completed Slides: {_safe_len(attempt.completed_slides)}")
            logger.info(f"   Total Slides: {attempt.total_slides}")
            logger.info(f"   CMI Data Keys: {list(attempt.cmi_data.keys()) if attempt.cmi_data else 'None'}")
            
            # CRITICAL: Extract and sync all tracking data from CMI data with safe extraction
            if attempt.cmi_data and isinstance(attempt.cmi_data, dict):
                try:
                    version = attempt.scorm_package.version if attempt.scorm_package else '1.2'
                    
                    # Extract score from CMI if not in model
                    if not attempt.score_raw:
                        score_key = 'cmi.core.score.raw' if version == '1.2' else 'cmi.score.raw'
                        cmi_score = attempt.cmi_data.get(score_key)
                        score_str = _safe_str(cmi_score)
                        if score_str:
                            try:
                                attempt.score_raw = Decimal(score_str)
                                logger.info(f"   ✅ Extracted score from CMI: {attempt.score_raw}")
                            except (InvalidOperation, ValueError) as e:
                                logger.warning(f"   ⚠️ Could not parse score '{score_str}': {e}")
                    
                    # Extract status from CMI if not in model
                    if attempt.lesson_status in ['not_attempted', 'not attempted', 'unknown']:
                        status_key = 'cmi.core.lesson_status' if version == '1.2' else 'cmi.completion_status'
                        cmi_status = attempt.cmi_data.get(status_key)
                        status_str = _safe_str(cmi_status)
                        if status_str and status_str not in ['not_attempted', 'not attempted']:
                            attempt.lesson_status = status_str.replace(' ', '_')
                            logger.info(f"   ✅ Extracted status from CMI: {attempt.lesson_status}")
                    
                    # Extract suspend data from CMI if not in model
                    if not attempt.suspend_data or _safe_len(attempt.suspend_data) == 0:
                        cmi_suspend = attempt.cmi_data.get('cmi.suspend_data')
                        suspend_str = _safe_str(cmi_suspend)
                        if suspend_str:
                            attempt.suspend_data = suspend_str
                            logger.info(f"   ✅ Extracted suspend data from CMI: {_safe_len(attempt.suspend_data)} chars")
                    
                    # Extract bookmark from CMI if not in model
                    if not attempt.lesson_location or _safe_len(attempt.lesson_location) == 0:
                        location_key = 'cmi.core.lesson_location' if version == '1.2' else 'cmi.location'
                        cmi_location = attempt.cmi_data.get(location_key)
                        location_str = _safe_str(cmi_location)
                        if location_str:
                            attempt.lesson_location = location_str[:1000]  # Respect field limit
                            logger.info(f"   ✅ Extracted bookmark from CMI: {attempt.lesson_location[:50]}")
                except Exception as e:
                    logger.error(f"   ⚠️ Error extracting CMI data: {str(e)}")
                    # Continue anyway - don't let CMI extraction errors block save
            
            # CRITICAL: Ensure all JSON fields have valid values (never None)
            try:
                if attempt.completed_slides is None:
                    attempt.completed_slides = []
                if attempt.navigation_history is None:
                    attempt.navigation_history = []
                if attempt.detailed_tracking is None:
                    attempt.detailed_tracking = {}
                if attempt.session_data is None:
                    attempt.session_data = {}
                if attempt.cmi_data is None:
                    attempt.cmi_data = {}
            except Exception as e:
                logger.error(f"   ⚠️ Error setting JSON defaults: {str(e)}")
            
            # Update last accessed timestamp
            attempt.last_accessed = timezone.now()
            
            # CRITICAL: Save ALL tracking data to database
            # Use update_fields to be explicit about what we're saving
            fields_to_update = [
                'lesson_status',
                'completion_status',
                'success_status',
                'score_raw',
                'score_max',
                'score_min',
                'score_scaled',
                'suspend_data',
                'lesson_location',
                'progress_percentage',
                'completed_slides',
                'total_slides',
                'navigation_history',
                'detailed_tracking',
                'session_data',
                'cmi_data',
                'last_accessed',
                'time_spent_seconds',
                'total_time',
                'session_time'
            ]
            
            try:
                attempt.save(update_fields=fields_to_update)
                logger.info(f"   ✅ All tracking data saved to database")
            except Exception as e:
                logger.error(f"   ❌ Error saving attempt: {str(e)}")
                # Re-raise to rollback transaction
                raise
            
            # Refresh from database to ensure we have the saved data
            try:
                attempt.refresh_from_db()
            except Exception as e:
                logger.warning(f"   ⚠️ Could not refresh from DB: {str(e)}")
            
            # Verify the save was successful
            logger.info(f"   ✅ Verification after save:")
            logger.info(f"      - Suspend data length: {_safe_len(attempt.suspend_data)}")
            logger.info(f"      - Bookmark: {attempt.lesson_location[:50] if attempt.lesson_location else 'None'}")
            logger.info(f"      - Score: {attempt.score_raw}")
            logger.info(f"      - Status: {attempt.lesson_status}")
            logger.info(f"      - Progress: {attempt.progress_percentage}%")
        
        # Sync the attempt data to TopicProgress (outside transaction for better performance)
        sync_result = False
        try:
            sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
            logger.info(f"   Exit sync to TopicProgress: {'✅ Success' if sync_result else '⚠️ Skipped'}")
        except Exception as e:
            logger.error(f"   ⚠️ Error syncing to TopicProgress: {str(e)}")
            # Don't fail the entire operation if sync fails
        
        # Clear relevant caches to ensure fresh data using centralized cache manager
        try:
            from .cache_utils import ScormCacheManager
            if attempt.scorm_package and attempt.scorm_package.topic:
                topic = attempt.scorm_package.topic
                # Get course IDs for this topic
                from courses.models import CourseTopic
                course_ids = list(CourseTopic.objects.filter(topic=topic).values_list('course_id', flat=True))
                
                # Use centralized cache invalidation
                ScormCacheManager.invalidate_for_attempt(
                    attempt_id=attempt.id,
                    user_id=request.user.id,
                    topic_id=topic.id,
                    course_ids=course_ids
                )
        except Exception as e:
            logger.error(f"   ⚠️ Error clearing caches: {str(e)}")
            # Don't fail the entire operation if cache clearing fails
        
        return JsonResponse({
            'success': True,
            'synced': sync_result,
            'message': 'SCORM data synchronized successfully' if sync_result else 'Data saved but not synced to gradebook',
            'attempt_id': attempt_id,
            'suspend_data_length': _safe_len(attempt.suspend_data),
            'bookmark_length': _safe_len(attempt.lesson_location),
            'score': float(attempt.score_raw) if attempt.score_raw else None,
            'status': attempt.lesson_status,
            'progress': float(attempt.progress_percentage) if attempt.progress_percentage else 0,
            'completed_slides': _safe_len(attempt.completed_slides),
            'total_slides': attempt.total_slides if attempt.total_slides else 0
        })
        
    except Exception as e:
        logger.error(f"❌ Exit sync error for attempt {attempt_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return a more graceful error response
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while saving your progress. Please try again.',
            'technical_error': str(e),
            'attempt_id': attempt_id
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
