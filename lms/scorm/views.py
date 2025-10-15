"""
Simplified SCORM Player - Direct S3 Embedding
No authentication required, direct iframe embedding from S3
"""
import logging
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.conf import settings
import boto3
from botocore.exceptions import NoCredentialsError

from .models import ScormPackage, ScormAttempt
from courses.models import Topic

logger = logging.getLogger(__name__)


# Removed complex package detection - using simple detection in views


def get_s3_direct_url(scorm_package, path=''):
    """
    Generate presigned S3 URL for SCORM content to avoid access denied issues
    """
    try:
        # Import the S3 direct access utility
        from .s3_direct import scorm_s3
        
        # Generate presigned URL using the existing utility
        if path:
            s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        else:
            s3_url = scorm_s3.generate_launch_url(scorm_package)
        
        if not s3_url:
            logger.error(f"Failed to generate presigned URL for package {scorm_package.id}")
            return None
            
        logger.info(f"Generated presigned S3 URL for SCORM package {scorm_package.id}")
        return s3_url
        
    except Exception as e:
        logger.error(f"Error generating S3 URL: {e}")
        return None


@xframe_options_exempt
def scorm_player(request, topic_id):
    """
    Enhanced SCORM Player - Direct S3 embedding with improved path handling
    """
    try:
        # Get topic and SCORM package
        topic = get_object_or_404(Topic, id=topic_id)
        
        if not hasattr(topic, 'scorm_package') or not topic.scorm_package:
            logger.error(f"No SCORM package found for topic {topic_id}")
            return HttpResponse("No SCORM package found for this topic", status=404)
        
        scorm_package = topic.scorm_package
        
        # Verify the SCORM package has required data
        if not scorm_package.launch_url or not scorm_package.extracted_path:
            logger.error(f"Invalid SCORM package data for topic {topic_id}: missing launch_url or extracted_path")
            return HttpResponse("Invalid SCORM package data", status=500)
        
        # Simple package type detection
        package_type = 'standard'
        if 'scormcontent' in scorm_package.launch_url.lower():
            package_type = 'articulate_rise'
        elif 'story.html' in scorm_package.launch_url.lower():
            package_type = 'articulate_storyline'
        logger.info(f"Package type: {package_type}")
        
        # Construct the launch URL with proper path handling
        launch_path = scorm_package.launch_url
        
        # Handle special cases for different package types
        if package_type == 'articulate_rise_content' and not launch_path.startswith('scormcontent/'):
            # Ensure scormcontent prefix is present for Rise content
            if 'scormcontent/' not in launch_path:
                logger.info(f"Adding scormcontent prefix for Articulate Rise content")
                launch_path = f"scormcontent/{launch_path}"
        
        # For HTML files, use Django proxy to inject SCORM API
        launch_url = f"/scorm/content/{topic_id}/{launch_path}"
        
        # Log the launch URL for debugging
        logger.info(f"Using proxied launch URL: {launch_url} for package type: {package_type}")
        
        # Verify the content exists in S3
        from .s3_direct import scorm_s3
        if not scorm_s3.verify_file_exists(scorm_package, launch_path):
            logger.error(f"SCORM content file not found in S3: {launch_path} for topic {topic_id}")
            # Try alternative paths
            alt_paths = [scorm_package.launch_url]
            if package_type == 'articulate_rise_content':
                alt_paths.append('scormcontent/index.html')
                
            content_found = False
            for alt_path in alt_paths:
                if scorm_s3.verify_file_exists(scorm_package, alt_path):
                    logger.info(f"Found alternative content path: {alt_path}")
                    launch_path = alt_path
                    launch_url = f"/scorm/content/{topic_id}/{launch_path}"
                    content_found = True
                    break
                    
            if not content_found:
                logger.error(f"Could not find SCORM content in S3 after trying alternatives")
                return HttpResponse("SCORM content not found in storage", status=404)
        
        # Create or get attempt for tracking (optional, works without auth)
        attempt_id = None
        if request.user.is_authenticated:
            try:
                attempt, created = ScormAttempt.objects.get_or_create(
                    user=request.user,
                    scorm_package=scorm_package,
                    defaults={
                        'attempt_number': 1,
                        'lesson_status': 'not attempted',
                        'completion_status': 'incomplete'
                    }
                )
                attempt_id = attempt.id
                logger.info(f"Attempt {attempt_id} for user {request.user.username}")
            except Exception as e:
                logger.warning(f"Could not create attempt: {e}")
        
        # Prepare context for template
        context = {
            'topic': topic,
            'scorm_package': scorm_package,
            'launch_url': launch_url,
            'package_type': package_type,
            'attempt_id': attempt_id,
            'topic_id': topic_id,
            'scorm_version': scorm_package.version,
            'direct_embed': True,  # Flag for direct embedding
        }
        
        response = render(request, 'scorm/player.html', context)
        # Override any CSP with permissive policy for SCORM content
        response['Content-Security-Policy'] = "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; worker-src * blob: data:; style-src * 'unsafe-inline'; img-src * data: blob:; font-src * data:; connect-src *; media-src * data: blob:; frame-src *; object-src 'none'"
        return response
        
    except Exception as e:
        logger.error(f"Error in SCORM player: {e}", exc_info=True)
        return HttpResponse(f"Error loading SCORM content: {str(e)}", status=500)


