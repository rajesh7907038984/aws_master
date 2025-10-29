"""
Views for SCORM package handling
"""
import json
import logging
import hashlib
from datetime import timedelta
from django.http import HttpResponse, JsonResponse, Http404, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .models import ScormPackage
from courses.models import Topic, TopicProgress

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def scorm_launcher(request, topic_id):
    """
    SCORM launcher page that loads the API wrapper and content
    This page provides the SCORM API to the content loaded in an iframe
    """
    try:
        # Get topic and package
        topic = get_object_or_404(Topic, id=topic_id)
        package = topic.scorm
        
        if not package:
            return HttpResponse("No SCORM package associated with this topic", status=404)
        
        if package.processing_status != 'ready':
            return HttpResponse(
                f"Package is not ready. Status: {package.get_processing_status_display()}",
                status=503
            )
        
        # Get entry point
        entry_point = package.get_entry_point()
        if not entry_point:
            return HttpResponse("Package entry point not found", status=404)
        
        # Get or create progress
        progress, created = TopicProgress.objects.get_or_create(
            user=request.user,
            topic=topic
        )
        
        # Generate session ID
        import uuid
        session_id = str(uuid.uuid4())
        
        # Prepare progress data for SCORM API
        # Safely extract progress data with None checks
        progress_dict = progress.progress_data if progress.progress_data else {}
        bookmark_dict = progress.bookmark if progress.bookmark else {}
        
        # Use camelCase keys to match JavaScript expectations
        progress_data = {
            'lessonLocation': bookmark_dict.get('lesson_location', ''),
            'suspendData': bookmark_dict.get('suspend_data', ''),
            'lessonStatus': progress_dict.get('scorm_completion_status', 'not attempted'),
            'scoreRaw': progress_dict.get('scorm_score', ''),
            'scoreMax': progress_dict.get('scorm_max_score', ''),
            'totalTime': progress_dict.get('scorm_total_time', '00:00:00'),
        }
        
        context = {
            'topic': topic,
            'package': package,
            'entry_point': entry_point,
            'scorm_version': package.version or '1.2',
            'session_id': session_id,
            'progress_data': json.dumps(progress_data),
        }
        
        from django.template.loader import render_to_string
        html = render_to_string('scorm/launcher.html', context, request=request)
        return HttpResponse(html)
        
    except Exception as e:
        logger.error(f"Error in SCORM launcher: {e}", exc_info=True)
        return HttpResponse(f"Error loading SCORM content: {str(e)}", status=500)


def validate_scorm_file_path(file_path):
    """
    Validate file path to prevent path traversal attacks
    
    Returns:
        Tuple of (is_valid, normalized_path, error_message)
    """
    import os
    
    # Remove any leading slashes
    file_path = file_path.lstrip('/')
    
    # Check for dangerous patterns
    if '..' in file_path:
        return False, None, "Path traversal detected: .."
    
    if file_path.startswith('/'):
        return False, None, "Absolute paths not allowed"
    
    if '\\' in file_path:
        return False, None, "Backslashes not allowed"
    
    # Normalize the path
    normalized = os.path.normpath(file_path)
    
    # Ensure normalization didn't introduce ..
    if '..' in normalized:
        return False, None, "Path traversal detected after normalization"
    
    # Ensure it's a relative path
    if os.path.isabs(normalized):
        return False, None, "Absolute path detected after normalization"
    
    return True, normalized, None


