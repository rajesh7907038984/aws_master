"""
Simplified SCORM API Handler
Implements basic SCORM 1.2 and SCORM 2004 Runtime API
Uses xAPI wrapper approach for modern SCORM packages
"""
import json
import logging
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class ScormAPIHandler:
    """
    Simplified handler for SCORM API calls
    Implements both SCORM 1.2 (API) and SCORM 2004 (API_1484_11) standards
    Uses xAPI wrapper approach for modern packages
    """
    
    # Basic SCORM error codes
    SCORM_ERRORS = {
        '0': 'No error',
        '101': 'General exception',
        '201': 'Invalid argument error',
        '301': 'Not initialized',
        '401': 'Not implemented error',
        '402': 'Invalid set value',
        '403': 'Element is read only',
        '404': 'Element is write only',
        '405': 'Incorrect data type',
    }
    
    def __init__(self, attempt):
        """
        Initialize API handler with a ScormAttempt object
        
        Args:
            attempt: ScormAttempt instance
        """
        self.attempt = attempt
        self.version = attempt.scorm_package.version
        self.last_error = '0'
        self.initialized = False
        
        # Initialize CMI data if needed
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
            self.attempt.save()
    
    def _initialize_cmi_data(self):
        """Initialize basic CMI data structure"""
        if self.version == '1.2':
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': self.attempt.lesson_status or 'not attempted',
                'cmi.core.entry': self.attempt.entry or 'ab-initio',
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw is not None else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.core.total_time': self.attempt.total_time or '0000:00:00.00',
                'cmi.core.lesson_mode': 'normal',
                'cmi.core.exit': self.attempt.exit_mode or '',
                'cmi.core.session_time': self.attempt.session_time or '0000:00:00.00',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
            }
        else:  # SCORM 2004 or xAPI
            return {
                'cmi.learner_id': str(self.attempt.user.id),
                'cmi.learner_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.location': self.attempt.lesson_location or '',
                'cmi.credit': 'credit',
                'cmi.completion_status': self.attempt.completion_status or 'incomplete',
                'cmi.success_status': self.attempt.success_status or 'unknown',
                'cmi.entry': self.attempt.entry or 'ab-initio',
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw is not None else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled is not None else '',
                'cmi.total_time': self.attempt.total_time or 'PT0H0M0S',
                'cmi.mode': 'normal',
                'cmi.exit': self.attempt.exit_mode or '',
                'cmi.session_time': self.attempt.session_time or 'PT0H0M0S',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
            }
    
    def initialize(self, parameter=''):
        """Initialize SCORM session"""
        try:
            if self.initialized:
                self.last_error = '0'
                return 'true'
            
            self.initialized = True
            self.attempt.started_at = timezone.now()
            self.attempt.last_accessed = timezone.now()
            self.attempt.save()
            
            logger.info(f"SCORM session initialized for attempt {self.attempt.id}")
            self.last_error = '0'
            return 'true'
            
        except Exception as e:
            logger.error(f"Error initializing SCORM session: {e}")
            self.last_error = '101'
            return 'false'
    
    def terminate(self, parameter=''):
        """Terminate SCORM session"""
        try:
            if not self.initialized:
                self.last_error = '301'
                return 'false'
            
            # Auto-commit before termination
            self.commit('')
            
            self.initialized = False
            self.attempt.last_accessed = timezone.now()
            self.attempt.save()
            
            logger.info(f"SCORM session terminated for attempt {self.attempt.id}")
            self.last_error = '0'
            return 'true'
            
        except Exception as e:
            logger.error(f"Error terminating SCORM session: {e}")
            self.last_error = '101'
            return 'false'
    
    def get_value(self, element):
        """Get SCORM data element value"""
        try:
            if not self.initialized:
                self.last_error = '301'
                return ''
            
            # Get value from CMI data
            value = self.attempt.cmi_data.get(element, '')
            
            # Handle special cases
            if element in ['cmi.core.lesson_status', 'cmi.completion_status']:
                if not value:
                    value = self.attempt.lesson_status or 'not attempted'
            elif element in ['cmi.core.score.raw', 'cmi.score.raw']:
                if not value and self.attempt.score_raw is not None:
                    value = str(self.attempt.score_raw)
            elif element in ['cmi.core.lesson_location', 'cmi.location']:
                if not value:
                    value = self.attempt.lesson_location or ''
            
            logger.info(f"SCORM GetValue: {element} = {value}")
            self.last_error = '0'
            return value
            
        except Exception as e:
            logger.error(f"Error getting SCORM value {element}: {e}")
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """Set SCORM data element value"""
        try:
            if not self.initialized:
                self.last_error = '301'
                return 'false'
            
            # Update CMI data
            self.attempt.cmi_data[element] = value
            
            # Update attempt fields for key elements
            if element == 'cmi.core.lesson_status':
                self.attempt.lesson_status = value
            elif element == 'cmi.completion_status':
                self.attempt.completion_status = value
            elif element == 'cmi.success_status':
                self.attempt.success_status = value
            elif element == 'cmi.core.score.raw':
                try:
                    self.attempt.score_raw = Decimal(str(value))
                except (ValueError, TypeError):
                    pass
            elif element == 'cmi.score.raw':
                try:
                    self.attempt.score_raw = Decimal(str(value))
                except (ValueError, TypeError):
                    pass
            elif element in ['cmi.core.lesson_location', 'cmi.location']:
                self.attempt.lesson_location = value
            elif element == 'cmi.suspend_data':
                self.attempt.suspend_data = value
            elif element in ['cmi.core.session_time', 'cmi.session_time']:
                self.attempt.session_time = value
            elif element in ['cmi.core.total_time', 'cmi.total_time']:
                self.attempt.total_time = value
            
            # Update last accessed
            self.attempt.last_accessed = timezone.now()
            
            logger.info(f"SCORM SetValue: {element} = {value}")
            self.last_error = '0'
            return 'true'
            
        except Exception as e:
            logger.error(f"Error setting SCORM value {element}: {e}")
            self.last_error = '101'
            return 'false'
    
    def commit(self, parameter=''):
        """Commit SCORM data to database"""
        try:
            if not self.initialized:
                self.last_error = '301'
                return 'false'
            
            # Save attempt with transaction
            with transaction.atomic():
                self.attempt.save()
                logger.info(f"SCORM data committed for attempt {self.attempt.id}")
            
            self.last_error = '0'
            return 'true'
            
        except Exception as e:
            logger.error(f"Error committing SCORM data: {e}")
            self.last_error = '101'
            return 'false'
    
    def get_last_error(self):
        """Get last error code"""
        return self.last_error
    
    def get_error_string(self, error_code):
        """Get error string for error code"""
        return self.SCORM_ERRORS.get(str(error_code), 'Unknown error')
    
    def get_diagnostic(self, error_code):
        """Get diagnostic information for error code"""
        return f"Error {error_code}: {self.get_error_string(error_code)}"
    
    # SCORM 1.2 compatibility methods
    def lms_initialize(self, parameter=''):
        return self.initialize(parameter)
    
    def lms_finish(self, parameter=''):
        return self.terminate(parameter)
    
    def lms_get_value(self, element):
        return self.get_value(element)
    
    def lms_set_value(self, element, value):
        return self.set_value(element, value)
    
    def lms_commit(self, parameter=''):
        return self.commit(parameter)
    
    def lms_get_last_error(self):
        return self.get_last_error()
    
    def lms_get_error_string(self, error_code):
        return self.get_error_string(error_code)
    
    def lms_get_diagnostic(self, error_code):
        return self.get_diagnostic(error_code)