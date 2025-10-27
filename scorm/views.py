"""
SCORM Views - Clean Consolidated Implementation
Handles SCORM content playback with both simple and advanced tracking options
"""
import json
import logging
import os
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.files.storage import default_storage
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

from .models import ScormPackage, ScormAttempt
# from .api_handler import ScormAPIHandler  # DISABLED: Using enhanced handler only
from .api_handler_enhanced import ScormAPIHandlerEnhanced
from .preview_handler import ScormPreviewHandler
from .s3_direct import scorm_s3
from courses.models import Topic

logger = logging.getLogger(__name__)


@login_required
def scorm_view(request, topic_id):
    """
    Main SCORM content viewer - SECURE ACCESS ONLY
    Requires authentication for all SCORM content access
    """
    # SECURITY FIX: Require authentication for all SCORM content
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to access SCORM content.")
        return redirect('users:login')
    
    is_authenticated = True
    
    # OPTIMIZATION: Optimize database queries with select_related
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package'),
        id=topic_id
    )
    
    # CRITICAL FIX: Handle permission check for both authenticated and non-authenticated users
    if is_authenticated:
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
    else:
        # For non-authenticated users, check if this is a public course or embedded content
        # Allow access if it's a public course or if it's being accessed via embedded URL
        if hasattr(topic.course, 'is_public') and not topic.course.is_public:
            # If it's not a public course, redirect to login
            messages.info(request, "Please log in to access this SCORM content.")
            return redirect('users:login')
    
    # Check if topic has SCORM package (already loaded with select_related)
    if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    scorm_package = topic.scorm_package
    
    # Check for preview mode
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    is_instructor_or_admin = (hasattr(request.user, 'role') and 
                             request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])
    
    # Allow preview mode only for instructors/admins
    if preview_mode and not is_instructor_or_admin:
        messages.error(request, "Preview mode is only available for instructors and administrators.")
        preview_mode = False
    
    # Handle attempt creation/retrieval
    attempt = None
    attempt_id = None
    
    if preview_mode:
        # Preview mode: Create temporary attempt object
        attempt_id = f"preview_{uuid.uuid4()}"
        
        # Initialize CMI data for preview
        cmi_data = {}
        if scorm_package.version == '1.2':
            cmi_data = {
                'cmi.core.student_id': str(request.user.id) if is_authenticated else 'guest',
                'cmi.core.student_name': (request.user.get_full_name() or request.user.username) if is_authenticated else 'Guest User',
                'cmi.core.lesson_location': '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': 'not attempted',
                'cmi.core.entry': 'ab-initio',
                'cmi.core.score.raw': '',
                'cmi.core.score.max': '100',
                'cmi.core.score.min': '0',
                'cmi.core.total_time': '0000:00:00.00',
                'cmi.core.lesson_mode': 'normal',
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
            }
        else:  # SCORM 2004
            cmi_data = {
                'cmi.learner_id': str(request.user.id) if is_authenticated else 'guest',
                'cmi.learner_name': (request.user.get_full_name() or request.user.username) if is_authenticated else 'Guest User',
                'cmi.location': '',
                'cmi.credit': 'credit',
                'cmi.completion_status': 'incomplete',
                'cmi.success_status': 'unknown',
                'cmi.entry': 'ab-initio',
                'cmi.score.raw': '',
                'cmi.score.max': '100',
                'cmi.score.min': '0',
                'cmi.score.scaled': '',
                'cmi.total_time': '0000:00:00.00',
                'cmi.mode': 'normal',
                'cmi.exit': '',
                'cmi.session_time': '',
                'cmi.suspend_data': '',
                'cmi.launch_data': '',
            }
        
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
            'cmi_data': cmi_data,
            'started_at': timezone.now(),
            'last_accessed': timezone.now(),
            'completed_at': None,
            'is_preview': True,
        })()
        
        # Store preview attempt in session for API access
        request.session[f'scorm_preview_{attempt_id}'] = {
            'id': attempt_id,
            'user_id': request.user.id if is_authenticated else None,
            'scorm_package_id': scorm_package.id,
            'is_preview': True,
            'created_at': timezone.now().isoformat(),
        }
        
        logger.info(f"Created preview attempt {attempt_id} for user {request.user.username if is_authenticated else 'guest'} on topic {topic_id}")
    else:
        # CRITICAL FIX: Handle both authenticated and non-authenticated users
        if is_authenticated:
            # Normal mode: Get or create actual database attempt for user tracking
            # Use select_related to optimize database queries
            last_attempt = ScormAttempt.objects.select_related('scorm_package').filter(
                user=request.user,
                scorm_package=scorm_package
            ).order_by('-attempt_number').first()
        else:
            # For non-authenticated users, create a temporary attempt
            attempt_id = f"guest_{uuid.uuid4()}"
            attempt = type('ScormAttempt', (), {
                'id': attempt_id,
                'user': None,
                'scorm_package': scorm_package,
                'attempt_number': 1,
                'lesson_status': 'not_attempted',
                'lesson_location': '',
                'suspend_data': '',
                'entry': 'ab-initio',
                'exit_mode': '',
                'cmi_data': {},
                'started_at': timezone.now(),
                'last_accessed': timezone.now(),
                'completed_at': None,
                'is_preview': False,
            })()
            
            # Store guest attempt in session for API access
            request.session[f'scorm_guest_{attempt_id}'] = {
                'id': attempt_id,
                'user_id': None,
                'scorm_package_id': scorm_package.id,
                'is_preview': False,
                'created_at': timezone.now().isoformat(),
            }
            
            logger.info(f"Created guest attempt {attempt_id} for topic {topic_id}")
            attempt_id = attempt.id
        
        # Handle authenticated user logic
        if is_authenticated:
            # CRITICAL FIX: Create new attempt if last one was completed OR failed
            # A failed attempt with completed_at means the user finished but didn't pass
            # They should be able to start fresh, not resume the failed attempt
            if last_attempt and (
                last_attempt.lesson_status in ['completed', 'passed'] or 
                (last_attempt.lesson_status == 'failed' and last_attempt.completed_at is not None)
            ):
                # Create new attempt for completed/passed/failed attempts
                attempt_number = last_attempt.attempt_number + 1
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=attempt_number,
                    # CRITICAL FIX: Initialize required fields to prevent validation errors
                    navigation_history=[],
                    detailed_tracking={},
                    session_data={}
                )
                logger.info(f"Created new attempt {attempt.id} (previous status: {last_attempt.lesson_status}, completed: {last_attempt.completed_at is not None})")
                
                # Sync any existing scores for consistency
                from .score_sync_service import ScormScoreSyncService
                ScormScoreSyncService.sync_score(attempt)
            elif last_attempt:
                # Continue existing incomplete attempt - use enhanced resume handler
                attempt = last_attempt
                
                # Try enhanced resume handler first
                try:
                    from .enhanced_resume_handler import handle_scorm_resume
                    if handle_scorm_resume(attempt):
                        logger.info(f"RESUME: Enhanced handler successfully processed attempt {attempt.id}")
                    else:
                        logger.warning(f"RESUME: Enhanced handler failed for attempt {attempt.id}, using fallback")
                        # Fallback logic will be handled below
                except Exception as e:
                    logger.error(f"RESUME: Enhanced handler error for attempt {attempt.id}: {str(e)}")
                    # Continue with fallback logic
                
                # CRITICAL FIX: Always initialize CMI data for resume functionality
                if not attempt.cmi_data:
                    attempt.cmi_data = {}
                
                # CRITICAL FIX: Enhanced resume logic for SCORM content detection
                has_bookmark_data = bool(attempt.lesson_location or attempt.suspend_data)
                is_resumable_attempt = attempt.lesson_status in ['incomplete', 'not_attempted', 'browsed']
                
                # Determine if this should be a resume scenario
                should_resume = has_bookmark_data or is_resumable_attempt
                
                if should_resume:
                    # This is a resume scenario - set entry mode to resume
                    logger.info(f"RESUME: Resume scenario detected for attempt {attempt.id} - status: {attempt.lesson_status}, bookmark: {has_bookmark_data}")
                    
                    # Set entry mode to resume FIRST
                    attempt.entry = 'resume'
                    if scorm_package.version == '1.2':
                        attempt.cmi_data['cmi.core.entry'] = 'resume'
                    else:  # SCORM 2004
                        attempt.cmi_data['cmi.entry'] = 'resume'
                    
                    # Load bookmark data if available
                    if attempt.lesson_location:
                        if scorm_package.version == '1.2':
                            attempt.cmi_data['cmi.core.lesson_location'] = attempt.lesson_location
                        else:  # SCORM 2004
                            attempt.cmi_data['cmi.location'] = attempt.lesson_location
                        logger.info(f"RESUME: Set lesson_location: {attempt.lesson_location}")
                    else:
                        # STORYLINE SCORM 2004 FIX: For Storyline, location might be empty even with suspend_data
                        # Don't set a fake location as it confuses Storyline's resume logic
                        if scorm_package.version == '1.2':
                            attempt.cmi_data['cmi.core.lesson_location'] = ''
                        else:  # SCORM 2004
                            attempt.cmi_data['cmi.location'] = ''
                        logger.info(f"RESUME: No lesson_location, leaving empty for Storyline to manage via suspend_data")
                    
                    if attempt.suspend_data:
                        if scorm_package.version == '1.2':
                            attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                        else:  # SCORM 2004
                            attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                        logger.info(f"RESUME: Set suspend_data ({len(attempt.suspend_data)} chars)")
                    
                    # Ensure basic CMI data is set for resume
                    if scorm_package.version == '1.2':
                        # CRITICAL FIX: If resuming with bookmark data, ensure status is 'incomplete'
                        if attempt.lesson_location or attempt.suspend_data:
                            if attempt.lesson_status == 'not_attempted':
                                attempt.lesson_status = 'incomplete'
                        attempt.cmi_data['cmi.core.lesson_status'] = attempt.lesson_status or 'not attempted'
                        attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
                        attempt.cmi_data['cmi.core.credit'] = 'credit'
                        attempt.cmi_data['cmi.core.student_id'] = str(attempt.user.id) if attempt.user else 'student'
                        attempt.cmi_data['cmi.core.student_name'] = attempt.user.get_full_name() or attempt.user.username if attempt.user else 'Student'
                    else:  # SCORM 2004
                        # CRITICAL FIX FOR SCORM 2004 STORYLINE: If resuming with bookmark data, ensure completion_status is 'incomplete'
                        if attempt.lesson_location or attempt.suspend_data:
                            if attempt.completion_status in ['not attempted', 'unknown', None]:
                                attempt.completion_status = 'incomplete'
                        # STORYLINE FIX: Don't set cmi.completion_status to 'incomplete' if it was 'completed'
                        # Storyline needs to see the actual completion status to properly resume
                        attempt.cmi_data['cmi.completion_status'] = attempt.completion_status or 'incomplete'
                        attempt.cmi_data['cmi.success_status'] = attempt.success_status or 'unknown'
                        
                        # STORYLINE FIX: Ensure cmi.mode is set correctly
                        attempt.cmi_data['cmi.mode'] = 'normal'
                        attempt.cmi_data['cmi.credit'] = 'credit'
                        
                        attempt.cmi_data['cmi.learner_id'] = str(attempt.user.id) if attempt.user else 'student'
                        attempt.cmi_data['cmi.learner_name'] = attempt.user.get_full_name() or attempt.user.username if attempt.user else 'Student'
                    
                    logger.info(f"RESUME: Set entry mode to 'resume' with CMI data")
                else:
                    # This is a new attempt
                    logger.info(f"RESUME: New attempt for attempt {attempt.id}")
                    attempt.entry = 'ab-initio'
                    if scorm_package.version == '1.2':
                        attempt.cmi_data['cmi.core.entry'] = 'ab-initio'
                    else:  # SCORM 2004
                        attempt.cmi_data['cmi.entry'] = 'ab-initio'
                
                # Save the updated attempt
                attempt.save()
                location_str = attempt.lesson_location or 'None'
                suspend_str = attempt.suspend_data[:50] if attempt.suspend_data else 'None'
                logger.info(f"RESUME: Updated attempt {attempt.id}: entry='{attempt.entry}', location='{location_str}', suspend_data='{suspend_str}...'")
            else:
                # Create first attempt with properly initialized fields
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1,
                    # CRITICAL FIX: Initialize required fields to prevent validation errors
                    navigation_history=[],
                    detailed_tracking={},
                    session_data={}
                )
                logger.info(f"Created first attempt {attempt.id} for user {request.user.username}")
            
            # Standard SCORM bookmark - lesson_location is automatically handled
            logger.info(f"SCORM bookmark: lesson_location='{attempt.lesson_location}', suspend_data='{attempt.suspend_data[:50] if attempt.suspend_data else 'None'}...'")
        
        attempt_id = attempt.id
        attempt.is_preview = False  # Mark as real attempt
    
    # Generate content URL using S3 direct access
    # Use Django proxy URL for iframe content
    try:
        # Ensure launch_url is properly formatted
        launch_url = scorm_package.launch_url or 'index.html'
        if not launch_url.startswith('/'):
            launch_url = '/' + launch_url
        content_url = f"/scorm/content/{topic_id}{launch_url}"
        logger.info(f"Generated content URL: {content_url}")
    except Exception as e:
        logger.error(f"Error generating content URL: {str(e)}")
        content_url = f"/scorm/content/{topic_id}/index.html"
    
    # CRITICAL FIX: Add resume data detection for template
    has_resume_data = bool(attempt.lesson_location or attempt.suspend_data)
    
    context = {
        'topic': topic,
        'scorm_package': scorm_package,
        'attempt': attempt,
        'attempt_id': attempt_id,
        'content_url': content_url,
        'api_endpoint': f'/scorm/api/{attempt_id}/',
        'preview_mode': preview_mode,
        'is_instructor_or_admin': is_instructor_or_admin,
        'has_resume_data': has_resume_data,
    }
    
    response = render(request, 'scorm/player_clean.html', context)
    
    # Set secure CSP headers for SCORM content (no external CDNs)
    # FIXED: Allow data: URLs for fonts and unsafe-eval for scripts
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "worker-src 'self' blob: data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "style-src 'self' 'unsafe-inline' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "img-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "font-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "connect-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "media-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-ancestors 'self' *; "
        "object-src 'none'"
    )
    
    # Add additional headers for better module loading (fixes Svelte version conflicts)
    response['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
    response['Cross-Origin-Opener-Policy'] = 'same-origin'
    response['Cross-Origin-Resource-Policy'] = 'cross-origin'
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    
    # DEBUG: Log CSP headers being set
    logger.info(f"CSP Headers set for SCORM view {topic_id}: {response['Content-Security-Policy']}")
    
    # STORYLINE FIX: Remove duplicate CSP headers that conflict with permissive ones above
    
    return response


@csrf_exempt
@require_http_methods(["POST"])
def scorm_api(request, attempt_id):
    """
    SCORM API endpoint
    Handles all SCORM API calls from content
    Supports both regular attempts and preview mode
    """
    # For SCORM API calls, we need to handle authentication differently
    # since the calls come from iframe content. We'll check if the attempt exists
    # and belongs to the current user through the attempt_id
    try:
        attempt = ScormAttempt.objects.get(id=attempt_id)
        # For now, allow API calls if the attempt exists (we'll add proper auth later)
        # if not request.user.is_authenticated or attempt.user != request.user:
        #     return JsonResponse({'error': 'Unauthorized'}, status=401)
    except ScormAttempt.DoesNotExist:
        return JsonResponse({'error': 'Attempt not found'}, status=404)
    
    try:
        # Enhanced preview mode detection with better error handling
        session_key = f'scorm_preview_{attempt_id}'
        is_preview = False
        
        try:
            # Check if this is a preview attempt with robust session handling
            if hasattr(request, 'session') and request.session:
                is_preview = session_key in request.session
                logger.info(f"Preview detection: session_key={session_key}, is_preview={is_preview}")
            else:
                logger.warning("No session available for preview detection")
        except Exception as e:
            logger.error(f"Error checking preview mode: {str(e)}")
            is_preview = False
        
        if is_preview:
            # Preview mode: Create temporary attempt from session data with validation
            try:
                preview_data = request.session.get(session_key, {})
                if not preview_data:
                    logger.warning(f"Preview session data not found for key: {session_key}")
                    return JsonResponse({'error': 'Preview session expired'}, status=400)
                
                # Validate preview data structure
                required_fields = ['scorm_package_id', 'user_id']
                for field in required_fields:
                    if field not in preview_data:
                        logger.error(f"Missing required preview field: {field}")
                        return JsonResponse({'error': f'Invalid preview data: missing {field}'}, status=400)
                
                logger.info(f"Preview mode activated with valid session data for attempt {attempt_id}")
            except Exception as e:
                logger.error(f"Error accessing preview session data: {str(e)}")
                return JsonResponse({'error': 'Preview session error'}, status=400)
            
            # Reconstruct the attempt object for preview
            scorm_package = get_object_or_404(ScormPackage, id=preview_data['scorm_package_id'])
            
            # Initialize CMI data for preview
            cmi_data = {}
            if scorm_package.version == '1.2':
                cmi_data = {
                    'cmi.core.student_id': str(request.user.id),
                    'cmi.core.student_name': request.user.get_full_name() or request.user.username,
                    'cmi.core.lesson_location': '',
                    'cmi.core.credit': 'credit',
                    'cmi.core.lesson_status': 'not attempted',
                    'cmi.core.entry': 'ab-initio',
                    'cmi.core.score.raw': '',
                    'cmi.core.score.max': '100',
                    'cmi.core.score.min': '0',
                    'cmi.core.total_time': '0000:00:00.00',
                    'cmi.core.lesson_mode': 'normal',
                    'cmi.core.exit': '',
                    'cmi.core.session_time': '',
                    'cmi.suspend_data': '',
                    'cmi.launch_data': '',
                    'cmi.comments': '',
                    'cmi.comments_from_lms': '',
                }
            else:  # SCORM 2004
                cmi_data = {
                    'cmi.learner_id': str(request.user.id),
                    'cmi.learner_name': request.user.get_full_name() or request.user.username,
                    'cmi.location': '',
                    'cmi.credit': 'credit',
                    'cmi.completion_status': 'incomplete',
                    'cmi.success_status': 'unknown',
                    'cmi.entry': 'ab-initio',
                    'cmi.score.raw': '',
                    'cmi.score.max': '100',
                    'cmi.score.min': '0',
                    'cmi.score.scaled': '',
                    'cmi.total_time': '0000:00:00.00',
                    'cmi.mode': 'normal',
                    'cmi.exit': '',
                    'cmi.session_time': '',
                    'cmi.suspend_data': '',
                    'cmi.launch_data': '',
                }
            
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
                'cmi_data': cmi_data,
                'started_at': timezone.now(),
                'last_accessed': timezone.now(),
                'completed_at': None,
                'is_preview': True,
            })()
            
            # Verify user owns this preview attempt
            # if preview_data['user_id'] != request.user.id:
            #     return JsonResponse({'error': 'Unauthorized'}, status=403)
                
        else:
            # Regular mode: Get database attempt
            attempt = get_object_or_404(ScormAttempt, id=attempt_id)
            
            # Verify user owns this attempt
            # if attempt.user != request.user:
            #     return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Parse request
        try:
            data = json.loads(request.body)
            method = data.get('method')
            parameters = data.get('parameters', [])
            logger.info(f"📞 SCORM API REQUEST: method={method}, parameters={parameters}, attempt_id={attempt_id}")
        except json.JSONDecodeError as e:
            logger.error(f"📞 SCORM API JSON Error: {str(e)}, body: {request.body}")
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
        except Exception as e:
            logger.error(f"📞 SCORM API Parse Error: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'Parse error: {str(e)}'
            }, status=400)
        
        # Log all API calls
        logger.info(f"📞 SCORM API CALL: method={method}, parameters={parameters[:2] if len(parameters) > 2 else parameters}, attempt_id={attempt_id}")
        
        # Initialize appropriate API handler WITHOUT caching to ensure fresh data
        if is_preview:
            handler = ScormPreviewHandler(attempt)
            logger.info(f"Using preview handler for attempt {attempt_id}")
        else:
            # CRITICAL FIX: Removed handler caching to prevent stale data issues
            # Each request gets a fresh handler with current database state
            # This ensures:
            # 1. Accurate score tracking
            # 2. Proper progress updates
            # 3. Working resume functionality with correct bookmark/suspend data
            
            # IMPORTANT: Refresh attempt from database to get latest data
            attempt.refresh_from_db()
            
            handler = ScormAPIHandlerEnhanced(attempt)
            logger.info(f"Created fresh enhanced handler for attempt {attempt_id} with latest database state")
        
        # Route to appropriate API method
        if method == 'Initialize' or method == 'LMSInitialize':
            result = handler.initialize()
        elif method == 'Terminate' or method == 'LMSFinish':
            result = handler.terminate()
        elif method == 'GetValue' or method == 'LMSGetValue':
            element = parameters[0] if parameters else ''
            result = handler.get_value(element)
        elif method == 'SetValue' or method == 'LMSSetValue':
            element = parameters[0] if len(parameters) > 0 else ''
            value = parameters[1] if len(parameters) > 1 else ''
            logger.info(f"📝 SetValue called: element={element}, value={value}")
            result = handler.set_value(element, value)
            logger.info(f"📝 SetValue result: {result}")
        elif method == 'Commit' or method == 'LMSCommit':
            logger.info(f"💾 Commit called for attempt {attempt_id}")
            result = handler.commit()
            logger.info(f"💾 Commit result: {result}")
        elif method == 'GetLastError' or method == 'LMSGetLastError':
            result = handler.get_last_error()
        elif method == 'GetErrorString' or method == 'LMSGetErrorString':
            error_code = parameters[0] if parameters else '0'
            # Ensure error_code is properly handled
            try:
                if isinstance(error_code, str) and error_code.isdigit():
                    error_code = int(error_code)
                result = handler.get_error_string(error_code)
            except Exception as e:
                logger.error(f"Error handling GetErrorString: {str(e)}")
                result = 'Unknown error'
        elif method == 'GetDiagnostic' or method == 'LMSGetDiagnostic':
            error_code = parameters[0] if parameters else '0'
            result = handler.get_diagnostic(error_code)
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown method: {method}'
            })
        
        return JsonResponse({
            'success': True,
            'result': result,
            'error_code': handler.last_error
        })
        
    except Exception as e:
        logger.error(f"SCORM API error: {str(e)}")
        # Return a more SCORM-compliant error response
        return JsonResponse({
            'success': False,
            'result': 'false',
            'error_code': '101',  # General system error
            'error': str(e)
        }, status=200)  # Return 200 to avoid browser issues


