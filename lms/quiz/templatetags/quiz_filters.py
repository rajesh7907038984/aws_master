from django import template
import json
import random
from datetime import timedelta
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def timesince_minutes(end_time, start_time):
    """Return the number of minutes between two timestamps"""
    if not end_time or not start_time:
        return 0
    
    time_difference = end_time - start_time
    total_seconds = time_difference.total_seconds()
    minutes = int(total_seconds // 60)
    return minutes

@register.filter
def timesince_seconds(end_time, start_time):
    """Return the number of seconds (excluding minutes) between two timestamps"""
    if not end_time or not start_time:
        return 0
    
    time_difference = end_time - start_time
    total_seconds = time_difference.total_seconds()
    seconds = int(total_seconds % 60)
    return seconds

@register.filter
def json_parse(value):
    """Parse a JSON string into a Python object"""
    if not value:
        return []
        
    # If value is already a list or dict, return it directly
    if isinstance(value, (list, dict)):
        return value
        
    try:
        # Print debug info
        print(f"Attempting to parse JSON value: {value[:100]}")
        parsed = json.loads(value)
        print(f"Successfully parsed JSON: {type(parsed)}, value: {parsed}")
        return parsed
    except (json.JSONDecodeError, TypeError) as e:
        print(f"JSON parse error: {e}, value: {value[:100]}")
        
        # Handle common fallback cases
        if isinstance(value, str):
            # Try comma-separated format
            if ',' in value:
                items = [item.strip() for item in value.split(',') if item.strip()]
                print(f"Falling back to comma-separated list: {items}")
                return items
        
        return []

@register.filter
def get_matching_pair(pairs, submitted_pair):
    """Get the correct matching pair for a submitted pair in a quiz question"""
    try:
        # Find the matching pair where the left item matches
        for pair in pairs:
            if pair.left_item == submitted_pair['left_item']:
                return {
                    'left': pair.left_item,
                    'right': pair.right_item
                }
        return None
    except (KeyError, AttributeError):
        return None

@register.filter
def join_with_or(value):
    """Join a list of values with 'or'"""
    if not value:
        return ''
    if len(value) == 1:
        return value[0]
    return ' or '.join(value)

@register.filter
def split(value, separator):
    """Split a string by a separator and return the resulting list"""
    if not value:
        return []
    return value.split(separator)

@register.filter
def search_substring(text, search_str):
    """Check if a substring exists in a text string, useful for checking IDs in JSON strings"""
    if not text or not search_str:
        return False
        
    # Convert both to strings for safety
    text = str(text)
    search_str = str(search_str)
    
    # Simple case - direct match
    if search_str in text:
        return True
        
    # Try to find in various formats that might be in the JSON
    for format_str in [
        f'"{search_str}"',  # Double quoted
        f"'{search_str}'",  # Single quoted
        f'[{search_str}]',  # Array format
        f'"{search_str},"',  # JSON array element
        f',"{search_str}"',  # JSON array element
    ]:
        if format_str in text:
            return True
            
    return False

@register.filter
def duration(td):
    """Convert timedelta to readable duration"""
    if not td:
        return "0 seconds"
    
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

@register.filter
def parse_json_array(value):
    """Parse JSON array string and return list of items"""
    if not value:
        return []
    
    try:
        if isinstance(value, str) and value.startswith('['):
            return json.loads(value)
        elif isinstance(value, list):
            return value
        else:
            # If it's not JSON, try to split by comma
            return [item.strip() for item in str(value).split(',') if item.strip()]
    except (json.JSONDecodeError, ValueError):
        # If parsing fails, return the original value as a single item list
        return [str(value)] if value else []

@register.filter
def format_multi_blank_answers(value):
    """Format multi-blank answers for display"""
    if not value:
        return mark_safe('<div class="text-gray-500">No answers provided</div>')
    
    try:
        if isinstance(value, str) and value.startswith('['):
            answers = json.loads(value)
        elif isinstance(value, list):
            answers = value
        else:
            # If it's not JSON, treat as single answer
            answers = [str(value)]
        
        html_parts = []
        for i, answer in enumerate(answers):
            html_parts.append(f'<div class="mb-1"><strong>Blank {i + 1}:</strong> "{answer}"</div>')
        
        return mark_safe(''.join(html_parts))
    except (json.JSONDecodeError, ValueError):
        return mark_safe(f'<div>{value}</div>')

@register.filter
def mul(value, arg):
    """Multiplies the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """Divides the value by the argument"""
    try:
        arg_float = float(arg)
        if arg_float == 0:
            return 0  # Avoid division by zero
        return float(value) / arg_float
    except (ValueError, TypeError):
        return 0

@register.filter
def replace(value, args):
    """Replace text in a string. Usage: {{ value|replace:"old,new" }}"""
    try:
        if not args or ',' not in args:
            return value
        old, new = args.split(',', 1)
        return str(value).replace(old, new)
    except (ValueError, TypeError, AttributeError):
        return value

@register.simple_tag
def is_matching_correct(user_match, correct_pairs):
    """Check if a user's matching answer is correct"""
    # Handle different data types for user_match
    if isinstance(user_match, str):
        try:
            # Try to parse as JSON if it's a string
            user_match = json.loads(user_match)
        except (json.JSONDecodeError, ValueError):
            # If not JSON, return False as we can't process it
            return False
    
    # Ensure user_match is a dictionary
    if not isinstance(user_match, dict):
        return False
    
    # Only check correctness if the user made a selection
    # Handle backward compatibility - if was_selected doesn't exist, check if there's a valid answer
    was_selected = user_match.get('was_selected')
    if was_selected is False:  # Explicitly False means no selection
        return False
    elif was_selected is None:  # Field doesn't exist (old data), check if there's a valid answer
        right_item = str(user_match.get('right_item', '')).strip()
        if not right_item or right_item in ['(No selection)', 'Unknown', '']:
            return False
    
    # Get the user's matching attempt
    user_left = str(user_match.get('left_item', '')).strip()
    user_right = str(user_match.get('right_item', '')).strip()
    
    # Skip if this is "(No selection)"
    if user_right == "(No selection)":
        return False
    
    # Check if this match is correct
    for pair in correct_pairs:
        if (str(pair.left_item).strip() == user_left and 
            str(pair.right_item).strip() == user_right):
            return True
    return False

@register.filter
def shuffle(value):
    """Shuffle a list or queryset"""
    if not value:
        return value
    
    # Convert to list if it's a queryset
    if hasattr(value, '__iter__') and not isinstance(value, (str, dict)):
        value_list = list(value)
        random.shuffle(value_list)
        return value_list
    
    return value 