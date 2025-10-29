"""
Gradebook-specific validation utilities for enhanced type safety and data integrity.
"""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union
import logging

logger = logging.getLogger(__name__)


def validate_grade_score(score: Any, max_score: Optional[Union[int, float, Decimal]] = None) -> Decimal:
    """
    Validate and convert a grade score to Decimal with proper bounds checking.
    
    Args:
        score: The score to validate (can be string, int, float, or Decimal)
        max_score: Optional maximum score for validation
        
    Returns:
        Validated Decimal score
        
    Raises:
        ValidationError: If score is invalid
    """
    if score is None:
        raise ValidationError(_('Score cannot be None'))
    
    # Convert to Decimal safely
    try:
        if isinstance(score, str):
            score = score.strip()
            if not score:
                raise ValidationError(_('Score cannot be empty'))
        
        decimal_score = Decimal(str(score))
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.warning(f"Invalid score conversion: {score} - {e}")
        raise ValidationError(_('Score must be a valid number'))
    
    # Validate bounds
    if decimal_score < 0:
        raise ValidationError(_('Score cannot be negative'))
    
    if decimal_score > 9999.99:  # Based on model field constraints
        raise ValidationError(_('Score is too large (maximum: 9999.99)'))
    
    # Validate against max_score if provided
    if max_score is not None:
        try:
            max_decimal = Decimal(str(max_score))
            if decimal_score > max_decimal:
                raise ValidationError(
                    _('Score (%(score)s) cannot exceed maximum score (%(max_score)s)'),
                    params={'score': decimal_score, 'max_score': max_decimal}
                )
        except (InvalidOperation, ValueError, TypeError):
            logger.warning(f"Invalid max_score for validation: {max_score}")
    
    return decimal_score


def validate_student_id(student_id: Any) -> int:
    """
    Validate and convert student ID to integer.
    
    Args:
        student_id: The student ID to validate
        
    Returns:
        Validated integer student ID
        
    Raises:
        ValidationError: If student ID is invalid
    """
    if student_id is None:
        raise ValidationError(_('Student ID cannot be None'))
    
    try:
        int_id = int(student_id)
        if int_id <= 0:
            raise ValidationError(_('Student ID must be positive'))
        return int_id
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid student ID: {student_id} - {e}")
        raise ValidationError(_('Student ID must be a valid positive integer'))


def validate_activity_id(activity_id: Any) -> int:
    """
    Validate and convert activity ID to integer.
    
    Args:
        activity_id: The activity ID to validate
        
    Returns:
        Validated integer activity ID
        
    Raises:
        ValidationError: If activity ID is invalid
    """
    if activity_id is None:
        raise ValidationError(_('Activity ID cannot be None'))
    
    try:
        int_id = int(activity_id)
        if int_id <= 0:
            raise ValidationError(_('Activity ID must be positive'))
        return int_id
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid activity ID: {activity_id} - {e}")
        raise ValidationError(_('Activity ID must be a valid positive integer'))


def validate_activity_type(activity_type: Any) -> str:
    """
    Validate activity type against allowed values.
    
    Args:
        activity_type: The activity type to validate
        
    Returns:
        Validated activity type string
        
    Raises:
        ValidationError: If activity type is invalid
    """
    if not activity_type:
        raise ValidationError(_('Activity type cannot be empty'))
    
    if not isinstance(activity_type, str):
        raise ValidationError(_('Activity type must be a string'))
    
    activity_type = activity_type.strip().lower()
    
    allowed_types = {
        'assignment', 'quiz', 'discussion', 'conference', 
        'initial_assessment', 'vak_test', 'scorm'
    }
    
    if activity_type not in allowed_types:
        raise ValidationError(
            _('Invalid activity type: %(type)s. Allowed types: %(allowed)s'),
            params={
                'type': activity_type,
                'allowed': ', '.join(sorted(allowed_types))
            }
        )
    
    return activity_type


