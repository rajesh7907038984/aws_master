"""
Universal SCORM Handler
Handles all SCORM package types with a single comprehensive implementation
"""
import logging
import json
import mimetypes
import os
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse, Http404, FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings

from .models import ScormPackage, ScormAttempt
from courses.models import Topic

logger = logging.getLogger(__name__)


@login_required
def scorm_view(request, topic_id):
    """
    Universal SCORM content viewer
    Handles all SCORM package types with auto-detection
    """
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check if user has permission to access this topic's course
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    if not topic.user_has_access(request.user) and not is_instructor_or_admin:
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
                # Continue existing attempt to preserve progress and location
                attempt = last_attempt
                logger.info(f"Continuing existing attempt {attempt.attempt_number} for user {request.user.username}")
            else:
                # Create first attempt only if no previous attempt exists
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
                )
                logger.info(f"Created new attempt {attempt.attempt_number} for user {request.user.username}")
        
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
            logger.info(f"Setting entry='resume' (bookmark={has_bookmark}, suspend_data={has_suspend_data}, progress={has_progress})")
        else:
            attempt.entry = 'ab-initio'
            logger.info(f"Setting entry='ab-initio' (fresh start)")
    
    # Generate content URL using Django proxy (for iframe compatibility)
    launch_path = scorm_package.launch_url.strip()
    if not launch_path:
        launch_path = 'index.html'  # Default fallback
    # Remove leading slash if present to avoid double slashes
    if launch_path.startswith('/'):
        launch_path = launch_path[1:]
    content_url = f'/scorm/content/{topic_id}/{launch_path}?attempt_id={attempt_id}'
    
    # Check if resume is needed
    resume_needed = attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted')
    
    # Universal SCORM handling: Use query parameters for resume
    if resume_needed:
        content_url += '&resume=true'
        if attempt.lesson_location:
            content_url += f'&location={attempt.lesson_location}'
        if attempt.suspend_data:
            content_url += f'&suspend_data={attempt.suspend_data[:100]}'  # First 100 chars
        logger.info(f"Added resume parameters to content URL")
    
    # Handle bookmark/hash fragments for all SCORM packages
    hash_fragment = None
    bookmark_applied = False
    
    # Case 1: Regular bookmark with or without hash
    if attempt.lesson_location:
        # Handle lesson locations (avoid double hash)
        if attempt.lesson_location.startswith('#'):
            hash_fragment = attempt.lesson_location  # Already has hash
        else:
            hash_fragment = f'#{attempt.lesson_location}'  # Add hash
        logger.info(f"Set location hash fragment: {hash_fragment}")
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
            r'slideId[=:]([^&]+)',               # slideId=slide3
            r'#?/?lessons/([a-zA-Z0-9_-]+)',     # Rise 360 pattern
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
                    logger.info(f"Extracted bookmark '{extracted_location}' from suspend_data")
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
            logger.info(f"Created default location '{default_slide}' based on progress {progress}%")
            bookmark_applied = True
            
    # Case 3: Always ensure resume works
    if resume_needed and not bookmark_applied:
        # Final fallback - use slide_1 as a safe default
        attempt.lesson_location = 'slide_1'
        hash_fragment = '#slide_1'
        attempt.save()
        logger.info(f"Created failsafe default location 'slide_1'")
    
    # Add hash fragment ONLY ONCE at the end
    if hash_fragment:
        content_url += hash_fragment
        logger.info(f"Final content URL with hash: {content_url}")
    
    # Show the player template
    logger.info(f"Showing player template with content URL: {content_url}")
    
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


