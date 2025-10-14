"""
Universal SCORM Handler - Complete Implementation
Single file containing views, API handler, and player template
Handles all SCORM package types
"""
import logging
import json
import mimetypes
import os
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import quote as urlquote

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


class ScormAPIHandler:
    """
    Universal SCORM API Handler
    Implements both SCORM 1.2 and SCORM 2004 Runtime API
    """
    
    # SCORM 1.2 Error codes
    SCORM_12_ERRORS = {
        '0': 'No error',
        '101': 'General exception',
        '201': 'Invalid argument error',
        '202': 'Element cannot have children',
        '203': 'Element not an array',
        '301': 'Not initialized',
        '401': 'Not implemented error',
        '402': 'Invalid set value',
        '403': 'Element is read only',
        '404': 'Element is write only',
        '405': 'Incorrect data type',
    }
    
    def __init__(self, attempt):
        """Initialize API handler with a ScormAttempt object"""
        self.attempt = attempt
        self.attempt_id = getattr(attempt, 'id', 'unknown')
        self.version = attempt.scorm_package.version
        self.last_error = '0'
        self.initialized = False
        
        # Always ensure CMI data is properly initialized
        if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
            self.attempt.cmi_data = self._initialize_cmi_data()
            self.attempt.save()
    
    def _initialize_cmi_data(self):
        """Initialize CMI data structure based on SCORM version"""
        if self.version == '1.2':
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': self.attempt.lesson_status or 'not attempted',
                'cmi.core.entry': self.attempt.entry,
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.core.total_time': self.attempt.total_time,
                'cmi.core.lesson_mode': 'normal',
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
            }
        else:  # SCORM 2004
            progress_measure = ''
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
            
            return {
                'cmi.learner_id': str(self.attempt.user.id),
                'cmi.learner_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.location': self.attempt.lesson_location or '',
                'cmi.credit': 'credit',
                'cmi.completion_status': self.attempt.completion_status,
                'cmi.success_status': self.attempt.success_status,
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.total_time': self.attempt.total_time,
                'cmi.session_time': self.attempt.session_time,
                'cmi.entry': self.attempt.entry,
                'cmi.exit': self.attempt.exit_mode or '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
                'cmi.progress_measure': progress_measure,
            }
    
    def get_value(self, element):
        """Get value from CMI data model"""
        try:
            if element in self.attempt.cmi_data:
                return self.attempt.cmi_data[element]
            return ''
        except Exception as e:
            logger.error(f"Error getting value for {element}: {str(e)}")
            return ''
    
    def set_value(self, element, value):
        """Set value in CMI data model"""
        try:
            # Update CMI data
            self.attempt.cmi_data[element] = str(value)
            
            # Update specific fields based on element
            if element == 'cmi.core.lesson_status' or element == 'cmi.completion_status':
                self.attempt.lesson_status = str(value)
            elif element == 'cmi.core.score.raw' or element == 'cmi.score.raw':
                try:
                    self.attempt.score_raw = Decimal(str(value))
                except:
                    pass
            elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                self.attempt.lesson_location = str(value)
            elif element == 'cmi.suspend_data':
                self.attempt.suspend_data = str(value)
            elif element == 'cmi.core.total_time' or element == 'cmi.total_time':
                self.attempt.total_time = str(value)
            
            # Save the attempt
            self.attempt.save()
            return 'true'
        except Exception as e:
            logger.error(f"Error setting value for {element}: {str(e)}")
            return 'false'
    
    def initialize(self):
        """LMSInitialize / Initialize"""
        if self.initialized:
            self.last_error = '101'
            logger.warning(f"SCORM API already initialized for attempt {self.attempt_id}")
            return 'false'
        
        self.initialized = True
        self.last_error = '0'
        logger.info(f"SCORM API initialized for attempt {self.attempt_id}")
        return 'true'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning(f"SCORM API terminate called before initialization for attempt {self.attempt_id}")
            return 'false'
        
        # Save final data
        try:
            self.attempt.save()
            logger.info(f"SCORM API terminated for attempt {self.attempt_id}")
        except Exception as e:
            logger.error(f"Error saving attempt on terminate: {str(e)}")
        
        self.initialized = False
        self.last_error = '0'
        return 'true'
    
    def commit(self):
        """LMSCommit / Commit"""
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        try:
            self.attempt.save()
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error(f"Error committing data for attempt {self.attempt_id}: {str(e)}")
            self.last_error = '101'
            return 'false'
    
    def get_last_error(self):
        """LMSGetLastError / GetLastError"""
        return self.last_error
    
    def get_error_string(self, error_code):
        """LMSGetErrorString / GetErrorString"""
        return self.SCORM_12_ERRORS.get(str(error_code), 'Unknown error')
    
    def get_diagnostic(self, error_code):
        """LMSGetDiagnostic / GetDiagnostic"""
        return f"Diagnostic for error {error_code}"


