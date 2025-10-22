from django import template
import json
import ast
import logging

logger = logging.getLogger(__name__)
register = template.Library()

@register.filter
def json_parse(value):
    """Parse a JSON string into a Python object or use directly if already parsed"""
    if not value:
        return []
        
    # If value is already a list of dicts, return it directly
    if isinstance(value, list):
        # For matching pairs, we expect dicts with left_item and right_item
        if all(isinstance(item, dict) and 'left_item' in item and 'right_item' in item for item in value):
            return value
        # Convert simple lists to structured dicts if needed
        structured_items = []
        for idx, item in enumerate(value):
            if isinstance(item, dict) and ('left_item' in item or 'right_item' in item):
                structured_items.append(item)
            else:
                structured_items.append({'left_item': str(idx+1), 'right_item': str(item)})
        if structured_items:
            return structured_items
    
    # If value is already a dict, wrap it in a list
    if isinstance(value, dict):
        if 'left_item' in value and 'right_item' in value:
            return [value]
        return [value]
        
    # Handle JSON strings
    try:
        parsed_value = json.loads(value)
        # Ensure we always return a list for matching pairs
        if isinstance(parsed_value, list):
            return parsed_value
        elif isinstance(parsed_value, dict):
            return [parsed_value]
        else:
            return []
    except (json.JSONDecodeError, TypeError):
        # If parsing fails, try to handle common issues
        if isinstance(value, str):
            # Handle admin interface format with arrows
            if '→' in value or '->' in value:
                pairs = []
                if '<br>' in value:
                    items = value.split('<br>')
                elif ',' in value:
                    items = value.split(',')
                else:
                    items = [value]
                
                for item in items:
                    for arrow in ['→', '->', '→', '⟶', '>']:
                        if arrow in item:
                            try:
                                left, right = item.split(arrow)
                                pairs.append({
                                    'left_item': left.strip(),
                                    'right_item': right.strip()
                                })
                                break
                            except ValueError:
                                continue
                
                if pairs:
                    return pairs
            
            if value.startswith('[') and value.endswith(']'):
                # Try to safely parse as Python list (last resort)
                try:
                    # Only allow safe literal evaluation - check for dangerous content
                    if all(c in '[]{}(),"\'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._-: \t\n' for c in value):
                        return ast.literal_eval(value)
                    else:
                        # Log potentially dangerous content
                        logger.warning(f"Potentially unsafe string rejected in json_parse: {value[:100]}...")
                        return []
                except ValueError:
                    return []
        return []

@register.filter
def get_matching_pair(pairs, submitted_pair):
    """Get the correct matching pair for a submitted pair"""
    try:
        # Find the matching pair where the left item matches
        left_item = submitted_pair.get('left_item')
        if not left_item:
            return None
            
        for pair in pairs:
            if pair.left_item == left_item:
                return {
                    'left': pair.left_item,
                    'right': pair.right_item
                }
        return None
    except (KeyError, AttributeError, TypeError) as e:
        # Add robust error handling by returning None
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
def get_assessment_classification(attempt):
    """Get the assessment classification data for an initial assessment attempt"""
    if not attempt or not hasattr(attempt, 'calculate_assessment_classification'):
        return None
    
    try:
        return attempt.calculate_assessment_classification()
    except Exception:
        return None 