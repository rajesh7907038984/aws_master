from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from decimal import Decimal
from collections import defaultdict
import os

register = template.Library()

@register.filter
def contains(queryset, user):
    """Check if queryset contains a specific user"""
    if not queryset:
        return False
    try:
        return user in queryset
    except (TypeError, AttributeError):
        return False

@register.filter 
def sum_points(evaluations):
    """Calculate the sum of points from rubric evaluations"""
    if not evaluations:
        return 0
    try:
        return sum(Decimal(str(eval.points)) for eval in evaluations if eval.points is not None)
    except (TypeError, ValueError, AttributeError):
        return 0

@register.filter
def safe_file_size(file_field):
    """
    Safely get file size without raising FileNotFoundError.
    Returns 0 if file doesn't exist or can't be accessed.
    
    Args:
        file_field: Django FileField instance
    
    Returns:
        File size in bytes or 0 if not accessible
    """
    try:
        if file_field and hasattr(file_field, 'size') and file_field.name:
            return file_field.size
    except (FileNotFoundError, OSError, ValueError):
        # File doesn't exist on disk or other file access error
        pass
    return 0

@register.filter
def format_duration(seconds):
    """Format duration in seconds to human readable format"""
    if not seconds:
        return "0s"
    
    try:
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {remaining_seconds}s"
        elif minutes > 0:
            return f"{minutes}m {remaining_seconds}s"
        else:
            return f"{remaining_seconds}s"
    except (TypeError, ValueError):
        return "0s"

@register.filter
def get_interaction_count(interactions, interaction_type):
    """Count interactions of a specific type"""
    if not interactions:
        return 0
    
    try:
        return len([i for i in interactions if i.get('type') == interaction_type])
    except (TypeError, AttributeError):
        return 0

@register.filter
def get_total_session_time(session_logs):
    """Calculate total time from session logs"""
    if not session_logs:
        return 0
    
    try:
        return sum(session.total_duration_seconds for session in session_logs if session.total_duration_seconds)
    except (TypeError, AttributeError):
        return 0