def scorm_content(request, topic_id, path):
    """Serve SCORM content files from S3 storage"""
    try:
        # Get the SCORM package
        topic = Topic.objects.get(id=topic_id)
        scorm_package = topic.scorm_package
        
        # Build the full path to the content file
        if not scorm_package.extracted_path:
            logger.error(f"SCORM package {scorm_package.id} has no extracted_path")
            raise Http404("SCORM content not found")
        
        # Clean the path to prevent directory traversal
        path = path.strip('/')
        if '..' in path or path.startswith('/'):
            logger.warning(f"Potential directory traversal attempt: {path}")
            raise Http404("Invalid path")
        
        # Build the full S3 path
        full_path = f"{scorm_package.extracted_path}/{path}"
        
        # Check if file exists in S3
        if not default_storage.exists(full_path):
            logger.warning(f"SCORM content file not found: {full_path}")
            raise Http404("SCORM content file not found")
        
        # Get file info
        file_size = default_storage.size(full_path)
        if file_size is None:
            logger.error(f"Could not get size for SCORM file: {full_path}")
            raise Http404("SCORM content file not accessible")
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(path)
        if not content_type:
            if path.endswith('.html') or path.endswith('.htm'):
                content_type = 'text/html'
            elif path.endswith('.js'):
                content_type = 'application/javascript'
            elif path.endswith('.css'):
                content_type = 'text/css'
            elif path.endswith('.json'):
                content_type = 'application/json'
            else:
                content_type = 'application/octet-stream'
        
        # Handle different file types
        if content_type.startswith('text/') or content_type == 'application/javascript' or content_type == 'application/json':
            # For text files, read content and serve with proper encoding
            try:
                with default_storage.open(full_path, 'r') as f:
                    content = f.read()
                
                response = HttpResponse(content, content_type=content_type)
                response['Content-Length'] = len(content.encode('utf-8'))
                
                # Set CORS headers for SCORM content
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                
                return response
            except Exception as e:
                logger.error(f"Error reading SCORM text file {full_path}: {str(e)}")
                raise Http404("Error reading SCORM content")
        else:
            # For binary files, use FileResponse
            try:
                file_obj = default_storage.open(full_path, 'rb')
                response = FileResponse(file_obj, content_type=content_type)
                response['Content-Length'] = file_size
                
                # Set CORS headers for SCORM content
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                
                return response
            except Exception as e:
                logger.error(f"Error serving SCORM binary file {full_path}: {str(e)}")
                raise Http404("Error serving SCORM content")
                
    except Topic.DoesNotExist:
        logger.error(f"Topic {topic_id} not found for SCORM content request")
        raise Http404("Topic not found")
    except Exception as e:
        logger.error(f"Error serving SCORM content for topic {topic_id}, path {path}: {str(e)}")
        raise Http404("SCORM content not available")


