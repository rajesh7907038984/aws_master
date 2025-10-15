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
    Generate direct S3 URL for SCORM content
    """
    try:
        # Get S3 settings
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        region_name = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
        custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
        
        if not bucket_name:
            logger.error("AWS_STORAGE_BUCKET_NAME not configured")
            return None
        
        # Build the S3 path
        base_path = scorm_package.extracted_path
        if not base_path:
            logger.error(f"No extracted_path for package {scorm_package.id}")
            return None
        
        # Combine paths
        if path:
            full_path = f"{base_path}/{path}".replace('//', '/')
        else:
            full_path = f"{base_path}/{scorm_package.launch_url}".replace('//', '/')
        
        # Generate URL
        if custom_domain:
            # Use CloudFront or custom domain
            s3_url = f"https://{custom_domain}/{full_path}"
        else:
            # Use direct S3 URL
            s3_url = f"https://{bucket_name}.s3.{region_name}.amazonaws.com/{full_path}"
        
        logger.info(f"Generated S3 URL: {s3_url}")
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
        
        # Get direct S3 URL
        launch_url = get_s3_direct_url(scorm_package)
        
        if not launch_url:
            return HttpResponse("Could not generate SCORM content URL", status=500)
        
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
    Direct proxy to S3 content with minimal processing
    """
    try:
        topic = get_object_or_404(Topic, id=topic_id)
        scorm_package = topic.scorm_package
        
        if not scorm_package:
            return HttpResponse("No SCORM package", status=404)
        
        # Get S3 URL for the requested path
        s3_url = get_s3_direct_url(scorm_package, path)
        
        if not s3_url:
            return HttpResponse("Content not found", status=404)
        
        # For non-HTML files, redirect directly to S3
        if not path.endswith(('.html', '.htm')):
            from django.http import HttpResponseRedirect
            response = HttpResponseRedirect(s3_url)
            response['Access-Control-Allow-Origin'] = '*'
            response['Cache-Control'] = 'public, max-age=3600'
            return response
        
        # For HTML files, fetch and inject minimal SCORM API
        import requests
        
        try:
            # Fetch from S3
            s3_response = requests.get(s3_url, timeout=30)
            if s3_response.status_code != 200:
                logger.error(f"S3 fetch failed: {s3_response.status_code}")
                return HttpResponse("Content not accessible", status=404)
            
            content = s3_response.text
            
            # Inject minimal SCORM API only if needed
            if 'scormdriver' in path or 'story.html' in path or 'index' in path:
                api_script = f'''
<script>
// Minimal SCORM API for compatibility
(function() {{
    if (window.API || window.API_1484_11) return;
    
    var API = {{
        LMSInitialize: function() {{ return "true"; }},
        LMSFinish: function() {{ return "true"; }},
        LMSGetValue: function(key) {{ 
            var defaults = {{
                "cmi.core.student_name": "Guest",
                "cmi.core.student_id": "guest",
                "cmi.core.lesson_status": "incomplete",
                "cmi.core.credit": "credit",
                "cmi.core.entry": "ab-initio",
                "cmi.core.lesson_mode": "normal",
                "cmi.core.total_time": "0000:00:00.00"
            }};
            return defaults[key] || "";
        }},
        LMSSetValue: function(key, val) {{ return "true"; }},
        LMSCommit: function() {{ return "true"; }},
        LMSGetLastError: function() {{ return "0"; }},
        LMSGetErrorString: function() {{ return "No error"; }},
        LMSGetDiagnostic: function() {{ return ""; }}
    }};
    
    // SCORM 1.2 compatibility
    window.API = API;
    
    // SCORM 2004 compatibility
    window.API_1484_11 = {{
        Initialize: function() {{ return "true"; }},
        Terminate: function() {{ return "true"; }},
        GetValue: function(key) {{ return API.LMSGetValue(key); }},
        SetValue: function(key, val) {{ return "true"; }},
        Commit: function() {{ return "true"; }},
        GetLastError: function() {{ return "0"; }},
        GetErrorString: function() {{ return "No error"; }},
        GetDiagnostic: function() {{ return ""; }}
    }};
}})();
</script>
'''
                
                # Inject before </head> or at start
                if '</head>' in content:
                    content = content.replace('</head>', api_script + '</head>')
                else:
                    content = api_script + content
            
            # Return processed content
            response = HttpResponse(content, content_type='text/html; charset=utf-8')
            response['Access-Control-Allow-Origin'] = '*'
            response['X-Frame-Options'] = 'ALLOWALL'
            response['Cache-Control'] = 'public, max-age=3600'
            return response
            
        except requests.RequestException as e:
            logger.error(f"Error fetching from S3: {e}")
            return HttpResponse("Error loading content", status=500)
    
    except Exception as e:
        logger.error(f"Error in direct content: {e}")
        return HttpResponse("Error", status=500)


# Remove all old complex views - keeping only simplified versions above
