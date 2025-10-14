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
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.clickjacking import xframe_options_exempt
from django.core.files.storage import default_storage
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from .models import ScormPackage, ScormAttempt
from .api_handler import ScormAPIHandler
from .preview_handler import ScormPreviewHandler
from .s3_direct import scorm_s3
from courses.models import Topic

logger = logging.getLogger(__name__)

# Configure detailed logging for SCORM operations
class ScormLogger:
    """Enhanced logging for SCORM operations"""
    
    @staticmethod
    def log_api_call(method, parameters, attempt_id, user_id=None):
        """Log SCORM API calls with context"""
        logger.info(f"📞 SCORM API: {method} | attempt_id={attempt_id} | user_id={user_id} | params={parameters[:2] if len(parameters) > 2 else parameters}")
    
    @staticmethod
    def log_score_sync(attempt_id, old_score, new_score, status):
        """Log score synchronization events"""
        logger.info(f"📊 SCORE SYNC: attempt_id={attempt_id} | {old_score} → {new_score} | status={status}")
    
    @staticmethod
    def log_content_access(topic_id, path, user_id=None, success=True):
        """Log content access events"""
        status = "✅" if success else "❌"
        logger.info(f"{status} CONTENT ACCESS: topic_id={topic_id} | path={path} | user_id={user_id}")
    
    @staticmethod
    def log_performance(operation, duration_ms, details=""):
        """Log performance metrics"""
        logger.info(f"⚡ PERFORMANCE: {operation} took {duration_ms}ms {details}")
    
    @staticmethod
    def log_error(operation, error, context=""):
        """Log errors with context"""
        logger.error(f"❌ ERROR in {operation}: {str(error)} | context: {context}")




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
            # CRITICAL FIX: Only create new attempt for truly completed courses, not partial completions
            # For Rise 360 courses, 'completed' status might mean one lesson completed, not entire course
            should_create_new_attempt = False
            
            if last_attempt:
                # Check if this is a truly completed course (not just one lesson)
                is_truly_completed = (
                    # Only create new attempt if:
                    # 1. Status is 'passed' (user passed the entire course)
                    # 2. Status is 'completed' AND completed_at is set (user finished entire course)
                    # 3. Status is 'failed' AND completed_at is set (user finished but failed)
                    (last_attempt.lesson_status == 'passed') or
                    (last_attempt.lesson_status == 'completed' and last_attempt.completed_at is not None) or
                    (last_attempt.lesson_status == 'failed' and last_attempt.completed_at is not None)
                )
                
                # For Rise 360 courses with lesson_location, check if user is at the end
                if last_attempt.lesson_location and '#/lessons/' in last_attempt.lesson_location:
                    # If user has lesson_location, they're in a multi-lesson course
                    # Only create new attempt if they truly completed everything
                    # For now, assume 'completed' with completed_at means truly done
                    should_create_new_attempt = is_truly_completed and last_attempt.completed_at is not None
                    logger.info(f"Rise 360 course detected - lesson_location: {last_attempt.lesson_location}, should_create_new: {should_create_new_attempt}")
                else:
                    # For other SCORM packages, use original logic
                    should_create_new_attempt = is_truly_completed
                    logger.info(f"Standard SCORM package - should_create_new: {should_create_new_attempt}")
            
            if should_create_new_attempt:
                # Create new attempt for truly completed courses
                attempt_number = last_attempt.attempt_number + 1
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=attempt_number
                )
                logger.info(f"Created new attempt {attempt.id} (previous status: {last_attempt.lesson_status}, completed: {last_attempt.completed_at is not None})")
                
                # Sync any existing scores for consistency
                from .score_sync_service import ScormScoreSyncService
                ScormScoreSyncService.sync_score(attempt)
            elif last_attempt:
                # Continue existing incomplete attempt - ensure resume data is loaded
                attempt = last_attempt
                
                # Load resume data into CMI data for proper resume functionality
                if attempt.lesson_location or attempt.suspend_data:
                    # Ensure CMI data is properly initialized with resume data
                    if not attempt.cmi_data:
                        attempt.cmi_data = {}
                    
                    # Load resume data into CMI data
                    if attempt.lesson_location:
                        if scorm_package.version == '1.2':
                            attempt.cmi_data['cmi.core.lesson_location'] = attempt.lesson_location
                        else:  # SCORM 2004
                            attempt.cmi_data['cmi.location'] = attempt.lesson_location
                    
                    if attempt.suspend_data:
                        if scorm_package.version == '1.2':
                            attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                        else:  # SCORM 2004
                            attempt.cmi_data['cmi.suspend_data'] = attempt.suspend_data
                    
                    # Set entry mode to resume
                    attempt.entry = 'resume'
                    if scorm_package.version == '1.2':
                        attempt.cmi_data['cmi.core.entry'] = 'resume'
                    else:  # SCORM 2004
                        attempt.cmi_data['cmi.entry'] = 'resume'
                
                # Save the updated attempt
                attempt.save()
                logger.info(f"RESUME: Loaded resume data for attempt {attempt.id}: entry='{attempt.entry}', location='{attempt.lesson_location}', suspend_data='{attempt.suspend_data[:50] if attempt.suspend_data else 'None'}...'")
            else:
                # Create first attempt
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
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
        if launch_url.startswith('/'):
            launch_url = launch_url[1:]  # Remove leading slash if present
        
        # CRITICAL FIX: Remove "scormcontent/" prefix if it already exists in launch_url
        # This prevents duplication like /scorm/content/121/scormcontent/scormcontent/index.html
        if launch_url.startswith('scormcontent/'):
            launch_url = launch_url[13:]  # Remove "scormcontent/" prefix (13 characters)
        
        # Get lesson ID from URL parameter first (for redirects), then from database
        lesson_id = ""
        
        # Check for lesson_id in URL parameters (from redirects)
        url_lesson_id = request.GET.get('lesson_id', '')
        if url_lesson_id and '#/lessons/' in url_lesson_id:
            lesson_id = url_lesson_id
            logger.info(f"Using lesson ID from URL parameter: {lesson_id}")
        else:
            # Get lesson ID from database if available
            if hasattr(attempt, 'lesson_location') and attempt.lesson_location and '#/lessons/' in attempt.lesson_location:
                lesson_id = attempt.lesson_location
                logger.info(f"Using lesson ID from database lesson_location: {lesson_id}")
            elif hasattr(attempt, 'cmi_data') and attempt.cmi_data:
                # Try to get from SCORM 1.2 cmi data
                if scorm_package.version == '1.2' and 'cmi.core.lesson_location' in attempt.cmi_data:
                    location = attempt.cmi_data.get('cmi.core.lesson_location', '')
                    if '#/lessons/' in location:
                        lesson_id = location
                        logger.info(f"Using lesson ID from SCORM 1.2 cmi_data: {lesson_id}")
                # Try to get from SCORM 2004 cmi data
                elif 'cmi.location' in attempt.cmi_data:
                    location = attempt.cmi_data.get('cmi.location', '')
                    if '#/lessons/' in location:
                        lesson_id = location
                        logger.info(f"Using lesson ID from SCORM 2004 cmi_data: {lesson_id}")
        
        # CRITICAL FIX: Clean lesson_id to ensure it only contains the hash fragment
        # Remove any filename prefix like "index.html#" to prevent duplication
        if lesson_id and '#' in lesson_id:
            # Extract only the hash part (e.g., "#/lessons/K-d9I0z0XgHP-W64WbJ6WjZCSgV5uiK8")
            hash_parts = lesson_id.split('#')
            # Get the last hash part (in case there are multiple # characters)
            lesson_id = '#' + hash_parts[-1] if hash_parts[-1] else ''
        
        content_url = f"/scorm/content/{topic_id}/{launch_url}"
        # Only add hash fragment if it contains a lesson ID
        if lesson_id and '#/lessons/' in lesson_id:
            content_url = f"{content_url}{lesson_id}"
        
        logger.info(f"Generated content URL: {content_url}")
    except Exception as e:
        logger.error(f"Error generating content URL: {str(e)}")
        content_url = f"/scorm/content/{topic_id}/index.html"
        # Try to add lesson ID even in fallback mode
        try:
            # Check URL parameter first, then database
            url_lesson_id = request.GET.get('lesson_id', '')
            if url_lesson_id and '#/lessons/' in url_lesson_id:
                lesson_hash = url_lesson_id
                content_url = f"{content_url}{lesson_hash}"
                logger.info(f"Added lesson ID from URL parameter to fallback URL: {lesson_hash}")
            elif hasattr(attempt, 'lesson_location') and attempt.lesson_location and '#/lessons/' in attempt.lesson_location:
                lesson_location = attempt.lesson_location
                # Clean lesson location to get only hash fragment
                if '#' in lesson_location:
                    hash_parts = lesson_location.split('#')
                    lesson_hash = '#' + hash_parts[-1] if hash_parts[-1] else ''
                    content_url = f"{content_url}{lesson_hash}"
                    logger.info(f"Added lesson ID from database to fallback URL: {lesson_hash}")
        except Exception as lesson_err:
            logger.error(f"Error adding lesson ID to fallback URL: {str(lesson_err)}")
    
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
    
    response = render(request, 'scorm/player.html', context)
    
    # Set permissive CSP headers for SCORM content
    response['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "worker-src 'self' blob: data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "style-src 'self' 'unsafe-inline' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "img-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "font-src 'self' data: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "connect-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "media-src 'self' data: blob: https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "frame-src 'self' https://*.s3.*.amazonaws.com https://*.amazonaws.com *; "
        "object-src 'none'"
    )
    
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    
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
        # Check if this is a preview attempt first
        session_key = f'scorm_preview_{attempt_id}'
        is_preview = hasattr(request, 'session') and session_key in request.session
        
        if is_preview:
            # Preview mode: Create temporary attempt from session data
            preview_data = request.session.get(session_key, {})
            
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
        data = json.loads(request.body)
        method = data.get('method')
        parameters = data.get('parameters', [])
        
        # Enhanced logging for API calls
        ScormLogger.log_api_call(method, parameters, attempt_id, request.user.id if request.user.is_authenticated else None)
        
        # Initialize appropriate API handler WITHOUT caching to ensure fresh data
        if is_preview:
            handler = ScormPreviewHandler(attempt)
            logger.info(f"Using preview handler for attempt {attempt_id}")
        else:
            # Refresh attempt from database to get latest data
            attempt.refresh_from_db()
            
            handler = ScormAPIHandler(attempt)
            logger.info(f"Created fresh handler for attempt {attempt_id} with latest database state")
        
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
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def scorm_content(request, topic_id=None, path=None, attempt_id=None):
    """
    Serve SCORM content files from S3 with optimized loading
    Uses direct S3 URLs for maximum performance
    Handles both topic_id and attempt_id parameters for backward compatibility
    Supports both authenticated and non-authenticated access for embedded content
    """
    try:
        # Handle both authenticated and non-authenticated access
        is_authenticated = request.user.is_authenticated
        
        # For non-authenticated users, check if this is embedded content
        if not is_authenticated:
            # Allow access to embedded SCORM content without authentication
            # This is needed for iframe embedding and external access
            logger.info(f"Non-authenticated access to SCORM content: topic_id={topic_id}, path={path}")
        else:
            logger.info(f"Authenticated access to SCORM content: user={request.user.username}, topic_id={topic_id}, path={path}")
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
            
            # SECURITY FIX: Verify user has access to this topic (only for authenticated users)
            if is_authenticated and not topic.user_has_access(request.user):
                return HttpResponse('Access denied - You do not have permission to access this content', status=403)
            
            # Get the current attempt for this user and topic
            from .models import ScormAttempt
            try:
                if is_authenticated:
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
        
        # OPTIMIZATION: For ALL files, redirect directly to S3 for maximum performance
        # The SCORM API is injected in the player template, not in individual content files
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(s3_url)
        
        # For HTML files, inject minimal SCORM API reference
        try:
            import requests
            from django.core.cache import cache
            
            # DISABLED: Skip cache check for development
            # cache_key = f"scorm_content_v3_{scorm_package.id}_{path}_{scorm_package.updated_at.timestamp()}"
            # cached_content = cache.get(cache_key)
            # 
            # if cached_content:
            #     logger.info(f"Serving cached content for {path}")
            #     response_obj = HttpResponse(cached_content, content_type='text/html; charset=utf-8')
            #     response_obj['Access-Control-Allow-Origin'] = '*'
            #     response_obj['X-Frame-Options'] = 'SAMEORIGIN'
            #     response_obj['Cache-Control'] = 'no-cache, no-store, must-revalidate'  # No cache for development
            #     return response_obj
            
            # Fetch from S3 with optimized timeout
            response = requests.get(s3_url, timeout=30)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get('content-type', 'text/html; charset=utf-8')
            
            # Inject lightweight SCORM API for HTML files
            if 'text/html' in content_type:
                html_content = content.decode('utf-8')
                
                # CRITICAL FIX: For xAPI/Tin Can packages (Articulate Storyline), 
                # don't inject complex SCORM code - just provide parent API reference
                if scorm_package.version == 'xapi':
                    # Minimal API bridge for xAPI content - doesn't interfere with Storyline
                    api_injection = '''
<script>
// Minimal API bridge for Tin Can/xAPI content
// Version: 4.1 - Non-intrusive for Articulate Storyline with exit button support
console.log('[xAPI] Minimal API bridge loaded');

// Only provide parent window API reference if needed
if (window.parent && window.parent !== window) {
    if (window.parent.API && !window.API) {
        window.API = window.parent.API;
        console.log('[xAPI] Parent SCORM API available');
    }
    if (window.parent.API_1484_11 && !window.API_1484_11) {
        window.API_1484_11 = window.parent.API_1484_11;
        console.log('[xAPI] Parent SCORM 2004 API available');
    }
}

// Minimal fallback API stub (only if no API exists)
if (!window.API && !window.API_1484_11) {
    window.API = window.API_1484_11 = {
        LMSInitialize: function() { return 'true'; },
        Initialize: function() { return 'true'; },
        LMSFinish: function() { return 'true'; },
        Terminate: function() { return 'true'; },
        LMSGetValue: function(e) { return ''; },
        GetValue: function(e) { return ''; },
        LMSSetValue: function(e,v) { return 'true'; },
        SetValue: function(e,v) { return 'true'; },
        LMSCommit: function() { return 'true'; },
        Commit: function() { return 'true'; },
        LMSGetLastError: function() { return '0'; },
        GetLastError: function() { return '0'; },
        LMSGetErrorString: function(c) { return ''; },
        GetErrorString: function(c) { return ''; },
        LMSGetDiagnostic: function(c) { return ''; },
        GetDiagnostic: function(c) { return ''; }
    };
    console.log('[xAPI] Minimal fallback API created');
}

// Enhanced exit button support for xAPI content
window.courseExit = function() {
    console.log('[xAPI] courseExit() called - sending exit message to parent');
    if (window.parent && window.parent !== window) {
        window.parent.postMessage({action: 'courseExit', type: 'exit'}, '*');
        window.parent.postMessage('exit_assessment', '*');
    }
};

// Let xAPI content handle its own exit buttons naturally
// Only provide courseExit function if content explicitly calls it
</script>'''
                else:
                    # For SCORM 1.2 and 2004 packages, also use minimal injection
                    # The heavy tracking code is handled in the player template
                    api_injection = '''
<script>
// Lightweight SCORM API - Points to parent window API
// Version: 4.1 - Simplified for all SCORM types with exit button support
console.log('[SCORM] API bridge loaded for content');

// Try to use parent window's API if available (iframe scenario)
if (window.parent && window.parent !== window) {
    if (window.parent.API && !window.API) {
        window.API = window.parent.API;
        console.log('[SCORM] Using parent SCORM 1.2 API');
    }
    if (window.parent.API_1484_11 && !window.API_1484_11) {
        window.API_1484_11 = window.parent.API_1484_11;
        console.log('[SCORM] Using parent SCORM 2004 API');
    }
}

// Minimal fallback API stub (only if no API exists)
if (!window.API) {
    window.API = {
        LMSInitialize: function() { return 'true'; },
        LMSFinish: function() { return 'true'; },
        LMSGetValue: function(e) { return ''; },
        LMSSetValue: function(e,v) { return 'true'; },
        LMSCommit: function() { return 'true'; },
        LMSGetLastError: function() { return '0'; },
        LMSGetErrorString: function(c) { return ''; },
        LMSGetDiagnostic: function(c) { return ''; }
    };
    console.log('[SCORM] Minimal SCORM 1.2 fallback API created');
}

if (!window.API_1484_11) {
    window.API_1484_11 = {
        Initialize: function() { return 'true'; },
        Terminate: function() { return 'true'; },
        GetValue: function(e) { return ''; },
        SetValue: function(e,v) { return 'true'; },
        Commit: function() { return 'true'; },
        GetLastError: function() { return '0'; },
        GetErrorString: function(c) { return ''; },
        GetDiagnostic: function(c) { return ''; }
    };
    console.log('[SCORM] Minimal SCORM 2004 fallback API created');
}

// Enhanced exit button support for SCORM content
window.courseExit = function() {
    console.log('[SCORM] courseExit() called - sending exit message to parent');
    if (window.parent && window.parent !== window) {
        window.parent.postMessage({action: 'courseExit', type: 'exit'}, '*');
        window.parent.postMessage('exit_assessment', '*');
    }
};

// Let SCORM content handle its own exit buttons naturally
// Only provide courseExit function if SCORM explicitly calls it
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
                # DISABLED: No server-side cache for development
                # cache.set(cache_key, content, 3600)
                logger.info(f"Injected minimal SCORM API into {path} and cached")
            
            response_obj = HttpResponse(content, content_type=content_type)
            response_obj['Access-Control-Allow-Origin'] = '*'
            response_obj['X-Frame-Options'] = 'SAMEORIGIN'
            # OPTIMIZATION: Enable browser caching for better performance
            response_obj['Cache-Control'] = 'no-cache, no-store, must-revalidate'  # No cache for development
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
    Emergency save endpoint for SCORM data
    Used when browser is closing or user navigates away
    """
    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        
        if not attempt_id:
            return JsonResponse({'error': 'No attempt_id provided'}, status=400)
        
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # Verify user owns this attempt
        if request.user.is_authenticated and attempt.user != request.user:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Force score sync
        from .score_sync_service import ScormScoreSyncService
        sync_result = ScormScoreSyncService.sync_score(attempt, force=True)
        
        logger.info(f"Emergency save for attempt {attempt_id}: sync_result={sync_result}")
        
        return JsonResponse({
            'success': True,
            'synced': sync_result,
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
def scorm_content_simple(request, topic_id, path):
    """
    Simplified SCORM content serving without complex JavaScript injection
    
    IMPORTANT: For old URLs like /scorm/direct/31/scormcontent/index.html,
    redirect to the proper /scorm/view/ endpoint which handles SCORM properly.
    """
    try:
        from .models import ScormPackage
        from courses.models import Topic
        
        # REDIRECT old hardcoded URLs to proper SCORM player
        # URLs like: /scorm/direct/31/scormcontent/index.html
        # or: /scorm/direct/31/scormcontent/index.html#/lessons/K-d9I0z0XgHP-W64WbJ6WjZCSgV5uiK8
        if path.endswith('.html') or path.endswith('.htm'):
            # Check if there's a lesson ID in the path
            lesson_id = ""
            if '#/lessons/' in request.get_full_path():
                # Extract lesson ID from URL fragment
                full_path = request.get_full_path()
                lesson_part = full_path.split('#/lessons/')
                if len(lesson_part) > 1:
                    lesson_id = f"#/lessons/{lesson_part[1]}"
            
            # Preserve the lesson ID in the redirect URL if available
            redirect_url = reverse('scorm:view', kwargs={'topic_id': topic_id})
            if lesson_id:
                redirect_url += f"?lesson_id={lesson_id}"
            
            logger.info(f"Redirecting SCORM URL pattern to proper view: {redirect_url}")
            return HttpResponseRedirect(redirect_url)
        
        # Get the topic and package
        topic = Topic.objects.get(id=topic_id)
        scorm_package = ScormPackage.objects.get(topic=topic)
        
        # Clean up path
        path = path.lstrip('/')
        if '..' in path or path.startswith('/'):
            return HttpResponse('Invalid path', status=400)
        
        # Check if file exists in S3
        if not scorm_s3.verify_file_exists(scorm_package, path):
            logger.warning(f"File not found in S3: {path}, creating simple fallback content")
            
            # Create simple fallback content
            fallback_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>SCORM Content - {path}</title>
    <script>
        window.API = {{
            Initialize: function(param) {{ return 'true'; }},
            Terminate: function(param) {{ return 'true'; }},
            GetValue: function(element) {{ return ''; }},
            SetValue: function(element, value) {{ return 'true'; }},
            Commit: function(param) {{ return 'true'; }},
            GetLastError: function() {{ return '0'; }},
            GetErrorString: function(code) {{ return 'No error'; }},
            GetDiagnostic: function(code) {{ return 'No error'; }}
        }};
    </script>
</head>
<body>
    <h1>SCORM Content</h1>
    <p>File: {path}</p>
    <p>This is fallback content for missing SCORM files.</p>
    <button onclick="alert('SCORM API working!')">Test SCORM</button>
</body>
</html>'''
            
            response = HttpResponse(fallback_content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            return response
        
        # Generate S3 URL for existing files
        s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        if not s3_url:
            return HttpResponse('Content not found', status=404)
        
        # For non-HTML files, redirect to S3
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect(s3_url)
        
        # For HTML files, serve with simple SCORM API injection
        try:
            # Get content from S3
            content_path = f"{scorm_package.extracted_path}/{path}"
            if default_storage.exists(content_path):
                content = default_storage.open(content_path).read().decode('utf-8')
            else:
                # Fallback to S3 URL
                import requests
                response = requests.get(s3_url)
                content = response.text
            
            # Simple SCORM API injection
            simple_api = '''
<script>
window.API = {
    Initialize: function(param) { return 'true'; },
    Terminate: function(param) { return 'true'; },
    GetValue: function(element) { return ''; },
    SetValue: function(element, value) { return 'true'; },
    Commit: function(param) { return 'true'; },
    GetLastError: function() { return '0'; },
    GetErrorString: function(code) { return 'No error'; },
    GetDiagnostic: function(code) { return 'No error'; }
};
</script>'''
            
            # Inject API before closing head tag
            if '</head>' in content:
                content = content.replace('</head>', simple_api + '</head>')
            else:
                content = simple_api + content
            
            response = HttpResponse(content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            return response
            
        except Exception as e:
            logger.error(f"Error serving content: {e}")
            return HttpResponse('Error loading content', status=500)
            
    except Exception as e:
        logger.error(f"Error in scorm_content_simple: {e}")
        return HttpResponse('Error loading content', status=500)


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
