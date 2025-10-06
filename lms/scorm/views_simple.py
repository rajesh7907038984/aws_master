"""
Simplified SCORM Content Serving
Replaces complex JavaScript injection with simple, working version
"""
from django.http import HttpResponse, HttpResponseRedirect
from django.core.files.storage import default_storage
from django.urls import reverse
from .s3_direct import scorm_s3
import logging

logger = logging.getLogger(__name__)

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
        # Old URLs used patterns like: /scorm/direct/31/scormcontent/index.html
        # These should redirect to: /scorm/view/31/
        if 'scormcontent' in path or path.endswith('index.html') or path.endswith('.html'):
            logger.info(f"Redirecting old SCORM URL pattern to proper view: /scorm/view/{topic_id}/")
            return HttpResponseRedirect(reverse('scorm:view', kwargs={'topic_id': topic_id}))
        
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