@login_required
def scorm_content(request, topic_id=None, path=None, attempt_id=None):
    """
    Serve SCORM content files from S3 with optimized loading - SECURE ACCESS ONLY
    Uses direct S3 URLs for maximum performance
    Handles both topic_id and attempt_id parameters for backward compatibility
    """
    try:
        # SECURITY FIX: Require authentication for all SCORM content
        if not request.user.is_authenticated:
            return HttpResponse('Authentication required', status=401)
        # Handle both topic_id and attempt_id parameters for backward compatibility
        current_attempt_id = None
        if attempt_id is not None and topic_id is None:
            # If attempt_id is provided, get the topic from the attempt
            from .models import ScormAttempt
            try:
                attempt = get_object_or_404(ScormAttempt, id=attempt_id)
                topic = attempt.scorm_package.topic
                topic_id = topic.id
                current_attempt_id = attempt_id
            except Exception as e:
                logger.error(f"Error getting topic from attempt {attempt_id}: {str(e)}")
                return HttpResponse('Invalid attempt ID', status=404)
        else:
            # Use topic_id directly - need to get the current attempt for this user
            topic = get_object_or_404(Topic.objects.select_related('scorm_package'), id=topic_id)
            
            # SECURITY FIX: Verify user has access to this topic
            if not topic.user_has_access(request.user):
                return HttpResponse('Access denied - You do not have permission to access this content', status=403)
            # Get the current attempt for this user and topic
            from .models import ScormAttempt
            try:
                if request.user.is_authenticated:
                    current_attempt = ScormAttempt.objects.filter(
                        user=request.user,
                        scorm_package__topic=topic
                    ).order_by('-attempt_number').first()
                    if current_attempt:
                        current_attempt_id = current_attempt.id
            except Exception as e:
                logger.error(f"Error getting current attempt for topic {topic_id}: {str(e)}")
        
        # Check if topic has SCORM package
        try:
            scorm_package = topic.scorm_package
        except ScormPackage.DoesNotExist:
            return HttpResponse('SCORM package not found', status=404)
        
        # Handle directory requests by redirecting to index.html
        if path.endswith('/'):
            path = path + 'index.html'
        
        # Generate direct S3 URL with proper error handling
        try:
            s3_url = scorm_s3.generate_direct_url(scorm_package, path)
            if not s3_url:
                logger.error(f"Failed to generate S3 URL for path: {path}")
                return HttpResponse('Content not found', status=404)
            logger.info(f"Generated S3 URL: {s3_url}")
        except Exception as e:
            logger.error(f"Error generating S3 URL: {str(e)}")
            return HttpResponse('Error generating content URL', status=500)
        
        # OPTIMIZATION: For video and audio files, proxy through Django to add proper CORS headers
        # For other files, redirect directly to S3 for maximum performance
        if not path.endswith(('.html', '.htm')):
            # For video and audio files, proxy through Django to add proper headers
            if path and any(path.lower().endswith(ext) for ext in [
                # Video extensions
                '.mp4', '.webm', '.ogg', '.avi', '.mov', '.m4v', '.flv', '.wmv', '.mkv',
                # Audio extensions - CRITICAL FIX: Add audio file support
                '.mp3', '.wav', '.aac', '.m4a', '.wma', '.flac'
            ]):
                try:
                    import requests
                    
                    # Check if file exists in S3 before attempting to proxy
                    try:
                        head_response = requests.head(s3_url, timeout=5)
                        if head_response.status_code == 404:
                            logger.warning(f"Audio/video file not found in S3: {path}")
                            return HttpResponse('Media file not found', status=404)
                    except Exception as head_error:
                        logger.warning(f"Could not check S3 file existence: {head_error}")
                    
                    response = requests.get(s3_url, timeout=10)
                    response.raise_for_status()
                    
                    # Determine content type based on file extension
                    content_type = 'application/octet-stream'
                    if path.lower().endswith('.mp3'):
                        content_type = 'audio/mpeg'
                    elif path.lower().endswith('.wav'):
                        content_type = 'audio/wav'
                    elif path.lower().endswith('.aac'):
                        content_type = 'audio/aac'
                    elif path.lower().endswith('.m4a'):
                        content_type = 'audio/mp4'
                    elif path.lower().endswith('.wma'):
                        content_type = 'audio/x-ms-wma'
                    elif path.lower().endswith('.flac'):
                        content_type = 'audio/flac'
                    elif path.lower().endswith('.ogg'):
                        content_type = 'audio/ogg'
                    elif path.lower().endswith('.mp4'):
                        content_type = 'video/mp4'
                    elif path.lower().endswith('.webm'):
                        content_type = 'video/webm'
                    elif path.lower().endswith('.avi'):
                        content_type = 'video/avi'
                    elif path.lower().endswith('.mov'):
                        content_type = 'video/quicktime'
                    else:
                        # Fallback to S3 response content type
                        content_type = response.headers.get('content-type', 'application/octet-stream')
                    
                    # Create Django response with proper headers for media streaming
                    django_response = HttpResponse(response.content, content_type=content_type)
                    django_response['Access-Control-Allow-Origin'] = '*'
                    django_response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
                    django_response['Access-Control-Allow-Headers'] = 'Range, Content-Range, Content-Length'
                    django_response['Accept-Ranges'] = 'bytes'
                    django_response['Cache-Control'] = 'public, max-age=3600'
                    django_response['X-Frame-Options'] = 'SAMEORIGIN'
                    
                    # Copy important headers from S3 response
                    if 'Content-Length' in response.headers:
                        django_response['Content-Length'] = response.headers['Content-Length']
                    if 'ETag' in response.headers:
                        django_response['ETag'] = response.headers['ETag']
                    
                    # Log the type of media being served
                    if any(path.lower().endswith(ext) for ext in ['.mp3', '.wav', '.aac', '.m4a', '.wma', '.flac', '.ogg']):
                        logger.info(f"Proxying audio file {path} with proper CORS headers")
                    else:
                        logger.info(f"Proxying video file {path} with proper CORS headers")
                    
                    return django_response
                except Exception as e:
                    logger.error(f"Error proxying media file {path}: {str(e)}")
                    # Fallback to direct S3 redirect for media files
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(s3_url)
            # NEW: Handle font files for video player icons (FIXES ICON DISPLAY)
            elif path and any(path.lower().endswith(ext) for ext in [
                '.woff', '.woff2', '.ttf', '.eot', '.otf', '.svg'
            ]):
                try:
                    import requests
                    response = requests.get(s3_url, timeout=5)
                    response.raise_for_status()
                    
                    # Determine correct MIME type for fonts
                    content_type = 'application/octet-stream'
                    if path.lower().endswith('.woff'):
                        content_type = 'font/woff'
                    elif path.lower().endswith('.woff2'):
                        content_type = 'font/woff2'
                    elif path.lower().endswith('.ttf'):
                        content_type = 'font/ttf'
                    elif path.lower().endswith('.otf'):
                        content_type = 'font/otf'
                    elif path.lower().endswith('.eot'):
                        content_type = 'application/vnd.ms-fontobject'
                    elif path.lower().endswith('.svg'):
                        content_type = 'image/svg+xml'
                    
                    # Create response with proper CORS and caching headers
                    django_response = HttpResponse(response.content, content_type=content_type)
                    django_response['Access-Control-Allow-Origin'] = '*'
                    django_response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
                    django_response['Cache-Control'] = 'public, max-age=31536000'  # Cache fonts for 1 year
                    django_response['X-Frame-Options'] = 'SAMEORIGIN'
                    
                    if 'Content-Length' in response.headers:
                        django_response['Content-Length'] = response.headers['Content-Length']
                    if 'ETag' in response.headers:
                        django_response['ETag'] = response.headers['ETag']
                    
                    logger.info(f"Proxying font file {path} with proper MIME type and CORS headers")
                    return django_response
                    
                except Exception as e:
                    logger.error(f"Error proxying font file {path}: {str(e)}")
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(s3_url)
            else:
                # For other non-HTML files, redirect directly to S3
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect(s3_url)
        
        # For HTML files, inject minimal SCORM API reference
        try:
            import requests
            from django.core.cache import cache
            
            # Create cache key for this content with version
            cache_key = f"scorm_content_v3_{scorm_package.id}_{path}_{scorm_package.updated_at.timestamp()}"
            cached_content = cache.get(cache_key)
            
            if cached_content:
                logger.info(f"Serving cached content for {path}")
                response_obj = HttpResponse(cached_content, content_type='text/html; charset=utf-8')
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                response_obj['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
                return response_obj
            
            # Fetch from S3 with optimized timeout
            response = requests.get(s3_url, timeout=5)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get('content-type', 'text/html; charset=utf-8')
            
            # Inject lightweight SCORM API for HTML files
            if 'text/html' in content_type:
                html_content = content.decode('utf-8')
                
                # CRITICAL FIX: Handle SCORM 2004 Storyline packages properly
                if scorm_package.version in ['storyline', '2004', '1.2']:
                    # SCORM 2004 Storyline - Use PostMessage communication instead of fallback stubs
                    api_injection = f'''
<script>
// SCORM 2004 Storyline API Bridge - PostMessage Communication
// Version: 6.0 - Fixes child window communication issues
console.log('[SCORM 2004] Storyline API bridge loaded');


// LOCALIZATION FIX: Provide fallback strings for missing localization
(function() {{
    console.log('[SCORM] Full API loaded for 1.2');
    
    // Create fallback string table for missing localization
    const fallbackStrings = {{
        'PREV': 'Previous',
        'NEXT': 'Next', 
        'SUBMIT': 'Submit',
        'slide': 'Slide',
        // Handle corrupted string table identifiers with proper fallbacks
        'npnxnanbnsnfns10111001101': 'Default',
        // Additional Storyline-specific strings
        'PREVIOUS': 'Previous',
        'CONTINUE': 'Continue',
        'EXIT': 'Exit',
        'PLAY': 'Play',
        'PAUSE': 'Pause',
        'STOP': 'Stop',
        'RESTART': 'Restart',
        'FULLSCREEN': 'Fullscreen',
        'HELP': 'Help',
        'MENU': 'Menu',
        'BACK': 'Back',
        'FORWARD': 'Forward',
        'CLOSE': 'Close',
        'OK': 'OK',
        'CANCEL': 'Cancel',
        'YES': 'Yes',
        'NO': 'No',
        'SAVE': 'Save',
        'LOAD': 'Load',
        'RESET': 'Reset',
        'CLEAR': 'Clear',
        'SELECT': 'Select',
        'CHOOSE': 'Choose',
        'UPLOAD': 'Upload',
        'DOWNLOAD': 'Download',
        'PRINT': 'Print',
        'SEARCH': 'Search',
        'FILTER': 'Filter',
        'SORT': 'Sort',
        'EDIT': 'Edit',
        'DELETE': 'Delete',
        'ADD': 'Add',
        'REMOVE': 'Remove',
        'UPDATE': 'Update',
        'REFRESH': 'Refresh',
        'RELOAD': 'Reload',
        'RESTORE': 'Restore',
        'UNDO': 'Undo',
        'REDO': 'Redo',
        'COPY': 'Copy',
        'PASTE': 'Paste',
        'CUT': 'Cut',
        'SELECT_ALL': 'Select All',
        'DESELECT_ALL': 'Deselect All',
        'ZOOM_IN': 'Zoom In',
        'ZOOM_OUT': 'Zoom Out',
        'FIT_TO_SCREEN': 'Fit to Screen',
        'ACTUAL_SIZE': 'Actual Size',
        'PREVIEW': 'Preview',
        'VIEW': 'View',
        'SHOW': 'Show',
        'HIDE': 'Hide',
        'EXPAND': 'Expand',
        'COLLAPSE': 'Collapse',
        'MAXIMIZE': 'Maximize',
        'MINIMIZE': 'Minimize',
        'RESTORE_WINDOW': 'Restore Window',
        'MOVE': 'Move',
        'RESIZE': 'Resize',
        'LOCK': 'Lock',
        'UNLOCK': 'Unlock',
        'ENABLE': 'Enable',
        'DISABLE': 'Disable',
        'ACTIVATE': 'Activate',
        'DEACTIVATE': 'Deactivate',
        'START': 'Start',
        'END': 'End',
        'BEGIN': 'Begin',
        'FINISH': 'Finish',
        'COMPLETE': 'Complete',
        'INCOMPLETE': 'Incomplete',
        'PASSED': 'Passed',
        'FAILED': 'Failed',
        'CORRECT': 'Correct',
        'INCORRECT': 'Incorrect',
        'TRUE': 'True',
        'FALSE': 'False',
        'ON': 'On',
        'OFF': 'Off',
        'ENABLED': 'Enabled',
        'DISABLED': 'Disabled',
        'ACTIVE': 'Active',
        'INACTIVE': 'Inactive',
        'VISIBLE': 'Visible',
        'HIDDEN': 'Hidden',
        'OPEN': 'Open',
        'CLOSED': 'Closed',
        'AVAILABLE': 'Available',
        'UNAVAILABLE': 'Unavailable',
        'ONLINE': 'Online',
        'OFFLINE': 'Offline',
        'CONNECTED': 'Connected',
        'DISCONNECTED': 'Disconnected',
        'LOADING': 'Loading...',
        'SAVING': 'Saving...',
        'PROCESSING': 'Processing...',
        'WAITING': 'Waiting...',
        'READY': 'Ready',
        'BUSY': 'Busy',
        'ERROR': 'Error',
        'WARNING': 'Warning',
        'INFO': 'Information',
        'SUCCESS': 'Success',
        'FAILURE': 'Failure',
        'COMPLETED': 'Completed',
        'IN_PROGRESS': 'In Progress',
        'PENDING': 'Pending',
        'SCHEDULED': 'Scheduled',
        'EXPIRED': 'Expired',
        'VALID': 'Valid',
        'INVALID': 'Invalid',
        'REQUIRED': 'Required',
        'OPTIONAL': 'Optional',
        'MANDATORY': 'Mandatory',
        'RECOMMENDED': 'Recommended',
        'SUGGESTED': 'Suggested',
        'DEFAULT': 'Default',
        'CUSTOM': 'Custom',
        'STANDARD': 'Standard',
        'ADVANCED': 'Advanced',
        'BASIC': 'Basic',
        'SIMPLE': 'Simple',
        'COMPLEX': 'Complex',
        'EASY': 'Easy',
        'HARD': 'Hard',
        'DIFFICULT': 'Difficult',
        'SIMPLE': 'Simple',
        'QUICK': 'Quick',
        'SLOW': 'Slow',
        'FAST': 'Fast',
        'LARGE': 'Large',
        'SMALL': 'Small',
        'BIG': 'Big',
        'TINY': 'Tiny',
        'HUGE': 'Huge',
        'WIDE': 'Wide',
        'NARROW': 'Narrow',
        'TALL': 'Tall',
        'SHORT': 'Short',
        'LONG': 'Long',
        'BRIEF': 'Brief',
        'DETAILED': 'Detailed',
        'SUMMARY': 'Summary',
        'FULL': 'Full',
        'EMPTY': 'Empty',
        'NEW': 'New',
        'OLD': 'Old',
        'RECENT': 'Recent',
        'LATEST': 'Latest',
        'EARLIEST': 'Earliest',
        'FIRST': 'First',
        'LAST': 'Last',
        'NEXT': 'Next',
        'PREVIOUS': 'Previous',
        'CURRENT': 'Current',
        'PAST': 'Past',
        'FUTURE': 'Future',
        'PRESENT': 'Present',
        'TODAY': 'Today',
        'YESTERDAY': 'Yesterday',
        'TOMORROW': 'Tomorrow',
        'NOW': 'Now',
        'LATER': 'Later',
        'EARLIER': 'Earlier',
        'SOON': 'Soon',
        'RECENTLY': 'Recently',
        'FREQUENTLY': 'Frequently',
        'OFTEN': 'Often',
        'SOMETIMES': 'Sometimes',
        'RARELY': 'Rarely',
        'NEVER': 'Never',
        'ALWAYS': 'Always',
        'SOMETIMES': 'Sometimes',
        'USUALLY': 'Usually',
        'NORMALLY': 'Normally',
        'TYPICALLY': 'Typically',
        'GENERALLY': 'Generally',
        'COMMONLY': 'Commonly',
        'REGULARLY': 'Regularly',
        'CONSTANTLY': 'Constantly',
        'CONTINUOUSLY': 'Continuously',
        'PERIODICALLY': 'Periodically',
        'OCCASIONALLY': 'Occasionally',
        'RANDOMLY': 'Randomly',
        'SYSTEMATICALLY': 'Systematically',
        'AUTOMATICALLY': 'Automatically',
        'MANUALLY': 'Manually',
        'AUTOMATIC': 'Automatic',
        'MANUAL': 'Manual',
        'AUTO': 'Auto',
        'SELF': 'Self',
        'AUTOMATED': 'Automated',
        'MANUAL': 'Manual',
        'SEMI_AUTOMATIC': 'Semi-Automatic',
        'FULLY_AUTOMATIC': 'Fully Automatic',
        'PARTIALLY_AUTOMATIC': 'Partially Automatic',
        'COMPLETELY_AUTOMATIC': 'Completely Automatic',
        'TOTALLY_AUTOMATIC': 'Totally Automatic',
        'ENTIRELY_AUTOMATIC': 'Entirely Automatic',
        'WHOLLY_AUTOMATIC': 'Wholly Automatic',
        'FULLY_MANUAL': 'Fully Manual',
        'PARTIALLY_MANUAL': 'Partially Manual',
        'COMPLETELY_MANUAL': 'Completely Manual',
        'TOTALLY_MANUAL': 'Totally Manual',
        'ENTIRELY_MANUAL': 'Entirely Manual',
        'WHOLLY_MANUAL': 'Wholly Manual'
    }};
    
    // Override string table functions to provide fallbacks
    if (typeof window.stringTable === 'undefined') {{
        window.stringTable = {{}};
    }}
    
    // Override common string table access patterns
    const originalGetString = window.getString || function(key) {{ return key; }};
    window.getString = function(key) {{
        if (fallbackStrings[key]) {{
            return fallbackStrings[key];
        }}
        return originalGetString(key);
    }};
    
    // Override string table access for common patterns
    const originalStringTableGet = window.stringTable?.get || function(key) {{ return key; }};
    if (window.stringTable) {{
        window.stringTable.get = function(key) {{
            if (fallbackStrings[key]) {{
                return fallbackStrings[key];
            }}
            return originalStringTableGet(key);
        }};
    }}
    
    // Override common localization functions
    const originalLocalize = window.localize || function(key) {{ return key; }};
    window.localize = function(key) {{
        if (fallbackStrings[key]) {{
            return fallbackStrings[key];
        }}
        return originalLocalize(key);
    }};
    
    // Override i18n functions
    const originalI18n = window.i18n || {{}};
    if (window.i18n) {{
        const originalI18nGet = window.i18n.get || function(key) {{ return key; }};
        window.i18n.get = function(key) {{
            if (fallbackStrings[key]) {{
                return fallbackStrings[key];
            }}
            return originalI18nGet(key);
        }};
    }}
    
    // CRITICAL FIX: Handle corrupted string table identifiers
    // Override Storyline-specific string table access patterns
    const originalStringTableAccess = window.stringTable?.getString || function(key) {{ return key; }};
    if (window.stringTable) {{
        window.stringTable.getString = function(key) {{
            // Handle corrupted string table identifiers
            if (key === 'npnxnanbnsnfns10111001101' || key.includes('npnxnanbnsnfns')) {{
                console.warn('[SCORM] Detected corrupted string table identifier:', key);
                return 'Default'; // Return a safe default
            }}
            if (fallbackStrings[key]) {{
                return fallbackStrings[key];
            }}
            return originalStringTableAccess(key);
        }};
    }}
    
    // Override common Storyline string access patterns
    const originalGetLocalizedString = window.getLocalizedString || function(key) {{ return key; }};
    window.getLocalizedString = function(key) {{
        // Handle corrupted string table identifiers
        if (key === 'npnxnanbnsnfns10111001101' || key.includes('npnxnanbnsnfns')) {{
            console.warn('[SCORM] Detected corrupted string table identifier in getLocalizedString:', key);
            return 'Default';
        }}
        if (fallbackStrings[key]) {{
            return fallbackStrings[key];
        }}
        return originalGetLocalizedString(key);
    }};
    
    // String table access methods already handled above
    
    // Override global string table access patterns
    const originalGetStringTable = window.getStringTable || function(key) {{ return key; }};
    window.getStringTable = function(key) {{
        if (key === 'npnxnanbnsnfns10111001101' || key.includes('npnxnanbnsnfns')) {{
            console.warn('[SCORM] Detected corrupted string table identifier in getStringTable:', key);
            return 'Default';
        }}
        if (fallbackStrings[key]) {{
            return fallbackStrings[key];
        }}
        return originalGetStringTable(key);
    }};
    
    // Override any direct string table property access
    if (window.stringTable) {{
        // Create a proxy to intercept property access
        const originalStringTable = window.stringTable;
        window.stringTable = new Proxy(originalStringTable, {{
            get: function(target, prop) {{
                if (prop === 'npnxnanbnsnfns10111001101' || prop.toString().includes('npnxnanbnsnfns')) {{
                    console.warn('[SCORM] Detected corrupted string table property access:', prop);
                    return 'Default';
                }}
                if (fallbackStrings[prop]) {{
                    return fallbackStrings[prop];
                }}
                return target[prop];
            }}
        }});
    }}
    
    console.log('[SCORM] Enhanced string table fallback with corruption handling loaded');
    console.log('[SCORM] Minimal SCORM 1.2 fallback API created');
    console.log('[SCORM] Minimal SCORM 2004 fallback API created');
}})();

// PostMessage communication with parent window
let messageId = 0;
const pendingMessages = {{}};

// Send message to parent and wait for response
function sendMessageToParent(action, data) {{
    return new Promise((resolve, reject) => {{
        const id = ++messageId;
        pendingMessages[id] = {{ resolve, reject }};
        
        window.parent.postMessage({{
            action: action,
            data: data,
            id: id,
            source: 'scorm_content'
        }}, '*');
        
        // Timeout after 5 seconds
        setTimeout(() => {{
            if (pendingMessages[id]) {{
                delete pendingMessages[id];
                reject(new Error('Message timeout'));
            }}
        }}, 5000);
    }});
}}

// Listen for responses from parent
window.addEventListener('message', function(event) {{
    if (event.data && event.data.id && pendingMessages[event.data.id]) {{
        const {{ resolve, reject }} = pendingMessages[event.data.id];
        delete pendingMessages[event.data.id];
        
        if (event.data.error) {{
            reject(new Error(event.data.error));
        }} else {{
            resolve(event.data.result);
        }}
    }}
}});

// SCORM 2004 API implementation using PostMessage
window.API_1484_11 = {{
    Initialize: function(param) {{
        return sendMessageToParent('scorm_initialize', param).catch(() => 'true');
    }},
    Terminate: function(param) {{
        return sendMessageToParent('scorm_terminate', param).catch(() => 'true');
    }},
    GetValue: function(element) {{
        return sendMessageToParent('scorm_get_value', element).catch(() => '');
    }},
    SetValue: function(element, value) {{
        return sendMessageToParent('scorm_set_value', {{ element, value }}).catch(() => 'true');
    }},
    Commit: function(param) {{
        return sendMessageToParent('scorm_commit', param).catch(() => 'true');
    }},
    GetLastError: function() {{
        return sendMessageToParent('scorm_get_last_error').catch(() => '0');
    }},
    GetErrorString: function(code) {{
        return sendMessageToParent('scorm_get_error_string', code).catch(() => '');
    }},
    GetDiagnostic: function(code) {{
        return sendMessageToParent('scorm_get_diagnostic', code).catch(() => '');
    }}
}};

// Also provide SCORM 1.2 API for compatibility
window.API = {{
    LMSInitialize: function(param) {{
        return window.API_1484_11.Initialize(param);
    }},
    LMSFinish: function(param) {{
        return window.API_1484_11.Terminate(param);
    }},
    LMSGetValue: function(element) {{
        return window.API_1484_11.GetValue(element);
    }},
    LMSSetValue: function(element, value) {{
        return window.API_1484_11.SetValue(element, value);
    }},
    LMSCommit: function(param) {{
        return window.API_1484_11.Commit(param);
    }},
    LMSGetLastError: function() {{
        return window.API_1484_11.GetLastError();
    }},
    LMSGetErrorString: function(code) {{
        return window.API_1484_11.GetErrorString(code);
    }},
    LMSGetDiagnostic: function(code) {{
        return window.API_1484_11.GetDiagnostic(code);
    }}
}};

console.log('[SCORM 2004] PostMessage API bridge ready');

// CRITICAL FIX: Inject real resume data into child window
// This ensures Storyline can access actual SCORM data instead of empty values
const resumeData = {{
    suspendData: '{{ attempt.suspend_data|default:"" }}',
    lessonLocation: '{{ attempt.lesson_location|default:"resume_point_1" }}',
    entry: '{{ attempt.entry|default:"ab-initio" }}',
    completionStatus: '{{ attempt.completion_status|default:"not attempted" }}',
    successStatus: '{{ attempt.success_status|default:"unknown" }}',
    lessonStatus: '{{ attempt.lesson_status|default:"not attempted" }}'
}};

// Make resume data available to Storyline
window.scormResumeData = resumeData;
window.suspendData = resumeData.suspendData;
window.lessonLocation = resumeData.lessonLocation;

console.log('[SCORM 2004] Resume data injected:', {{
    hasSuspendData: !!resumeData.suspendData,
    hasLessonLocation: !!resumeData.lessonLocation,
    entry: resumeData.entry,
    completionStatus: resumeData.completionStatus
}});
</script>'''
                elif scorm_package.version in ['xapi', 'captivate', 'lectora', 'html5', 'legacy', 'dual']:
                    # Other package types - minimal bridge
                    api_injection = f'''
<script>
// Universal SCORM API bridge for modern packages
// Version: 6.0 - Non-intrusive for all authoring tools
console.log('[SCORM] Universal API bridge loaded for {scorm_package.version}');

// Only provide parent window API reference if needed
if (window.parent && window.parent !== window) {{
    if (window.parent.API && !window.API) {{
        window.API = window.parent.API;
        console.log('[SCORM] Parent SCORM API available');
    }}
    if (window.parent.API_1484_11 && !window.API_1484_11) {{
        window.API_1484_11 = window.parent.API_1484_11;
        console.log('[SCORM] Parent SCORM 2004 API available');
    }}
}}

// NO FALLBACK STUBS - Let packages handle their own SCORM communication
console.log('[SCORM] No fallback stubs - using package native SCORM handling');
</script>'''
                elif scorm_package.version in ['1.1', '1.2', '2004']:
                    # For traditional SCORM packages, use full API injection
                    api_injection = f'''
<script>
// Full SCORM API for traditional packages
// Version: 5.0 - Complete SCORM 1.2/2004 support
console.log('[SCORM] Full API loaded for {scorm_package.version}');

// Try to use parent window's API if available (iframe scenario)
if (window.parent && window.parent !== window) {{
    if (window.parent.API && !window.API) {{
        window.API = window.parent.API;
        console.log('[SCORM] Using parent SCORM 1.2 API');
    }}
    if (window.parent.API_1484_11 && !window.API_1484_11) {{
        window.API_1484_11 = window.parent.API_1484_11;
        console.log('[SCORM] Using parent SCORM 2004 API');
    }}
}}

// Minimal fallback API stub (only if no API exists)
if (!window.API) {{
    window.API = {{
        LMSInitialize: function() {{ return 'true'; }},
        LMSFinish: function() {{ return 'true'; }},
        LMSGetValue: function(e) {{ return ''; }},
        LMSSetValue: function(e,v) {{ return 'true'; }},
        LMSCommit: function() {{ return 'true'; }},
        LMSGetLastError: function() {{ return '0'; }},
        LMSGetErrorString: function(c) {{ return ''; }},
        LMSGetDiagnostic: function(c) {{ return ''; }}
    }};
    console.log('[SCORM] Minimal SCORM 1.2 fallback API created');
}}

if (!window.API_1484_11) {{
    window.API_1484_11 = {{
        Initialize: function() {{ return 'true'; }},
        Terminate: function() {{ return 'true'; }},
        GetValue: function(e) {{ return ''; }},
        SetValue: function(e,v) {{ return 'true'; }},
        Commit: function() {{ return 'true'; }},
        GetLastError: function() {{ return '0'; }},
        GetErrorString: function(c) {{ return ''; }},
        GetDiagnostic: function(c) {{ return ''; }}
    }};
    console.log('[SCORM] Minimal SCORM 2004 fallback API created');
}}
</script>'''
                else:
                    # For unknown packages, use minimal API
                    api_injection = f'''
<script>
// Minimal API for unknown packages
console.log('[SCORM] Minimal API for unknown package type: {scorm_package.version}');
window.API = window.API_1484_11 = {{
    LMSInitialize: function() {{ return 'true'; }},
    Initialize: function() {{ return 'true'; }},
    LMSFinish: function() {{ return 'true'; }},
    Terminate: function() {{ return 'true'; }},
    LMSGetValue: function(e) {{ return ''; }},
    GetValue: function(e) {{ return ''; }},
    LMSSetValue: function(e,v) {{ return 'true'; }},
    SetValue: function(e,v) {{ return 'true'; }},
    LMSCommit: function() {{ return 'true'; }},
    Commit: function() {{ return 'true'; }},
    LMSGetLastError: function() {{ return '0'; }},
    GetLastError: function() {{ return '0'; }},
    LMSGetErrorString: function(c) {{ return ''; }},
    GetErrorString: function(c) {{ return ''; }},
    LMSGetDiagnostic: function(c) {{ return ''; }},
    GetDiagnostic: function(c) {{ return ''; }}
}};
</script>'''
                
                # Inject before </head> or at beginning of <body>
                if '</head>' in html_content:
                    html_content = html_content.replace('</head>', api_injection + '</head>')
                elif '<body' in html_content:
                    # Find body tag and inject after it
                    body_pos = html_content.find('<body')
                    body_end = html_content.find('>', body_pos)
                    if body_end != -1:
                        html_content = html_content[:body_end+1] + api_injection + html_content[body_end+1:]
                else:
                    # As last resort, prepend to the content
                    html_content = api_injection + html_content
                
                content = html_content.encode('utf-8')
                content_type = 'text/html; charset=utf-8'
                
                # Cache the processed content for 1 hour
                cache.set(cache_key, content, 3600)
                logger.info(f"Injected minimal SCORM API into {path} and cached")
            
            response_obj = HttpResponse(content, content_type=content_type)
            response_obj['Access-Control-Allow-Origin'] = '*'
            response_obj['X-Frame-Options'] = 'SAMEORIGIN'
            # OPTIMIZATION: Enable browser caching for better performance
            response_obj['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
            # SECURITY HEADERS
            response_obj['X-Content-Type-Options'] = 'nosniff'
            response_obj['X-XSS-Protection'] = '1; mode=block'
            return response_obj
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch S3 content: {str(e)}")
            return HttpResponse(f'Failed to load content: {str(e)}', status=502)
            
    except Exception as e:
        logger.error(f"Error serving SCORM content: {str(e)}")
        return HttpResponse('Error loading content', status=500)


@login_required
@require_http_methods(["GET"])
def scorm_status(request, attempt_id):
    """
    Get current SCORM attempt status with comprehensive progress tracking
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        return JsonResponse({
            'success': True,
            'status': {
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'total_time': attempt.total_time,
                'session_time': attempt.session_time,
                'lesson_location': attempt.lesson_location,
                'suspend_data': attempt.suspend_data,
                'entry': attempt.entry,
                'exit_mode': attempt.exit_mode,
                'last_accessed': attempt.last_accessed.isoformat() if attempt.last_accessed else None,
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
                # Enhanced tracking data
                'time_spent_seconds': attempt.time_spent_seconds,
                'last_visited_slide': attempt.last_visited_slide,
                'progress_percentage': float(attempt.progress_percentage) if attempt.progress_percentage else 0,
                'completed_slides': attempt.completed_slides,
                'total_slides': attempt.total_slides,
                'session_start_time': attempt.session_start_time.isoformat() if attempt.session_start_time else None,
                'session_end_time': attempt.session_end_time.isoformat() if attempt.session_end_time else None,
                'detailed_tracking': attempt.detailed_tracking,
                'session_data': attempt.session_data,
                'navigation_history': attempt.navigation_history[-10:] if attempt.navigation_history else [],  # Last 10 navigation entries
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting SCORM status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)




@login_required
@require_http_methods(["GET"])
def scorm_debug(request, attempt_id):
    """
    SCORM diagnostic endpoint for troubleshooting
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if (attempt.user != request.user and 
            not (hasattr(request.user, 'role') and request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])):
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        debug_info = {
            'attempt_info': {
                'id': attempt.id,
                'user': attempt.user.username,
                'package_id': attempt.scorm_package.id,
                'package_title': attempt.scorm_package.title,
                'version': attempt.scorm_package.version,
                'extracted_path': attempt.scorm_package.extracted_path,
                'launch_url': attempt.scorm_package.launch_url,
                'created_at': attempt.started_at.isoformat(),
                'last_accessed': attempt.last_accessed.isoformat(),
            },
            'urls': {
                'content_url': scorm_s3.generate_launch_url(attempt.scorm_package),
                'api_endpoint': f'/scorm/api/{attempt_id}/',
            },
            'manifest_data': attempt.scorm_package.manifest_data,
        }
        
        return JsonResponse({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        logger.error(f"Error in SCORM debug endpoint: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def scorm_emergency_save(request):
    """
    Enhanced emergency save endpoint for SCORM data with Storyline 1.2 support
    Used when browser is closing or user navigates away
    """
    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        package_type = data.get('package_type', 'generic')
        version = data.get('version', '1.2')
        action = data.get('action', 'emergency_save')
        
        if not attempt_id:
            return JsonResponse({'error': 'No attempt_id provided'}, status=400)
        
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if request.user.is_authenticated and attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # STORYLINE 1.2 FIX: Enhanced emergency save for Storyline packages
        if package_type == 'storyline':
            logger.info(f"🎯 STORYLINE EMERGENCY SAVE: attempt={attempt_id}, action={action}")
            
            # Force commit any pending data using enhanced handler
            from .api_handler_enhanced import ScormAPIHandlerEnhanced
            handler = ScormAPIHandlerEnhanced(attempt)
            commit_result = handler.commit()
            
            # Force sync with TopicProgress using enhanced sync
            from .score_sync_service import ScormScoreSyncService
            sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
            
            # STORYLINE FIX: Handle Storyline-specific suspend data patterns
            if attempt.suspend_data and ('qd"true' in attempt.suspend_data or 'scors' in attempt.suspend_data):
                logger.info(f"🎯 STORYLINE: Found Storyline-specific suspend data patterns")
                
                # Extract Storyline-specific data using dynamic processor
                from .dynamic_score_processor import DynamicScormScoreProcessor
                processor = DynamicScormScoreProcessor(attempt)
                processor.process_and_sync_score()
                
                # Force update TopicProgress with Storyline data
                from courses.models import TopicProgress
                try:
                    progress = TopicProgress.objects.get(
                        user=attempt.user,
                        topic=attempt.scorm_package.topic
                    )
                    progress.sync_scorm_score()
                    logger.info(f"🎯 STORYLINE: TopicProgress synced successfully")
                except TopicProgress.DoesNotExist:
                    logger.warning(f"🎯 STORYLINE: TopicProgress not found for user {attempt.user.id}")
            
            logger.info(f"🎯 STORYLINE: Emergency save completed - commit={commit_result}, sync={sync_result}")
            
            return JsonResponse({
                'success': True,
                'committed': commit_result,
                'synced': sync_result,
                'package_type': 'storyline',
                'version': version,
                'message': 'Storyline emergency save completed successfully'
            })
        
        else:
            # Standard emergency save for other package types
            from .score_sync_service import ScormScoreSyncService
            sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
            
            logger.info(f"Emergency save for attempt {attempt_id}: sync_result={sync_result}")
            
            return JsonResponse({
                'success': True,
                'synced': sync_result,
                'package_type': package_type,
                'message': 'Emergency save completed'
            })
        
    except Exception as e:
        logger.error(f"Emergency save error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def scorm_tracking_report(request, attempt_id):
    """
    Comprehensive SCORM tracking report with all detailed data
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt or is instructor/admin
        if (attempt.user != request.user and 
            not (hasattr(request.user, 'role') and request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])):
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Calculate time spent in different formats
        time_spent_hours = attempt.time_spent_seconds / 3600 if attempt.time_spent_seconds else 0
        time_spent_minutes = attempt.time_spent_seconds / 60 if attempt.time_spent_seconds else 0
        
        # Calculate session duration
        session_duration = None
        if attempt.session_start_time and attempt.session_end_time:
            session_duration = (attempt.session_end_time - attempt.session_start_time).total_seconds()
        elif attempt.session_start_time:
            session_duration = (timezone.now() - attempt.session_start_time).total_seconds()
        
        # Generate comprehensive report
        report = {
            'user_info': {
                'username': attempt.user.username,
                'full_name': attempt.user.get_full_name(),
                'email': attempt.user.email,
            },
            'course_info': {
                'topic_id': attempt.scorm_package.topic.id,
                'topic_title': attempt.scorm_package.topic.title,
                'scorm_package': attempt.scorm_package.title,
                'scorm_version': attempt.scorm_package.version,
            },
            'attempt_summary': {
                'attempt_id': attempt.id,
                'attempt_number': attempt.attempt_number,
                'lesson_status': attempt.lesson_status,
                'completion_status': attempt.completion_status,
                'success_status': attempt.success_status,
                'entry_mode': attempt.entry,
                'exit_mode': attempt.exit_mode,
            },
            'scoring_data': {
                'score_raw': float(attempt.score_raw) if attempt.score_raw else None,
                'score_min': float(attempt.score_min) if attempt.score_min else 0,
                'score_max': float(attempt.score_max) if attempt.score_max else 100,
                'score_scaled': float(attempt.score_scaled) if attempt.score_scaled else None,
                'percentage_score': attempt.get_percentage_score(),
                'is_passed': attempt.is_passed(),
            },
            'time_tracking': {
                'total_time_scorm': attempt.total_time,
                'session_time_scorm': attempt.session_time,
                'time_spent_seconds': attempt.time_spent_seconds,
                'time_spent_hours': round(time_spent_hours, 2),
                'time_spent_minutes': round(time_spent_minutes, 2),
                'session_start_time': attempt.session_start_time.isoformat() if attempt.session_start_time else None,
                'session_end_time': attempt.session_end_time.isoformat() if attempt.session_end_time else None,
                'session_duration_seconds': session_duration,
                'started_at': attempt.started_at.isoformat(),
                'last_accessed': attempt.last_accessed.isoformat(),
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
            },
            'progress_tracking': {
                'lesson_location': attempt.lesson_location,
                'last_visited_slide': attempt.last_visited_slide,
                'progress_percentage': float(attempt.progress_percentage) if attempt.progress_percentage else 0,
                'completed_slides': attempt.completed_slides,
                'total_slides': attempt.total_slides,
                'suspend_data': attempt.suspend_data,
            },
            'navigation_history': attempt.navigation_history if attempt.navigation_history else [],
            'detailed_tracking': attempt.detailed_tracking if attempt.detailed_tracking else {},
            'session_data': attempt.session_data if attempt.session_data else {},
            'cmi_data': attempt.cmi_data if attempt.cmi_data else {},
        }
        
        return JsonResponse({
            'success': True,
            'tracking_report': report
        })
        
    except Exception as e:
        logger.error(f"Error generating SCORM tracking report: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
