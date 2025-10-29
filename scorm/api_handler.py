"""
SCORM API Handler
Implements SCORM 1.2 and SCORM 2004 Runtime API
All operations are handled server-side without external APIs
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


class ScormAPIHandler:
    """
    Handler for SCORM API calls
    Implements both SCORM 1.2 (API) and SCORM 2004 (API_1484_11) standards
    """
    
    # SCORM 1.2 Error codes
    SCORM_12_ERRORS = {
        '0': 'No error',
        '101': 'General exception',
        '201': 'Invalid argument error',
        '202': 'Element cannot have children',
        '203': 'Element not an array',
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
        
        # Always ensure CMI data is properly initialized
        if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
            self.attempt.cmi_data = self._initialize_cmi_data()
            # Save the initialized data immediately
            self.attempt.save()
    
    def _get_schema_default(self, field):
        """Get schema-defined default value for a field based on SCORM version"""
        # Simple defaults based on SCORM version
        defaults = {
            'cmi.core.lesson_status': 'not attempted',
            'cmi.completion_status': 'not attempted',
            'cmi.success_status': 'unknown',
            'cmi.core.entry': 'ab-initio',
        }
        return defaults.get(field, '')
    
    def _initialize_cmi_data(self):
        """Initialize CMI data structure based on SCORM version"""
        if self.version == '1.2':
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': self._get_schema_default('cmi.core.credit'),
                'cmi.core.lesson_status': self.attempt.lesson_status or self._get_schema_default('cmi.core.lesson_status'),
                'cmi.core.entry': self.attempt.entry,
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '',
                'cmi.core.total_time': self.attempt.total_time,
                'cmi.core.lesson_mode': self._get_schema_default('cmi.core.lesson_mode'),
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
            }
        else:  # SCORM 2004
            return {
                'cmi.learner_id': str(self.attempt.user.id),
                'cmi.learner_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.location': self.attempt.lesson_location or '',
                'cmi.credit': self._get_schema_default('cmi.credit'),
                'cmi.completion_status': self.attempt.completion_status,
                'cmi.success_status': self.attempt.success_status,
                'cmi.entry': self.attempt.entry,
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled else '',
                'cmi.total_time': self.attempt.total_time,
                'cmi.mode': self._get_schema_default('cmi.mode'),
                'cmi.exit': '',
                'cmi.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
            }
    
    def initialize(self):
        """LMSInitialize / Initialize"""
        if self.initialized:
            self.last_error = '101'
            logger.warning(f"SCORM API already initialized for attempt {self.attempt.id}")
            return 'false'
        
        self.initialized = True
        self.last_error = '0'
        
        # CRITICAL FIX: Ensure CMI data is properly initialized with resume data BEFORE any GetValue calls
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
        
        # CRITICAL FIX: Enhanced resume detection for SCORM content
        has_bookmark_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
        is_resumable_attempt = self.attempt.lesson_status in ['incomplete', 'not_attempted', 'browsed']
        
        # Determine if this should be a resume scenario
        should_resume = has_bookmark_data or is_resumable_attempt
        
        if should_resume:
            self.attempt.entry = 'resume'
            logger.info(f"SCORM Resume: lesson_location='{self.attempt.lesson_location}', suspend_data='{self.attempt.suspend_data[:50] if self.attempt.suspend_data else 'None'}...', status='{self.attempt.lesson_status}'")
        else:
            self.attempt.entry = self._get_schema_default('cmi.core.entry')
            logger.info(f"SCORM New attempt: starting from beginning")
        
        if self.version == '1.2':
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            logger.info(f"🔖 RESUME: Set cmi.core.entry to '{self.attempt.entry}'")
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
                logger.info(f"🔖 RESUME: Set cmi.core.lesson_location to '{self.attempt.lesson_location}'")
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info(f"🔖 RESUME: Set cmi.suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # Ensure other required fields are set with schema defaults
            if not self.attempt.cmi_data.get('cmi.core.lesson_status'):
                self.attempt.cmi_data['cmi.core.lesson_status'] = self._get_schema_default('cmi.core.lesson_status')
            if not self.attempt.cmi_data.get('cmi.core.lesson_mode'):
                self.attempt.cmi_data['cmi.core.lesson_mode'] = self._get_schema_default('cmi.core.lesson_mode')
            if not self.attempt.cmi_data.get('cmi.core.credit'):
                self.attempt.cmi_data['cmi.core.credit'] = self._get_schema_default('cmi.core.credit')
        else:
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            logger.info(f"🔖 RESUME: Set cmi.entry to '{self.attempt.entry}'")
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location
                logger.info(f"🔖 RESUME: Set cmi.location to '{self.attempt.lesson_location}'")
            elif self.attempt.suspend_data:
                # CRITICAL FIX: If we have suspend_data but no lesson_location, 
                # set a schema-defined default location to enable resume functionality
                schema_default = self._get_schema_default('cmi.location')
                default_location = schema_default or 'lesson_1'
                self.attempt.cmi_data['cmi.location'] = default_location
                logger.info(f"🔖 RESUME: Set schema-defined default cmi.location for resume: '{default_location}'")
            
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info(f"🔖 RESUME: Set cmi.suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # Ensure other required fields are set with schema defaults
            if not self.attempt.cmi_data.get('cmi.completion_status'):
                self.attempt.cmi_data['cmi.completion_status'] = self._get_schema_default('cmi.completion_status')
            if not self.attempt.cmi_data.get('cmi.mode'):
                self.attempt.cmi_data['cmi.mode'] = self._get_schema_default('cmi.mode')
            if not self.attempt.cmi_data.get('cmi.credit'):
                self.attempt.cmi_data['cmi.credit'] = self._get_schema_default('cmi.credit')
        
        # CRITICAL FIX: Save the updated data immediately
        self.attempt.save()
        
        logger.info(f"SCORM API initialized for attempt {self.attempt.id}, version {self.version}")
        logger.info(f"CMI data keys: {list(self.attempt.cmi_data.keys())}")
        logger.info(f"Bookmark data: location='{self.attempt.lesson_location}', suspend_data='{self.attempt.suspend_data[:50] if self.attempt.suspend_data else 'None'}...'")
        logger.info(f"Resume data in CMI: entry='{self.attempt.cmi_data.get('cmi.core.entry' if self.version == '1.2' else 'cmi.entry')}', location='{self.attempt.cmi_data.get('cmi.core.lesson_location' if self.version == '1.2' else 'cmi.location')}'")
        
        return 'true'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning(f"SCORM API Terminate called before initialization for attempt {self.attempt.id}")
            return 'false'
        
        self.initialized = False
        self.last_error = '0'
        
        # CRITICAL FIX: Set exit mode to indicate proper termination
        self.attempt.exit_mode = 'logout'
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.exit'] = 'logout'
        else:
            self.attempt.cmi_data['cmi.exit'] = 'logout'
        
        # ENHANCED: Better completion detection in terminate
        if not self.attempt.lesson_status or self.attempt.lesson_status == 'not_attempted':
            # Check if we have a valid score first
            if self.attempt.score_raw is not None and self.attempt.score_raw > 0:
                mastery_score = self.attempt.scorm_package.mastery_score or 70
                if self.attempt.score_raw >= mastery_score:
                    self.attempt.lesson_status = 'passed'
                    status_to_set = 'passed'
                else:
                    self.attempt.lesson_status = 'failed'  
                    status_to_set = 'failed'
                logger.info(f"TERMINATE: Set lesson_status to {status_to_set} based on score {self.attempt.score_raw} (mastery: {mastery_score})")
            else:
                # SCORM COMPLIANCE: Use only CMI completion status
                # Check CMI data for completion status
                cmi_completion = self.attempt.cmi_data.get('cmi.completion_status')
                cmi_lesson_status = self.attempt.cmi_data.get('cmi.core.lesson_status')
                cmi_success = self.attempt.cmi_data.get('cmi.success_status')
                
                if cmi_completion in ['completed', 'passed'] or cmi_lesson_status in ['completed', 'passed'] or cmi_success in ['passed']:
                    self.attempt.lesson_status = 'completed'
                    status_to_set = 'completed'
                    logger.info(f"TERMINATE: Set lesson_status to completed based on CMI completion status")
                else:
                    self.attempt.lesson_status = 'incomplete'
                    status_to_set = 'incomplete'
                    logger.info(f"TERMINATE: Set lesson_status to incomplete (no CMI completion evidence)")
            
            # Update CMI data
            if self.version == '1.2':
                self.attempt.cmi_data['cmi.core.lesson_status'] = status_to_set
            else:
                self.attempt.cmi_data['cmi.completion_status'] = status_to_set
                if status_to_set in ['passed', 'failed']:
                    self.attempt.cmi_data['cmi.success_status'] = status_to_set
        
        # Save all data
        self._commit_data()
        
        logger.info(f"SCORM API Terminated for attempt {self.attempt.id} - exit_mode: {self.attempt.exit_mode}, lesson_status: {self.attempt.lesson_status}")
        
        return 'true'
    
    def get_value(self, element):
        """LMSGetValue / GetValue"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning(f"SCORM API GetValue called before initialization for element: {element}")
            return ''
        
        try:
            value = self.attempt.cmi_data.get(element, '')
            
            # Log the retrieved value for debugging
            logger.info(f"SCORM API GetValue({element}) - raw value from cmi_data: '{value}'")
            
            # Ensure critical elements have proper defaults if empty or whitespace
            if not value or str(value).strip() == '':
                logger.info(f"SCORM API GetValue({element}) - value is empty, applying default")
                if element == 'cmi.core.lesson_status':
                    # CRITICAL FIX FOR SCORM 1.2: If we have resume data, return 'incomplete' not 'not attempted'
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'incomplete'
                        logger.info(f"SCORM 1.2 RESUME: Override lesson_status to 'incomplete' for resume scenario")
                    else:
                        schema_default = self._get_schema_default('cmi.core.lesson_status')
                        value = self.attempt.lesson_status if self.attempt.lesson_status != 'not_attempted' else schema_default
                    # Ensure it's a valid SCORM 1.2 status
                    valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                    if value not in valid_statuses:
                        value = self._get_schema_default('cmi.core.lesson_status')
                elif element == 'cmi.core.lesson_mode':
                    value = self._get_schema_default('cmi.core.lesson_mode')
                elif element == 'cmi.core.credit':
                    value = self._get_schema_default('cmi.core.credit')
                elif element == 'cmi.completion_status':
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return the actual status
                    # Don't override to 'incomplete' if it's actually 'completed'
                    value = self.attempt.cmi_data.get(element, '')
                    if not value or value == '':
                        # Only set default if truly empty
                        has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                        if has_resume_data:
                            value = self.attempt.completion_status or 'incomplete'
                            logger.info(f"SCORM 2004 RESUME: Set completion_status to '{value}' for resume scenario")
                        else:
                            value = self.attempt.completion_status or 'incomplete'
                    logger.info(f"SCORM 2004: Returning completion_status = '{value}'")
                elif element == 'cmi.mode':
                    value = 'normal'
                elif element == 'cmi.success_status':
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return 'unknown' for resume scenarios
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'unknown'
                        logger.info(f"SCORM 2004 RESUME: Override success_status to 'unknown' for resume scenario")
                    else:
                        value = self.attempt.success_status or 'unknown'
                elif element in ['cmi.core.score.max', 'cmi.score.max']:
                    value = str(self.attempt.score_max) if self.attempt.score_max else '100'
                elif element in ['cmi.core.score.min', 'cmi.score.min']:
                    value = str(self.attempt.score_min) if self.attempt.score_min else '0'
                elif element == 'cmi.core.student_id' or element == 'cmi.learner_id':
                    value = str(self.attempt.user.id)
                elif element == 'cmi.core.student_name' or element == 'cmi.learner_name':
                    value = self.attempt.user.get_full_name() or self.attempt.user.username
                elif element == 'cmi.core.entry' or element == 'cmi.entry':
                    value = self.attempt.entry
                elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                    # CRITICAL FIX: Always return bookmark data from model fields
                    value = self.attempt.lesson_location or ''
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Always return suspend data from model fields
                    value = self.attempt.suspend_data or ''
            
            self.last_error = '0'
            logger.info(f"SCORM API GetValue({element}) - returning: '{value}'")
            return str(value)
        except Exception as e:
            logger.error(f"Error getting value for {element}: {str(e)}")
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """LMSSetValue / SetValue"""
        # CRITICAL FIX: Allow bookmark data to be stored even before initialization
        if not self.initialized and element not in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
            self.last_error = '301'
            logger.warning(f"SCORM API SetValue called before initialization for element: {element}")
            return 'false'
        
        try:
            # CRITICAL FIX: Handle bookmark data storage before initialization
            if not self.initialized and element in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
                # Ensure CMI data exists
                if not self.attempt.cmi_data:
                    self.attempt.cmi_data = {}
                
                # Store bookmark data immediately
                self.attempt.cmi_data[element] = value
                logger.info(f"SCORM API SetValue({element}, {value}) - stored before initialization")
                
                # Also store in model fields for persistence
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    self.attempt.lesson_location = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
                
                # Save immediately for persistence
                self.attempt.save()
                self.last_error = '0'
                return 'true'
            
            # Store the value
            self.attempt.cmi_data[element] = value
            logger.info(f"SCORM API SetValue({element}, {value}) - stored successfully")
            
            # Standard SCORM bookmark handling - lesson_location is already stored in the model
            
            # Update model fields based on element
            if self.version == '1.2':
                if element == 'cmi.core.lesson_status':
                    self.attempt.lesson_status = value
                    self._update_completion_from_status(value)
                elif element == 'cmi.core.score.raw':
                    try:
                        self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.raw value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.core.score.max':
                    try:
                        self.attempt.score_max = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.max value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.core.score.min':
                    try:
                        self.attempt.score_min = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.min value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.core.lesson_location':
                    # Store bookmark data in both CMI data and model fields
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.core.lesson_location'] = value
                elif element == 'cmi.core.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.core.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    # Store suspend data in both CMI data and model fields
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
            else:  # SCORM 2004
                if element == 'cmi.completion_status':
                    self.attempt.completion_status = value
                    if value == 'completed':
                        self.attempt.completed_at = timezone.now()
                elif element == 'cmi.success_status':
                    self.attempt.success_status = value
                elif element == 'cmi.score.raw':
                    try:
                        self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.raw value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.score.max':
                    try:
                        self.attempt.score_max = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.max value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.score.min':
                    try:
                        self.attempt.score_min = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.min value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.score.scaled':
                    try:
                        scaled_value = Decimal(value) if value and str(value).strip() else None
                        # SCORM 2004 scaled scores should be between -1 and 1
                        if scaled_value is not None and (scaled_value < -1 or scaled_value > 1):
                            logger.warning(f"Score.scaled out of range (-1 to 1): {value}")
                            self.last_error = '405'  # Incorrect data type
                            return 'false'
                        self.attempt.score_scaled = scaled_value
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score.scaled value: {value}")
                        self.last_error = '405'  # Incorrect data type
                        return 'false'
                elif element == 'cmi.location':
                    # Store bookmark data in both CMI data and model fields
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.location'] = value
                elif element == 'cmi.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    # Store suspend data in both CMI data and model fields
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
            
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error(f"Error setting value for {element}: {str(e)}")
            self.last_error = '101'
            return 'false'
    
    def commit(self):
        """LMSCommit / Commit"""
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        try:
            self._commit_data()
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error(f"Error committing data: {str(e)}")
            self.last_error = '101'
            return 'false'
    
    def get_last_error(self):
        """LMSGetLastError / GetLastError"""
        return self.last_error
    
    def get_error_string(self, error_code):
        """LMSGetErrorString / GetErrorString"""
        try:
            # Ensure error_code is a string
            error_code_str = str(error_code) if error_code is not None else '0'
            result = self.SCORM_12_ERRORS.get(error_code_str, 'Unknown error')
            logger.info(f"SCORM API GetErrorString({error_code_str}) -> {result}")
            return result
        except Exception as e:
            logger.error(f"Error in get_error_string: {str(e)}")
            return 'Unknown error'
    
    def get_diagnostic(self, error_code):
        """LMSGetDiagnostic / GetDiagnostic"""
        return self.get_error_string(error_code)
    
    def _update_completion_from_status(self, status):
        """Update completion fields based on lesson_status (SCORM 1.2)"""
        if status in ['completed', 'passed']:
            self.attempt.completion_status = 'completed'
            if not self.attempt.completed_at:
                self.attempt.completed_at = timezone.now()
        
        if status == 'passed':
            self.attempt.success_status = 'passed'
        elif status == 'failed':
            self.attempt.success_status = 'failed'
    
    def _update_total_time(self, session_time):
        """Update total time by adding session time"""
        try:
            # Simple time tracking without enhanced features
            if session_time and self.attempt.session_time:
                # Parse session time and add to total
                try:
                    session_parts = session_time.split(':')
                    if len(session_parts) == 3:
                        session_seconds = int(session_parts[0]) * 3600 + int(session_parts[1]) * 60 + float(session_parts[2])
                        
                        total_parts = self.attempt.total_time.split(':') if self.attempt.total_time else ['0', '0', '0']
                        if len(total_parts) == 3:
                            total_seconds = int(total_parts[0]) * 3600 + int(total_parts[1]) * 60 + float(total_parts[2])
                            new_total_seconds = total_seconds + session_seconds
                            
                            # Convert back to SCORM time format
                            hours = int(new_total_seconds // 3600)
                            minutes = int((new_total_seconds % 3600) // 60)
                            seconds = new_total_seconds % 60
                            
                            self.attempt.total_time = f"{hours:04d}:{minutes:02d}:{seconds:06.2f}"
                except (ValueError, IndexError):
                    pass
            
            self.attempt.session_time = session_time
            
        except Exception as e:
            logger.error(f"Error updating total time: {str(e)}")
    
    def _update_total_time_original(self, session_time):
        """Original time tracking method as fallback"""
        try:
            # Parse session time (format: hhhh:mm:ss.ss or PTxHxMxS for SCORM 2004)
            if session_time.startswith('PT'):
                # SCORM 2004 duration format
                total_seconds = self._parse_iso_duration(session_time)
            else:
                # SCORM 1.2 time format
                total_seconds = self._parse_scorm_time(session_time)
            
            # Parse current total time
            current_total = self._parse_scorm_time(self.attempt.total_time)
            
            # Add session time to total
            new_total = current_total + total_seconds
            
            # Update both SCORM format and seconds
            self.attempt.total_time = self._format_scorm_time(new_total)
            self.attempt.time_spent_seconds = int(new_total)
            
            # Update session tracking
            if not self.attempt.session_start_time:
                self.attempt.session_start_time = timezone.now()
            self.attempt.session_end_time = timezone.now()
            
        except Exception as e:
            logger.error(f"Error updating total time: {str(e)}")
    
    def _parse_scorm_time(self, time_str):
        """Parse SCORM time format (hhhh:mm:ss.ss) to seconds"""
        try:
            if not time_str or time_str == '':
                return 0
            
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            return 0
        except (ValueError, IndexError, TypeError) as e:
            logger.warning(f"Error parsing SCORM time '{time_str}': {str(e)}")
            return 0
    
    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration format (PT1H30M45S) to seconds"""
        try:
            if not duration_str or not duration_str.startswith('PT'):
                return 0
                
            # Remove PT prefix
            duration_str = duration_str[2:]
            
            hours = 0
            minutes = 0
            seconds = 0
            
            if 'H' in duration_str:
                hours = int(duration_str.split('H')[0])
                duration_str = duration_str.split('H')[1]
            
            if 'M' in duration_str:
                minutes = int(duration_str.split('M')[0])
                duration_str = duration_str.split('M')[1]
            
            if 'S' in duration_str:
                seconds = float(duration_str.split('S')[0])
            
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError, TypeError) as e:
            logger.warning(f"Error parsing ISO duration '{duration_str}': {str(e)}")
            return 0
    
    def _format_scorm_time(self, total_seconds):
        """Format seconds to SCORM time format (hhhh:mm:ss.ss)"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        return f"{hours:04d}:{minutes:02d}:{seconds:05.2f}"
    
    def _commit_data(self):
        """Save attempt data to database"""
        self.attempt.last_accessed = timezone.now()
        
        # Only save to database if not a preview attempt
        if not getattr(self.attempt, 'is_preview', False):
            # Set flag to prevent signal from processing this
            self.attempt._updating_from_api_handler = True
            try:
                self.attempt.save()
                
                # Score synchronization is handled by signals
            finally:
                # Clean up the flag
                if hasattr(self.attempt, '_updating_from_api_handler'):
                    delattr(self.attempt, '_updating_from_api_handler')
        else:
            logger.info("Preview attempt - skipping database save")
    
    def _update_topic_progress(self):
        """Update related TopicProgress based on SCORM data with enhanced sync"""
        try:
            from courses.models import TopicProgress
            from django.utils import timezone
            
            topic = self.attempt.scorm_package.topic
            
            # Get or create topic progress
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=topic
            )
            
            # Initialize progress_data if not exists
            if not isinstance(progress.progress_data, dict):
                progress.progress_data = {}
            
            # Update progress data with comprehensive SCORM tracking
            progress.progress_data.update({
                'scorm_attempt_id': self.attempt.id,
                'lesson_status': self.attempt.lesson_status,
                'completion_status': self.attempt.completion_status,
                'success_status': self.attempt.success_status,
                'score_raw': float(self.attempt.score_raw) if self.attempt.score_raw else None,
                'score_max': float(self.attempt.score_max) if self.attempt.score_max else None,
                'score_min': float(self.attempt.score_min) if self.attempt.score_min else None,
                'score_scaled': float(self.attempt.score_scaled) if self.attempt.score_scaled else None,
                'total_time': self.attempt.total_time,
                'session_time': self.attempt.session_time,
                'lesson_location': self.attempt.lesson_location,
                'suspend_data': self.attempt.suspend_data,
                'entry': self.attempt.entry,
                'exit_mode': self.attempt.exit_mode,
                'last_updated': timezone.now().isoformat(),
                'scorm_sync': True,  # Mark as synced
            })
            
            # CMI-ONLY: Use only standard SCORM CMI completion status
            is_completed = (
                self.attempt.lesson_status in ['completed', 'passed'] or
                self.attempt.completion_status in ['completed', 'passed'] or
                self.attempt.success_status in ['passed'] or
                # Check CMI data fields directly
                self.attempt.cmi_data.get('cmi.completion_status') in ['completed', 'passed'] or
                self.attempt.cmi_data.get('cmi.core.lesson_status') in ['completed', 'passed'] or
                self.attempt.cmi_data.get('cmi.success_status') in ['passed']
            )
            
            # Update completion status
            if is_completed:
                if not progress.completed:
                    progress.completed = True
                    progress.completion_method = 'scorm'
                    if not progress.completed_at:
                        progress.completed_at = timezone.now()
                    logger.info(f"✅ SCORM SYNC: Marked topic {topic.id} as completed for user {self.attempt.user.username}")
                else:
                    logger.info(f"📊 SCORM SYNC: Topic {topic.id} already completed for user {self.attempt.user.username}")
            else:
                # If not completed, ensure we don't mark as completed
                if progress.completed and progress.completion_method == 'scorm':
                    # Only unmark if it was auto-completed by SCORM, not manually
                    progress.completed = False
                    progress.completion_method = 'auto'
                    logger.info(f"🔄 SCORM SYNC: Unmarked completion for topic {topic.id} - status: {self.attempt.lesson_status}")
            
            # Enhanced score tracking - update scores even if not completed
            if self.attempt.score_raw is not None and self.attempt.score_raw > 0:
                score_value = float(self.attempt.score_raw)
                progress.last_score = score_value
                
                # Update best score if this is better
                if progress.best_score is None or score_value > progress.best_score:
                    progress.best_score = score_value
                
                logger.info(f"SCORM score updated - Score saved to TopicProgress: last_score={progress.last_score}, best_score={progress.best_score}")
            else:
                logger.info(f"No valid score to save (score_raw is None or 0, status: {self.attempt.lesson_status})")
            
            # Update time spent
            try:
                time_seconds = self._parse_scorm_time(self.attempt.total_time)
                progress.total_time_spent = int(time_seconds)
            except:
                pass
            
            progress.save()
            
        except Exception as e:
            logger.error(f"Error updating topic progress: {str(e)}")
    
