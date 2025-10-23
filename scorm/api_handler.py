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
                'cmi.total_time': self.attempt.total_time,
                'cmi.mode': 'normal',
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
        
        # CRITICAL FIX: Check for existing bookmark data and set entry mode accordingly
        has_bookmark_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
        
        if has_bookmark_data:
            self.attempt.entry = 'resume'
            logger.info(f"SCORM Resume: lesson_location='{self.attempt.lesson_location}', suspend_data='{self.attempt.suspend_data[:50] if self.attempt.suspend_data else 'None'}...'")
        else:
            self.attempt.entry = 'ab-initio'
            logger.info(f"SCORM New attempt: starting from beginning")
        
        if self.version == '1.2':
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
            
            # Ensure other required fields are set
            if not self.attempt.cmi_data.get('cmi.core.lesson_status'):
                self.attempt.cmi_data['cmi.core.lesson_status'] = 'not attempted'
            if not self.attempt.cmi_data.get('cmi.core.lesson_mode'):
                self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            if not self.attempt.cmi_data.get('cmi.core.credit'):
                self.attempt.cmi_data['cmi.core.credit'] = 'credit'
        else:
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
            
            # Ensure other required fields are set
            if not self.attempt.cmi_data.get('cmi.completion_status'):
                self.attempt.cmi_data['cmi.completion_status'] = 'incomplete'
            if not self.attempt.cmi_data.get('cmi.mode'):
                self.attempt.cmi_data['cmi.mode'] = 'normal'
            if not self.attempt.cmi_data.get('cmi.credit'):
                self.attempt.cmi_data['cmi.credit'] = 'credit'
        
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
        
        # SIMPLIFIED: Update lesson status based on score if available (trust SCORM's native logic)
        if not self.attempt.lesson_status or self.attempt.lesson_status == 'not_attempted':
            # If we have a valid score, determine pass/fail status
            if self.attempt.score_raw is not None:
                mastery_score = self.attempt.scorm_package.mastery_score or 70
                if self.attempt.score_raw >= mastery_score:
                    self.attempt.lesson_status = 'passed'
                    status_to_set = 'passed'
                else:
                    self.attempt.lesson_status = 'failed'  
                    status_to_set = 'failed'
                logger.info(f"TERMINATE: Set lesson_status to {status_to_set} based on score {self.attempt.score_raw} (mastery: {mastery_score})")
            else:
                # No score available, mark as incomplete
                self.attempt.lesson_status = 'incomplete'
                status_to_set = 'incomplete'
                logger.info(f"TERMINATE: Set lesson_status to incomplete (no score available)")
            
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
                    value = self.attempt.lesson_status if self.attempt.lesson_status != 'not_attempted' else 'not attempted'
                    # Ensure it's a valid SCORM 1.2 status
                    valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                    if value not in valid_statuses:
                        value = 'not attempted'
                elif element == 'cmi.core.lesson_mode':
                    value = 'normal'
                elif element == 'cmi.core.credit':
                    value = 'credit'
                elif element == 'cmi.completion_status':
                    value = self.attempt.completion_status or 'incomplete'
                elif element == 'cmi.mode':
                    value = 'normal'
                elif element == 'cmi.success_status':
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
                    # CRITICAL FIX: Store bookmark data in both CMI data and model fields
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.core.lesson_location'] = value
                    # Enhanced slide tracking
                    self._update_slide_tracking(value)
                elif element == 'cmi.core.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.core.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Store suspend data in both CMI data and model fields
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
                    # ENHANCED: Parse and sync progress from suspend data
                    self._parse_and_sync_suspend_data(value)
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
                    # CRITICAL FIX: Store bookmark data in both CMI data and model fields
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.location'] = value
                    # Enhanced slide tracking
                    self._update_slide_tracking(value)
                elif element == 'cmi.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Store suspend data in both CMI data and model fields
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
                    # ENHANCED: Parse and sync progress from suspend data
                    self._parse_and_sync_suspend_data(value)
            
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
        """Update total time by adding session time with enhanced reliability"""
        try:
            from .enhanced_time_tracking import EnhancedScormTimeTracker
            
            # Use enhanced time tracking for better reliability
            tracker = EnhancedScormTimeTracker(self.attempt)
            success = tracker.save_time_with_reliability(session_time)
            
            if not success:
                logger.error(f"❌ Enhanced time tracking failed for {self.attempt.scorm_package.version}")
                # Fallback to original method
                self._update_total_time_original(session_time)
            else:
                logger.info(f"✅ Enhanced time tracking successful for {self.attempt.scorm_package.version}")
                
        except Exception as e:
            logger.error(f"❌ Enhanced time tracking error: {str(e)}")
            # Fallback to original method
            self._update_total_time_original(session_time)
    
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
            
            # Update detailed tracking
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            
            self.attempt.detailed_tracking.update({
                'total_time_seconds': int(new_total),
                'last_session_duration': total_seconds,
                'session_count': self.attempt.detailed_tracking.get('session_count', 0) + 1,
                'last_updated': timezone.now().isoformat()
            })
            
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
                
                # Use centralized sync service for score synchronization
                from .score_sync_service import ScormScoreSyncService
                ScormScoreSyncService.sync_score(self.attempt)
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
            
            # CRITICAL: Enhanced completion status sync
            if self.version == '1.2':
                is_completed = self.attempt.lesson_status in ['completed', 'passed']
            else:
                is_completed = self.attempt.completion_status == 'completed'
            
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
            
            # Enhanced score tracking
            if self.attempt.score_raw is not None:
                score_value = float(self.attempt.score_raw)
                progress.last_score = score_value
                
                # Update best score if this is better
                if progress.best_score is None or score_value > progress.best_score:
                    progress.best_score = score_value
                
                if is_completed:
                    logger.info(f"SCORM completed - Score saved to TopicProgress: last_score={progress.last_score}, best_score={progress.best_score}")
                else:
                    logger.info(f"SCORM incomplete but score valid - Score saved to TopicProgress: last_score={progress.last_score}, best_score={progress.best_score}")
            else:
                logger.info(f"No valid score to save (score_raw is None, status: {self.attempt.lesson_status})")
            
            # Update time spent
            try:
                time_seconds = self._parse_scorm_time(self.attempt.total_time)
                progress.total_time_spent = int(time_seconds)
            except:
                pass
            
            progress.save()
            
        except Exception as e:
            logger.error(f"Error updating topic progress: {str(e)}")
    
    def _update_slide_tracking(self, slide_location):
        """Enhanced slide tracking with detailed navigation history"""
        try:
            current_time = timezone.now()
            
            # Update last visited slide
            self.attempt.last_visited_slide = slide_location
            
            # Initialize tracking data if not exists
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            if not self.attempt.navigation_history:
                self.attempt.navigation_history = []
            
            # Add to navigation history
            navigation_entry = {
                'slide': slide_location,
                'timestamp': current_time.isoformat(),
                'session_time': self.attempt.session_time,
                'total_time': self.attempt.total_time
            }
            self.attempt.navigation_history.append(navigation_entry)
            
            # Update progress calculation
            self._update_progress_calculation()
            
            # Update session data
            if not self.attempt.session_data:
                self.attempt.session_data = {}
            
            self.attempt.session_data.update({
                'current_slide': slide_location,
                'last_visit_time': current_time.isoformat(),
                'session_duration': self.attempt.session_time
            })
            
            logger.info(f"Updated slide tracking: {slide_location}")
            
        except Exception as e:
            logger.error(f"Error updating slide tracking: {str(e)}")
    
    def _update_progress_calculation(self):
        """Calculate and update progress percentage based on completed slides and suspend data"""
        try:
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            
            # Extract data from suspend data if available
            completed_slides = []
            progress_from_suspend = None
            
            if self.attempt.suspend_data:
                # Parse suspend data for completed slides and progress
                # Format: "progress=30&current_slide=3&completed_slides=1,2"
                import re
                
                # Extract progress percentage from suspend data
                progress_match = re.search(r'progress=(\d+)', self.attempt.suspend_data)
                if progress_match:
                    progress_from_suspend = int(progress_match.group(1))
                
                # Extract completed slides from suspend data
                completed_match = re.search(r'completed_slides=([^&]+)', self.attempt.suspend_data)
                if completed_match:
                    completed_slides = completed_match.group(1).split(',')
                    completed_slides = [s.strip() for s in completed_slides if s.strip()]
            
            # Update completed slides list
            self.attempt.completed_slides = completed_slides
            
            # Calculate progress percentage - prioritize suspend data
            if progress_from_suspend is not None:
                # Use progress from suspend data (most accurate)
                progress_percentage = progress_from_suspend
                logger.info(f"Using progress from suspend data: {progress_percentage}%")
            elif self.attempt.total_slides > 0:
                # Calculate based on completed slides
                progress_percentage = (len(completed_slides) / self.attempt.total_slides) * 100
            else:
                # Estimate based on current slide if total not set
                try:
                    current_slide_num = int(self.attempt.last_visited_slide.split('_')[-1]) if self.attempt.last_visited_slide else 1
                    progress_percentage = min((current_slide_num / 10) * 100, 100)  # Assume 10 slides if unknown
                except:
                    progress_percentage = 0
            
            self.attempt.progress_percentage = progress_percentage
            
            # Update detailed tracking
            self.attempt.detailed_tracking.update({
                'completed_slides': completed_slides,
                'progress_percentage': float(progress_percentage),
                'current_slide': self.attempt.last_visited_slide,
                'total_slides': self.attempt.total_slides,
                'progress_source': 'suspend_data' if progress_from_suspend is not None else 'calculated',
                'last_progress_update': timezone.now().isoformat()
            })
            
            logger.info(f"Updated progress: {progress_percentage}%, completed slides: {completed_slides}")
            
        except Exception as e:
            logger.error(f"Error updating progress calculation: {str(e)}")
    
    def _parse_and_sync_suspend_data(self, suspend_data):
        """Parse suspend data and immediately sync progress to backend"""
        try:
            if not suspend_data:
                return
            
            import re
            
            # Parse progress from suspend data
            progress_match = re.search(r'progress=(\d+)', suspend_data)
            current_slide_match = re.search(r'current_slide=([^&]+)', suspend_data)
            completed_slides_match = re.search(r'completed_slides=([^&]+)', suspend_data)
            
            if progress_match:
                progress_percentage = int(progress_match.group(1))
                current_slide = current_slide_match.group(1) if current_slide_match else 'current'
                completed_slides = []
                
                if completed_slides_match:
                    completed_slides = [s.strip() for s in completed_slides_match.group(1).split(',') if s.strip()]
                
                # Update progress immediately
                self.attempt.progress_percentage = progress_percentage
                self.attempt.last_visited_slide = f'slide_{current_slide}' if current_slide != 'current' else 'current'
                self.attempt.completed_slides = completed_slides
                
                # Update detailed tracking
                if not self.attempt.detailed_tracking:
                    self.attempt.detailed_tracking = {}
                
                self.attempt.detailed_tracking.update({
                    'progress_percentage': float(progress_percentage),
                    'current_slide': self.attempt.last_visited_slide,
                    'completed_slides': completed_slides,
                    'progress_source': 'suspend_data_parsing',
                    'last_progress_update': timezone.now().isoformat(),
                    'sync_method': 'automatic'
                })
                
                logger.info(f"[SCORM SYNC] Progress {progress_percentage}% synced from suspend data")
                
        except Exception as e:
            logger.error(f"Error parsing and syncing suspend data: {str(e)}")
    

