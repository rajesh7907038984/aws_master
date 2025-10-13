"""
SCORM Package Validation Views
Provides endpoints for validating SCORM packages before upload
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect

from .validators import validate_scorm_package, get_validation_summary

logger = logging.getLogger(__name__)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def validate_scorm_ajax(request):
    """
    AJAX endpoint for validating SCORM packages
    Used by JavaScript file upload widgets
    """
    if not request.FILES.get('scorm_package'):
        return JsonResponse({
            'valid': False,
            'error': 'No file uploaded'
        }, status=400)
    
    uploaded_file = request.FILES['scorm_package']
    
    try:
        # Validate the package
        validation_results = validate_scorm_package(uploaded_file)
        
        # Add summary message
        validation_results['summary'] = get_validation_summary(validation_results)
        
        logger.info(f"SCORM validation for {uploaded_file.name}: {validation_results['summary']}")
        
        return JsonResponse(validation_results)
        
    except Exception as e:
        logger.error(f"Error validating SCORM package {uploaded_file.name}: {str(e)}")
        return JsonResponse({
            'valid': False,
            'error': f'Validation error: {str(e)}',
            'summary': ' Validation failed'
        }, status=500)


@login_required
def validation_test_page(request):
    """
    Test page for SCORM package validation
    Useful for administrators to test packages
    """
    if request.method == 'POST' and request.FILES.get('scorm_package'):
        uploaded_file = request.FILES['scorm_package']
        
        try:
            validation_results = validate_scorm_package(uploaded_file)
            summary = get_validation_summary(validation_results)
            
            if validation_results['valid']:
                messages.success(request, f" {summary}")
            else:
                messages.error(request, f" {summary}")
            
            return render(request, 'scorm/validation_test.html', {
                'validation_results': validation_results,
                'uploaded_file': uploaded_file,
                'summary': summary
            })
            
        except Exception as e:
            messages.error(request, f"Validation error: {str(e)}")
    
    return render(request, 'scorm/validation_test.html')


def scorm_help(request):
    """
    SCORM help and documentation page
    """
    return render(request, 'scorm/help.html', {
        'scorm_requirements': {
            'max_size': '500MB',
            'required_files': ['imsmanifest.xml'],
            'supported_versions': ['SCORM 1.2', 'SCORM 2004'],
            'supported_formats': ['.zip'],
        }
    })