# SCORM Views
@login_required
def scorm_view(request, topic_id):
    """Universal SCORM content viewer"""
    topic = get_object_or_404(Topic, id=topic_id)
    
    # Check permissions
    is_instructor_or_admin = request.user.role in ['instructor', 'admin', 'superadmin', 'globaladmin']
    
    if not topic.user_has_access(request.user) and not is_instructor_or_admin:
        messages.error(request, "You need to be enrolled in this course to access the SCORM content.")
        return redirect('courses:course_list')
    
    # Check SCORM package
    try:
        scorm_package = topic.scorm_package
    except ScormPackage.DoesNotExist:
        messages.error(request, "SCORM package not found for this topic")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    if not scorm_package.extracted_path or not scorm_package.launch_url:
        messages.error(request, "SCORM content configuration is incomplete.")
        return redirect('courses:topic_view', topic_id=topic_id)
    
    # Handle attempt creation/retrieval
    attempt = None
    attempt_id = None
    
    # Check for preview mode
    preview_mode = request.GET.get('preview', '').lower() == 'true'
    if preview_mode and not is_instructor_or_admin:
        preview_mode = False
    
    if preview_mode:
        # Preview mode
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
        
        request.session[f'scorm_preview_{attempt_id}'] = {
            'id': attempt_id,
            'user_id': request.user.id,
            'scorm_package_id': scorm_package.id,
            'is_preview': True,
            'created_at': timezone.now().isoformat(),
        }
    else:
        # Normal mode
        from django.db import transaction
        
        with transaction.atomic():
            last_attempt = ScormAttempt.objects.select_for_update().filter(
                user=request.user,
                scorm_package=scorm_package
            ).order_by('-attempt_number').first()
            
            if last_attempt:
                attempt = last_attempt
            else:
                attempt = ScormAttempt.objects.create(
                    user=request.user,
                    scorm_package=scorm_package,
                    attempt_number=1
                )
        
        attempt_id = attempt.id
        attempt.is_preview = False
        attempt.refresh_from_db()
        
        # Set entry mode
        has_bookmark = bool(attempt.lesson_location and len(attempt.lesson_location) > 0)
        has_suspend_data = bool(attempt.suspend_data and len(attempt.suspend_data) > 0)
        has_progress = attempt.lesson_status not in ['not_attempted', 'not attempted']
        
        if has_bookmark or has_suspend_data or has_progress:
            attempt.entry = 'resume'
        else:
            attempt.entry = 'ab-initio'
    
    # Generate content URL
    launch_path = scorm_package.launch_url.strip()
    if not launch_path:
        launch_path = 'index.html'
    if launch_path.startswith('/'):
        launch_path = launch_path[1:]
    content_url = f'/scorm/content/{topic_id}/{launch_path}?attempt_id={attempt_id}'
    
    # Add resume parameters if needed
    resume_needed = attempt.entry == 'resume' or (attempt.lesson_status != 'not_attempted' and attempt.lesson_status != 'not attempted')
    if resume_needed:
        content_url += '&resume=true'
        if attempt.lesson_location:
            encoded_location = urlquote(attempt.lesson_location, safe='')
            content_url += f'&location={encoded_location}'
        if attempt.suspend_data:
            # Include only a short, URL-safe preview of suspend_data to avoid breaking the query string
            encoded_suspend = urlquote(attempt.suspend_data[:100], safe='')
            content_url += f'&suspend_data={encoded_suspend}'
    
    # Handle bookmarks
    hash_fragment = None
    if attempt.lesson_location:
        if attempt.lesson_location.startswith('#'):
            hash_fragment = attempt.lesson_location
        else:
            hash_fragment = f'#{attempt.lesson_location}'
    
    if hash_fragment:
        content_url += hash_fragment
    
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
    
    response['X-Frame-Options'] = 'SAMEORIGIN'
    response['Access-Control-Allow-Origin'] = '*'
    
    return response


