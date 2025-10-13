"""
Rise 360 SCORM View Handler
Clean, focused implementation for Rise 360 packages only
"""
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .models import ScormPackage, ScormAttempt
from courses.models import Topic

logger = logging.getLogger(__name__)


@login_required
def scorm_view_rise360(request, topic_id):
    """
    Rise 360 SCORM content viewer
    Handles Rise 360 packages with lesson bookmark navigation
    """
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has permission to access this topic's course
    if not topic.user_has_access(request.user):
        messages.error(request, "You need to be enrolled in this course to access the SCORM content.")
        try:
            from courses.models import CourseTopic
            course_topic = CourseTopic.objects.filter(topic=topic).first()
            if course_topic:
                return redirect('courses:course_view', course_id=course_topic.course.id)
        except Exception:
            pass
        return redirect('courses:course_list')
    
    # Check if topic has SCORM package
    try:
        scorm_package = topic.scorm_package
    except ScormPackage.DoesNotExist:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Check if SCORM package has extracted content path
    if not scorm_package.extracted_path or not scorm_package.launch_url:
        messages.error(request, "SCORM content configuration is incomplete. Please contact your administrator.")
        logger.error(f"SCORM package missing extracted_path or launch_url for topic {topic_id}, package {scorm_package.id}")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Check for preview mode
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    # Allow preview mode only for instructors/admins
    if preview_mode and not is_instructor_or_admin:
        messages.error(request, "Preview mode is only available for instructors and administrators.")
        preview_mode = False
    
    # Handle attempt creation/retrieval
    attempt = None
    attempt_id = None
    
    if preview_mode:
        # Preview mode: Create temporary attempt object
        import uuid
        attempt_id = f"preview_{uuid.uuid4()}"
        attempt = type('PreviewAttempt', (), {
            'id': attempt_id,
            'user': request.user,
            'scorm_package': scorm_package,
            'attempt_number': 1,
            'lesson_status': 'not_attempted',
            'completion_status': 'incomplete',
            'success_status': 'unknown',
            'score_raw': None,
            'score_max': 100,
            'score_min': 0,
            'score_scaled': None,
            'total_time': '0000:00:00.00',
            'session_time': '0000:00:00.00',
            'lesson_location': '',
            'suspend_data': '',
            'entry': 'ab-initio',
            'exit_mode': '',
            'cmi_data': {},
            'started_at': timezone.now(),
            'last_accessed': timezone.now(),
            'completed_at': None,
            'is_preview': True,
        })()
        
        # Store preview attempt in session for API access
        request.session[f'scorm_preview_{attempt_id}'] = {
            'id': attempt_id,
            'user_id': request.user.id,
            'scorm_package_id': scorm_package.id,
            'is_preview': True,
            'created_at': timezone.now().isoformat(),
        }
        
        logger.info(f"Created preview attempt {attempt_id} for user {request.user.username} on topic {topic_id}")
    else:
        # Normal mode: Get or create actual database attempt for user tracking
        from django.db import transaction
        
        with transaction.atomic():
            # Lock the rows to prevent concurrent creation
            last_attempt = ScormAttempt.objects.select_for_update().filter(
                user=request.user,
                scorm_package=scorm_package
            ).order_by('-attempt_number').first()
            
            if last_attempt:
                # CRITICAL FIX: Always resume existing attempt to preserve progress and location
                attempt = last_attempt
                logger.info(f"Rise 360: Continuing existing attempt {attempt.attempt_number} for user {request.user.username}")
            else:
                # Create first attempt only if no previous attempt exists
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
                )
                logger.info(f"Rise 360: Created new attempt {attempt.attempt_number} for user {request.user.username}")
        
        attempt_id = attempt.id
        attempt.is_preview = False
        
        # Refresh attempt data from database to get latest bookmark/suspend data
        attempt.refresh_from_db()
        
        # Set entry mode to 'resume' if there's existing progress/bookmark data
        has_bookmark = bool(attempt.lesson_location and len(attempt.lesson_location) > 0)
        has_suspend_data = bool(attempt.suspend_data and len(attempt.suspend_data) > 0)
        has_progress = attempt.lesson_status not in ['not_attempted', 'not attempted']
        
        if has_bookmark or has_suspend_data or has_progress:
            attempt.entry = 'resume'
            logger.info(f"Rise 360: Setting entry='resume' (bookmark={has_bookmark}, suspend_data={has_suspend_data}, progress={has_progress})")
        else:
            attempt.entry = 'ab-initio'
            logger.info(f"Rise 360: Setting entry='ab-initio' (fresh start)")
    
    # Generate content URL using Django proxy (for iframe compatibility)
    # CRITICAL FIX: Properly handle launch_url to avoid double paths
    launch_path = scorm_package.launch_url.strip()
    if not launch_path:
        launch_path = 'index.html'  # Default fallback
    # Remove leading slash if present to avoid double slashes
    if launch_path.startswith('/'):
        launch_path = launch_path[1:]
    content_url = f'/scorm/content/{topic_id}/{launch_path}?attempt_id={attempt_id}'
    
    # Check if resume is needed
    resume_needed = attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted')
    
    # RISE 360 HANDLING: Only use hash fragment for navigation
    # Rise 360 does NOT use query parameters for resume
    hash_fragment = None
    bookmark_applied = False
    
    # Case 1: Rise 360 format with lessons/ in lesson_location
    if attempt.lesson_location and 'lessons/' in attempt.lesson_location:
        # Extract lesson ID from lesson_location if it contains the lessons pattern
        lesson_id = attempt.lesson_location.split('lessons/')[-1] if 'lessons/' in attempt.lesson_location else ''
        # Validate that lesson_id is not empty and not just '/' or '#/'
        lesson_id = lesson_id.strip('/#').strip()
        if lesson_id and len(lesson_id) > 3:  # Must be a real lesson ID, not just empty or '/'
            hash_fragment = f'#/lessons/{lesson_id}'
            logger.info(f"Rise 360: Set lesson hash fragment from lesson_location: #/lessons/{lesson_id}")
            bookmark_applied = True
        else:
            logger.warning(f"Rise 360: Invalid lesson_id extracted: '{lesson_id}' from '{attempt.lesson_location}'")
    
    # Case 2: FALLBACK - Check suspend_data for bookmark (Rise 360 sometimes saves here)
    if not bookmark_applied and attempt.suspend_data and 'lessons/' in attempt.suspend_data:
        # Extract lesson ID from suspend_data if it contains the lessons pattern
        import re
        # Look for patterns like #/lessons/XXXXX or lessons/XXXXX
        lesson_pattern = r'#?/?lessons/([a-zA-Z0-9_-]+)'
        match = re.search(lesson_pattern, attempt.suspend_data)
        if match:
            lesson_id = match.group(1).strip()
            if lesson_id and len(lesson_id) > 3:
                hash_fragment = f'#/lessons/{lesson_id}'
                logger.info(f"Rise 360: Set lesson hash fragment from suspend_data: #/lessons/{lesson_id}")
                bookmark_applied = True
    
    # Case 3: No specific lesson, start from beginning
    if not bookmark_applied:
        # Rise 360 will handle navigation on its own
        logger.info(f"Rise 360: No lesson bookmark found, starting from beginning")
    
    # Add hash fragment if we have one
    if hash_fragment:
        content_url += hash_fragment
        logger.info(f"Rise 360: Final URL with bookmark: {content_url}")
    else:
        logger.info(f"Rise 360: Final URL (no hash): {content_url}")
    
    # CRITICAL FIX: For returning learners with existing progress, redirect directly to content URL
    # This ensures they go to the correct lesson instead of the player template
    logger.info(f"Rise 360: Debug - resume_needed={resume_needed}, bookmark_applied={bookmark_applied}, lesson_status={attempt.lesson_status}")
    if resume_needed and (bookmark_applied or attempt.lesson_status not in ['not_attempted', 'not attempted']):
        logger.info(f"Rise 360: Returning learner with progress - redirecting to content URL: {content_url}")
        return redirect(content_url)
    else:
        logger.info(f"Rise 360: No redirect needed - showing player template")
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'content_url': content_url,
        'api_endpoint': f'/scorm/api/{attempt_id}/',
        'preview_mode': preview_mode,
        'is_instructor_or_admin': is_instructor_or_admin,
    }
    
    response = render(request, 'scorm/player_rise360.html', context)
    
    # Set permissive CSP headers for SCORM content
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'unsafe-hashes' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "worker-src 'self' blob: data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "style-src 'self' 'unsafe-inline' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "img-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "font-src 'self' data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "connect-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "media-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    
    return response