@login_required
@require_http_methods(["GET"])
def scorm_player(request, package_id, file_path):
    """
    Proxy endpoint for serving SCORM content with same-origin
    This ensures SCORM API can communicate with parent window
    
    URL pattern: /scorm/player/<package_id>/<file_path>
    """
    try:
        # Validate file path for security
        is_valid, normalized_path, error = validate_scorm_file_path(file_path)
        if not is_valid:
            logger.warning(f"Invalid file path rejected: {file_path} - {error}")
            return HttpResponse(f"Invalid file path: {error}", status=400)
        
        file_path = normalized_path
        
        # Feature flag
        if not getattr(settings, 'ENABLE_SCORM_FEATURES', True):
            return HttpResponse("SCORM features are disabled", status=503)
        package = get_object_or_404(ScormPackage, id=package_id)
        
        # Check processing status
        if package.processing_status != 'ready':
            return HttpResponse(
                f"Package is not ready. Status: {package.get_processing_status_display()}",
                status=503
            )
        
        if not package.extracted_path:
            return HttpResponse("Package extraction path not set", status=404)
        
        # Build S3 key with proper normalization
        s3_key = f"{package.extracted_path}/{file_path}"
        # Remove all double slashes
        while '//' in s3_key:
            s3_key = s3_key.replace('//', '/')
        # Remove leading slash if present
        s3_key = s3_key.lstrip('/')
        
        # Get S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-west-2'),
            config=Config(signature_version='s3v4')
        )
        
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        try:
            # Get object from S3
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            
            # Determine content type
            content_type = response.get('ContentType', 'application/octet-stream')
            
            # Generate ETag for conditional requests (for caching)
            etag = hashlib.md5(f"{package_id}:{file_path}:{package.updated_at}".encode()).hexdigest()
            
            # Check If-None-Match header for 304 Not Modified
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
            if if_none_match and if_none_match.strip('"') == etag:
                return HttpResponse(status=304)  # Not Modified
            
            # Override content type for HTML files to ensure proper rendering
            if file_path.endswith('.html') or file_path.endswith('.htm'):
                content_type = 'text/html; charset=utf-8'
                
                # For HTML files, inject SCORM API script
                file_content = response['Body'].read().decode('utf-8', errors='ignore')
                
                # Inject SCORM API script before closing </head> or at the end if no </head>
                scorm_api_url = f"{request.scheme}://{request.get_host()}/static/scorm/js/scorm-api.js"
                topic_id_param = request.GET.get('topic_id', None)
                topic_id = int(topic_id_param) if topic_id_param and topic_id_param.isdigit() else None
                
                # Get CSRF token for JavaScript access
                from django.middleware.csrf import get_token
                csrf_token = get_token(request)
                
                # Get existing progress data for resume
                progress_data = {}
                if topic_id:
                    try:
                        from courses.models import Topic, TopicProgress
                        topic = Topic.objects.get(id=topic_id)
                        if hasattr(request, 'user') and request.user.is_authenticated:
                            progress = TopicProgress.objects.filter(
                                user=request.user,
                                topic=topic
                            ).first()
                            if progress:
                                progress_data = progress.progress_data or {}
                                if progress.bookmark:
                                    progress_data.update(progress.bookmark)
                    except Exception as e:
                        logger.warning(f"Could not load progress data for resume: {e}")
                
                # Get resume data - safely escape single quotes
                # Determine entry parameter: "resume" if there's existing progress, "ab-initio" for first launch
                has_bookmark = bool(progress_data.get("lesson_location") or progress_data.get("suspend_data"))
                default_entry = "resume" if has_bookmark else "ab-initio"
                entry_value = request.GET.get("entry", progress_data.get("scorm_entry", default_entry))
                location_value = request.GET.get("location", progress_data.get("lesson_location", "")).replace("'", "\\'")
                suspend_value = request.GET.get("suspend_data", progress_data.get("suspend_data", "")).replace("'", "\\'")
                
                scorm_init_script = f"""
<meta name="csrf-token" content="{csrf_token}">
<script>
    // Make CSRF token available globally
    window.CSRF_TOKEN = '{csrf_token}';
</script>
<script src="{scorm_api_url}"></script>
<script>
    // Configure SCORM API when DOM is ready
    (function() {{
        function initScormAPI() {{
            if (typeof SCORM !== 'undefined' && SCORM.configure) {{
                var topicId = {topic_id if topic_id else 'null'};
                var progressUrl = topicId ? '/courses/api/update_scorm_progress/' + topicId + '/' : null;
                console.log('SCORM API Configuration:', {{ topicId: topicId, progressUpdateUrl: progressUrl }});
                
                // Get resume data
                var entry = '{entry_value}';
                var lessonLocation = '{location_value}';
                var suspendData = '{suspend_value}';
                
                SCORM.configure({{
                    version: '{package.version or "1.2"}',
                    progressUpdateUrl: progressUrl,
                    topicId: topicId,
                    progressData: {{
                        entry: entry,
                        lessonLocation: lessonLocation,
                        suspendData: suspendData
                    }}
                }});
                
                // Initialize SCORM API
                if (typeof window.parent !== 'undefined' && window.parent !== window) {{
                    window.parent.scormConfig = {{
                        version: '{package.version or "1.2"}',
                        progressUpdateUrl: progressUrl,
                        topicId: topicId
                    }};
                }}
            }} else {{
                // Retry if SCORM API not loaded yet
                setTimeout(initScormAPI, 100);
            }}
        }}
        
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initScormAPI);
        }} else {{
            initScormAPI();
        }}
    }})();
</script>
"""
                
                # Insert before </head> if it exists, otherwise before </body>, otherwise at the end
                if '</head>' in file_content:
                    file_content = file_content.replace('</head>', scorm_init_script + '</head>', 1)
                elif '</body>' in file_content:
                    file_content = file_content.replace('</body>', scorm_init_script + '</body>', 1)
                else:
                    file_content += scorm_init_script
                
                http_response = HttpResponse(file_content, content_type=content_type)
            elif file_path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
                # Stream JS files directly
                def stream_file():
                    while True:
                        chunk = response['Body'].read(8192)
                        if not chunk:
                            break
                        yield chunk
                http_response = StreamingHttpResponse(stream_file(), content_type=content_type)
            elif file_path.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
                # Stream CSS files directly
                def stream_file():
                    while True:
                        chunk = response['Body'].read(8192)
                        if not chunk:
                            break
                        yield chunk
                http_response = StreamingHttpResponse(stream_file(), content_type=content_type)
            else:
                # Stream other files
                def stream_file():
                    while True:
                        chunk = response['Body'].read(8192)
                        if not chunk:
                            break
                        yield chunk
                http_response = StreamingHttpResponse(stream_file(), content_type=content_type)
            
            # Add security headers with stricter CSP
            host = request.get_host()
            http_response['Content-Security-Policy'] = (
                f"default-src 'self'; "
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # unsafe-eval needed for some SCORM
                f"style-src 'self' 'unsafe-inline'; "
                f"img-src 'self' data: blob: https:; "
                f"font-src 'self' data:; "
                f"connect-src 'self' https://{host}; "
                f"media-src 'self' blob: data:; "
                f"object-src 'none'; "
                f"frame-ancestors 'self'; "
                f"base-uri 'self'; "
                f"form-action 'self';"
            )
            
            http_response['X-Frame-Options'] = 'SAMEORIGIN'
            http_response['X-Content-Type-Options'] = 'nosniff'
            http_response['X-XSS-Protection'] = '1; mode=block'
            http_response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            # Add caching headers for better performance
            cache_duration = 86400  # 24 hours
            http_response['Cache-Control'] = f'public, max-age={cache_duration}, immutable'
            http_response['Expires'] = (
                timezone.now() + timedelta(seconds=cache_duration)
            ).strftime('%a, %d %b %Y %H:%M:%S GMT')
            http_response['ETag'] = f'"{etag}"'
            
            return http_response
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"SCORM file not found in S3: {s3_key} (requested path: {file_path})")
                # Try common alternatives if index.html was requested
                if file_path == "index.html" or file_path.endswith("/index.html"):
                    # Try without index.html suffix
                    alternatives = [
                        file_path.replace("/index.html", "").replace("index.html", ""),
                        "story.html",
                        "story_content.html",
                        "launch.html"
                    ]
                    for alt_path in alternatives:
                        if not alt_path:
                            continue
                        alt_s3_key = f"{package.extracted_path}{alt_path}".replace('//', '/')
                        try:
                            s3_client.head_object(Bucket=bucket_name, Key=alt_s3_key)
                            logger.info(f"SCORM package {package_id}: Found alternative entry point: {alt_path}")
                            # Redirect to alternative
                            from django.urls import reverse
                            alt_url = reverse('scorm:player', args=[package_id, alt_path])
                            from django.shortcuts import redirect
                            return redirect(f"{alt_url}?{request.GET.urlencode()}")
                        except ClientError:
                            continue
                
                error_msg = (
                    f"File not found: {file_path}\n\n"
                    f"Package ID: {package_id}\n"
                    f"Expected S3 key: {s3_key}\n"
                    f"Extracted path: {package.extracted_path}\n"
                    f"Entry point determined: {package.get_entry_point()}"
                )
                return HttpResponse(error_msg, status=404, content_type='text/plain')
            raise
        
    except Exception as e:
        logger.error(f"Error serving SCORM file {file_path} for package {package_id}: {e}", exc_info=True)
        return HttpResponse(f"Error serving file: {str(e)}", status=500)