@csrf_exempt
@require_http_methods(["GET", "POST", "OPTIONS"])
def scorm_api(request, attempt_id):
    """Universal SCORM API endpoint for tracking and data exchange"""
    try:
        # Handle CORS preflight requests
        if request.method == 'OPTIONS':
            response = JsonResponse({})
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        
        # Get attempt (handle both database attempts and preview attempts)
        attempt = None
        is_preview = False
        
        # Check if it's a preview attempt
        if str(attempt_id).startswith('preview_'):
            preview_data = request.session.get(f'scorm_preview_{attempt_id}')
            if preview_data:
                is_preview = True
                # Create a mock attempt object for preview
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'user_id': preview_data['user_id'],
                    'scorm_package_id': preview_data['scorm_package_id'],
                    'is_preview': True,
                })()
            else:
                return JsonResponse({"error": "Preview attempt not found"}, status=404)
        else:
            # Get real attempt from database with related data
            try:
                attempt = ScormAttempt.objects.select_related(
                    'scorm_package',
                    'scorm_package__topic',
                    'user'
                ).get(id=attempt_id)
                # Refresh to ensure we have the absolute latest data (lesson_location, suspend_data, progress)
                attempt.refresh_from_db()
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Initialize API handler with fresh data
        from .api_handler import ScormAPIHandler
        api_handler = ScormAPIHandler(attempt)
        
        # Handle different API methods
        if request.method == 'GET':
            # Get SCORM data
            method = request.GET.get('method', '')
            if method:
                result = api_handler.get_value(method)
                return JsonResponse({"result": result})
            else:
                return JsonResponse({"error": "Method parameter required"})
        
        elif request.method == 'POST':
            # Parse SCORM API call
            data = json.loads(request.body.decode('utf-8'))
            method = data.get('method', '')
            parameters = data.get('parameters', [])
            
            if not method:
                return JsonResponse({"error": "Method parameter required"})
            
            # Route to appropriate handler method
            result = None
            try:
                # Initialize/Terminate methods
                if method in ['LMSInitialize', 'Initialize']:
                    result = api_handler.initialize()
                elif method in ['LMSFinish', 'Terminate']:
                    result = api_handler.terminate()
                elif method in ['LMSCommit', 'Commit']:
                    result = api_handler.commit()
                
                # Get methods
                elif method in ['LMSGetValue', 'GetValue']:
                    element = parameters[0] if parameters else ''
                    result = api_handler.get_value(element)
                elif method in ['LMSGetLastError', 'GetLastError']:
                    result = api_handler.get_last_error()
                elif method in ['LMSGetErrorString', 'GetErrorString']:
                    error_code = parameters[0] if parameters else '0'
                    result = api_handler.get_error_string(error_code)
                elif method in ['LMSGetDiagnostic', 'GetDiagnostic']:
                    error_code = parameters[0] if parameters else '0'
                    result = api_handler.get_diagnostic(error_code)
                
                # Set methods
                elif method in ['LMSSetValue', 'SetValue']:
                    element = parameters[0] if len(parameters) > 0 else ''
                    value = parameters[1] if len(parameters) > 1 else ''
                    result = api_handler.set_value(element, value)
                
                else:
                    logger.warning(f"Unknown SCORM API method: {method}")
                    return JsonResponse({"error": f"Unknown method: {method}"}, status=400)
                
                return JsonResponse({"success": True, "result": result})
                
            except Exception as e:
                logger.error(f"Error executing SCORM API method {method}: {str(e)}")
                return JsonResponse({"error": f"Error executing {method}"}, status=500)
        
    except Exception as e:
        logger.error(f"Error in SCORM API for attempt {attempt_id}: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def scorm_emergency_save(request):
    """Emergency save endpoint for SCORM data"""
    try:
        # Handle CORS preflight requests
        if request.method == 'OPTIONS':
            response = JsonResponse({})
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        
        # Parse request data
        data = json.loads(request.body.decode('utf-8'))
        attempt_id = data.get('attempt_id')
        scorm_data = data.get('scorm_data', {})
        
        if not attempt_id:
            return JsonResponse({"error": "attempt_id required"}, status=400)
        
        # Get attempt (handle both database attempts and preview attempts)
        attempt = None
        is_preview = False
        
        # Check if it's a preview attempt
        if str(attempt_id).startswith('preview_'):
            # For preview attempts, just store in session
            request.session[f'scorm_emergency_save_{attempt_id}'] = {
                'scorm_data': scorm_data,
                'timestamp': timezone.now().isoformat()
            }
            return JsonResponse({"status": "saved", "preview": True})
        else:
            # Get real attempt from database
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Save SCORM data to attempt
        if attempt:
            # Update attempt with emergency save data
            if 'lesson_status' in scorm_data:
                attempt.lesson_status = scorm_data['lesson_status']
            if 'completion_status' in scorm_data:
                attempt.completion_status = scorm_data['completion_status']
            if 'score_raw' in scorm_data:
                attempt.score_raw = scorm_data['score_raw']
            if 'lesson_location' in scorm_data:
                attempt.lesson_location = scorm_data['lesson_location']
            if 'suspend_data' in scorm_data:
                attempt.suspend_data = scorm_data['suspend_data']
            if 'total_time' in scorm_data:
                attempt.total_time = scorm_data['total_time']
            
            # Update CMI data
            if 'cmi_data' in scorm_data:
                attempt.cmi_data.update(scorm_data['cmi_data'])
            
            # Update session data
            if 'session_data' in scorm_data:
                attempt.session_data.update(scorm_data['session_data'])
            
            attempt.save()
            logger.info(f"Emergency save completed for attempt {attempt_id}")
            return JsonResponse({"status": "saved"})
        
    except Exception as e:
        logger.error(f"Error in emergency save: {str(e)}")
        return JsonResponse({"error": "Emergency save failed"}, status=500)


def scorm_status(request, attempt_id):
    """SCORM status endpoint"""
    try:
        # Get attempt (handle both database attempts and preview attempts)
        attempt = None
        is_preview = False
        
        # Check if it's a preview attempt
        if str(attempt_id).startswith('preview_'):
            preview_data = request.session.get(f'scorm_preview_{attempt_id}')
            if preview_data:
                is_preview = True
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'user_id': preview_data['user_id'],
                    'scorm_package_id': preview_data['scorm_package_id'],
                    'is_preview': True,
                    'lesson_status': 'not_attempted',
                    'completion_status': 'incomplete',
                    'score_raw': None,
                    'total_time': '0000:00:00.00',
                    'lesson_location': '',
                    'suspend_data': '',
                })()
            else:
                return JsonResponse({"error": "Preview attempt not found"}, status=404)
        else:
            # Get real attempt from database
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Return status information
        status_data = {
            'attempt_id': attempt.id,
            'is_preview': is_preview,
            'lesson_status': getattr(attempt, 'lesson_status', 'not_attempted'),
            'completion_status': getattr(attempt, 'completion_status', 'incomplete'),
            'score_raw': getattr(attempt, 'score_raw', None),
            'total_time': getattr(attempt, 'total_time', '0000:00:00.00'),
            'lesson_location': getattr(attempt, 'lesson_location', ''),
            'last_accessed': getattr(attempt, 'last_accessed', None),
            'started_at': getattr(attempt, 'started_at', None),
        }
        
        return JsonResponse(status_data)
        
    except Exception as e:
        logger.error(f"Error getting SCORM status for attempt {attempt_id}: {str(e)}")
        return JsonResponse({"error": "Status retrieval failed"}, status=500)


