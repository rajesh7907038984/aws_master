from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import json
import html

register = template.Library()


@register.filter
def get_display_name(user_or_name):
    """
    Get a human-readable display name for a user or name string.
    
    Args:
        user_or_name: Either a User object or a string name
    
    Returns:
        A human-readable display name
    """
    if hasattr(user_or_name, 'get_full_name'):
        # This is a User object
        full_name = user_or_name.get_full_name()
        return full_name if full_name else user_or_name.username
    elif isinstance(user_or_name, str):
        # This is already a string name
        return user_or_name
    else:
        # Fallback
        return str(user_or_name)


@register.filter
def get_attendance_display_name(attendance):
    """
    Get the best display name for an attendance record.
    Prioritizes LMS user name over Zoom participant name.
    
    Args:
        attendance: ConferenceAttendance object
    
    Returns:
        Human-readable name for display
    """
    if attendance.user:
        # Use LMS user's full name
        full_name = attendance.user.get_full_name()
        if full_name:
            return full_name
        else:
            return attendance.user.username
    
    # Fallback to Zoom participant name if available
    zoom_name = attendance.device_info.get('zoom_participant_name', '')
    if zoom_name:
        return zoom_name
    
    # Final fallback
    return f"Participant {attendance.participant_id[:8]}" if attendance.participant_id else "Unknown Participant"


@register.filter
def get_chat_sender_display_name(chat_message):
    """
    Get the best display name for a chat message sender.
    Prioritizes LMS user name over platform sender name.
    
    Args:
        chat_message: ConferenceChat object
    
    Returns:
        Human-readable sender name for display
    """
    if chat_message.sender:
        # Use LMS user's full name
        full_name = chat_message.sender.get_full_name()
        if full_name:
            return full_name
        else:
            return chat_message.sender.username
    
    # Fallback to platform sender name
    return chat_message.sender_name if chat_message.sender_name else "Unknown Sender"


@register.filter
def format_duration(minutes):
    """
    Format duration in minutes to a human-readable format.
    
    Args:
        minutes: Duration in minutes (integer)
    
    Returns:
        Formatted duration string (e.g., "1h 30m", "45m")
    """
    if not minutes or minutes <= 0:
        return "0m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if hours > 0:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        else:
            return f"{hours}h"
    else:
        return f"{remaining_minutes}m"


@register.filter
def get_user_email_safe(user):
    """
    Safely get user email, returning empty string if not available.
    
    Args:
        user: User object
    
    Returns:
        User email or empty string
    """
    if hasattr(user, 'email'):
        return user.email if user.email else ""
    return ""


@register.filter
def get_file_icon_class(file_obj):
    """
    Get appropriate Font Awesome icon class based on file type.
    
    Args:
        file_obj: ConferenceFile object
    
    Returns:
        Font Awesome icon class string
    """
    if not hasattr(file_obj, 'file_type'):
        return "fas fa-file"
    
    file_type = file_obj.file_type.lower()
    
    if file_type in ['pdf']:
        return "fas fa-file-pdf"
    elif file_type in ['doc', 'docx']:
        return "fas fa-file-word"
    elif file_type in ['xls', 'xlsx']:
        return "fas fa-file-excel"
    elif file_type in ['ppt', 'pptx']:
        return "fas fa-file-powerpoint"
    elif file_type in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
        return "fas fa-file-image"
    elif file_type in ['mp4', 'avi', 'mov', 'wmv']:
        return "fas fa-file-video"
    elif file_type in ['mp3', 'wav', 'ogg']:
        return "fas fa-file-audio"
    elif file_type in ['zip', 'rar', '7z']:
        return "fas fa-file-archive"
    elif file_type in ['txt']:
        return "fas fa-file-alt"
    else:
        return "fas fa-file"


