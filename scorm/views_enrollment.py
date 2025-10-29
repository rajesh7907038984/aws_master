"""
Enhanced SCORM progress tracking with proper enrollment and attempt models
This replaces/augments the basic progress tracking in courses/views.py
"""
import json
import logging
import uuid
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction

from courses.models import Topic, TopicProgress
from scorm.models import ScormPackage, ScormEnrollment, ScormAttempt
from core.utils.type_guards import safe_get_float, safe_get_int, safe_get_string
from scorm.utils import parse_scorm_time

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def update_scorm_progress_with_enrollment(request, topic_id):
    """
    Enhanced SCORM progress update that:
    1. Creates/gets enrollment
    2. Creates/gets current attempt
    3. Stores complete CMI data in attempt
    4. Updates TopicProgress for backward compatibility
    5. Returns enrollment/attempt info
    """
    try:
        # Get topic and validate
        topic = Topic.objects.select_related('scorm').get(id=topic_id)
        
        if topic.content_type != 'SCORM' or not topic.scorm:
            return JsonResponse({'error': 'This topic is not SCORM content'}, status=400)
        
        package = topic.scorm
        
        # Parse request data
        data = json.loads(request.body)
        
        # Extract metadata
        session_id_str = safe_get_string(data, 'session_id')
        seq = safe_get_int(data, 'seq', 0)
        client_timestamp = safe_get_string(data, 'client_timestamp')
        scorm_version = safe_get_string(data, 'scorm_version', package.version or '1.2')
        raw_cmi_data = data.get('raw', {})
        
        # Parse or generate session ID
        if session_id_str:
            try:
                session_uuid = uuid.UUID(session_id_str)
            except ValueError:
                session_uuid = uuid.uuid4()
        else:
            session_uuid = uuid.uuid4()
        
        with transaction.atomic():
            # 1. Get or create enrollment
            enrollment, enrollment_created = ScormEnrollment.objects.get_or_create(
                user=request.user,
                topic=topic,
                defaults={
                    'package': package,
                    'enrollment_status': 'enrolled'
                }
            )
            
            if enrollment_created:
                logger.info(
                    f"Created SCORM enrollment: user={request.user.username}, "
                    f"topic_id={topic_id}, package_id={package.id}"
                )
            
            # 2. Get or create current attempt
            # Check if we have an existing attempt with this session_id
            attempt = ScormAttempt.objects.filter(
                session_id=session_uuid,
                enrollment=enrollment
            ).first()
            
            if not attempt:
                # Check for an incomplete attempt to resume
                attempt = enrollment.get_current_attempt()
                
                if not attempt:
                    # Create new attempt
                    attempt = enrollment.create_new_attempt()
                    attempt.session_id = session_uuid
                    attempt.scorm_version = scorm_version
                    attempt.save()
                    logger.info(
                        f"Created SCORM attempt #{attempt.attempt_number}: "
                        f"user={request.user.username}, topic_id={topic_id}, "
                        f"session_id={session_uuid}"
                    )
                else:
                    # Resume existing attempt, update session_id
                    attempt.session_id = session_uuid
                    attempt.save()
            
            # 3. Idempotency check
            if seq <= attempt.last_sequence_number:
                logger.info(
                    f"Ignoring out-of-order/duplicate SCORM update: "
                    f"session={session_uuid}, seq={seq} <= current_seq={attempt.last_sequence_number}"
                )
                return JsonResponse({
                    'ok': True,
                    'ignored': True,
                    'reason': 'out_of_order_or_duplicate',
                    'enrollment_id': enrollment.id,
                    'attempt_id': attempt.id,
                    'attempt_number': attempt.attempt_number
                })
            
            # Update sequence number
            attempt.last_sequence_number = seq
            
            # 4. Update attempt with complete CMI data
            attempt.update_from_cmi_data(raw_cmi_data, scorm_version)
            
            # 5. Update TopicProgress for backward compatibility
            topic_progress, _ = TopicProgress.objects.get_or_create(
                user=request.user,
                topic=topic
            )
            
            # Sync key fields to TopicProgress
            if attempt.score_raw is not None:
                topic_progress.last_score = attempt.score_raw
                topic_progress.best_score = enrollment.best_score
            
            topic_progress.total_time_spent = attempt.total_time_seconds
            topic_progress.completed = attempt.completed
            
            if not topic_progress.progress_data:
                topic_progress.progress_data = {}
            
            # Store summary in progress_data for dashboard/reporting
            topic_progress.progress_data.update({
                'scorm_enrollment_id': enrollment.id,
                'scorm_attempt_id': attempt.id,
                'scorm_attempt_number': attempt.attempt_number,
                'scorm_completion_status': attempt.completion_status,
                'scorm_success_status': attempt.success_status,
                'scorm_score': float(attempt.score_raw) if attempt.score_raw else None,
                'scorm_total_time': attempt.total_time,
            })
            
            # Update bookmark for resume
            if not topic_progress.bookmark:
                topic_progress.bookmark = {}
            
            if attempt.lesson_location:
                topic_progress.bookmark['lesson_location'] = attempt.lesson_location
            if attempt.suspend_data:
                topic_progress.bookmark['suspend_data'] = attempt.suspend_data
            
            topic_progress.save()
            
            # 6. Build response
            response_data = {
                'ok': True,
                'saved_at': timezone.now().isoformat(),
                'enrollment': {
                    'id': enrollment.id,
                    'status': enrollment.enrollment_status,
                    'total_attempts': enrollment.total_attempts,
                    'best_score': float(enrollment.best_score) if enrollment.best_score else None,
                },
                'attempt': {
                    'id': attempt.id,
                    'number': attempt.attempt_number,
                    'session_id': str(attempt.session_id),
                    'completed': attempt.completed,
                    'terminated': attempt.terminated,
                    'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                    'completion_status': attempt.completion_status,
                    'success_status': attempt.success_status,
                    'total_time': attempt.total_time,
                    'commit_count': attempt.commit_count,
                },
                'progress': {
                    'completed': topic_progress.completed,
                    'score': float(topic_progress.last_score) if topic_progress.last_score else None,
                    'best_score': float(topic_progress.best_score) if topic_progress.best_score else None,
                }
            }
            
            logger.info(
                f"SCORM progress updated: user={request.user.username}, "
                f"topic_id={topic_id}, attempt={attempt.attempt_number}, "
                f"seq={seq}, completed={attempt.completed}"
            )
            
            return JsonResponse(response_data)
        
    except Topic.DoesNotExist:
        logger.error(f"Topic {topic_id} not found")
        return JsonResponse({'error': 'Topic not found'}, status=404)
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in SCORM progress request: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    
    except Exception as e:
        logger.error(f"Error updating SCORM progress: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

