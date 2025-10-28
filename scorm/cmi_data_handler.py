"""
Complete CMI Data Storage Handler
Handles real-time CMI data updates, validation, and history tracking
"""
import json
import logging
from datetime import datetime
from django.utils import timezone
from django.db import transaction
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class CMIDataHandler:
    """
    Handles complete CMI data storage with real-time updates and history tracking
    """
    
    # Complete SCORM 1.2 CMI Data Model fields
    SCORM_12_CMI_FIELDS = {
        # Core fields
        'cmi.core.lesson_status': {'type': 'string', 'values': ['not attempted', 'incomplete', 'completed', 'passed', 'failed', 'browsed']},
        'cmi.core.score.raw': {'type': 'decimal', 'range': [0, 100]},
        'cmi.core.score.max': {'type': 'decimal', 'range': [0, 100]},
        'cmi.core.score.min': {'type': 'decimal', 'range': [0, 100]},
        'cmi.core.total_time': {'type': 'time'},
        'cmi.core.lesson_location': {'type': 'string', 'max_length': 1000},
        'cmi.core.entry': {'type': 'string', 'values': ['ab-initio', 'resume']},
        'cmi.core.exit': {'type': 'string', 'values': ['time-out', 'suspend', 'logout', 'normal', '']},
        'cmi.core.session_time': {'type': 'time'},
        'cmi.core.student_id': {'type': 'string', 'max_length': 255},
        'cmi.core.student_name': {'type': 'string', 'max_length': 250},
        'cmi.core.credit': {'type': 'string', 'values': ['credit', 'no-credit']},
        'cmi.core.lesson_mode': {'type': 'string', 'values': ['browse', 'normal']},
        
        # Interactions
        'cmi.interactions._count': {'type': 'integer'},
        'cmi.interactions.n.id': {'type': 'string', 'max_length': 255},
        'cmi.interactions.n.type': {'type': 'string', 'values': ['true-false', 'choice', 'fill-in', 'matching', 'performance', 'sequencing', 'likert', 'numeric']},
        'cmi.interactions.n.objectives._count': {'type': 'integer'},
        'cmi.interactions.n.objectives.n.id': {'type': 'string', 'max_length': 255},
        'cmi.interactions.n.correct_responses._count': {'type': 'integer'},
        'cmi.interactions.n.correct_responses.n.pattern': {'type': 'string', 'max_length': 250},
        'cmi.interactions.n.weighting': {'type': 'decimal', 'range': [0, 1]},
        'cmi.interactions.n.student_response': {'type': 'string', 'max_length': 250},
        'cmi.interactions.n.result': {'type': 'string', 'values': ['correct', 'incorrect', 'unanticipated', 'neutral']},
        'cmi.interactions.n.latency': {'type': 'time'},
        
        # Objectives
        'cmi.objectives._count': {'type': 'integer'},
        'cmi.objectives.n.id': {'type': 'string', 'max_length': 255},
        'cmi.objectives.n.score.raw': {'type': 'decimal', 'range': [0, 100]},
        'cmi.objectives.n.score.max': {'type': 'decimal', 'range': [0, 100]},
        'cmi.objectives.n.score.min': {'type': 'decimal', 'range': [0, 100]},
        'cmi.objectives.n.status': {'type': 'string', 'values': ['not attempted', 'incomplete', 'completed', 'passed', 'failed', 'browsed']},
        
        # Comments
        'cmi.comments_from_learner._count': {'type': 'integer'},
        'cmi.comments_from_learner.n.comment': {'type': 'string', 'max_length': 1000},
        'cmi.comments_from_learner.n.location': {'type': 'string', 'max_length': 250},
        'cmi.comments_from_learner.n.timestamp': {'type': 'datetime'},
        'cmi.comments_from_lms._count': {'type': 'integer'},
        'cmi.comments_from_lms.n.comment': {'type': 'string', 'max_length': 1000},
        'cmi.comments_from_lms.n.location': {'type': 'string', 'max_length': 250},
        'cmi.comments_from_lms.n.timestamp': {'type': 'datetime'},
        
        # Student data
        'cmi.student_data.mastery_score': {'type': 'decimal', 'range': [0, 100]},
        'cmi.student_data.max_time_allowed': {'type': 'time'},
        'cmi.student_data.time_limit_action': {'type': 'string', 'values': ['exit,message', 'exit,no message', 'continue,message', 'continue,no message']},
        
        # Student preferences
        'cmi.student_preference.audio': {'type': 'integer', 'range': [0, 10]},
        'cmi.student_preference.language': {'type': 'string', 'max_length': 250},
        'cmi.student_preference.speed': {'type': 'decimal', 'range': [0.1, 10.0]},
        'cmi.student_preference.text': {'type': 'integer', 'range': [0, 10]},
    }
    
    # SCORM 2004 CMI Data Model fields
    SCORM_2004_CMI_FIELDS = {
        'cmi.completion_status': {'type': 'string', 'values': ['completed', 'incomplete', 'not attempted', 'unknown']},
        'cmi.success_status': {'type': 'string', 'values': ['passed', 'failed', 'unknown']},
        'cmi.score.raw': {'type': 'decimal', 'range': [0, 100]},
        'cmi.score.max': {'type': 'decimal', 'range': [0, 100]},
        'cmi.score.min': {'type': 'decimal', 'range': [0, 100]},
        'cmi.score.scaled': {'type': 'decimal', 'range': [0, 1]},
        'cmi.progress_measure': {'type': 'decimal', 'range': [0, 1]},
        'cmi.location': {'type': 'string', 'max_length': 1000},
        'cmi.suspend_data': {'type': 'string', 'max_length': 64000},
        'cmi.launch_data': {'type': 'string', 'max_length': 4000},
        'cmi.comments': {'type': 'string', 'max_length': 1000},
        'cmi.comments_from_lms': {'type': 'string', 'max_length': 1000},
        'cmi.mode': {'type': 'string', 'values': ['browse', 'normal', 'review']},
        'cmi.prerequisites': {'type': 'string', 'max_length': 1000},
        'cmi.max_time_allowed': {'type': 'time'},
        'cmi.time_limit_action': {'type': 'string', 'values': ['exit,message', 'exit,no message', 'continue,message', 'continue,no message']},
        'cmi.data_from_lms': {'type': 'string', 'max_length': 1000},
        'cmi.mastery_score': {'type': 'decimal', 'range': [0, 100]},
        'cmi.max_time_allowed': {'type': 'time'},
        'cmi.total_time': {'type': 'time'},
        'cmi.session_time': {'type': 'time'},
        'cmi.entry': {'type': 'string', 'values': ['ab-initio', 'resume']},
        'cmi.exit': {'type': 'string', 'values': ['time-out', 'suspend', 'logout', 'normal', '']},
        'cmi.learner_id': {'type': 'string', 'max_length': 255},
        'cmi.learner_name': {'type': 'string', 'max_length': 250},
        'cmi.credit': {'type': 'string', 'values': ['credit', 'no-credit']},
    }
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.cmi_data = attempt.cmi_data or {}
        self.cmi_history = getattr(attempt, 'cmi_data_history', []) or []
    
    def update_cmi_field(self, field, value, validate=True):
        """
        Update a CMI field with validation and history tracking
        
        Args:
            field (str): CMI field name (e.g., 'cmi.score.raw')
            value (any): Field value
            validate (bool): Whether to validate the field
        """
        try:
            # Store old value for history
            old_value = self.cmi_data.get(field)
            
            # Validate field if requested
            if validate:
                validated_value = self.validate_cmi_field(field, value)
            else:
                validated_value = value
            
            # Update CMI data
            self.cmi_data[field] = validated_value
            
            # Add to history
            self.cmi_history.append({
                'field': field,
                'old_value': old_value,
                'new_value': validated_value,
                'timestamp': timezone.now().isoformat(),
                'user_id': self.attempt.user.id,
                'attempt_id': self.attempt.id
            })
            
            # Update attempt fields if they map to CMI fields
            self.update_attempt_fields(field, validated_value)
            
            logger.info(f"Updated CMI field {field}: {old_value} -> {validated_value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating CMI field {field}: {str(e)}")
            return False
    
    def validate_cmi_field(self, field, value):
        """
        Validate a CMI field according to SCORM specifications
        
        Args:
            field (str): CMI field name
            value (any): Field value to validate
            
        Returns:
            Validated value
        """
        # Get field specification
        spec = self.get_field_specification(field)
        if not spec:
            logger.warning(f"No specification found for field {field}")
            return value
        
        # Type validation
        if spec['type'] == 'decimal':
            try:
                decimal_value = Decimal(str(value))
                if 'range' in spec:
                    min_val, max_val = spec['range']
                    if not (min_val <= decimal_value <= max_val):
                        raise ValueError(f"Value {decimal_value} out of range [{min_val}, {max_val}]")
                return str(decimal_value)
            except (InvalidOperation, ValueError) as e:
                logger.error(f"Invalid decimal value for {field}: {value} - {str(e)}")
                raise ValueError(f"Invalid decimal value: {value}")
        
        elif spec['type'] == 'integer':
            try:
                int_value = int(value)
                if 'range' in spec:
                    min_val, max_val = spec['range']
                    if not (min_val <= int_value <= max_val):
                        raise ValueError(f"Value {int_value} out of range [{min_val}, {max_val}]")
                return str(int_value)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid integer value for {field}: {value} - {str(e)}")
                raise ValueError(f"Invalid integer value: {value}")
        
        elif spec['type'] == 'string':
            str_value = str(value)
            if 'max_length' in spec and len(str_value) > spec['max_length']:
                logger.warning(f"String value truncated for {field}: {len(str_value)} > {spec['max_length']}")
                str_value = str_value[:spec['max_length']]
            
            if 'values' in spec and str_value not in spec['values']:
                logger.warning(f"Invalid string value for {field}: {str_value} not in {spec['values']}")
                # Don't raise error, just log warning for flexibility
            
            return str_value
        
        elif spec['type'] == 'time':
            # Validate SCORM time format (PT1H30M45S or hhhh:mm:ss.ss)
            if not self.is_valid_scorm_time(value):
                logger.warning(f"Invalid time format for {field}: {value}")
            return str(value)
        
        elif spec['type'] == 'datetime':
            # Validate datetime format
            if not self.is_valid_datetime(value):
                logger.warning(f"Invalid datetime format for {field}: {value}")
            return str(value)
        
        return value
    
    def get_field_specification(self, field):
        """Get field specification from SCORM 1.2 or 2004 specs"""
        # Check SCORM 1.2 fields
        if field in self.SCORM_12_CMI_FIELDS:
            return self.SCORM_12_CMI_FIELDS[field]
        
        # Check SCORM 2004 fields
        if field in self.SCORM_2004_CMI_FIELDS:
            return self.SCORM_2004_CMI_FIELDS[field]
        
        # Check for indexed fields (e.g., cmi.interactions.0.id)
        base_field = self.get_base_field(field)
        if base_field in self.SCORM_12_CMI_FIELDS:
            return self.SCORM_12_CMI_FIELDS[base_field]
        if base_field in self.SCORM_2004_CMI_FIELDS:
            return self.SCORM_2004_CMI_FIELDS[base_field]
        
        return None
    
    def get_base_field(self, field):
        """Get base field name for indexed fields"""
        # Handle indexed fields like cmi.interactions.0.id -> cmi.interactions.n.id
        import re
        pattern = r'(\w+\.\d+\.\w+)'
        match = re.search(pattern, field)
        if match:
            return re.sub(r'\.\d+\.', '.n.', field)
        return field
    
    def is_valid_scorm_time(self, value):
        """Validate SCORM time format"""
        if not value:
            return True
        
        str_value = str(value)
        # SCORM 2004 format: PT1H30M45S
        if str_value.startswith('PT'):
            return True
        # SCORM 1.2 format: hhhh:mm:ss.ss
        if ':' in str_value:
            parts = str_value.split(':')
            if len(parts) == 3:
                try:
                    int(parts[0])  # hours
                    int(parts[1])  # minutes
                    float(parts[2])  # seconds
                    return True
                except ValueError:
                    return False
        return False
    
    def is_valid_datetime(self, value):
        """Validate datetime format"""
        if not value:
            return True
        
        try:
            datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return True
        except ValueError:
            return False
    
    def update_attempt_fields(self, field, value):
        """Update corresponding attempt fields when CMI fields change"""
        field_mapping = {
            'cmi.score.raw': 'score_raw',
            'cmi.score.min': 'score_min',
            'cmi.score.max': 'score_max',
            'cmi.score.scaled': 'score_scaled',
            'cmi.completion_status': 'completion_status',
            'cmi.success_status': 'success_status',
            'cmi.core.lesson_status': 'lesson_status',
            'cmi.core.lesson_location': 'lesson_location',
            'cmi.core.total_time': 'total_time',
            'cmi.core.session_time': 'session_time',
            'cmi.core.exit': 'exit_mode',
            'cmi.core.entry': 'entry',
        }
        
        if field in field_mapping:
            attempt_field = field_mapping[field]
            if hasattr(self.attempt, attempt_field):
                # Convert value to appropriate type
                if attempt_field in ['score_raw', 'score_min', 'score_max', 'score_scaled']:
                    try:
                        setattr(self.attempt, attempt_field, Decimal(str(value)))
                    except (InvalidOperation, ValueError):
                        pass
                elif attempt_field in ['completion_status', 'success_status', 'lesson_status']:
                    setattr(self.attempt, attempt_field, str(value))
                else:
                    setattr(self.attempt, attempt_field, str(value))
    
    def save_cmi_data(self):
        """Save CMI data and history to database"""
        try:
            with transaction.atomic():
                # Update attempt CMI data
                self.attempt.cmi_data = self.cmi_data
                
                # Save CMI history if the field exists
                if hasattr(self.attempt, 'cmi_data_history'):
                    self.attempt.cmi_data_history = self.cmi_history
                
                # Save attempt
                self.attempt.save()
                
                logger.info(f"Saved CMI data for attempt {self.attempt.id}")
                return True
                
        except Exception as e:
            logger.error(f"Error saving CMI data: {str(e)}")
            return False
    
    def get_cmi_field(self, field):
        """Get CMI field value"""
        return self.cmi_data.get(field)
    
    def get_cmi_history(self, field=None):
        """Get CMI history for a specific field or all fields"""
        if field:
            return [entry for entry in self.cmi_history if entry['field'] == field]
        return self.cmi_history
    
    def export_cmi_data(self):
        """Export complete CMI data for compliance reporting"""
        return {
            'attempt_id': self.attempt.id,
            'user_id': self.attempt.user.id,
            'scorm_package_id': self.attempt.scorm_package.id,
            'cmi_data': self.cmi_data,
            'cmi_history': self.cmi_history,
            'export_timestamp': timezone.now().isoformat(),
            'scorm_version': self.attempt.scorm_package.version,
        }
    
    @classmethod
    def get_schema_default(cls, field, version='1.2'):
        """
        Get schema-defined default value for a field based on SCORM version
        
        Args:
            field (str): CMI field name (e.g., 'cmi.core.lesson_status')
            version (str): SCORM version ('1.2' or '2004')
            
        Returns:
            str: Schema-defined default value
        """
        # Get field specification based on SCORM version
        if version == '1.2':
            spec = cls.SCORM_12_CMI_FIELDS.get(field)
        elif version == '2004':
            spec = cls.SCORM_2004_CMI_FIELDS.get(field)
        else:
            # Default to SCORM 1.2 for unknown versions
            spec = cls.SCORM_12_CMI_FIELDS.get(field)
        
        if spec and 'values' in spec:
            # Return first valid value as default
            return spec['values'][0]
        
        # Fallback defaults for common fields
        fallback_defaults = {
            'cmi.core.lesson_status': 'not attempted',
            'cmi.completion_status': 'not attempted', 
            'cmi.success_status': 'unknown',
            'cmi.core.entry': 'ab-initio',
            'cmi.core.credit': 'credit',
            'cmi.core.lesson_mode': 'normal',
            'cmi.core.lesson_location': 'lesson_1',
            'cmi.location': 'lesson_1',
            'cmi.mode': 'normal',
            'cmi.core.exit': '',
            'cmi.exit': '',
            'cmi.core.session_time': '0000:00:00.00',
            'cmi.session_time': '0000:00:00.00',
            'cmi.core.total_time': '0000:00:00.00',
            'cmi.total_time': '0000:00:00.00',
            'cmi.core.score.raw': '0',
            'cmi.score.raw': '0',
            'cmi.core.score.max': '100',
            'cmi.score.max': '100',
            'cmi.core.score.min': '0',
            'cmi.score.min': '0',
            'cmi.core.score.scaled': '0',
            'cmi.score.scaled': '0'
        }
        
        return fallback_defaults.get(field, '')
    
    def validate_all_cmi_data(self):
        """Validate all CMI data fields"""
        validation_results = {}
        
        for field, value in self.cmi_data.items():
            try:
                validated_value = self.validate_cmi_field(field, value)
                validation_results[field] = {
                    'valid': True,
                    'value': validated_value,
                    'error': None
                }
            except Exception as e:
                validation_results[field] = {
                    'valid': False,
                    'value': value,
                    'error': str(e)
                }
        
        return validation_results
