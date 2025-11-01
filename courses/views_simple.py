"""
Simplified views for section management
Clean, simple implementations without complex error handling
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Section, Topic
import logging

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["DELETE"])
def simple_section_delete(request, section_id):
    """
    Simple section deletion - clean implementation
    """
    try:
        section = get_object_or_404(Section, id=section_id)
        course = section.course
        
        # Proper permission check using the course model's permission method
        if not course.user_can_modify(request.user):
            logger.warning(f"Permission denied for user {request.user.id} ({request.user.role}) to delete section {section_id}")
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            }, status=403)
        
        # Move topics to unsectioned
        Topic.objects.filter(section=section).update(section=None)
        
        # Delete section
        section_name = section.name or f"Section {section.id}"
        section.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Section "{section_name}" deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Section delete error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to delete section'
        }, status=500)
