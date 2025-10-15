"""
SCORM Views
Handles package uploads, player rendering, and API endpoints
"""
import json
import os
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any
from datetime import datetime

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, Http404
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, DeleteView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.db import transaction
from django.contrib import messages

from .models import (
    SCORMPackage, SCORMAttempt, SCORMInteraction, 
    SCORMObjective, SCORMEvent, SCORMPackageType
)
from courses.models import Topic

import logging

logger = logging.getLogger(__name__)


class SCORMPackageUploadView(LoginRequiredMixin, CreateView):
    """
    Handle SCORM package upload with S3 storage
    """
    model = SCORMPackage
    template_name = 'scorm/upload.html'
    fields = ['title', 'description', 'package_type', 'package_file', 'topic']
    success_url = reverse_lazy('scorm:package_list')
    
    def form_valid(self, form):
        """Process the uploaded package"""
        form.instance.created_by = self.request.user
        
        # Save the package
        response = super().form_valid(form)
        package = self.object
        
        try:
            # Get file size
            package.file_size = package.package_file.size
            package.save()
            
            # AUTO-LINK: If topic is specified, ensure it's set to SCORM type
            if package.topic:
                if package.topic.content_type != 'SCORM':
                    package.topic.content_type = 'SCORM'
                    package.topic.save()
                    logger.info(f"Updated topic {package.topic.id} to SCORM type")
            
            # Process the package asynchronously or synchronously
            if settings.SCORM_IMMEDIATE_SYNC:
                self.process_package(package)
                messages.success(self.request, f'SCORM package "{package.title}" uploaded and processed successfully.')
            else:
                # Queue for background processing
                from .tasks import process_scorm_package
                process_scorm_package.delay(str(package.id))
                messages.success(self.request, f'SCORM package "{package.title}" uploaded. Processing in background.')
            
        except Exception as e:
            logger.error(f"Error processing SCORM package: {str(e)}", exc_info=True)
            package.processing_error = str(e)
            package.save()
            messages.error(self.request, f'Error processing package: {str(e)}')
        
        return response
    
    def process_package(self, package: SCORMPackage) -> bool:
        """
        Extract and process SCORM package
        """
        try:
            # Create temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download package file to temp location
                temp_zip_path = os.path.join(temp_dir, 'package.zip')
                
                with default_storage.open(package.package_file.name, 'rb') as f:
                    with open(temp_zip_path, 'wb') as temp_file:
                        temp_file.write(f.read())
                
                # Extract ZIP file
                extract_dir = os.path.join(temp_dir, 'extracted')
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find and parse imsmanifest.xml
                manifest_path = self.find_manifest(extract_dir)
                if manifest_path:
                    manifest_data = self.parse_manifest_file(manifest_path)
                    package.manifest_data = manifest_data
                    package.identifier = manifest_data.get('identifier', '')
                    
                    # Get launch file from manifest
                    launch_file = self.get_launch_file_from_manifest(manifest_data)
                    if launch_file:
                        package.launch_file = launch_file
                
                # If no launch file from manifest, try to detect it
                if not package.launch_file:
                    package.launch_file = self.detect_launch_file(extract_dir)
                
                # Upload extracted files to S3
                s3_base_path = f"scorm/content/{package.id}"
                package.extracted_path = s3_base_path
                
                self.upload_directory_to_s3(extract_dir, s3_base_path)
                
                # Detect package type
                detected_type = package.detect_package_type()
                if package.package_type == SCORMPackageType.AUTO:
                    package.package_type = detected_type
                
                # Mark as processed
                package.is_processed = True
                package.processing_error = ""
                package.save()
                
                logger.info(f"Successfully processed SCORM package: {package.title}")
                return True
                
        except Exception as e:
            logger.error(f"Error in process_package: {str(e)}", exc_info=True)
            package.processing_error = str(e)
            package.is_processed = False
            package.save()
            return False
    
    def find_manifest(self, directory: str) -> Optional[str]:
        """Find imsmanifest.xml in directory"""
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower() == 'imsmanifest.xml':
                    return os.path.join(root, file)
        return None
    
    def parse_manifest_file(self, manifest_path: str) -> Dict[str, Any]:
        """Parse imsmanifest.xml file"""
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            
            # Remove namespace for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            manifest_data = {
                'identifier': root.get('identifier', ''),
                'version': root.get('version', ''),
                'schemaversion': '',
                'resources': [],
                'organizations': [],
                'title': ''
            }
            
            # Get schema version
            metadata = root.find('.//metadata')
            if metadata is not None:
                schema = metadata.find('.//schemaversion')
                if schema is not None:
                    manifest_data['schemaversion'] = schema.text or ''
            
            # Get title from organization
            org = root.find('.//organization')
            if org is not None:
                title_elem = org.find('.//title')
                if title_elem is not None:
                    manifest_data['title'] = title_elem.text or ''
            
            # Get resources
            resources = root.findall('.//resource')
            for resource in resources:
                res_type = resource.get('type', '')
                if 'sco' in res_type.lower() or 'asset' in res_type.lower():
                    manifest_data['resources'].append({
                        'identifier': resource.get('identifier', ''),
                        'type': res_type,
                        'href': resource.get('href', ''),
                    })
            
            return manifest_data
            
        except Exception as e:
            logger.error(f"Error parsing manifest: {str(e)}")
            return {}
    
    def get_launch_file_from_manifest(self, manifest_data: Dict[str, Any]) -> str:
        """Extract launch file from manifest resources"""
        resources = manifest_data.get('resources', [])
        for resource in resources:
            href = resource.get('href', '')
            if href and ('.html' in href.lower() or '.htm' in href.lower()):
                return href
        return ''
    
    def detect_launch_file(self, directory: str) -> str:
        """Detect launch file by common patterns"""
        common_names = [
            'index.html', 'index.htm',
            'story.html', 'story_html5.html',
            'index_lms.html', 'scormdriver.html',
            'multiscreen.html',
            'presentation.html',
            'res/index.html'
        ]
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower() in [n.lower() for n in common_names]:
                    rel_path = os.path.relpath(os.path.join(root, file), directory)
                    return rel_path.replace('\\', '/')
        
        # Fallback: find any HTML file
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.html') or file.lower().endswith('.htm'):
                    rel_path = os.path.relpath(os.path.join(root, file), directory)
                    return rel_path.replace('\\', '/')
        
        return 'index.html'
    
    def upload_directory_to_s3(self, local_dir: str, s3_base_path: str):
        """Upload entire directory to S3"""
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                s3_path = os.path.join(s3_base_path, relative_path).replace('\\', '/')
                
                with open(local_path, 'rb') as f:
                    default_storage.save(s3_path, ContentFile(f.read()))


