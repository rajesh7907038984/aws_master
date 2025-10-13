"""
Storyline SCORM View Handler
Clean, focused implementation for Articulate Storyline packages only
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
def scorm_view_storyline(request, topic_id):
    """
    Storyline SCORM content viewer
    Handles Articulate Storyline packages with slide-based navigation
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
                logger.info(f"Storyline: Continuing existing attempt {attempt.attempt_number} for user {request.user.username}")
            else:
                # Create first attempt only if no previous attempt exists
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
                )
                logger.info(f"Storyline: Created new attempt {attempt.attempt_number} for user {request.user.username}")
        
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
            logger.info(f"Storyline: Setting entry='resume' (bookmark={has_bookmark}, suspend_data={has_suspend_data}, progress={has_progress})")
        else:
            attempt.entry = 'ab-initio'
            logger.info(f"Storyline: Setting entry='ab-initio' (fresh start)")
    
    # Generate content URL using Django proxy (for iframe compatibility)
    content_url = f'/scorm/content/{topic_id}/{scorm_package.launch_url}?attempt_id={attempt_id}'
    
    # Check if resume is needed
    resume_needed = attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted')
    
    # STORYLINE HANDLING: Use query parameters for resume
    # Add resume parameters BEFORE hash fragment (correct URL structure)
    if resume_needed:
        content_url += '&resume=true'
        if attempt.lesson_location:
            content_url += f'&location={attempt.lesson_location}'
        if attempt.suspend_data:
            content_url += f'&suspend_data={attempt.suspend_data[:100]}'  # First 100 chars
        logger.info(f"Storyline: Added resume parameters to content URL")
    
    # Handle bookmark/hash fragments for Storyline packages
    hash_fragment = None
    bookmark_applied = False
    
    # Case 1: Regular bookmark with or without hash
    if attempt.lesson_location:
        # Handle lesson locations (avoid double hash)
        if attempt.lesson_location.startswith('#'):
            hash_fragment = attempt.lesson_location  # Already has hash
        else:
            hash_fragment = f'#{attempt.lesson_location}'  # Add hash
        logger.info(f"Storyline: Set location hash fragment: {hash_fragment}")
        bookmark_applied = True
    
    # Case 2: Extract bookmark from suspend_data if no direct bookmark exists
    elif attempt.suspend_data and resume_needed:
        # Try to extract location from suspend_data
        import re
        
        # Common patterns for bookmarks in suspend_data
        bookmark_patterns = [
            r'current_slide[=:]([^&]+)',        # current_slide=slide3
            r'current_location[=:]([^&]+)',      # current_location=slide3
            r'bookmark[=:]([^&]+)',              # bookmark=slide3
            r'\"bookmark\"[=:]\"([^\"]+)\"',     # "bookmark":"slide3"
            r'\"slide\"[=:]\"([^\"]+)\"',        # "slide":"slide3"
            r'\"location\"[=:]\"([^\"]+)\"',     # "location":"slide3"
            r'currentSlide[=:]([^&]+)',          # currentSlide=slide3
            r'slideId[=:]([^&]+)'                # slideId=slide3
        ]
        
        # Try all patterns
        for pattern in bookmark_patterns:
            match = re.search(pattern, attempt.suspend_data)
            if match:
                extracted_location = match.group(1).strip()
                if extracted_location:
                    # Set location in attempt
                    attempt.lesson_location = extracted_location
                    hash_fragment = f'#{extracted_location}'
                    attempt.save()
                    logger.info(f"Storyline: Extracted bookmark '{extracted_location}' from suspend_data")
                    bookmark_applied = True
                    break
        
        # If no pattern matched but we know we need to resume
        if not bookmark_applied:
            # Use a generic slide ID based on progress percentage
            progress = attempt.progress_percentage or 0
            if progress > 75:
                default_slide = "slide_75"  # Near the end
            elif progress > 50:
                default_slide = "slide_50"  # Middle
            elif progress > 25:
                default_slide = "slide_25"  # Quarter way
            else:
                default_slide = "slide_1"   # Beginning
                
            attempt.lesson_location = default_slide
            hash_fragment = f'#{default_slide}'
            attempt.save()
            logger.info(f"Storyline: Created default location '{default_slide}' based on progress {progress}%")
            bookmark_applied = True
            
    # Case 3: Always ensure resume works
    if resume_needed and not bookmark_applied:
        # Final fallback - use slide_1 as a safe default
        attempt.lesson_location = 'slide_1'
        hash_fragment = '#slide_1'
        attempt.save()
        logger.info(f"Storyline: Created failsafe default location 'slide_1'")
    
    # Add hash fragment ONLY ONCE at the end
    if hash_fragment:
        content_url += hash_fragment
        logger.info(f"Storyline: Final content URL with hash: {content_url}")
    
    # CRITICAL FIX: For returning learners with existing progress, redirect directly to content URL
    # This ensures they go to the correct lesson instead of the player template
    logger.info(f"Storyline: Debug - resume_needed={resume_needed}, bookmark_applied={bookmark_applied}, lesson_status={attempt.lesson_status}")
    if resume_needed and (bookmark_applied or attempt.lesson_status not in ['not_attempted', 'not attempted']):
        logger.info(f"Storyline: Returning learner with progress - redirecting to content URL: {content_url}")
        return redirect(content_url)
    else:
        logger.info(f"Storyline: No redirect needed - showing player template")
    
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
    
    response = render(request, 'scorm/player_storyline.html', context)
    
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