@register.filter
def format_file_size(size_bytes):
    """Format file size in bytes to human readable format"""
    if not size_bytes:
        return "0 B"
    
    try:
        size_bytes = int(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    except (TypeError, ValueError):
        return "0 B"

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    try:
        return dictionary.get(key)
    except (TypeError, AttributeError):
        return None

@register.filter
def multiply(value, multiplier):
    """Multiply two values"""
    try:
        return float(value) * float(multiplier)
    except (TypeError, ValueError):
        return 0

@register.filter
def mul(value, multiplier):
    """Multiply two values (alias for multiply filter)"""
    try:
        return float(value) * float(multiplier)
    except (TypeError, ValueError):
        return 0

@register.filter
def div(value, divisor):
    """Divide two values"""
    try:
        if not divisor or divisor == 0:
            return 0
        return float(value) / float(divisor)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0

@register.filter
def percentage(value, total):
    """Calculate percentage"""
    try:
        if not total or total == 0:
            return 0
        return round((float(value) / float(total)) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0

@register.filter
def group_interactions_by_type(interactions):
    """Group interactions by type for analysis"""
    if not interactions:
        return {}
    
    grouped = defaultdict(list)
    try:
        for interaction in interactions:
            interaction_type = interaction.get('type', 'unknown')
            grouped[interaction_type].append(interaction)
        return dict(grouped)
    except (TypeError, AttributeError):
        return {}

@register.filter
def format_interaction_type(interaction_type):
    """Format interaction type for display"""
    type_mapping = {
        'interaction_view': 'Page View',
        'interaction_file_download': 'File Download',
        'interaction_draft_save': 'Draft Saved',
        'interaction_submission_edit': 'Submission Edit',
        'interaction_start_submission': 'Started Submission',
        'session_start': 'Session Started',
        'session_end': 'Session Ended',
        'submission': 'Submission',
        'resubmission': 'Resubmission',
        'feedback': 'Instructor Feedback',
        'grade_change': 'Grade Change',
        'rubric_evaluation': 'Rubric Evaluation',
        'comment': 'Comment',
        'comment_reply': 'Reply',
    }
    
    return type_mapping.get(interaction_type, interaction_type.replace('_', ' ').title())

@register.filter 
def interaction_icon(interaction_type):
    """Get appropriate icon for interaction type"""
    icon_mapping = {
        'interaction_view': 'fas fa-eye',
        'interaction_file_download': 'fas fa-download',
        'interaction_draft_save': 'fas fa-save',
        'interaction_submission_edit': 'fas fa-edit',
        'interaction_start_submission': 'fas fa-play',
        'session_start': 'fas fa-sign-in-alt',
        'session_end': 'fas fa-sign-out-alt',
        'submission': 'fas fa-upload',
        'resubmission': 'fas fa-redo',
        'feedback': 'fas fa-comment-dots',
        'grade_change': 'fas fa-edit',
        'rubric_evaluation': 'fas fa-list-check',
        'comment': 'fas fa-comment',
        'comment_reply': 'fas fa-reply',
    }
    
    return icon_mapping.get(interaction_type, 'fas fa-circle')

@register.filter
def interaction_color(interaction_type):
    """Get appropriate color class for interaction type"""
    color_mapping = {
        'interaction_view': 'text-blue-600',
        'interaction_file_download': 'text-purple-600',
        'interaction_draft_save': 'text-orange-600',
        'interaction_submission_edit': 'text-yellow-600',
        'interaction_start_submission': 'text-green-600',
        'session_start': 'text-green-600',
        'session_end': 'text-red-600',
        'submission': 'text-green-600',
        'resubmission': 'text-amber-600',
        'feedback': 'text-blue-600',
        'grade_change': 'text-purple-600',
        'rubric_evaluation': 'text-yellow-600',
        'comment': 'text-cyan-600',
        'comment_reply': 'text-lime-600',
    }
    
    return color_mapping.get(interaction_type, 'text-gray-600')

@register.filter
def time_since_interaction(interaction_datetime):
    """Calculate time since interaction"""
    from django.utils import timezone
    from datetime import timedelta
    
    if not interaction_datetime:
        return "Unknown"
    
    try:
        now = timezone.now()
        diff = now - interaction_datetime
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just now"
    except (TypeError, AttributeError):
        return "Unknown"

@register.filter
def interaction_summary_stats(interactions):
    """Generate summary statistics for interactions"""
    if not interactions:
        return {}
    
    try:
        stats = {
            'total_count': len(interactions),
            'unique_types': len(set(i.get('type') for i in interactions)),
            'date_range': None,
            'most_common_type': None,
        }
        
        # Find date range
        dates = [i.get('datetime') for i in interactions if i.get('datetime')]
        if dates:
            stats['date_range'] = {
                'start': min(dates),
                'end': max(dates)
            }
        
        # Find most common interaction type
        type_counts = defaultdict(int)
        for interaction in interactions:
            interaction_type = interaction.get('type', 'unknown')
            type_counts[interaction_type] += 1
        
        if type_counts:
            stats['most_common_type'] = max(type_counts.items(), key=lambda x: x[1])
        
        return stats
    except (TypeError, AttributeError):
        return {}

@register.simple_tag
def interaction_timeline_position(interaction, all_interactions):
    """Calculate timeline position for interaction"""
    try:
        if not all_interactions:
            return 0
        
        interaction_time = interaction.get('datetime')
        if not interaction_time:
            return 0
        
        times = [i.get('datetime') for i in all_interactions if i.get('datetime')]
        if not times:
            return 0
        
        min_time = min(times)
        max_time = max(times)
        
        if min_time == max_time:
            return 50  # Single interaction, place in middle
        
        time_range = (max_time - min_time).total_seconds()
        if time_range == 0:
            return 50
        
        position = ((interaction_time - min_time).total_seconds() / time_range) * 100
        return max(0, min(100, position))
    except (TypeError, AttributeError, ZeroDivisionError):
        return 0

@register.filter
def basename(value):
    """Extract the filename from a file path"""
    if value:
        return os.path.basename(str(value))
    return value

@register.filter
def split(value, delimiter):
    """Split a string by delimiter"""
    return value.split(delimiter) if value else []

@register.filter
def file_extension(filename):
    """Extract the file extension from a filename"""
    if not filename:
        return ''
    parts = filename.rsplit('.', 1)
    return parts[1].lower() if len(parts) > 1 else ''

@register.filter
def replace_underscores(value):
    """Replace underscores with spaces and format for display"""
    if not value:
        return value
    return str(value).replace('_', ' ')