class SCORMPackageListView(LoginRequiredMixin, ListView):
    """List all SCORM packages"""
    model = SCORMPackage
    template_name = 'scorm/package_list.html'
    context_object_name = 'packages'
    paginate_by = 20
    
    def get_queryset(self):
        """Filter packages based on user permissions"""
        queryset = SCORMPackage.objects.filter(is_active=True)
        
        # Filter by topic if specified
        topic_id = self.request.GET.get('topic')
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)
        
        return queryset.order_by('-created_at')


class SCORMPlayerView(LoginRequiredMixin, DetailView):
    """
    Render SCORM player interface
    """
    model = SCORMPackage
    template_name = 'scorm/player.html'
    context_object_name = 'package'
    pk_url_kwarg = 'package_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        package = self.object
        
        # Get or create attempt
        attempt = self.get_or_create_attempt(package)
        context['attempt'] = attempt
        context['launch_url'] = package.get_launch_url()
        context['api_endpoint'] = reverse('scorm:api_endpoint', kwargs={'topic_id': package.topic_id if package.topic else 0})
        
        return context
    
    def get_or_create_attempt(self, package: SCORMPackage) -> SCORMAttempt:
        """Get existing active attempt or create a new one"""
        # Try to get last incomplete attempt
        attempt = SCORMAttempt.objects.filter(
            package=package,
            user=self.request.user,
            is_active=True
        ).exclude(
            lesson_status__in=['completed', 'passed']
        ).order_by('-started_at').first()
        
        if not attempt:
            # Count existing attempts for attempt number
            attempt_count = SCORMAttempt.objects.filter(
                package=package,
                user=self.request.user
            ).count()
            
            # Create new attempt
            attempt = SCORMAttempt.objects.create(
                package=package,
                user=self.request.user,
                topic=package.topic,
                attempt_number=attempt_count + 1,
                cmi_data={}
            )
        
        return attempt


