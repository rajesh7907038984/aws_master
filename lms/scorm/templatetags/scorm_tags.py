"""
SCORM Template Tags and Filters
"""
from django import template
from django.urls import reverse
from scorm.models import SCORMPackage, SCORMAttempt
from scorm.utils import get_topic_scorm_package, is_topic_scorm_enabled

register = template.Library()


@register.simple_tag
def get_scorm_package_for_topic(topic):
    """Get SCORM package for a topic"""
    return get_topic_scorm_package(topic)


@register.simple_tag
def topic_has_scorm(topic):
    """Check if topic has SCORM content"""
    return is_topic_scorm_enabled(topic)


@register.simple_tag
def get_scorm_player_url(topic):
    """Get SCORM player URL for a topic"""
    package = get_topic_scorm_package(topic)
    if package:
        return reverse('scorm:player', kwargs={'package_id': package.id})
    return None


@register.simple_tag
def get_user_scorm_progress(user, topic):
    """Get user's SCORM progress for a topic"""
    package = get_topic_scorm_package(topic)
    if not package:
        return None
    
    attempt = SCORMAttempt.objects.filter(
        user=user,
        package=package
    ).order_by('-started_at').first()
    
    if attempt:
        return {
            'status': attempt.lesson_status,
            'score': attempt.score_raw,
            'progress': attempt.get_progress_percentage(),
            'completed': attempt.is_completed()
        }
    
    return None


@register.filter
def scorm_status_badge(status):
    """Return Bootstrap badge class for SCORM status"""
    status_map = {
        'completed': 'success',
        'passed': 'success',
        'incomplete': 'warning',
        'failed': 'danger',
        'browsed': 'info',
        'not attempted': 'secondary'
    }
    return status_map.get(status, 'secondary')


@register.filter
def scorm_package_type_icon(package_type):
    """Return icon for package type"""
    icon_map = {
        'SCORM_12': 'fa-file-archive',
        'SCORM_2004': 'fa-file-archive',
        'XAPI': 'fa-cloud',
        'ARTICULATE_RISE': 'fa-graduation-cap',
        'ARTICULATE_STORYLINE': 'fa-graduation-cap',
        'ADOBE_CAPTIVATE': 'fa-play-circle',
        'ISPRING': 'fa-chalkboard-teacher',
        'LECTORA': 'fa-book-open',
        'HTML5': 'fa-html5',
        'AUTO': 'fa-magic'
    }
    return icon_map.get(package_type, 'fa-file')