def scorm_content(request, topic_id, path):
    """Serve SCORM content files from S3 storage"""
    try:
        topic = Topic.objects.get(id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package.extracted_path:
            raise Http404("SCORM content not found")
        
        # Clean the path
        path = path.strip('/')
        if '..' in path or path.startswith('/'):
            raise Http404("Invalid path")
        
        # If path is a directory (no file extension), append index.html
        if path and '.' not in path.split('/')[-1]:
            # Check if we're requesting a directory - append index.html
            if not path.endswith('/'):
                path = path + '/'
            path = path + 'index.html'
            logger.info(f"Directory request detected, redirecting to: {path}")
        
        # Build multiple path attempts (like the old implementation)
        path_attempts = []
        
        # Use the extracted_path as-is (it should include 'media/' prefix)
        extracted_path = scorm_package.extracted_path
        
        # Attempt 1: Direct path using extracted_path as-is
        path_attempts.append(f"{extracted_path}/{path}")
        
        # Attempt 2: If path contains subdirectories, try without the first directory
        if '/' in path:
            path_parts = path.split('/', 1)
            if len(path_parts) > 1:
                path_attempts.append(f"{extracted_path}/{path_parts[1]}")
        
        # Attempt 3: Try with scormcontent/ prefix (for Rise packages)
        if not path.startswith('scormcontent/'):
            path_attempts.append(f"{extracted_path}/scormcontent/{path}")
        
        # Attempt 4: Try with just the filename (for deeply nested structures)
        if '/' in path:
            filename = path.split('/')[-1]
            path_attempts.append(f"{extracted_path}/{filename}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for p in path_attempts:
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)
        
        # Try each path until one works
        successful_path = None
        for attempt_num, test_path in enumerate(unique_paths, 1):
            try:
                if default_storage.exists(test_path):
                    successful_path = test_path
                    logger.info(f"Found SCORM content at path attempt #{attempt_num}: {test_path}")
                    break
            except Exception as e:
                logger.warning(f"Error checking path {test_path}: {str(e)}")
                continue
        
        # If no path worked, return detailed error
        if not successful_path:
            error_msg = f"SCORM content file not found. Tried {len(unique_paths)} paths:\n"
            for p in unique_paths[:5]:  # Show first 5 attempts
                error_msg += f"  - {p}\n"
            if len(unique_paths) > 5:
                error_msg += f"  ... and {len(unique_paths) - 5} more\n"
            error_msg += "\nPlease contact your administrator."
            logger.error(f"Failed to find SCORM content for topic {topic_id}, path: {path}")
            logger.error(f"Tried paths: {unique_paths}")
            raise Http404(error_msg)
        
        # Remove 'media/' prefix for opening the file since S3 storage adds it automatically
        full_path = successful_path
        if full_path.startswith('media/'):
            full_path = full_path[6:]  # Remove 'media/' prefix for open() operation
        
        file_size = default_storage.size(full_path)
        if file_size is None:
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
        if content_type.startswith('text/') or content_type in ['application/javascript', 'application/json']:
            with default_storage.open(full_path, 'r') as f:
                content = f.read()
            
            response = HttpResponse(content, content_type=content_type)
            response['Content-Length'] = len(content.encode('utf-8'))
            response['Access-Control-Allow-Origin'] = '*'
            return response
        else:
            file_obj = default_storage.open(full_path, 'rb')
            response = FileResponse(file_obj, content_type=content_type)
            response['Content-Length'] = file_size
            response['Access-Control-Allow-Origin'] = '*'
            return response
                
    except Topic.DoesNotExist:
        raise Http404("Topic not found")
    except Exception as e:
        logger.error(f"Error serving SCORM content for topic {topic_id}, path {path}: {str(e)}")
        raise Http404("SCORM content not available")


@csrf_exempt
@require_http_methods(["GET", "POST", "OPTIONS"])
def scorm_api(request, attempt_id):
    """Universal SCORM API endpoint"""
    try:
        if request.method == 'OPTIONS':
            response = JsonResponse({})
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        
        # Get attempt
        attempt = None
        is_preview = False
        
        if str(attempt_id).startswith('preview_'):
            preview_data = request.session.get(f'scorm_preview_{attempt_id}')
            if preview_data:
                is_preview = True
                attempt = type('PreviewAttempt', (), {
                    'id': attempt_id,
                    'user_id': preview_data['user_id'],
                    'scorm_package_id': preview_data['scorm_package_id'],
                    'is_preview': True,
                })()
            else:
                return JsonResponse({"error": "Preview attempt not found"}, status=404)
        else:
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        # Initialize API handler
        api_handler = ScormAPIHandler(attempt)
        
        if request.method == 'GET':
            method = request.GET.get('method', '')
            if method:
                result = api_handler.get_value(method)
                return JsonResponse({"result": result})
            else:
                return JsonResponse({"error": "Method parameter required"})
        
        elif request.method == 'POST':
            data = json.loads(request.body.decode('utf-8'))
            method = data.get('method', '')
            parameters = data.get('parameters', [])
            value = data.get('value', '')
            
            if not method:
                return JsonResponse({"error": "Method parameter required"})
            
            # Handle SCORM API calls
            if method in ['LMSInitialize', 'Initialize']:
                result = api_handler.initialize()
                return JsonResponse({"result": result})
            
            elif method in ['LMSFinish', 'Terminate']:
                result = api_handler.terminate()
                return JsonResponse({"result": result})
            
            elif method in ['LMSCommit', 'Commit']:
                result = api_handler.commit()
                return JsonResponse({"result": result})
            
            elif method in ['LMSGetValue', 'GetValue']:
                if len(parameters) > 0:
                    result = api_handler.get_value(parameters[0])
                else:
                    result = api_handler.get_value(value)
                return JsonResponse({"result": result})
            
            elif method in ['LMSSetValue', 'SetValue']:
                if len(parameters) >= 2:
                    result = api_handler.set_value(parameters[0], parameters[1])
                else:
                    result = api_handler.set_value(method, value)
                return JsonResponse({"result": result})
            
            elif method in ['LMSGetLastError', 'GetLastError']:
                result = api_handler.get_last_error()
                return JsonResponse({"result": result})
            
            elif method in ['LMSGetErrorString', 'GetErrorString']:
                error_code = parameters[0] if len(parameters) > 0 else value
                result = api_handler.get_error_string(error_code)
                return JsonResponse({"result": result})
            
            elif method in ['LMSGetDiagnostic', 'GetDiagnostic']:
                error_code = parameters[0] if len(parameters) > 0 else value
                result = api_handler.get_diagnostic(error_code)
                return JsonResponse({"result": result})
            
            else:
                # Fallback to set_value for unknown methods
                result = api_handler.set_value(method, value)
                return JsonResponse({"result": result})
        
    except Exception as e:
        logger.error(f"Error in SCORM API for attempt {attempt_id}: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def scorm_emergency_save(request):
    """Emergency save endpoint"""
    try:
        if request.method == 'OPTIONS':
            response = JsonResponse({})
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        
        data = json.loads(request.body.decode('utf-8'))
        attempt_id = data.get('attempt_id')
        scorm_data = data.get('scorm_data', {})
        
        if not attempt_id:
            return JsonResponse({"error": "attempt_id required"}, status=400)
        
        if str(attempt_id).startswith('preview_'):
            request.session[f'scorm_emergency_save_{attempt_id}'] = {
                'scorm_data': scorm_data,
                'timestamp': timezone.now().isoformat()
            }
            return JsonResponse({"status": "saved", "preview": True})
        else:
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
            
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
            
            if 'cmi_data' in scorm_data:
                attempt.cmi_data.update(scorm_data['cmi_data'])
            
            if 'session_data' in scorm_data:
                attempt.session_data.update(scorm_data['session_data'])
            
            attempt.save()
            return JsonResponse({"status": "saved"})
        
    except Exception as e:
        logger.error(f"Error in emergency save: {str(e)}")
        return JsonResponse({"error": "Emergency save failed"}, status=500)


def scorm_status(request, attempt_id):
    """SCORM status endpoint"""
    try:
        attempt = None
        is_preview = False
        
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
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
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
        attempt = None
        is_preview = False
        
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
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
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
        attempt = None
        is_preview = False
        
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
            try:
                attempt = ScormAttempt.objects.get(id=attempt_id)
            except ScormAttempt.DoesNotExist:
                return JsonResponse({"error": "Attempt not found"}, status=404)
        
        interactions = []
        objectives = []
        comments = []
        
        if not is_preview:
            interactions = list(attempt.interactions.values(
                'interaction_id', 'interaction_type', 'description', 
                'student_response', 'result', 'score_raw', 'timestamp'
            ))
            
            objectives = list(attempt.objectives.values(
                'objective_id', 'description', 'success_status', 
                'completion_status', 'score_raw', 'progress_measure'
            ))
            
            comments = list(attempt.comments.values(
                'comment_type', 'comment_text', 'location', 'timestamp'
            ))
        
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
