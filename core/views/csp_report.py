"""
CSP Violation Report Handler
Handles Content Security Policy violation reports for debugging
"""

import json
import logging
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def csp_report_view(request):
    """
    Handle CSP violation reports
    This endpoint receives CSP violation reports from browsers
    """
    try:
        if request.content_type == 'application/csp-report':
            # Parse the CSP report
            report_data = json.loads(request.body.decode('utf-8'))
            
            # Log the violation for debugging
            logger.warning(f"CSP Violation Report: {report_data}")
            
            # Extract useful information
            if 'csp-report' in report_data:
                csp_report = report_data['csp-report']
                violated_directive = csp_report.get('violated-directive', 'unknown')
                blocked_uri = csp_report.get('blocked-uri', 'unknown')
                source_file = csp_report.get('source-file', 'unknown')
                line_number = csp_report.get('line-number', 'unknown')
                
                logger.warning(
                    f"CSP Violation Details - "
                    f"Directive: {violated_directive}, "
                    f"Blocked URI: {blocked_uri}, "
                    f"Source: {source_file}:{line_number}"
                )
        
        return HttpResponse(status=204)
        
    except Exception as e:
        logger.error(f"Error processing CSP report: {e}")
        return HttpResponse(status=400)