@login_required
@require_http_methods(["GET"])
def package_status(request, package_id):
    """
    Get SCORM package processing status
    
    Returns JSON with processing status and metadata
    """
    try:
        package = get_object_or_404(ScormPackage, id=package_id)
        
        entry_point = None
        entry_point_exists = None
        entry_point_error = None
        
        if package.processing_status == 'ready':
            entry_point = package.get_entry_point()
            # Verify entry point exists if extracted_path is set
            if package.extracted_path and entry_point:
                exists, error = package.verify_entry_point_exists()
                entry_point_exists = exists
                entry_point_error = error
        
        # Get launch URL if available
        launch_url = package.launch_url or (package.get_launch_url() if package.processing_status == 'ready' else None)
        
        response_data = {
            'status': package.processing_status,
            'status_display': package.get_processing_status_display(),
            'error': package.processing_error,
            'version': package.version,
            'title': package.title,
            'authoring_tool': package.authoring_tool,
            'authoring_tool_display': package.get_authoring_tool_display() if package.authoring_tool else None,
            'has_extracted_path': bool(package.extracted_path),
            'extracted_path': package.extracted_path,
            'entry_point': entry_point,
            'entry_point_exists': entry_point_exists,
            'entry_point_error': entry_point_error,
            'launch_url': launch_url
        }
        
        # Include primary resource information if available
        if package.primary_resource_identifier:
            response_data['primary_resource'] = {
                'identifier': package.primary_resource_identifier,
                'type': package.primary_resource_type,
                'scorm_type': package.primary_resource_scorm_type,
                'scorm_type_display': package.get_primary_resource_scorm_type_display() if package.primary_resource_scorm_type else None,
                'href': package.primary_resource_href,
            }
        
        # Include resource count if resources are available
        if package.resources:
            response_data['resource_count'] = len(package.resources)
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Error getting package status for {package_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)