@csrf_exempt
def scorm_api_endpoint(request, topic_id):
    """
    SCORM API endpoint for handling LMS API calls
    Handles both SCORM 1.2 and SCORM 2004 API calls
    """
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        return response
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Parse request data with better error handling
        data = {}
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Error parsing JSON: {e}")
                return JsonResponse({
                    'result': 'false',
                    'error': '101',
                    'error_message': 'Invalid JSON format'
                })
        else:
            # Try to parse as form data or query parameters
            data = request.POST.dict() or request.GET.dict()
            if not data:
                # Try to parse raw body as text
                try:
                    body_text = request.body.decode('utf-8')
                    if body_text:
                        data = {'method': body_text}
                except:
                    pass
        
        method = data.get('method', '')
        parameters = data.get('parameters', [])
        attempt_id = data.get('attempt_id')
        
        # Log the API call
        logger.debug(f"SCORM API Call: {method} with params: {parameters}")
        
        # Get or create attempt
        attempt = None
        if attempt_id:
            try:
                attempt = SCORMAttempt.objects.get(id=attempt_id)
            except SCORMAttempt.DoesNotExist:
                pass
        
        # If no attempt, try to get from topic and user
        if not attempt:
            # Try to get user from session or create a default user for SCORM
            user = request.user if request.user.is_authenticated else None
            
            if not user:
                # For SCORM content, we might need to handle unauthenticated users
                # Try to get a default user or create a guest session
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.filter(is_active=True).first()
                    if not user:
                        logger.warning("No users found for SCORM API")
                        return JsonResponse({
                            'result': 'false',
                            'error': '301',
                            'error_message': 'User not authenticated'
                        })
                except Exception as e:
                    logger.error(f"Error getting user for SCORM: {e}")
                    return JsonResponse({
                        'result': 'false',
                        'error': '301',
                        'error_message': 'Authentication required'
                    })
            
            topic = get_object_or_404(Topic, id=topic_id)
            package = SCORMPackage.objects.filter(topic=topic, is_active=True).first()
            
            if package:
                # Get or create attempt
                attempt = SCORMAttempt.objects.filter(
                    package=package,
                    user=user,
                    is_active=True
                ).order_by('-started_at').first()
                
                if not attempt:
                    attempt_count = SCORMAttempt.objects.filter(
                        package=package,
                        user=user
                    ).count()
                    
                    attempt = SCORMAttempt.objects.create(
                        package=package,
                        user=user,
                        topic=topic,
                        attempt_number=attempt_count + 1
                    )
        
        # Handle different API methods
        result = 'true'
        error_code = '0'
        return_value = ''
        
        if method == 'LMSInitialize' or method == 'Initialize':
            result = handle_initialize(attempt)
            
        elif method == 'LMSFinish' or method == 'Terminate':
            result = handle_terminate(attempt)
            
        elif method == 'LMSGetValue' or method == 'GetValue':
            return_value = handle_get_value(attempt, parameters[0] if parameters else '')
            result = 'true'
            
        elif method == 'LMSSetValue' or method == 'SetValue':
            if len(parameters) >= 2:
                result = handle_set_value(attempt, parameters[0], parameters[1])
            
        elif method == 'LMSCommit' or method == 'Commit':
            result = handle_commit(attempt)
            
        elif method == 'LMSGetLastError' or method == 'GetLastError':
            return_value = error_code
            
        elif method == 'LMSGetErrorString' or method == 'GetErrorString':
            return_value = get_error_string(parameters[0] if parameters else '0')
            
        elif method == 'LMSGetDiagnostic' or method == 'GetDiagnostic':
            return_value = ''
        
        # Log the event
        if attempt:
            SCORMEvent.objects.create(
                attempt=attempt,
                event_type=method,
                element=parameters[0] if parameters else '',
                value=parameters[1] if len(parameters) > 1 else '',
                result=result,
                error_code=error_code,
                request_data=data
            )
        
        # Return response
        response_data = {
            'result': result if not return_value else return_value,
            'error': error_code,
            'attempt_id': str(attempt.id) if attempt else None
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error in SCORM API endpoint: {str(e)}", exc_info=True)
        return JsonResponse({
            'result': 'false',
            'error': '101',
            'error_message': str(e)
        }, status=500)


def handle_initialize(attempt: Optional[SCORMAttempt]) -> str:
    """Handle LMSInitialize"""
    if not attempt:
        return 'false'
    
    attempt.last_accessed = timezone.now()
    attempt.save()
    return 'true'


def handle_terminate(attempt: Optional[SCORMAttempt]) -> str:
    """Handle LMSFinish/Terminate"""
    if not attempt:
        return 'false'
    
    # Save any pending data
    attempt.last_accessed = timezone.now()
    
    # Check if completed
    if attempt.is_completed() and not attempt.completed_at:
        attempt.completed_at = timezone.now()
    
    attempt.save()
    
    # Update topic progress if linked
    if attempt.topic:
        from courses.models import TopicProgress
        topic_progress, created = TopicProgress.objects.get_or_create(
            user=attempt.user,
            topic=attempt.topic
        )
        
        if attempt.is_completed():
            topic_progress.completed = True
            topic_progress.completion_date = timezone.now()
        
        # Update score if available
        if attempt.score_raw is not None:
            topic_progress.score = attempt.score_raw
        
        topic_progress.save()
    
    return 'true'


def handle_get_value(attempt: Optional[SCORMAttempt], element: str) -> str:
    """Handle LMSGetValue"""
    if not attempt:
        return ''
    
    # Check if value exists in cmi_data
    if element in attempt.cmi_data:
        value = attempt.cmi_data[element]
        return str(value) if value is not None else ''
    
    # Map common elements to model fields
    value_map = {
        'cmi.core.lesson_status': attempt.lesson_status,
        'cmi.completion_status': attempt.completion_status,
        'cmi.success_status': attempt.success_status,
        'cmi.core.score.raw': attempt.score_raw,
        'cmi.score.raw': attempt.score_raw,
        'cmi.core.score.min': attempt.score_min,
        'cmi.score.min': attempt.score_min,
        'cmi.core.score.max': attempt.score_max,
        'cmi.score.max': attempt.score_max,
        'cmi.score.scaled': attempt.score_scaled,
        'cmi.core.lesson_location': attempt.lesson_location,
        'cmi.location': attempt.lesson_location,
        'cmi.suspend_data': attempt.suspend_data,
        'cmi.core.student_id': str(attempt.user.id),
        'cmi.learner_id': str(attempt.user.id),
        'cmi.core.student_name': attempt.user.get_full_name(),
        'cmi.learner_name': attempt.user.get_full_name(),
    }
    
    value = value_map.get(element, '')
    return str(value) if value is not None else ''


def handle_set_value(attempt: Optional[SCORMAttempt], element: str, value: Any) -> str:
    """Handle LMSSetValue"""
    if not attempt:
        return 'false'
    
    try:
        # Update the attempt with the new value
        attempt.update_from_cmi(element, value)
        attempt.save()
        return 'true'
    except Exception as e:
        logger.error(f"Error in handle_set_value: {str(e)}")
        return 'false'


def handle_commit(attempt: Optional[SCORMAttempt]) -> str:
    """Handle LMSCommit"""
    if not attempt:
        return 'false'
    
    try:
        attempt.last_accessed = timezone.now()
        attempt.save()
        return 'true'
    except Exception as e:
        logger.error(f"Error in handle_commit: {str(e)}")
        return 'false'


def get_error_string(error_code: str) -> str:
    """Get error message for error code"""
    error_strings = {
        '0': 'No error',
        '101': 'General exception',
        '102': 'Invalid argument error',
        '103': 'Element not initialized',
        '104': 'Element not implemented',
        '201': 'Invalid argument error',
        '301': 'Not initialized',
        '401': 'Not implemented error',
        '402': 'Invalid set value',
        '403': 'Element is read only',
        '404': 'Element is write only',
        '405': 'Incorrect data type',
    }
    return error_strings.get(error_code, 'Unknown error')


@login_required
def scorm_attempt_detail(request, attempt_id):
    """View details of a SCORM attempt"""
    attempt = get_object_or_404(SCORMAttempt, id=attempt_id)
    
    # Check permissions
    if attempt.user != request.user and not request.user.is_staff:
        raise Http404
    
    context = {
        'attempt': attempt,
        'interactions': attempt.interactions.all(),
        'objectives': attempt.objectives.all(),
        'events': attempt.events.all()[:100]  # Last 100 events
    }
    
    return render(request, 'scorm/attempt_detail.html', context)


@csrf_exempt
def scorm_test_endpoint(request):
    """Test endpoint for SCORM API debugging"""
    return JsonResponse({
        'status': 'ok',
        'message': 'SCORM API test endpoint working',
        'method': request.method,
        'content_type': request.content_type,
        'user_authenticated': request.user.is_authenticated,
        'user': str(request.user) if request.user.is_authenticated else 'Anonymous'
    })


@login_required
def scorm_user_attempts(request):
    """List all user's SCORM attempts"""
    attempts = SCORMAttempt.objects.filter(
        user=request.user
    ).select_related('package', 'topic').order_by('-started_at')
    
    context = {
        'attempts': attempts
    }
    
    return render(request, 'scorm/user_attempts.html', context)

