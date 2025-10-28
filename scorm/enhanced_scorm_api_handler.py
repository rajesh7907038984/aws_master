"""
Enhanced SCORM API Handler with Complete CMI Data Storage
Integrates with CMIDataHandler for real-time CMI data updates
"""
import logging
from django.utils import timezone
from django.db import transaction
from .cmi_data_handler import CMIDataHandler

logger = logging.getLogger(__name__)


class EnhancedScormAPIHandler:
    """
    Enhanced SCORM API handler with complete CMI data storage
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.cmi_handler = CMIDataHandler(attempt)
        self.last_error = None
    
    def get_value(self, element):
        """
        Get CMI element value with complete data storage
        
        Args:
            element (str): CMI element name (e.g., 'cmi.score.raw')
            
        Returns:
            str: Element value or empty string if not found
        """
        try:
            value = self.cmi_handler.get_cmi_field(element)
            if value is None:
                logger.info(f"CMI GetValue: {element} = '' (not set)")
                return ''
            
            logger.info(f"CMI GetValue: {element} = '{value}'")
            return str(value)
            
        except Exception as e:
            logger.error(f"Error getting CMI value {element}: {str(e)}")
            self.last_error = '301'
            return ''
    
    def set_value(self, element, value):
        """
        Set CMI element value with complete data storage and validation
        
        Args:
            element (str): CMI element name (e.g., 'cmi.score.raw')
            value (str): Element value
            
        Returns:
            str: 'true' if successful, 'false' if error
        """
        try:
            # Validate element name
            if not self.is_valid_cmi_element(element):
                logger.error(f"Invalid CMI element: {element}")
                self.last_error = '401'
                return 'false'
            
            # Update CMI data with validation and history tracking
            success = self.cmi_handler.update_cmi_field(element, value, validate=True)
            
            if success:
                logger.info(f"CMI SetValue: {element} = '{value}'")
                return 'true'
            else:
                logger.error(f"Failed to set CMI value: {element} = '{value}'")
                self.last_error = '405'
                return 'false'
                
        except Exception as e:
            logger.error(f"Error setting CMI value {element}: {str(e)}")
            self.last_error = '405'
            return 'false'
    
    def commit(self):
        """
        Commit CMI data changes to database
        
        Returns:
            str: 'true' if successful, 'false' if error
        """
        try:
            # Save all CMI data and history
            success = self.cmi_handler.save_cmi_data()
            
            if success:
                logger.info(f"CMI Commit: Successfully saved CMI data for attempt {self.attempt.id}")
                return 'true'
            else:
                logger.error(f"CMI Commit: Failed to save CMI data for attempt {self.attempt.id}")
                self.last_error = '301'
                return 'false'
                
        except Exception as e:
            logger.error(f"Error committing CMI data: {str(e)}")
            self.last_error = '301'
            return 'false'
    
    def get_last_error(self):
        """
        Get last error code
        
        Returns:
            str: Error code or '0' if no error
        """
        return self.last_error or '0'
    
    def get_error_string(self, error_code):
        """
        Get error string for error code
        
        Args:
            error_code (str): Error code
            
        Returns:
            str: Error description
        """
        error_messages = {
            '0': 'No Error',
            '101': 'General Exception',
            '201': 'Invalid Argument Error',
            '202': 'Element Cannot Have Children',
            '203': 'Element Not An Array - Cannot Have Count',
            '301': 'Not Initialized',
            '401': 'Not Implemented Error',
            '402': 'Invalid Set Value, Element Is A Keyword',
            '403': 'Element Is Read Only',
            '404': 'Element Is Write Only',
            '405': 'Incorrect Data Type',
        }
        
        return error_messages.get(error_code, f'Unknown Error: {error_code}')
    
    def get_diagnostic(self, error_code):
        """
        Get diagnostic information for error code
        
        Args:
            error_code (str): Error code
            
        Returns:
            str: Diagnostic information
        """
        return self.get_error_string(error_code)
    
    def initialize(self, parameter):
        """
        Initialize SCORM session with complete CMI data setup
        
        Args:
            parameter (str): Parameter (usually empty)
            
        Returns:
            str: 'true' if successful, 'false' if error
        """
        try:
            # Initialize CMI data if not already done
            if not self.cmi_handler.cmi_data.get('_initialized'):
                self.cmi_handler.update_cmi_field('_initialized', 'true', validate=False)
                self.cmi_handler.update_cmi_field('cmi._version', '1.0', validate=False)
                self.cmi_handler.update_cmi_field('cmi.learner_id', str(self.attempt.user.id), validate=False)
                self.cmi_handler.update_cmi_field('cmi.learner_name', self.attempt.user.get_full_name() or self.attempt.user.username, validate=False)
                
                # Set default values for common fields
                self.cmi_handler.update_cmi_field('cmi.core.lesson_status', 'not attempted', validate=False)
                self.cmi_handler.update_cmi_field('cmi.core.entry', 'ab-initio', validate=False)
                self.cmi_handler.update_cmi_field('cmi.core.credit', 'credit', validate=False)
                self.cmi_handler.update_cmi_field('cmi.core.lesson_mode', 'normal', validate=False)
                
                # Set score range defaults
                self.cmi_handler.update_cmi_field('cmi.core.score.min', '0', validate=False)
                self.cmi_handler.update_cmi_field('cmi.core.score.max', '100', validate=False)
                
                # Set mastery score from package
                if self.attempt.scorm_package.mastery_score:
                    self.cmi_handler.update_cmi_field('cmi.student_data.mastery_score', str(self.attempt.scorm_package.mastery_score), validate=False)
            
            logger.info(f"CMI Initialize: Successfully initialized for attempt {self.attempt.id}")
            return 'true'
            
        except Exception as e:
            logger.error(f"Error initializing CMI: {str(e)}")
            self.last_error = '301'
            return 'false'
    
    def terminate(self, parameter):
        """
        Terminate SCORM session with complete CMI data finalization
        
        Args:
            parameter (str): Parameter (usually empty)
            
        Returns:
            str: 'true' if successful, 'false' if error
        """
        try:
            # Set exit mode
            self.cmi_handler.update_cmi_field('cmi.core.exit', 'normal', validate=False)
            
            # Update completion status if not already set
            if not self.cmi_handler.get_cmi_field('cmi.core.lesson_status') or self.cmi_handler.get_cmi_field('cmi.core.lesson_status') == 'not attempted':
                self.cmi_handler.update_cmi_field('cmi.core.lesson_status', 'completed', validate=False)
            
            # Save all CMI data
            success = self.cmi_handler.save_cmi_data()
            
            if success:
                logger.info(f"CMI Terminate: Successfully terminated session for attempt {self.attempt.id}")
                return 'true'
            else:
                logger.error(f"CMI Terminate: Failed to save CMI data for attempt {self.attempt.id}")
                self.last_error = '301'
                return 'false'
                
        except Exception as e:
            logger.error(f"Error terminating CMI: {str(e)}")
            self.last_error = '301'
            return 'false'
    
    def is_valid_cmi_element(self, element):
        """
        Validate CMI element name
        
        Args:
            element (str): CMI element name
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Check if element exists in CMI specifications
        spec = self.cmi_handler.get_field_specification(element)
        return spec is not None
    
    def get_cmi_data_summary(self):
        """
        Get summary of CMI data for debugging/reporting
        
        Returns:
            dict: CMI data summary
        """
        return {
            'attempt_id': self.attempt.id,
            'user_id': self.attempt.user.id,
            'scorm_package_id': self.attempt.scorm_package.id,
            'total_cmi_fields': len(self.cmi_handler.cmi_data),
            'cmi_history_entries': len(self.cmi_handler.cmi_history),
            'last_updated': timezone.now().isoformat(),
            'score_fields': {
                'raw': self.cmi_handler.get_cmi_field('cmi.score.raw'),
                'min': self.cmi_handler.get_cmi_field('cmi.score.min'),
                'max': self.cmi_handler.get_cmi_field('cmi.score.max'),
                'scaled': self.cmi_handler.get_cmi_field('cmi.score.scaled'),
            },
            'status_fields': {
                'lesson_status': self.cmi_handler.get_cmi_field('cmi.core.lesson_status'),
                'completion_status': self.cmi_handler.get_cmi_field('cmi.completion_status'),
                'success_status': self.cmi_handler.get_cmi_field('cmi.success_status'),
            },
            'time_fields': {
                'total_time': self.cmi_handler.get_cmi_field('cmi.core.total_time'),
                'session_time': self.cmi_handler.get_cmi_field('cmi.core.session_time'),
            }
        }
    
    def export_complete_cmi_data(self):
        """
        Export complete CMI data for compliance reporting
        
        Returns:
            dict: Complete CMI data export
        """
        return self.cmi_handler.export_cmi_data()
    
    def validate_cmi_data(self):
        """
        Validate all CMI data fields
        
        Returns:
            dict: Validation results
        """
        return self.cmi_handler.validate_all_cmi_data()