@xframe_options_exempt
def scorm_view(request, topic_id):
    """
    Alias for scorm_player - backwards compatibility
    """
    return scorm_player(request, topic_id)


@csrf_exempt
@xframe_options_exempt
def scorm_api_lite(request, topic_id):
    """
    Simplified SCORM API with xAPI wrapper support
    """
    try:
        if request.method == "OPTIONS":
            response = JsonResponse({'status': 'ok'})
            response['Access-Control-Allow-Origin'] = '*'
            response['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
            response['Access-Control-Allow-Headers'] = '*'
            return response
        
        # Get SCORM package
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package:
            return JsonResponse({'error': 'No SCORM package'}, status=404)
        
        # Handle API calls
        if request.method == 'POST':
            import json
            data = json.loads(request.body) if request.body else {}
            
            method = data.get('method', '')
            parameters = data.get('parameters', [])
            
            # Check if this is xAPI/Tin Can request
            if 'xapi' in request.path or scorm_package.version == 'xapi':
                from .xapi_wrapper import xapi_endpoint
                attempt_id = data.get('attempt_id', 0)
                if not attempt_id and request.user.is_authenticated:
                    # Try to get or create attempt for authenticated users
                    try:
                        attempt, created = ScormAttempt.objects.get_or_create(
                            user=request.user,
                            scorm_package=scorm_package,
                            defaults={
                                'attempt_number': 1,
                                'lesson_status': 'not attempted',
                                'completion_status': 'incomplete'
                            }
                        )
                        attempt_id = attempt.id
                    except Exception as e:
                        logger.warning(f"Could not create attempt for xAPI: {e}")
                return xapi_endpoint(request, attempt_id)
            
            # Handle attempt creation for authenticated users
            attempt_id = None
            if request.user.is_authenticated:
                try:
                    attempt, created = ScormAttempt.objects.get_or_create(
                        user=request.user,
                        scorm_package=scorm_package,
                        defaults={
                            'attempt_number': 1,
                            'lesson_status': 'not attempted',
                            'completion_status': 'incomplete'
                        }
                    )
                    attempt_id = attempt.id
                    logger.info(f"SCORM API using attempt {attempt_id} for user {request.user.username}")
                except Exception as e:
                    logger.warning(f"Could not create attempt for SCORM API: {e}")
            
            # Standard SCORM API responses
            if method in ['Initialize', 'LMSInitialize']:
                return JsonResponse({'result': 'true', 'error': '0', 'attempt_id': attempt_id})
            
            elif method in ['Terminate', 'LMSFinish', 'LMSTerminate']:
                return JsonResponse({'result': 'true', 'error': '0', 'attempt_id': attempt_id})
            
            elif method in ['Commit', 'LMSCommit']:
                return JsonResponse({'result': 'true', 'error': '0', 'attempt_id': attempt_id})
            
            elif method in ['GetValue', 'LMSGetValue']:
                element = parameters[0] if parameters else ''
                
                # Get value from attempt if available
                value = ''
                if attempt_id:
                    try:
                        attempt = ScormAttempt.objects.get(id=attempt_id)
                        from .api_handler import ScormAPIHandler
                        api_handler = ScormAPIHandler(attempt)
                        value = api_handler.get_value(element)
                        logger.info(f"SCORM GetValue from attempt {attempt_id}: {element} = {value}")
                    except ScormAttempt.DoesNotExist:
                        logger.warning(f"Attempt {attempt_id} not found for GetValue")
                    except Exception as e:
                        logger.error(f"Error getting value from attempt: {e}")
                
                # Fallback to default values if no attempt or value not found
                if not value:
                    defaults = {
                        'cmi.core.student_id': str(request.user.id) if request.user.is_authenticated else 'guest',
                        'cmi.core.student_name': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'Guest User',
                        'cmi.core.lesson_status': 'incomplete',
                        'cmi.core.score.raw': '',
                        'cmi.core.score.min': '0',
                        'cmi.core.score.max': '100',
                        'cmi.core.total_time': '0000:00:00.00',
                        'cmi.core.lesson_mode': 'normal',
                        'cmi.core.credit': 'credit',
                        'cmi.suspend_data': '',
                        'cmi.launch_data': '',
                        'cmi.core.lesson_location': '',
                        'cmi.core.entry': 'ab-initio'
                    }
                    value = defaults.get(element, '')
                
                return JsonResponse({'result': value, 'error': '0', 'attempt_id': attempt_id})
            
            elif method in ['SetValue', 'LMSSetValue']:
                element = parameters[0] if len(parameters) > 0 else ''
                value = parameters[1] if len(parameters) > 1 else ''
                
                # Store value in attempt if available
                if attempt_id and element and value is not None:
                    try:
                        attempt = ScormAttempt.objects.get(id=attempt_id)
                        from .api_handler import ScormAPIHandler
                        api_handler = ScormAPIHandler(attempt)
                        result = api_handler.set_value(element, value)
                        logger.info(f"SCORM SetValue to attempt {attempt_id}: {element} = {value}, result: {result}")
                    except ScormAttempt.DoesNotExist:
                        logger.warning(f"Attempt {attempt_id} not found for SetValue")
                    except Exception as e:
                        logger.error(f"Error setting value in attempt: {e}")
                
                return JsonResponse({'result': 'true', 'error': '0', 'attempt_id': attempt_id})
            
            elif method in ['GetLastError', 'LMSGetLastError']:
                return JsonResponse({'result': '0', 'error': '0'})
            
            elif method in ['GetErrorString', 'LMSGetErrorString']:
                return JsonResponse({'result': 'No error', 'error': '0'})
            
            elif method in ['GetDiagnostic', 'LMSGetDiagnostic']:
                return JsonResponse({'result': '', 'error': '0'})
            
            else:
                return JsonResponse({'result': 'false', 'error': '401'})
        
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    except Exception as e:
        logger.error(f"SCORM API error: {e}")
        return JsonResponse({'error': str(e), 'result': 'false'}, status=500)


@csrf_exempt
@xframe_options_exempt
def xapi_endpoint(request, attempt_id):
    """
    xAPI endpoint for SCORM packages that use Tin Can API
    """
    try:
        from .xapi_wrapper import xapi_endpoint as xapi_handler
        return xapi_handler(request, attempt_id)
    except Exception as e:
        logger.error(f"xAPI endpoint error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@xframe_options_exempt
def scorm_direct_content(request, topic_id, path=''):
    """
    Direct proxy to S3 content with minimal processing - uses presigned URLs
    """
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package:
            return HttpResponse("No SCORM package", status=404)
        
        # Import S3 utility
        from .s3_direct import scorm_s3
        
        # Handle hash fragments in paths (they should be ignored server-side)
        if '#' in path:
            path = path.split('#')[0]
            logger.info(f"Removed hash fragment from path: {path}")
        
        # Handle directory requests (trailing slashes)
        if path.endswith('/'):
            # If it's a directory request, try to serve an index.html
            original_path = path
            path = path.rstrip('/')
            if not path:  # If path becomes empty after stripping
                path = 'index.html'
            logger.info(f"Directory request detected: {original_path} → {path}")
        
        # Fix for path handling - ensure proper path resolution
        # Check if the requested path might be missing the base folder structure
        if path and not path.startswith(scorm_package.launch_url.split('/')[0]) and '/' in scorm_package.launch_url:
            base_folder = scorm_package.launch_url.split('/')[0]
            if not path.startswith(base_folder):
                # Add the base folder to the path for proper resolution
                path = f"{base_folder}/{path}"
                logger.info(f"Path adjusted to include base folder: {path}")
        
        # Generate presigned URL for the requested path
        logger.info(f"Generating S3 URL for topic {topic_id}, path: '{path}'")
        if path:
            s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        else:
            s3_url = scorm_s3.generate_launch_url(scorm_package)
        
        if s3_url:
            logger.info(f"Successfully generated S3 URL for path: {path}")
        else:
            logger.error(f"Failed to generate S3 URL for path: {path}")
        
        # If URL generation failed, try multiple alternative path resolutions
        if not s3_url:
            logger.warning(f"First attempt to generate URL for path failed: {path}")
            
            # Try a series of fallback paths based on package type
            fallback_paths = []
            
            # Handle hash fragments and trailing slashes
            # Remove hash fragments as they are client-side only
            if '#' in path:
                path = path.split('#')[0]
            
            # Handle trailing slashes
            if path.endswith('/'):
                path = path.rstrip('/')
                if not path:  # If path becomes empty after stripping
                    path = 'index.html'
            
            # Get the base directory if any
            base_dir = path.split('/')[0] if '/' in path else ''
            file_name = path.split('/')[-1] if '/' in path else path
            
            # Simple package type detection based on launch URL
            package_type = 'standard'
            if 'scormcontent' in scorm_package.launch_url.lower():
                package_type = 'articulate_rise'
            elif 'story.html' in scorm_package.launch_url.lower():
                package_type = 'articulate_storyline'
            elif 'multiscreen.html' in scorm_package.launch_url.lower():
                package_type = 'adobe_captivate'
            elif 'presentation.html' in scorm_package.launch_url.lower():
                package_type = 'ispring'
            
            logger.info(f"Detected package type: {package_type} for launch URL: {scorm_package.launch_url}")
            
            # Add potential fallback paths based on package type
            if 'scormcontent' not in path and 'scormcontent' in scorm_package.launch_url:
                fallback_paths.append(f"scormcontent/{path}")
            
            # Articulate Rise specific fallbacks
            if package_type == 'articulate_rise_content' or package_type == 'articulate_rise' or package_type == 'articulate_rise_driver':
                # Handle empty paths or directory requests for Rise content
                if not path or path == 'scormcontent' or path == 'scormcontent/':
                    fallback_paths.append(f"scormcontent/index.html")
                
                fallback_paths.append(f"scormcontent/{file_name}")
                fallback_paths.append(f"scormcontent/index.html")
                if not path.startswith('scormcontent/'):
                    fallback_paths.append(f"scormcontent/{path}")
                    
                # Common Rise content structure paths
                if file_name.endswith('.js') or file_name.endswith('.css'):
                    fallback_paths.append(f"scormcontent/lib/{file_name}")
                elif file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.gif'):
                    fallback_paths.append(f"scormcontent/assets/{file_name}")
            
            # Articulate Storyline specific fallbacks
            elif package_type == 'articulate_storyline':
                fallback_paths.append(f"story_content/{file_name}")
                fallback_paths.append(f"story.html")
                fallback_paths.append(f"story_html5.html")
                if not path.startswith('story_content/'):
                    fallback_paths.append(f"story_content/{path}")
                    
                # Common Storyline structure paths
                if file_name.endswith('.js') or file_name.endswith('.css'):
                    fallback_paths.append(f"story_content/user.js")
                    fallback_paths.append(f"story_content/story.js")
                elif file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.gif'):
                    fallback_paths.append(f"story_content/assets/{file_name}")
            
            # Adobe Captivate specific fallbacks
            elif package_type == 'adobe_captivate':
                fallback_paths.append(f"assets/{file_name}")
                fallback_paths.append(f"multiscreen.html")
                fallback_paths.append(f"index.html")
                
                # Common Captivate structure paths
                if file_name.endswith('.js') or file_name.endswith('.css'):
                    fallback_paths.append(f"assets/js/{file_name}")
                    fallback_paths.append(f"assets/css/{file_name}")
                elif file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.gif'):
                    fallback_paths.append(f"assets/image/{file_name}")
            
            # iSpring specific fallbacks
            elif package_type == 'ispring':
                fallback_paths.append(f"data/{file_name}")
                fallback_paths.append(f"index_lms.html")
                fallback_paths.append(f"index.html")
                fallback_paths.append(f"presentation.html")
                
                # Common iSpring structure paths
                if file_name.endswith('.js') or file_name.endswith('.css'):
                    fallback_paths.append(f"data/js/{file_name}")
                elif file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.gif'):
                    fallback_paths.append(f"resources/{file_name}")
            
            # Lectora specific fallbacks
            elif package_type == 'lectora':
                fallback_paths.append(f"trivantis/{file_name}")
                fallback_paths.append(f"index.html")
                fallback_paths.append(f"course.html")
            
            # DominKnow specific fallbacks
            elif package_type == 'dominknow':
                fallback_paths.append(f"index_lms.html")
                fallback_paths.append(f"index.html")
            
            # Generic fallbacks for other package types
            else:
                fallback_paths.append(f"index.html")
                fallback_paths.append(f"index_lms.html")
                fallback_paths.append(f"story.html")
                fallback_paths.append(f"course.html")
                
                # Common content directories to try
                if file_name.endswith('.js') or file_name.endswith('.css'):
                    fallback_paths.append(f"content/{file_name}")
                    fallback_paths.append(f"assets/{file_name}")
                    fallback_paths.append(f"data/{file_name}")
                elif file_name.endswith('.png') or file_name.endswith('.jpg') or file_name.endswith('.jpeg') or file_name.endswith('.gif'):
                    fallback_paths.append(f"content/images/{file_name}")
                    fallback_paths.append(f"assets/images/{file_name}")
                    fallback_paths.append(f"data/images/{file_name}")
            
            # If it's a deep path with nested directories, try simplifying
            if path.count('/') > 1:
                fallback_paths.append(file_name)
            
            # Always try the original launch URL as a last resort
            fallback_paths.append(scorm_package.launch_url)
            
            # Try each fallback path
            for alt_path in fallback_paths:
                logger.info(f"Trying alternative path: {alt_path}")
                s3_url = scorm_s3.generate_direct_url(scorm_package, alt_path)
                if s3_url:
                    logger.info(f"Successfully generated URL using alternate path: {alt_path}")
                    path = alt_path  # Update the path to the successful one
                    break
            
            if not s3_url:
                logger.error(f"Could not generate URL after trying multiple paths: {path}")
                return HttpResponse("Content not found", status=404)
        
        # For JavaScript, CSS, and other resource files, fetch and serve directly
        if path.endswith(('.js', '.css', '.json', '.xml', '.xsd', '.dtd')):
            import requests
            try:
                # Fetch the resource from S3
                s3_response = requests.get(s3_url, timeout=30)
                if s3_response.status_code == 200:
                    # Determine content type
                    content_type = 'text/plain'
                    if path.endswith('.js'):
                        content_type = 'application/javascript'
                    elif path.endswith('.css'):
                        content_type = 'text/css'
                    elif path.endswith('.json'):
                        content_type = 'application/json'
                    elif path.endswith('.xml'):
                        content_type = 'application/xml'
                    
                    response = HttpResponse(s3_response.content, content_type=content_type)
                    response['Access-Control-Allow-Origin'] = '*'
                    response['Cache-Control'] = 'private, max-age=3600'
                    return response
                else:
                    logger.error(f"Failed to fetch resource from S3: {path}")
                    return HttpResponse("Resource not found", status=404)
            except Exception as e:
                logger.error(f"Error fetching resource: {e}")
                return HttpResponse("Error loading resource", status=500)
        
        # For media files (images, audio, video), redirect to S3
        if path.endswith(('.png', '.jpg', '.jpeg', '.gif', '.mp3', '.mp4', '.wav', '.webm', '.svg', '.ico')):
            response = HttpResponseRedirect(s3_url)
            response['Access-Control-Allow-Origin'] = '*'
            response['Cache-Control'] = 'private, max-age=7200'
            return response
        
        # For HTML files, fetch and inject SCORM API
        import requests
        
        try:
            # Debug logging
            logger.info(f"Processing request for topic {topic_id}, path: '{path}'")
            
            # Special handling for directory requests (common in SPA SCORM packages)
            if path == 'scormcontent' or path == 'scormcontent/' or path.endswith('/'):
                logger.info(f"Directory request detected: {path}")
                # Try to automatically redirect to index.html
                if path.endswith('/'):
                    redirect_path = f"{path}index.html"
                else:
                    redirect_path = f"{path}/index.html"
                redirect_path = redirect_path.replace('//', '/')
                
                logger.info(f"Redirecting directory request: {path} → {redirect_path}")
                # Use 302 redirect with proper headers to avoid circular redirects
                redirect_url = f"/scorm/content/{topic_id}/{redirect_path}"
                logger.info(f"Redirect URL: {redirect_url}")
                response = HttpResponseRedirect(redirect_url)
                response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
                return response
            
            # Fetch from S3 with proper encoding handling and better error handling
            try:
                s3_response = requests.get(s3_url, timeout=30)
                if s3_response.status_code != 200:
                    logger.error(f"S3 fetch failed: {s3_response.status_code} for path {path}")
                    # Try with index.html if path seems to be a directory
                    if not path.endswith('.html') and not path.endswith('.htm') and '.' not in path.split('/')[-1]:
                        alternative_path = f"{path}/index.html".replace('//', '/')
                        logger.info(f"Trying alternative path: {alternative_path}")
                        return HttpResponseRedirect(f"/scorm/content/{topic_id}/{alternative_path}")
                    return HttpResponse("Content not accessible", status=404)
            except requests.exceptions.RequestException as req_err:
                logger.error(f"S3 request failed: {req_err} for path {path}")
                return HttpResponse("Error accessing content storage", status=500)
            
            # Handle encoding properly - detect and use correct encoding
            if s3_response.encoding:
                s3_response.encoding = s3_response.apparent_encoding or 'utf-8'
            content = s3_response.text
            
            # Fix relative paths to use our proxy endpoint
            # This ensures all resources go through our server
            # Handle different path patterns based on package type
            if 'scormdriver' in path.lower():
                # Articulate Rise - paths are relative to scormdriver
                base_path = '/'.join(path.split('/')[:-1])  # Get directory path
                # Only replace relative paths, not absolute ones or already processed ones
                import re
                # Replace relative src paths
                content = re.sub(r'src="(?!http|/scorm/content/|data:|#)([^"]*)"', 
                                f'src="/scorm/content/{topic_id}/{base_path}/\\1"', content)
                content = re.sub(r"src='(?!http|/scorm/content/|data:|#)([^']*)'", 
                                f"src='/scorm/content/{topic_id}/{base_path}/\\1'", content)
                # Replace relative href paths
                content = re.sub(r'href="(?!http|/scorm/content/|data:|#|javascript:)([^"]*)"', 
                                f'href="/scorm/content/{topic_id}/{base_path}/\\1"', content)
                content = re.sub(r"href='(?!http|/scorm/content/|data:|#|javascript:)([^']*)'", 
                                f"href='/scorm/content/{topic_id}/{base_path}/\\1'", content)
            else:
                # Standard SCORM packages
                import re
                content = re.sub(r'src="(?!http|/scorm/content/|data:|#)([^"]*)"', 
                                f'src="/scorm/content/{topic_id}/\\1"', content)
                content = re.sub(r"src='(?!http|/scorm/content/|data:|#)([^']*)'", 
                                f"src='/scorm/content/{topic_id}/\\1'", content)
            # Additional href replacements for non-scormdriver packages
            if 'scormdriver' not in path.lower():
                content = re.sub(r'href="(?!http|/scorm/content/|data:|#|javascript:)([^"]*)"', 
                                f'href="/scorm/content/{topic_id}/\\1"', content)
                content = re.sub(r"href='(?!http|/scorm/content/|data:|#|javascript:)([^']*)'", 
                                f"href='/scorm/content/{topic_id}/\\1'", content)
            
            # Fix paths that already have ./ or ../
            content = content.replace(f'/scorm/content/{topic_id}/./', f'/scorm/content/{topic_id}/')
            content = content.replace(f'/scorm/content/{topic_id}/../', f'/scorm/content/{topic_id}/')
            content = content.replace(f'/scorm/content/{topic_id}/http', 'http')  # Don't break absolute URLs
            content = content.replace(f'/scorm/content/{topic_id}//', f'/scorm/content/{topic_id}/')  # Fix double slashes
            
            # Fix for Articulate Rise content - ensure scormcontent prefix is properly handled
            if 'scormcontent' in scorm_package.launch_url and 'scormcontent' not in path and not path.startswith('scormcontent'):
                content = content.replace(f'/scorm/content/{topic_id}/', f'/scorm/content/{topic_id}/scormcontent/')
                logger.info(f"Added scormcontent prefix to paths for Articulate Rise content")
            
            # Get base path for relative URL resolution
            if '/' in path:
                base_path = '/'.join(path.split('/')[:-1]) + '/'
            else:
                base_path = ''
            
            # Enhanced SCORM API injection - works for all package types
            api_script = f'''
<script>
// Enhanced SCORM API Bridge - Supports all authoring tools
(function() {{
    console.log('Initializing Enhanced SCORM API Bridge...');
    
    // Detect authoring tool from URL patterns
    var authoringTool = 'standard';
    var currentUrl = window.location.href;
    
    if (currentUrl.indexOf('scormdriver') > -1 || currentUrl.indexOf('index_lms') > -1) {{
        authoringTool = 'rise';
        console.log('Detected Articulate Rise 360 package');
    }} else if (currentUrl.indexOf('story.html') > -1 || currentUrl.indexOf('story_html5.html') > -1) {{
        authoringTool = 'storyline';
        console.log('Detected Articulate Storyline package');
    }} else if (currentUrl.indexOf('multiscreen.html') > -1) {{
        authoringTool = 'captivate';
        console.log('Detected Adobe Captivate package');
    }} else if (currentUrl.indexOf('presentation.html') > -1) {{
        authoringTool = 'ispring';
        console.log('Detected iSpring package');
    }}
    
    // Check if API already exists
    if (window.API || window.API_1484_11) {{
        console.log('SCORM API already exists, skipping initialization');
        return;
    }}
    
    // SCORM 1.2 API
    var API = {{
        _initialized: false,
        _data: {{}},
        
        LMSInitialize: function(param) {{
            console.log('SCORM 1.2: Initialize');
            this._initialized = true;
            this._data['cmi.core.student_name'] = 'Guest User';
            this._data['cmi.core.student_id'] = 'guest';
            this._data['cmi.core.lesson_status'] = 'incomplete';
            this._data['cmi.core.credit'] = 'credit';
            this._data['cmi.core.entry'] = 'ab-initio';
            this._data['cmi.core.lesson_mode'] = 'normal';
            this._data['cmi.core.lesson_location'] = '';
            this._data['cmi.core.total_time'] = '0000:00:00.00';
            this._data['cmi.core.session_time'] = '0000:00:00.00';
            this._data['cmi.core.score.raw'] = '';
            this._data['cmi.core.score.min'] = '0';
            this._data['cmi.core.score.max'] = '100';
            this._data['cmi.suspend_data'] = '';
            this._data['cmi.launch_data'] = '';
            return 'true';
        }},
        
        LMSFinish: function(param) {{
            console.log('SCORM 1.2: Finish');
            this._initialized = false;
            // Return immediately to allow SCORM package to navigate to exit page
            return 'true';
        }},
        
        LMSGetValue: function(key) {{
            console.log('SCORM 1.2: GetValue', key);
            return this._data[key] || '';
        }},
        
        LMSSetValue: function(key, value) {{
            console.log('SCORM 1.2: SetValue', key, '=', value);
            this._data[key] = value;
            return 'true';
        }},
        
        LMSCommit: function(param) {{
            console.log('SCORM 1.2: Commit');
            return 'true';
        }},
        
        LMSGetLastError: function() {{ return '0'; }},
        LMSGetErrorString: function(code) {{ return 'No error'; }},
        LMSGetDiagnostic: function(code) {{ return ''; }}
    }};
    
    // SCORM 2004 API
    var API_1484_11 = {{
        _initialized: false,
        _data: {{}},
        
        Initialize: function(param) {{
            console.log('SCORM 2004: Initialize');
            this._initialized = true;
            this._data['cmi.learner_name'] = 'Guest User';
            this._data['cmi.learner_id'] = 'guest';
            this._data['cmi.completion_status'] = 'incomplete';
            this._data['cmi.success_status'] = 'unknown';
            this._data['cmi.entry'] = 'ab-initio';
            this._data['cmi.mode'] = 'normal';
            this._data['cmi.location'] = '';
            this._data['cmi.total_time'] = 'PT0H0M0S';
            this._data['cmi.session_time'] = 'PT0H0M0S';
            this._data['cmi.score.raw'] = '';
            this._data['cmi.score.min'] = '0';
            this._data['cmi.score.max'] = '100';
            this._data['cmi.score.scaled'] = '';
            this._data['cmi.suspend_data'] = '';
            this._data['cmi.launch_data'] = '';
            return 'true';
        }},
        
        Terminate: function(param) {{
            console.log('SCORM 2004: Terminate');
            this._initialized = false;
            // Return immediately to allow SCORM package to navigate to exit page
            return 'true';
        }},
        
        GetValue: function(key) {{
            console.log('SCORM 2004: GetValue', key);
            return this._data[key] || '';
        }},
        
        SetValue: function(key, value) {{
            console.log('SCORM 2004: SetValue', key, '=', value);
            this._data[key] = value;
            return 'true';
        }},
        
        Commit: function(param) {{
            console.log('SCORM 2004: Commit');
            return 'true';
        }},
        
        GetLastError: function() {{ return '0'; }},
        GetErrorString: function(code) {{ return 'No error'; }},
        GetDiagnostic: function(code) {{ return ''; }}
    }};
    
    // Set APIs globally
    window.API = API;
    window.API_1484_11 = API_1484_11;
    
    // Also set on parent for packages that look there
    if (window.parent && window.parent !== window) {{
        window.parent.API = API;
        window.parent.API_1484_11 = API_1484_11;
    }}
    
    console.log('SCORM API Bridge initialized successfully');
}})();

// Fix for packages that look for API in parent frames
if (!window.API && window.parent && window.parent.API) {{
    window.API = window.parent.API;
}}
if (!window.API_1484_11 && window.parent && window.parent.API_1484_11) {{
    window.API_1484_11 = window.parent.API_1484_11;
}}
</script>
<base href="/scorm/content/{topic_id}/{base_path}">
'''
            
            # Inject API at the beginning of <head> or at start of document
            if '<head>' in content:
                content = content.replace('<head>', '<head>' + api_script)
            elif '<HEAD>' in content:
                content = content.replace('<HEAD>', '<HEAD>' + api_script)
            else:
                # No head tag, inject at beginning
                content = api_script + content
            
            # Return processed content
            response = HttpResponse(content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Cache-Control'] = 'private, max-age=3600'
            # Override any CSP with permissive policy for SCORM content
            response['Content-Security-Policy'] = "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; worker-src * blob: data:; style-src * 'unsafe-inline'; img-src * data: blob:; font-src * data:; connect-src *; media-src * data: blob:; frame-src *; object-src 'none'"
            return response
            
        except requests.RequestException as e:
            logger.error(f"Error fetching from S3: {e} for path {path}", exc_info=True)
            
            # Try to return a more helpful error page with refresh option
            error_html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Content Error</title>
                <style>
                    body {{ font-family: Arial, sans-serif; padding: 20px; text-align: center; }}
                    .error-container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #f5c6cb; background-color: #f8d7da; color: #721c24; border-radius: 5px; }}
                    .btn {{ display: inline-block; margin-top: 20px; padding: 10px 20px; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h2>Error Loading Content</h2>
                    <p>The SCORM content could not be loaded from storage. This may be due to a temporary issue.</p>
                    <p>Error details: Failed to load {path}</p>
                    <a href="javascript:window.location.reload();" class="btn">Refresh Page</a>
                </div>
            </body>
            </html>
            '''
            
            return HttpResponse(error_html, content_type='text/html', status=500)
    
    except Exception as e:
        logger.error(f"Error in direct content: {e}")
        return HttpResponse("Error", status=500)


# Remove all old complex views - keeping only simplified versions above
