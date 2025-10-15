"""
Simplified SCORM Player - Direct S3 Embedding
No authentication required, direct iframe embedding from S3
"""
import logging
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.conf import settings
import boto3
from botocore.exceptions import NoCredentialsError

from .models import ScormPackage, ScormAttempt
from courses.models import Topic

logger = logging.getLogger(__name__)


def detect_package_type(launch_url):
    """
    Auto-detect SCORM package type based on launch URL patterns
    """
    launch_url_lower = launch_url.lower() if launch_url else ''
    
    # Articulate Rise with scormdriver
    if 'scormdriver' in launch_url_lower and 'indexapi' in launch_url_lower:
        return 'articulate_rise_driver'
    elif 'scormdriver' in launch_url_lower:
        return 'articulate_rise'
    
    # Articulate Rise content only
    elif 'scormcontent' in launch_url_lower:
        return 'articulate_rise_content'
    
    # Articulate Storyline
    elif 'story.html' in launch_url_lower or 'story_html5.html' in launch_url_lower:
        return 'articulate_storyline'
    
    # Adobe Captivate
    elif 'captivate' in launch_url_lower or 'multiscreen.html' in launch_url_lower:
        return 'adobe_captivate'
    
    # Lectora
    elif 'lectora' in launch_url_lower or 'trivantis' in launch_url_lower:
        return 'lectora'
    
    # iSpring
    elif 'ispring' in launch_url_lower or 'presentation.html' in launch_url_lower:
        return 'ispring'
    
    # Index-based packages
    elif 'index_lms.html' in launch_url_lower:
        return 'lms_specific'
    elif 'index.html' in launch_url_lower:
        return 'standard_html'
    
    # Default
    return 'unknown'


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
    Simplified SCORM Player - Direct S3 embedding without authentication
    """
    try:
        # Get topic and SCORM package
        topic = get_object_or_404(Topic, id=topic_id)
        
        if not hasattr(topic, 'scorm_package'):
            return HttpResponse("No SCORM package found for this topic", status=404)
        
        scorm_package = topic.scorm_package
        
        # Detect package type
        package_type = detect_package_type(scorm_package.launch_url)
        logger.info(f"Detected package type: {package_type} for {scorm_package.launch_url}")
        
        # For HTML files, use Django proxy to inject SCORM API
        # For other resources, they'll be loaded directly from S3
        launch_url = f"/scorm/content/{topic_id}/{scorm_package.launch_url}"
        
        # Log the launch URL for debugging
        logger.info(f"Using proxied launch URL: {launch_url} for package type: {package_type}")
        
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
            'scorm_version': scorm_package.version,
            'direct_embed': True,  # Flag for direct embedding
        }
        
        return render(request, 'scorm/player.html', context)
        
    except Exception as e:
        logger.error(f"Error in SCORM player: {e}")
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
    Lightweight SCORM API for basic tracking (works without authentication)
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
            
            # Basic SCORM API responses (minimal tracking)
            if method in ['Initialize', 'LMSInitialize']:
                return JsonResponse({'result': 'true', 'error': '0'})
            
            elif method in ['Terminate', 'LMSFinish', 'LMSTerminate']:
                return JsonResponse({'result': 'true', 'error': '0'})
            
            elif method in ['Commit', 'LMSCommit']:
                return JsonResponse({'result': 'true', 'error': '0'})
            
            elif method in ['GetValue', 'LMSGetValue']:
                element = parameters[0] if parameters else ''
                
                # Return minimal default values
                defaults = {
                    'cmi.core.student_id': 'guest',
                    'cmi.core.student_name': 'Guest User',
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
                return JsonResponse({'result': value, 'error': '0'})
            
            elif method in ['SetValue', 'LMSSetValue']:
                # Accept but don't store (no auth required)
                return JsonResponse({'result': 'true', 'error': '0'})
            
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
        
        # Generate presigned URL for the requested path
        if path:
            s3_url = scorm_s3.generate_direct_url(scorm_package, path)
        else:
            s3_url = scorm_s3.generate_launch_url(scorm_package)
        
        if not s3_url:
            logger.error(f"Could not generate URL for path: {path}")
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
            from django.http import HttpResponseRedirect
            response = HttpResponseRedirect(s3_url)
            response['Access-Control-Allow-Origin'] = '*'
            response['Cache-Control'] = 'private, max-age=7200'
            return response
        
        # For HTML files, fetch and inject SCORM API
        import requests
        
        try:
            # Fetch from S3 with proper encoding handling
            s3_response = requests.get(s3_url, timeout=30)
            if s3_response.status_code != 200:
                logger.error(f"S3 fetch failed: {s3_response.status_code}")
                return HttpResponse("Content not accessible", status=404)
            
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
            return response
            
        except requests.RequestException as e:
            logger.error(f"Error fetching from S3: {e}")
            return HttpResponse("Error loading content", status=500)
    
    except Exception as e:
        logger.error(f"Error in direct content: {e}")
        return HttpResponse("Error", status=500)


# Remove all old complex views - keeping only simplified versions above