def scorm_debug(request, attempt_id):
    """SCORM debug endpoint"""
    try:
        # Get attempt (handle both database attempts and preview attempts)
        attempt = None
        is_preview = False
        
        # Check if it's a preview attempt
        if str(attempt_id).startswith('preview_'):
            preview_data = request.session.get(f'scorm_preview_{attempt_id}')
            if preview_data:
                is_preview = True
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'user_id': preview_data['user_id'],
                    'scorm_package_id': preview_data['scorm_package_id'],
                    'is_preview': True,
                    'cmi_data': {},
                    'session_data': {},
                    'detailed_tracking': {},
                })()
            else:
                return JsonResponse({"error": "Preview attempt not found"}, status=404)
        else:
            # Get real attempt from database
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Return debug information
        debug_data = {
            'attempt_id': attempt.id,
            'is_preview': is_preview,
            'cmi_data': getattr(attempt, 'cmi_data', {}),
            'session_data': getattr(attempt, 'session_data', {}),
            'detailed_tracking': getattr(attempt, 'detailed_tracking', {}),
            'scorm_package_id': getattr(attempt, 'scorm_package_id', None),
            'user_id': getattr(attempt, 'user_id', None),
        }
        
        return JsonResponse(debug_data)
        
    except Exception as e:
        logger.error(f"Error getting SCORM debug info for attempt {attempt_id}: {str(e)}")
        return JsonResponse({"error": "Debug info retrieval failed"}, status=500)


def scorm_tracking_report(request, attempt_id):
    """SCORM tracking report endpoint"""
    try:
        # Get attempt (handle both database attempts and preview attempts)
        attempt = None
        is_preview = False
        
        # Check if it's a preview attempt
        if str(attempt_id).startswith('preview_'):
            preview_data = request.session.get(f'scorm_preview_{attempt_id}')
            if preview_data:
                is_preview = True
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'user_id': preview_data['user_id'],
                    'scorm_package_id': preview_data['scorm_package_id'],
                    'is_preview': True,
                    'interactions': [],
                    'objectives': [],
                    'comments': [],
                })()
            else:
                return JsonResponse({"error": "Preview attempt not found"}, status=404)
        else:
            # Get real attempt from database
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Get related tracking data
        interactions = []
        objectives = []
        comments = []
        
        if not is_preview:
            # Get interactions
            interactions = list(attempt.interactions.values(
                'interaction_id', 'interaction_type', 'description', 
                'student_response', 'result', 'score_raw', 'timestamp'
            ))
            
            # Get objectives
            objectives = list(attempt.objectives.values(
                'objective_id', 'description', 'success_status', 
                'completion_status', 'score_raw', 'progress_measure'
            ))
            
            # Get comments
            comments = list(attempt.comments.values(
                'comment_type', 'comment_text', 'location', 'timestamp'
            ))
        
        # Return tracking report
        report_data = {
            'attempt_id': attempt.id,
            'is_preview': is_preview,
            'interactions': interactions,
            'objectives': objectives,
            'comments': comments,
            'total_interactions': len(interactions),
            'total_objectives': len(objectives),
            'total_comments': len(comments),
        }
        
        return JsonResponse(report_data)
        
    except Exception as e:
        logger.error(f"Error getting SCORM tracking report for attempt {attempt_id}: {str(e)}")
        return JsonResponse({"error": "Tracking report retrieval failed"}, status=500)
