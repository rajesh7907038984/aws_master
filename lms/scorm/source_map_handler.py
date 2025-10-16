"""
SCORM Source Map Handler
Provides fallback responses for missing source map files to reduce console errors
"""

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json


@csrf_exempt
@require_http_methods(["GET"])
def handle_source_map(request, filename):
    """
    Handle requests for missing source map files
    Returns an empty source map to prevent 404 errors
    """
    # Return an empty source map to prevent console errors
    empty_source_map = {
        "version": 3,
        "sources": [],
        "names": [],
        "mappings": "",
        "file": filename
    }
    
    response = HttpResponse(
        json.dumps(empty_source_map),
        content_type='application/json'
    )
    
    # Add cache headers to prevent repeated requests
    response['Cache-Control'] = 'public, max-age=3600'
    response['Expires'] = 'Thu, 31 Dec 2025 23:59:59 GMT'
    
    return response


@csrf_exempt
@require_http_methods(["GET"])
def handle_desktop_css_map(request):
    """
    Handle requests for desktop.min.css.map specifically
    """
    return handle_source_map(request, "desktop.min.css.map")
