"""
Type Safety Utilities for LMS Project
Provides comprehensive type guards and validation functions to prevent type-related bugs.
"""

from typing import Any, Dict, List, Optional, Union, TypeVar, Type, cast
try:
    from typing import TypedDict
except ImportError:
    # TypedDict not available in Python < 3.8, use Dict as fallback
    TypedDict = Dict
import json
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

T = TypeVar('T')


# Type definitions for common data structures (Python 3.7 compatible)
ProgressData = Dict[str, Union[int, float, bool, str, Dict[str, Any]]]
EducationRecord = Dict[str, Optional[str]]
EmploymentRecord = Dict[str, Optional[str]]
UserCapabilities = Dict[str, Any]


ScormData = Dict[str, Any]


FormFieldData = Dict[str, Any]


ErrorContext = Dict[str, Any]


class TypeValidationError(Exception):
    """Custom exception for type validation errors"""
    pass


def safe_json_loads(json_string: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON string with proper error handling
    
    Args:
        json_string: JSON string to parse
        
    Returns:
        Parsed dictionary or None if parsing fails
    """
    if not json_string or not isinstance(json_string, str):
        return None
        
    try:
        result = json.loads(json_string)
        if isinstance(result, dict):
            return result
        logger.warning(f"JSON parsing returned non-dict type: {type(result)}")
        return None
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"JSON parsing failed: {e}")
        return None


def safe_get_string(data: Dict[str, Any], key: str, default: str = "") -> str:
    """
    Safely get a string value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        String value or default
    """
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        try:
            return str(value)
        except (TypeError, ValueError):
            return default
    return value


def safe_get_int(data: Dict[str, Any], key: str, default: int = 0) -> int:
    """
    Safely get an integer value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        Integer value or default
    """
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    
    try:
        if isinstance(value, (int, float)):
            return int(value)
        elif isinstance(value, str):
            return int(value)
        elif isinstance(value, Decimal):
            return int(value)
        else:
            return default
    except (ValueError, TypeError, OverflowError):
        return default


def safe_get_float(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """
    Safely get a float value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        Float value or default
    """
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    
    try:
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            return float(value)
        elif isinstance(value, Decimal):
            return float(value)
        else:
            return default
    except (ValueError, TypeError, OverflowError):
        return default


def safe_get_bool(data: Dict[str, Any], key: str, default: bool = False) -> bool:
    """
    Safely get a boolean value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        Boolean value or default
    """
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    elif isinstance(value, (int, float)):
        return bool(value)
    else:
        return default


def safe_get_list(data: Dict[str, Any], key: str, default: Optional[List[Any]] = None) -> List[Any]:
    """
    Safely get a list value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        List value or default (empty list if default is None)
    """
    if default is None:
        default = []
        
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    
    if isinstance(value, list):
        return value
    elif isinstance(value, (tuple, set)):
        return list(value)
    else:
        return default


def safe_get_dict(data: Dict[str, Any], key: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely get a dictionary value from a dictionary with type validation
    
    Args:
        data: Dictionary to search in
        key: Key to look for
        default: Default value if key not found or value is invalid
        
    Returns:
        Dictionary value or default (empty dict if default is None)
    """
    if default is None:
        default = {}
        
    if not isinstance(data, dict):
        return default
        
    value = data.get(key, default)
    if value is None:
        return default
    
    if isinstance(value, dict):
        return value
    else:
        return default


def validate_timezone_data(data: Any) -> Optional[Dict[str, Any]]:
    """
    Validate timezone data structure
    
    Args:
        data: Data to validate
        
    Returns:
        Validated timezone data or None if invalid
    """
    if not isinstance(data, dict):
        return None
    
    timezone = safe_get_string(data, 'timezone')
    if not timezone:
        return None
    
    offset = safe_get_int(data, 'offset', 0)
    
    return {
        'timezone': timezone,
        'offset': offset
    }


def is_valid_email(email: Any) -> bool:
    """
    Check if value is a valid email string
    
    Args:
        email: Value to check
        
    Returns:
        True if valid email, False otherwise
    """
    if not isinstance(email, str):
        return False
    
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_url(url: Any) -> bool:
    """
    Check if value is a valid URL string
    
    Args:
        url: Value to check
        
    Returns:
        True if valid URL, False otherwise
    """
    if not isinstance(url, str):
        return False
    
    import re
    pattern = r'^https?://(?:[-\w.])+(?::\d+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?$'
    return bool(re.match(pattern, url))


def safe_cast(value: Any, target_type: Type[T], default: Optional[T] = None) -> Optional[T]:
    """
    Safely cast a value to target type
    
    Args:
        value: Value to cast
        target_type: Target type to cast to
        default: Default value if casting fails
        
    Returns:
        Casted value or default
    """
    if value is None:
        return default
    
    if isinstance(value, target_type):
        return value
    
    try:
        return target_type(value)
    except (TypeError, ValueError, OverflowError):
        return default


def ensure_list(value: Any) -> List[Any]:
    """
    Ensure value is a list
    
    Args:
        value: Value to convert to list
        
    Returns:
        List containing the value or empty list
    """
    if value is None:
        return []
    elif isinstance(value, list):
        return value
    elif isinstance(value, (tuple, set)):
        return list(value)
    else:
        return [value]


def ensure_dict(value: Any) -> Dict[str, Any]:
    """
    Ensure value is a dictionary
    
    Args:
        value: Value to convert to dict
        
    Returns:
        Dictionary or empty dict if conversion fails
    """
    if isinstance(value, dict):
        return value
    else:
        return {}


def validate_request_data(request, required_fields: List[str]) -> Dict[str, Any]:
    """
    Validate request POST/GET data with required fields
    
    Args:
        request: Django request object
        required_fields: List of required field names
        
    Returns:
        Validated data dictionary
        
    Raises:
        TypeValidationError: If required fields are missing or invalid
    """
    if not hasattr(request, 'POST') and not hasattr(request, 'GET'):
        raise TypeValidationError("Invalid request object")
    
    # Use POST data if available, otherwise GET data
    data = request.POST if hasattr(request, 'POST') and request.POST else request.GET
    
    validated_data = {}
    missing_fields = []
    
    for field in required_fields:
        value = safe_get_string(data, field)
        if not value:
            missing_fields.append(field)
        else:
            validated_data[field] = value
    
    if missing_fields:
        raise TypeValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    
    return validated_data


def safe_model_get(model_class, **kwargs):
    """
    Safely get model instance with proper error handling
    
    Args:
        model_class: Django model class
        **kwargs: Query parameters
        
    Returns:
        Model instance or None if not found
    """
    try:
        return model_class.objects.get(**kwargs)
    except model_class.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Error getting {model_class.__name__}: {e}")
        return None


def safe_model_filter(model_class, **kwargs):
    """
    Safely filter model instances with proper error handling
    
    Args:
        model_class: Django model class
        **kwargs: Query parameters
        
    Returns:
        QuerySet or empty QuerySet if error
    """
    try:
        return model_class.objects.filter(**kwargs)
    except Exception as e:
        logger.error(f"Error filtering {model_class.__name__}: {e}")
        return model_class.objects.none()


def validate_user_permissions(user, required_permissions: List[str]) -> bool:
    """
    Validate user has required permissions
    
    Args:
        user: Django user object
        required_permissions: List of required permission names
        
    Returns:
        True if user has all permissions, False otherwise
    """
    if not hasattr(user, 'has_perm'):
        return False
    
    if not user.is_authenticated:
        return False
    
    return all(user.has_perm(perm) for perm in required_permissions)


class TypeSafeDict(dict):
    """
    Type-safe dictionary wrapper with built-in validation
    """
    
    def get_string(self, key: str, default: str = "") -> str:
        """Get string value safely"""
        return safe_get_string(self, key, default)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer value safely"""
        return safe_get_int(self, key, default)
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get float value safely"""
        return safe_get_float(self, key, default)
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean value safely"""
        return safe_get_bool(self, key, default)
    
    def get_list(self, key: str, default: Optional[List[Any]] = None) -> List[Any]:
        """Get list value safely"""
        return safe_get_list(self, key, default)
    
    def get_dict(self, key: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get dictionary value safely"""
        return safe_get_dict(self, key, default)


def create_type_safe_dict(data: Any) -> TypeSafeDict:
    """
    Create a type-safe dictionary from any data
    
    Args:
        data: Data to convert
        
    Returns:
        TypeSafeDict instance
    """
    if isinstance(data, dict):
        return TypeSafeDict(data)
    else:
        return TypeSafeDict()


def validate_progress_data(data: Any) -> Optional[ProgressData]:
    """
    Validate and normalize progress data structure
    
    Args:
        data: Raw progress data
        
    Returns:
        Validated ProgressData or None if invalid
    """
    if not isinstance(data, dict):
        return None
    
    validated: ProgressData = {}
    
    # Validate progress (required numeric field)
    progress = safe_get_float(data, 'progress')
    if progress is not None and 0 <= progress <= 100:
        validated['progress'] = progress
    
    # Validate completion (optional numeric field)
    completion = safe_get_float(data, 'completion')
    if completion is not None and 0 <= completion <= 100:
        validated['completion'] = completion
    
    # Validate completed (boolean field)
    completed = safe_get_bool(data, 'completed')
    validated['completed'] = completed
    
    # Validate time fields
    current_time = safe_get_float(data, 'current_time')
    if current_time is not None and current_time >= 0:
        validated['current_time'] = current_time
    
    duration = safe_get_float(data, 'duration')
    if duration is not None and duration >= 0:
        validated['duration'] = duration
    
    # Validate bookmark (optional dict)
    bookmark = safe_get_dict(data, 'bookmark')
    if bookmark:
        validated['bookmark'] = bookmark
    
    # Validate last_accessed (optional string)
    last_accessed = safe_get_string(data, 'last_accessed')
    if last_accessed:
        validated['last_accessed'] = last_accessed
    
    # Validate score (optional numeric)
    score = safe_get_float(data, 'score')
    if score is not None and score >= 0:
        validated['score'] = score
    
    return validated


def validate_education_record(data: Any) -> Optional[EducationRecord]:
    """
    Validate education record structure
    
    Args:
        data: Raw education record data
        
    Returns:
        Validated EducationRecord or None if invalid
    """
    if not isinstance(data, dict):
        return None
    
    validated: EducationRecord = {}
    
    # Required fields
    institution = safe_get_string(data, 'institution')
    degree = safe_get_string(data, 'degree')
    field_of_study = safe_get_string(data, 'field_of_study')
    
    if not all([institution, degree, field_of_study]):
        return None
    
    validated['institution'] = institution
    validated['degree'] = degree
    validated['field_of_study'] = field_of_study
    
    # Optional fields
    for field in ['start_date', 'end_date', 'grade', 'description']:
        value = safe_get_string(data, field)
        if value:
            validated[field] = value
    
    return validated


def validate_employment_record(data: Any) -> Optional[EmploymentRecord]:
    """
    Validate employment record structure
    
    Args:
        data: Raw employment record data
        
    Returns:
        Validated EmploymentRecord or None if invalid
    """
    if not isinstance(data, dict):
        return None
    
    validated: EmploymentRecord = {}
    
    # Required fields
    company = safe_get_string(data, 'company')
    position = safe_get_string(data, 'position')
    
    if not all([company, position]):
        return None
    
    validated['company'] = company
    validated['position'] = position
    
    # Optional fields
    for field in ['start_date', 'end_date', 'description', 'location']:
        value = safe_get_string(data, field)
        if value:
            validated[field] = value
    
    # Boolean field
    validated['is_current'] = safe_get_bool(data, 'is_current', False)
    
    return validated


def validate_scorm_data(data: Any) -> Optional[ScormData]:
    """
    Validate SCORM data structure
    
    Args:
        data: Raw SCORM data
        
    Returns:
        Validated ScormData or None if invalid
    """
    if not isinstance(data, dict):
        return None
    
    validated: ScormData = {}
    
    # Required string fields
    completion_status = safe_get_string(data, 'completion_status')
    success_status = safe_get_string(data, 'success_status')
    
    if not completion_status or not success_status:
        return None
    
    validated['completion_status'] = completion_status
    validated['success_status'] = success_status
    
    # Optional numeric fields
    for field in ['score_raw', 'score_max', 'score_min']:
        value = safe_get_float(data, field)
        if value is not None and value >= 0:
            validated[field] = value
    
    # Optional string fields
    for field in ['lesson_location', 'lesson_status', 'session_time', 'total_time']:
        value = safe_get_string(data, field)
        if value:
            validated[field] = value
    
    return validated


def normalize_mixed_type_field(value: Any) -> Optional[Dict[str, Any]]:
    """
    Normalize fields that can be dict, string (JSON), or None
    Common pattern in the codebase for progress_data, employment_data, etc.
    
    Args:
        value: Mixed type value (dict, str, None, etc.)
        
    Returns:
        Normalized dictionary or None
    """
    if value is None:
        return None
    
    if isinstance(value, dict):
        return value
    
    if isinstance(value, str):
        return safe_json_loads(value)
    
    if isinstance(value, list):
        # Some fields store list of records
        return {'records': value}
    
    logger.warning(f"Unexpected type for mixed field: {type(value)}")
    return None


def safe_extract_records_list(mixed_field: Any) -> List[Dict[str, Any]]:
    """
    Safely extract a list of records from mixed-type fields
    Common pattern for education_data, employment_data, etc.
    
    Args:
        mixed_field: Field that can be list, JSON string, dict, or None
        
    Returns:
        List of record dictionaries
    """
    if isinstance(mixed_field, list):
        return [record for record in mixed_field if isinstance(record, dict)]
    
    normalized = normalize_mixed_type_field(mixed_field)
    if normalized:
        if 'records' in normalized:
            records = safe_get_list(normalized, 'records', [])
            return [record for record in records if isinstance(record, dict)]
        elif isinstance(normalized, dict):
            # Single record wrapped in dict
            return [normalized]
    
    return []


def validate_cache_capabilities(capabilities: Any) -> Optional[List[str]]:
    """
    Validate user capabilities cache data
    
    Args:
        capabilities: Raw capabilities data from cache
        
    Returns:
        Validated list of capability strings or None if invalid
    """
    if not isinstance(capabilities, list):
        logger.warning(f"Cache capabilities must be list, got {type(capabilities)}")
        return None
    
    # Size validation to prevent memory exhaustion
    if len(capabilities) > 500:  # Maximum 500 capabilities per user
        logger.warning(f"Cache capabilities exceed maximum size: {len(capabilities)}")
        return None
    
    validated_capabilities = []
    for cap in capabilities:
        if not isinstance(cap, str):
            logger.warning(f"Invalid capability type: {type(cap)}")
            continue
        
        cap = cap.strip()
        if not cap:
            logger.warning("Empty capability string found")
            continue
        
        if len(cap) > 100:  # Max 100 chars per capability
            logger.warning(f"Capability name too long: {len(cap)} chars")
            continue
        
        validated_capabilities.append(cap)
    
    return validated_capabilities


def validate_user_capabilities_cache(cache_data: Any) -> Optional[UserCapabilities]:
    """
    Validate complete user capabilities cache structure
    
    Args:
        cache_data: Raw cache data
        
    Returns:
        Validated UserCapabilities or None if invalid
    """
    if not isinstance(cache_data, dict):
        return None
    
    # Validate capabilities list
    capabilities = validate_cache_capabilities(cache_data.get('capabilities'))
    if capabilities is None:
        return None
    
    # Validate version string
    version = safe_get_string(cache_data, 'version')
    if not version:
        return None
    
    # Validate integrity hash
    integrity = safe_get_string(cache_data, 'integrity')
    if not integrity:
        return None
    
    # Validate timestamp
    timestamp = safe_get_float(cache_data, 'timestamp')
    if timestamp is None or timestamp <= 0:
        return None
    
    return UserCapabilities(
        capabilities=capabilities,
        version=version,
        integrity=integrity,
        timestamp=timestamp
    )