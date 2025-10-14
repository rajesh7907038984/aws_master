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
def scorm_api_test(request):
    """
    Diagnostic tool for testing SCORM API calls
    """
    return render(request, 'scorm/api_test.html')


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
    
    # ENHANCED AUTHENTICATION: Log user access for tracking
    logger.info(f"🔐 SCORM ACCESS: User {request.user.username} (ID: {request.user.id}) accessing topic {topic_id}")
    
    # OPTIMIZATION: Optimize database queries with select_related
    topic = get_object_or_404(
        Topic.objects.select_related('scorm_package'),
        id=topic_id
    )
    
    # ENHANCED AUTHENTICATION: Strict permission check for authenticated users
    if is_authenticated:
        # Check if user has permission to access this topic's course
        if not topic.user_has_access(request.user):
            logger.warning(f"❌ ACCESS DENIED: User {request.user.username} denied access to topic {topic_id}")
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
            logger.info(f"✅ ACCESS GRANTED: User {request.user.username} has access to topic {topic_id}")
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
            # Optimize database queries with select_related
            last_attempt = ScormAttempt.objects.select_related('scorm_package', 'user').filter(
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
                
                # CRITICAL FIX: Always set entry mode to 'resume' for existing attempts
                # This ensures learners return to their last location instead of fresh start
                attempt.entry = 'resume'
                
                # Load resume data into CMI data for proper resume functionality
                if not attempt.cmi_data:
                    attempt.cmi_data = {}
                
                # Always load resume data into CMI data, even if empty
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
                
                # CRITICAL FIX: Always set entry mode to resume in CMI data
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
        
        # ENHANCED BOOKMARK: Log bookmark data for debugging
        logger.info(f"🔖 BOOKMARK DEBUG: lesson_id='{lesson_id}', lesson_location='{attempt.lesson_location if hasattr(attempt, 'lesson_location') else 'N/A'}', suspend_data='{attempt.suspend_data[:50] if hasattr(attempt, 'suspend_data') and attempt.suspend_data else 'N/A'}...'")
        
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
    
    # Remove any conflicting CSP headers first
    for header in ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']:
        if header in response:
            del response[header]
    
    # CRITICAL FIX: CSP without 'unsafe-eval' for main player page
    # The iframe will have its own CSP that allows 'unsafe-eval' if needed
    response['Content-Security-Policy'] = (
        "default-src * 'unsafe-inline' data: blob:; "
        "script-src * 'unsafe-inline' data: blob:; "
        "worker-src * blob: data:; "
        "style-src * 'unsafe-inline'; "
        "img-src * data: blob:; "
        "font-src * data:; "
        "connect-src * 'self'; "
        "media-src * data: blob:; "
        "frame-src *; "
        "object-src 'none'"
    )
    
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
    
    return response


@login_required
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def scorm_api(request, attempt_id):
    """
    SCORM API endpoint
    Handles all SCORM API calls from content
    Supports both regular attempts and preview mode
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == "OPTIONS":
        response = JsonResponse({'status': 'ok'})
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        return response
    
    # CRITICAL: Log all incoming API requests for debugging
    logger.info(f"🔵 SCORM API CALLED: attempt_id={attempt_id}, method={request.method}, path={request.path}, content_type={request.content_type}")
    logger.info(f"🔵 Headers: {dict(request.headers)}")
    logger.info(f"🔵 Body preview: {request.body[:200] if request.body else 'Empty'}")
    
    # ENHANCED AUTHENTICATION: Strict user verification for SCORM API calls
    try:
        attempt = ScormAttempt.objects.select_related('user', 'scorm_package').get(id=attempt_id)
        logger.info(f"🔵 SCORM API: Found attempt {attempt_id} for user {attempt.user.username}")
        
        # ENHANCED SECURITY: Verify user authentication and ownership
        if not request.user.is_authenticated:
            logger.warning(f"❌ UNAUTHENTICATED: Unauthenticated request to attempt {attempt_id}")
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        if attempt.user != request.user:
            logger.warning(f"❌ UNAUTHORIZED: User {request.user.username} (ID: {request.user.id}) tried to access attempt {attempt_id} owned by {attempt.user.username} (ID: {attempt.user.id})")
            return JsonResponse({'error': 'Unauthorized - You can only access your own attempts'}, status=403)
        
        # ENHANCED TRACKING: Log successful API access
        logger.info(f"✅ SCORM API: User {request.user.username} (ID: {request.user.id}) accessing attempt {attempt_id}")
        
    except ScormAttempt.DoesNotExist:
        logger.error(f"❌ SCORM API: Attempt {attempt_id} not found")
        response = JsonResponse({'error': 'Attempt not found'}, status=404)
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
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
            if preview_data['user_id'] != request.user.id:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
                
        else:
            # Regular mode: Get database attempt
            attempt = get_object_or_404(ScormAttempt, id=attempt_id)
            
            # Verify user owns this attempt
            if attempt.user != request.user:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Parse request
        try:
            data = json.loads(request.body)
            method = data.get('method')
            parameters = data.get('parameters', [])
            
            # CRITICAL: Enhanced logging for ALL API calls
            logger.info(f"📞 SCORM API CALL: method={method}, params={parameters[:2] if len(parameters) > 2 else parameters}, attempt={attempt_id}")
            ScormLogger.log_api_call(method, parameters, attempt_id, request.user.id if request.user.is_authenticated else None)
        except json.JSONDecodeError as e:
            logger.error(f"❌ SCORM API: Invalid JSON in request body: {e}")
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        
        # Initialize appropriate API handler with session persistence
        if is_preview:
            handler = ScormPreviewHandler(attempt)
            logger.info(f"Using preview handler for attempt {attempt_id}")
        else:
            # Refresh attempt from database to get latest data
            attempt.refresh_from_db()
            
            handler = ScormAPIHandler(attempt)
            
            # CRITICAL FIX: Restore initialized state if previously initialized
            # Check if this attempt was already initialized in this session
            session_key = f'scorm_initialized_{attempt_id}'
            if session_key in request.session and request.session[session_key]:
                handler.initialized = True
                logger.info(f"Restored initialized state for attempt {attempt_id}")
            else:
                logger.info(f"Created fresh handler for attempt {attempt_id}")
        
        # Route to appropriate API method
        if method == 'Initialize' or method == 'LMSInitialize':
            result = handler.initialize()
            # CRITICAL FIX: Store initialized state in session for future calls
            if result == 'true' and not is_preview:
                session_key = f'scorm_initialized_{attempt_id}'
                request.session[session_key] = True
                logger.info(f"Stored initialized state in session for attempt {attempt_id}")
        elif method == 'Terminate' or method == 'LMSFinish':
            result = handler.terminate()
            # CRITICAL FIX: Clear initialized state on terminate
            if not is_preview:
                session_key = f'scorm_initialized_{attempt_id}'
                request.session.pop(session_key, None)
                logger.info(f"Cleared initialized state for attempt {attempt_id}")
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
        
        response = JsonResponse({
            'success': True,
            'result': result,
            'error_code': handler.last_error
        })
        # Add CORS headers to response
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        return response
        
    except Exception as e:
        logger.error(f"❌ SCORM API error: {str(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        response = JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        # Add CORS headers to error response
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        return response


def scorm_content(request, topic_id=None, path=None, attempt_id=None):
    """
    Serve SCORM content files from S3 with optimized loading
    Uses direct S3 URLs for maximum performance
    Handles both topic_id and attempt_id parameters for backward compatibility
    ENHANCED: Requires authentication for all SCORM content access
    """
    try:
        # ENHANCED AUTHENTICATION: Require authentication for all SCORM content access
        if not request.user.is_authenticated:
            logger.warning(f"❌ UNAUTHENTICATED ACCESS: Attempted access to SCORM content without authentication")
            return HttpResponse('Authentication required to access SCORM content', status=401)
        
        is_authenticated = True
        logger.info(f"✅ AUTHENTICATED ACCESS: User {request.user.username} (ID: {request.user.id}) accessing SCORM content: topic_id={topic_id}, path={path}")
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
        
        # CRITICAL FIX: Proxy JavaScript and JSON files to avoid CORB
        # For other files (images, videos, etc.), redirect to S3
        should_proxy = path.endswith(('.html', '.htm', '.js', '.json', '.xml'))
        
        if not should_proxy:
            # Images, videos, fonts, etc. - redirect directly to S3
            from django.http import HttpResponseRedirect
            response = HttpResponseRedirect(s3_url)
            # Set minimal headers for redirect
            response['Access-Control-Allow-Origin'] = '*'
            return response
        
        # For HTML/JS/JSON files, proxy through Django with proper headers
        try:
            import requests
            from django.core.cache import cache
            
            # Fetch from S3 with optimized timeout
            response = requests.get(s3_url, timeout=30)
            response.raise_for_status()
            
            content = response.content
            
            # Determine proper Content-Type based on file extension
            if path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif path.endswith('.json'):
                content_type = 'application/json; charset=utf-8'
            elif path.endswith('.xml'):
                content_type = 'application/xml; charset=utf-8'
            else:
                content_type = response.headers.get('content-type', 'text/html; charset=utf-8')
            
            # For JavaScript and JSON files, serve directly with proper headers
            if path.endswith(('.js', '.json')):
                response_obj = HttpResponse(content, content_type=content_type)
                
                # Remove any conflicting security headers
                for header in ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']:
                    if header in response_obj:
                        del response_obj[header]
                
                # Set comprehensive CSP that allows everything SCORM needs
                response_obj['Content-Security-Policy'] = (
                    "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                    "script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                    "worker-src * blob: data:; "
                    "style-src * 'unsafe-inline'; "
                    "connect-src *"
                )
                
                # CORS headers for cross-origin access
                response_obj['Access-Control-Allow-Origin'] = '*'
                response_obj['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
                response_obj['Access-Control-Allow-Headers'] = '*'
                response_obj['Access-Control-Expose-Headers'] = '*'
                
                # Frame and caching headers
                response_obj['X-Frame-Options'] = 'SAMEORIGIN'
                response_obj['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
                
                # Remove X-Content-Type-Options for JS files to prevent CORB
                if 'X-Content-Type-Options' in response_obj:
                    del response_obj['X-Content-Type-Options']
                
                logger.info(f"Serving JavaScript file {path} with proper headers")
                return response_obj
            
            # Inject lightweight SCORM API for HTML files
            if 'text/html' in content_type:
                html_content = content.decode('utf-8')
                
                # CRITICAL FIX: Use Django proxy URL instead of direct S3 URL
                # This ensures all resources go through Django which generates presigned URLs
                # Extract the directory path from the requested file
                if '/' in path:
                    dir_path = '/'.join(path.split('/')[:-1]) + '/'
                else:
                    dir_path = ''
                
                # Use Django proxy endpoint as base URL to avoid S3 Access Denied errors
                base_url = f"/scorm/content/{topic_id}/{dir_path}"
                base_tag = f'<base href="{base_url}">'
                
                # CRITICAL FIX: Inject CSP meta tag to allow 'unsafe-eval' ONLY in iframe
                csp_meta_tag = '''<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; connect-src *;">'''
                
                # Inject both CSP and base tag right after <head> tag
                injection = f'\n    {csp_meta_tag}\n    {base_tag}'
                if '<head>' in html_content:
                    html_content = html_content.replace('<head>', f'<head>{injection}', 1)
                elif '<HEAD>' in html_content:
                    html_content = html_content.replace('<HEAD>', f'<HEAD>{injection}', 1)
                
                logger.info(f"Injected CSP meta tag and base tag with Django proxy URL: {base_url}")
                
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
                
                logger.info(f"Injected minimal SCORM API into {path}")
            
            response_obj = HttpResponse(content, content_type=content_type)
            
            # Remove any conflicting security headers
            for header in ['Content-Security-Policy', 'Content-Security-Policy-Report-Only', 'X-Content-Security-Policy']:
                if header in response_obj:
                    del response_obj[header]
            
            # Set comprehensive CSP headers for SCORM content
            response_obj['Content-Security-Policy'] = (
                "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
                "worker-src * blob: data:; "
                "style-src * 'unsafe-inline'; "
                "img-src * data: blob:; "
                "font-src * data:; "
                "connect-src *; "
                "media-src * data: blob:; "
                "frame-src *; "
                "object-src 'none'"
            )
            
            # CORS headers for cross-origin access
            response_obj['Access-Control-Allow-Origin'] = '*'
            response_obj['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response_obj['Access-Control-Allow-Headers'] = '*'
            response_obj['Access-Control-Expose-Headers'] = '*'
            
            # Frame and caching headers
            response_obj['X-Frame-Options'] = 'SAMEORIGIN'
            response_obj['Cache-Control'] = 'no-cache, no-store, must-revalidate'  # No cache for development
            
            # Security headers (relaxed for SCORM content)
            # Removed X-Content-Type-Options to allow SCORM content flexibility
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


@login_required
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


@login_required
def scorm_tracking_report(request, attempt_id):
    """
    Comprehensive SCORM tracking report with all detailed data
    ENHANCED: Provides complete learner progress tracking information
    """
    try:
        attempt = get_object_or_404(ScormAttempt, id=attempt_id)
        
        # ENHANCED AUTHENTICATION: Verify user owns this attempt or is instructor/admin
        if (attempt.user != request.user and 
            not (hasattr(request.user, 'role') and request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])):
            logger.warning(f"❌ UNAUTHORIZED TRACKING ACCESS: User {request.user.username} denied access to tracking report for attempt {attempt_id}")
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        logger.info(f"📊 TRACKING REPORT: User {request.user.username} accessing tracking data for attempt {attempt_id}")
        
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


@login_required
@require_http_methods(["GET"])
def learner_progress_dashboard(request, user_id=None):
    """
    ENHANCED: Comprehensive learner progress dashboard
    Shows all SCORM tracking data for a specific learner
    """
    try:
        # ENHANCED AUTHENTICATION: Check if user can access this data
        target_user_id = user_id or request.user.id
        
        # Users can only access their own data unless they're instructors/admins
        if (target_user_id != request.user.id and 
            not (hasattr(request.user, 'role') and request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin'])):
            logger.warning(f"❌ UNAUTHORIZED DASHBOARD ACCESS: User {request.user.username} denied access to dashboard for user {target_user_id}")
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        target_user = get_object_or_404(User, id=target_user_id)
        
        # Get all SCORM attempts for this user
        attempts = ScormAttempt.objects.filter(user=target_user).select_related(
            'scorm_package', 'scorm_package__topic'
        ).order_by('-started_at')
        
        # Calculate comprehensive progress statistics
        total_attempts = attempts.count()
        completed_attempts = attempts.filter(lesson_status__in=['completed', 'passed']).count()
        in_progress_attempts = attempts.filter(lesson_status='incomplete').count()
        
        # Calculate total time spent across all attempts
        total_time_seconds = sum(attempt.time_spent_seconds or 0 for attempt in attempts)
        total_time_hours = total_time_seconds / 3600
        
        # Get recent activity (last 10 attempts)
        recent_attempts = attempts[:10]
        
        # Calculate completion rate
        completion_rate = (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0
        
        # Get detailed progress for each attempt
        detailed_progress = []
        for attempt in recent_attempts:
            progress_data = {
                'attempt_id': attempt.id,
                'course_title': attempt.scorm_package.title,
                'topic_title': attempt.scorm_package.topic.title,
                'status': attempt.lesson_status,
                'score': float(attempt.score_raw) if attempt.score_raw else None,
                'max_score': float(attempt.score_max) if attempt.score_max else 100,
                'percentage_score': attempt.get_percentage_score(),
                'time_spent_seconds': attempt.time_spent_seconds,
                'time_spent_hours': (attempt.time_spent_seconds / 3600) if attempt.time_spent_seconds else 0,
                'started_at': attempt.started_at.isoformat(),
                'last_accessed': attempt.last_accessed.isoformat(),
                'completed_at': attempt.completed_at.isoformat() if attempt.completed_at else None,
                'progress_percentage': float(attempt.progress_percentage) if attempt.progress_percentage else 0,
                'completed_slides': attempt.completed_slides,
                'total_slides': attempt.total_slides,
                'navigation_history_count': len(attempt.navigation_history) if attempt.navigation_history else 0,
                'is_passed': attempt.is_passed(),
            }
            detailed_progress.append(progress_data)
        
        dashboard_data = {
            'user_info': {
                'username': target_user.username,
                'full_name': target_user.get_full_name(),
                'email': target_user.email,
                'user_id': target_user.id,
            },
            'summary_statistics': {
                'total_attempts': total_attempts,
                'completed_attempts': completed_attempts,
                'in_progress_attempts': in_progress_attempts,
                'completion_rate': round(completion_rate, 2),
                'total_time_seconds': total_time_seconds,
                'total_time_hours': round(total_time_hours, 2),
            },
            'detailed_progress': detailed_progress,
            'recent_activity': recent_attempts.count(),
        }
        
        logger.info(f"📊 LEARNER DASHBOARD: Generated progress dashboard for user {target_user.username}")
        
        return JsonResponse({
            'success': True,
            'dashboard_data': dashboard_data
        })
        
    except Exception as e:
        logger.error(f"Error generating learner progress dashboard: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