def validate_grade_status(status: Any) -> str:
    """
    Validate grade status against allowed values.
    
    Args:
        status: The status to validate
        
    Returns:
        Validated status string
        
    Raises:
        ValidationError: If status is invalid
    """
    if not status:
        raise ValidationError(_('Status cannot be empty'))
    
    if not isinstance(status, str):
        raise ValidationError(_('Status must be a string'))
    
    status = status.strip().lower()
    
    allowed_statuses = {
        'not_graded', 'graded', 'returned', 'late', 'missing', 'excused'
    }
    
    if status not in allowed_statuses:
        raise ValidationError(
            _('Invalid status: %(status)s. Allowed statuses: %(allowed)s'),
            params={
                'status': status,
                'allowed': ', '.join(sorted(allowed_statuses))
            }
        )
    
    return status


def validate_feedback_text(feedback: Any) -> str:
    """
    Validate and sanitize feedback text.
    
    Args:
        feedback: The feedback text to validate
        
    Returns:
        Validated feedback string
        
    Raises:
        ValidationError: If feedback is invalid
    """
    if feedback is None:
        return ''
    
    if not isinstance(feedback, str):
        try:
            feedback = str(feedback)
        except (ValueError, TypeError):
            raise ValidationError(_('Feedback must be convertible to string'))
    
    feedback = feedback.strip()
    
    # Check length limits (adjust as needed)
    max_length = 10000  # 10KB of text
    if len(feedback) > max_length:
        raise ValidationError(
            _('Feedback is too long (maximum: %(max)d characters)'),
            params={'max': max_length}
        )
    
    return feedback


def validate_gradebook_request_data(request_data: dict) -> dict:
    """
    Comprehensive validation for gradebook AJAX request data.
    
    Args:
        request_data: Dictionary of request data to validate
        
    Returns:
        Dictionary of validated data
        
    Raises:
        ValidationError: If any validation fails
    """
    validated_data = {}
    
    # Required fields validation
    required_fields = ['activity_type', 'activity_id', 'student_id']
    for field in required_fields:
        if field not in request_data:
            raise ValidationError(
                _('Missing required field: %(field)s'),
                params={'field': field}
            )
    
    # Validate each field
    validated_data['activity_type'] = validate_activity_type(
        request_data['activity_type']
    )
    validated_data['activity_id'] = validate_activity_id(
        request_data['activity_id']
    )
    validated_data['student_id'] = validate_student_id(
        request_data['student_id']
    )
    
    # Optional fields
    if 'grade' in request_data and request_data['grade']:
        validated_data['grade'] = validate_grade_score(request_data['grade'])
    
    if 'status' in request_data:
        validated_data['status'] = validate_grade_status(
            request_data.get('status', 'graded')
        )
    
    if 'feedback' in request_data:
        validated_data['feedback'] = validate_feedback_text(
            request_data.get('feedback', '')
        )
    
    # Validate submission_id if provided
    if 'submission_id' in request_data and request_data['submission_id']:
        try:
            validated_data['submission_id'] = int(request_data['submission_id'])
            if validated_data['submission_id'] <= 0:
                raise ValidationError(_('Submission ID must be positive'))
        except (ValueError, TypeError):
            raise ValidationError(_('Invalid submission ID'))
    
    # Validate attempt_id if provided
    if 'attempt_id' in request_data and request_data['attempt_id']:
        try:
            validated_data['attempt_id'] = int(request_data['attempt_id'])
            if validated_data['attempt_id'] <= 0:
                raise ValidationError(_('Attempt ID must be positive'))
        except (ValueError, TypeError):
            raise ValidationError(_('Invalid attempt ID'))
    
    return validated_data


class GradebookValidationError(ValidationError):
    """Custom exception for gradebook-specific validation errors."""
    pass


def safe_grade_conversion(grade_value: Any, assignment_max_score: Optional[Any] = None) -> Optional[Decimal]:
    """
    Safely convert and validate a grade value with comprehensive error handling.
    
    Args:
        grade_value: The grade value to convert
        assignment_max_score: Optional maximum score for the assignment
        
    Returns:
        Validated Decimal grade or None if conversion fails
        
    Raises:
        GradebookValidationError: If validation fails with detailed error info
    """
    if not grade_value:
        return None
    
    try:
        return validate_grade_score(grade_value, assignment_max_score)
    except ValidationError as e:
        raise GradebookValidationError(
            f"Grade validation failed: {e.message}",
            code='invalid_grade'
        )