@register.filter
def participant_info_json(participant_data):
    """
    Safely convert participant device info to JSON for JavaScript use.
    
    Args:
        participant_data: Dictionary with participant information
    
    Returns:
        JSON string safe for use in templates
    """
    try:
        # Extract safe information for frontend use
        safe_data = {
            'lms_user_id': participant_data.get('lms_user', {}).get('id') if isinstance(participant_data.get('lms_user'), dict) else getattr(participant_data.get('lms_user'), 'id', None),
            'zoom_participant_id': participant_data.get('zoom_participant_id', ''),
            'duration': participant_data.get('duration', 0),
            'status': participant_data.get('status', ''),
            'join_time': participant_data.get('join_time', ''),
            'leave_time': participant_data.get('leave_time', '')
        }
        return mark_safe(json.dumps(safe_data))
    except (TypeError, ValueError):
        return mark_safe('{}')


@register.simple_tag
def conference_sync_status_badge(conference):
    """
    Generate HTML for conference sync status badge.
    
    Args:
        conference: Conference object
    
    Returns:
        HTML badge for sync status
    """
    status = conference.data_sync_status
    status_classes = {
        'pending': 'bg-yellow-100 text-yellow-800',
        'in_progress': 'bg-blue-100 text-blue-800',
        'completed': 'bg-green-100 text-green-800',
        'failed': 'bg-red-100 text-red-800'
    }
    
    status_icons = {
        'pending': 'fas fa-clock',
        'in_progress': 'fas fa-spinner fa-spin',
        'completed': 'fas fa-check-circle',
        'failed': 'fas fa-exclamation-triangle'
    }
    
    css_class = status_classes.get(status, 'bg-gray-100 text-gray-800')
    icon_class = status_icons.get(status, 'fas fa-question')
    
    html = f'''
    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {css_class}">
        <i class="{icon_class} mr-1"></i>
        {conference.get_data_sync_status_display()}
    </span>
    '''
    
    return mark_safe(html)


@register.simple_tag
def meeting_recording_badge(conference):
    """
    Generate HTML for meeting recording status badge.
    
    Args:
        conference: Conference object
    
    Returns:
        HTML badge for recording status
    """
    status = conference.auto_recording_status
    status_classes = {
        'pending': 'bg-yellow-100 text-yellow-800',
        'enabled': 'bg-green-100 text-green-800',
        'failed_no_integration': 'bg-red-100 text-red-800',
        'failed_invalid_credentials': 'bg-red-100 text-red-800',
        'failed_auth': 'bg-red-100 text-red-800',
        'failed_api_error': 'bg-red-100 text-red-800',
        'failed_exception': 'bg-red-100 text-red-800',
        'not_applicable': 'bg-gray-100 text-gray-800'
    }
    
    status_icons = {
        'pending': 'fas fa-clock',
        'enabled': 'fas fa-video',
        'failed_no_integration': 'fas fa-exclamation-triangle',
        'failed_invalid_credentials': 'fas fa-key',
        'failed_auth': 'fas fa-lock',
        'failed_api_error': 'fas fa-times-circle',
        'failed_exception': 'fas fa-bug',
        'not_applicable': 'fas fa-minus'
    }
    
    css_class = status_classes.get(status, 'bg-gray-100 text-gray-800')
    icon_class = status_icons.get(status, 'fas fa-question')
    
    html = f'''
    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {css_class}">
        <i class="{icon_class} mr-1"></i>
        Recording: {conference.get_auto_recording_status_display()}
    </span>
    '''
    
    return mark_safe(html)


@register.filter
def attendance_status_class(status):
    """
    Get CSS class for attendance status.
    
    Args:
        status: Attendance status string
    
    Returns:
        CSS class string for styling
    """
    status_classes = {
        'present': 'text-green-600 bg-green-100',
        'absent': 'text-gray-600 bg-gray-100',
        'late': 'text-yellow-600 bg-yellow-100',
        'left_early': 'text-red-600 bg-red-100'
    }
    
    return status_classes.get(status, 'text-gray-600 bg-gray-100')


@register.filter
def zoom_participant_id_short(participant_id):
    """
    Show a shortened version of Zoom participant ID for display.
    
    Args:
        participant_id: Full Zoom participant ID
    
    Returns:
        Shortened ID for display
    """
    if not participant_id:
        return "N/A"
    
    # Show first 8 characters for identification
    return participant_id[:8] + "..." if len(participant_id) > 8 else participant_id


