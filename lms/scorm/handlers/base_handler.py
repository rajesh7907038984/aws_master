"""
Base SCORM API Handler
Common functionality for all SCORM package types
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)


class BaseScormAPIHandler:
    """
    Base handler for SCORM API calls
    Implements common SCORM 1.2 and SCORM 2004 functionality
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
            self.attempt.save()
    
    def _initialize_cmi_data(self):
        """Initialize CMI data structure based on SCORM version"""
        if self.version == '1.2':
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': self.attempt.lesson_status or 'not attempted',
                'cmi.core.entry': self.attempt.entry,
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.core.total_time': self.attempt.total_time,
                'cmi.core.lesson_mode': 'normal',
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
            }
        else:  # SCORM 2004
            progress_measure = ''
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
            
            return {
                'cmi.learner_id': str(self.attempt.user.id),
                'cmi.learner_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.location': self.attempt.lesson_location or '',
                'cmi.credit': 'credit',
                'cmi.completion_status': self.attempt.completion_status,
                'cmi.success_status': self.attempt.success_status,
                'cmi.entry': self.attempt.entry,
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled else '',
                'cmi.progress_measure': progress_measure,
                'cmi.total_time': self.attempt.total_time,
                'cmi.mode': 'normal',
                'cmi.exit': '',
                'cmi.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
            }
    
    def initialize(self):
        """LMSInitialize / Initialize - Can be overridden by subclasses"""
        if self.initialized:
            self.last_error = '101'
            logger.warning(f"SCORM API already initialized for attempt {self.attempt.id}")
            return 'false'
        
        self.initialized = True
        self.last_error = '0'
        
        # Ensure CMI data is properly initialized
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
        
        # Check for resume data
        has_bookmark = bool(self.attempt.lesson_location and len(self.attempt.lesson_location) > 0)
        has_suspend_data = bool(self.attempt.suspend_data and len(self.attempt.suspend_data) > 0)
        
        if has_bookmark or has_suspend_data:
            self.attempt.entry = 'resume'
            if self.attempt.lesson_status == 'not_attempted':
                self.attempt.lesson_status = 'incomplete'
            logger.info(f"🔄 SCORM RESUME MODE: bookmark={has_bookmark}, suspend_data={has_suspend_data}")
            logger.info(f"   lesson_location='{self.attempt.lesson_location[:50]}'")
            logger.info(f"   suspend_data length={len(self.attempt.suspend_data)} chars")
        else:
            self.attempt.entry = 'ab-initio'
            logger.info(f"🆕 SCORM FRESH START: no saved data")
        
        # Update CMI data with entry mode and resume data
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status
        else:
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
                self.attempt.cmi_data['cmi.progress_measure'] = progress_measure
        
        self.attempt.save()
        
        logger.info(f"✅ SCORM API initialized for attempt {self.attempt.id} ({self.get_handler_name()})")
        return 'true'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning(f"SCORM API Terminate called before initialization for attempt {self.attempt.id}")
            return 'false'
        
        self.initialized = False
        self.last_error = '0'
        
        self.attempt.exit_mode = 'logout'
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.exit'] = 'logout'
        else:
            self.attempt.cmi_data['cmi.exit'] = 'logout'
        
        self._commit_data()
        
        logger.info(f"SCORM API Terminated for attempt {self.attempt.id}")
        return 'true'
    
    def get_value(self, element):
        """LMSGetValue / GetValue"""
        # Allow critical elements before initialization
        resume_critical = ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.entry', 'cmi.entry']
        
        if not self.initialized and element not in resume_critical:
            self.last_error = '301'
            return ''
        
        try:
            if not self.initialized and element in resume_critical:
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    value = self.attempt.lesson_location or ''
                elif element == 'cmi.suspend_data':
                    value = self.attempt.suspend_data or ''
                elif element in ['cmi.core.entry', 'cmi.entry']:
                    has_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    value = 'resume' if has_data else 'ab-initio'
                else:
                    value = ''
                self.last_error = '0'
                return str(value)
            
            value = self.attempt.cmi_data.get(element, '')
            
            if element in ['cmi.core.entry', 'cmi.entry', 'cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
                logger.info(f"📖 GetValue({element}) = '{str(value)[:100]}'")
            
            # Apply defaults for empty values
            if not value or str(value).strip() == '':
                value = self._get_default_value(element)
            
            self.last_error = '0'
            return str(value)
        except Exception as e:
            logger.error(f"Error getting value for {element}: {str(e)}")
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """LMSSetValue / SetValue"""
        # Allow bookmark data before initialization
        if not self.initialized and element not in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
            self.last_error = '301'
            return 'false'
        
        try:
            # Handle pre-init bookmark storage
            if not self.initialized and element in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
                if not self.attempt.cmi_data:
                    self.attempt.cmi_data = {}
                self.attempt.cmi_data[element] = value
                
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    self.attempt.lesson_location = value[:1000] if value else value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
                
                self.attempt.save()
                self.last_error = '0'
                return 'true'
            
            # Store value
            self.attempt.cmi_data[element] = value
            
            if element in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.score.raw', 'cmi.score.raw']:
                if element == 'cmi.suspend_data' and len(str(value)) > 100:
                    logger.info(f"💾 SetValue({element}) - {len(str(value))} chars")
                else:
                    logger.info(f"💾 SetValue({element}) = '{str(value)[:100]}'")
            
            # Update model fields
            self._update_model_field(element, value)
            
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error(f"Error setting value for {element}: {str(e)}")
            self.last_error = '101'
            return 'false'
    
    def commit(self):
        """LMSCommit / Commit"""
        was_initialized = bool(self.attempt.cmi_data and len(self.attempt.cmi_data) > 0)
        
        if not self.initialized and not was_initialized:
            self.last_error = '301'
            return 'false'
        
        try:
            self._commit_data()
            self.last_error = '0'
            logger.info(f"✅ SCORM Commit successful for attempt {self.attempt.id}")
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
            error_code_str = str(error_code) if error_code is not None else '0'
            return self.SCORM_12_ERRORS.get(error_code_str, 'Unknown error')
        except:
            return 'Unknown error'
    
    def get_diagnostic(self, error_code):
        """LMSGetDiagnostic / GetDiagnostic"""
        return self.get_error_string(error_code)
    
    def _get_default_value(self, element):
        """Get default value for empty CMI element"""
        defaults = {
            'cmi.core.lesson_mode': 'normal',
            'cmi.core.credit': 'credit',
            'cmi.mode': 'normal',
            'cmi.credit': 'credit',
            'cmi.core.score.max': '100',
            'cmi.score.max': '100',
            'cmi.core.score.min': '0',
            'cmi.score.min': '0',
            'cmi.core.lesson_location': self.attempt.lesson_location or '',
            'cmi.location': self.attempt.lesson_location or '',
            'cmi.suspend_data': self.attempt.suspend_data or '',
            'cmi.core.entry': self.attempt.entry,
            'cmi.entry': self.attempt.entry,
        }
        return defaults.get(element, '')
    
    def _update_model_field(self, element, value):
        """Update attempt model fields based on CMI element"""
        if self.version == '1.2':
            if element == 'cmi.core.lesson_status':
                self.attempt.lesson_status = value
            elif element == 'cmi.core.score.raw':
                try:
                    self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                except:
                    pass
            elif element == 'cmi.core.lesson_location':
                self.attempt.lesson_location = value
                self.attempt.save()  # Immediate save for bookmarks
            elif element == 'cmi.suspend_data':
                self.attempt.suspend_data = value
                self.attempt.save()  # Immediate save for suspend data
        else:
            if element == 'cmi.completion_status':
                self.attempt.completion_status = value
            elif element == 'cmi.score.raw':
                try:
                    self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                except:
                    pass
            elif element == 'cmi.location':
                self.attempt.lesson_location = value
                self.attempt.save()  # Immediate save for bookmarks
            elif element == 'cmi.suspend_data':
                self.attempt.suspend_data = value
                self.attempt.save()  # Immediate save for suspend data
    
    def _commit_data(self):
        """Save attempt data to database"""
        self.attempt.last_accessed = timezone.now()
        
        if not getattr(self.attempt, 'is_preview', False):
            self.attempt._updating_from_api_handler = True
            try:
                # Ensure JSON fields are never None
                if self.attempt.completed_slides is None:
                    self.attempt.completed_slides = []
                if self.attempt.navigation_history is None:
                    self.attempt.navigation_history = []
                if self.attempt.detailed_tracking is None:
                    self.attempt.detailed_tracking = {}
                if self.attempt.cmi_data is None:
                    self.attempt.cmi_data = {}
                
                self.attempt.save()
                logger.info(f"[COMMIT] Saved attempt {self.attempt.id}")
                
                # Sync score to gradebook
                from scorm.score_sync_service import ScormScoreSyncService
                sync_success = ScormScoreSyncService.sync_score(self.attempt, force=True)
                logger.info(f"[COMMIT] Score sync: {sync_success}")
            except Exception as e:
                logger.error(f"[COMMIT] Error: {str(e)}")
            finally:
                if hasattr(self.attempt, '_updating_from_api_handler'):
                    delattr(self.attempt, '_updating_from_api_handler')
    
    def get_handler_name(self):
        """Get handler name for logging"""
        return self.__class__.__name__

