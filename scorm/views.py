"""
Views for SCORM package handling
"""
import json
import logging
from django.http import HttpResponse, JsonResponse, Http404, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .models import ScormPackage

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def scorm_player(request, package_id, file_path):
    """
    Proxy endpoint for serving SCORM content with same-origin
    This ensures SCORM API can communicate with parent window
    
    URL pattern: /scorm/player/<package_id>/<file_path>
    """
    try:
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
        
        # Build S3 key
        s3_key = f"{package.extracted_path}{file_path}".replace('//', '/')
        
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
            
            # Override content type for HTML files to ensure proper rendering
            if file_path.endswith('.html') or file_path.endswith('.htm'):
                content_type = 'text/html; charset=utf-8'
                
                # For HTML files, inject SCORM API script
                file_content = response['Body'].read().decode('utf-8', errors='ignore')
                
                # Inject SCORM API script before closing </head> or at the end if no </head>
                scorm_api_url = f"{request.scheme}://{request.get_host()}/static/scorm/js/scorm-api.js"
                topic_id = request.GET.get('topic_id', '')
                
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
<script src="{scorm_api_url}"></script>
<script>
    // Configure SCORM API when DOM is ready
    (function() {{
        function initScormAPI() {{
            if (typeof SCORM !== 'undefined' && SCORM.configure) {{
                var topicId = {topic_id if topic_id else 'null'};
                var progressUrl = topicId ? '/courses/api/update_scorm_progress/' + topicId + '/' : null;
                
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
            
            # Add security headers
            http_response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self' https://{}; "
                "font-src 'self' data:; "
                "frame-ancestors 'self';"
            ).format(request.get_host())
            
            http_response['X-Frame-Options'] = 'SAMEORIGIN'
            http_response['X-Content-Type-Options'] = 'nosniff'
            
            return http_response
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"SCORM file not found in S3: {s3_key}")
                return HttpResponse(f"File not found: {file_path}", status=404)
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
        
        return JsonResponse({
            'status': package.processing_status,
            'status_display': package.get_processing_status_display(),
            'error': package.processing_error,
            'version': package.version,
            'title': package.title,
            'has_extracted_path': bool(package.extracted_path),
            'entry_point': package.get_entry_point() if package.processing_status == 'ready' else None
        })
        
    except Exception as e:
        logger.error(f"Error getting package status for {package_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)