@register.filter
def average_score(attendance_scores):
    """
    Calculate the average score from a list of attendance score data.
    
    Args:
        attendance_scores: List of dictionaries containing 'total_points' key
    
    Returns:
        Average score as a float, or 0 if no scores
    """
    if not attendance_scores:
        return 0
    
    try:
        total = sum(score_data.get('total_points', 0) for score_data in attendance_scores)
        count = len(attendance_scores)
        return total / count if count > 0 else 0
    except (TypeError, AttributeError):
        # Handle case where attendance_scores might not be a list of dicts
        return 0


@register.filter
def mul(value, arg):
    """
    Multiply value by arg.
    
    Args:
        value: The value to multiply
        arg: The multiplier
    
    Returns:
        The product of value and arg
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def div(value, arg):
    """
    Divide value by arg.
    
    Args:
        value: The dividend
        arg: The divisor
    
    Returns:
        The quotient of value divided by arg
    """
    try:
        divisor = float(arg)
        if divisor == 0:
            return 0
        return float(value) / divisor
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def decode_html(value):
    """
    Decode HTML entities and render HTML content properly.
    This helps fix conference descriptions that show HTML code instead of rendered content.
    Handles both escaped HTML entities and raw HTML tags.
    
    Args:
        value: String that might contain HTML entities or HTML tags
    
    Returns:
        Decoded HTML string safe for rendering
    """
    if not value:
        return ""
    
    try:
        content = str(value)
        
        # First decode any HTML entities (like &lt; to <, &amp; to &)
        decoded = html.unescape(content)
        
        # Check if content contains HTML tags (like <br>, <strong>, <a>, etc.)
        import re
        html_tag_pattern = r'</?[a-zA-Z][^>]*>'
        has_html_tags = re.search(html_tag_pattern, decoded)
        
        # If content has HTML tags, mark it as safe for rendering
        if has_html_tags:
            return mark_safe(decoded)
        
        # If content has HTML entities but no tags, unescape and mark safe
        # This handles cases where entities are escaped but tags aren't present
        if '&lt;' in content or '&gt;' in content or '&amp;' in content:
            return mark_safe(decoded)
        
        # For plain text, return as-is (marked safe to allow any HTML that might be there)
        return mark_safe(decoded)
        
    except (ValueError, TypeError, AttributeError) as e:
        # If decoding fails, try to return the original value as safe
        # This handles edge cases where content might be in an unexpected format
        try:
            return mark_safe(str(value))
        except Exception:
            return ""


@register.filter
def filter_by_user(queryset, user):
    """
    Filter a queryset to get the first object matching a specific user.
    
    Args:
        queryset: QuerySet to filter
        user: User object to filter by
    
    Returns:
        First matching object or None
    """
    if not queryset or not user:
        return None
    try:
        return queryset.filter(user=user).first()
    except:
        return None


@register.filter
def filter_all_by_user(queryset, user):
    """
    Filter a queryset to get all objects matching a specific user.
    Useful for cases where users can have multiple selections (e.g., instructors with multiple time slots).
    
    Args:
        queryset: QuerySet to filter
        user: User object to filter by
    
    Returns:
        QuerySet of all matching objects
    """
    if not queryset or not user:
        return queryset.none() if queryset else []
    try:
        return queryset.filter(user=user)
    except:
        return queryset.none() if queryset else []


@register.simple_tag
def is_slot_selected_by_user(conference, time_slot, user):
    """
    Check if a specific time slot is selected by a user.
    
    Args:
        conference: Conference object
        time_slot: TimeSlot object to check
        user: User object
    
    Returns:
        Boolean indicating if the slot is selected
    """
    from conferences.models import ConferenceTimeSlotSelection
    
    if not conference or not time_slot or not user:
        return False
    
    try:
        return ConferenceTimeSlotSelection.objects.filter(
            conference=conference,
            time_slot=time_slot,
            user=user
        ).exists()
    except:
        return False 