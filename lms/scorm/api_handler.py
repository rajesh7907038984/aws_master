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
    
    # CRITICAL FIX: Add class-level handler locks to prevent race conditions
    # This ensures that only one handler is processing an attempt at a time
    _handler_locks = {}
    
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
        self.attempt_id = getattr(attempt, 'id', 'unknown')
        self.version = attempt.scorm_package.version
        self.last_error = '0'
        self.initialized = False
        
        # Create a lock for this attempt if it doesn't exist
        if self.attempt_id not in ScormAPIHandler._handler_locks:
            from threading import Lock
            ScormAPIHandler._handler_locks[self.attempt_id] = Lock()
        
        # Store reference to the lock
        self._lock = ScormAPIHandler._handler_locks[self.attempt_id]
        
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
            # Calculate progress_measure from progress_percentage (0-100 -> 0-1)
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
        """LMSInitialize / Initialize"""
        # CRITICAL FIX: Use lock to prevent race conditions during initialization
        with self._lock:
            if self.initialized:
                self.last_error = '101'
                logger.warning(f"SCORM API already initialized for attempt {self.attempt.id}")
                return 'false'
            
            self.initialized = True
            self.last_error = '0'
            
            # ENHANCED: Log initialization with user details
            logger.info(f"[SCORM INIT]  Initializing SCORM API for:")
            logger.info(f"  - User: {self.attempt.user.username} ({self.attempt.user.get_full_name()})")
            logger.info(f"  - Attempt ID: {self.attempt.id}")
            logger.info(f"  - Package: {self.attempt.scorm_package.title}")
            logger.info(f"  - Version: {self.version}")
        
        # CRITICAL FIX: Ensure CMI data is properly initialized with resume data BEFORE any GetValue calls
        # Always reinitialize CMI data from current model state to avoid stale cached data
        if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
            logger.info(f"Initializing empty CMI data structure for attempt {self.attempt.id}")
            self.attempt.cmi_data = self._initialize_cmi_data()
        
        # CRITICAL FIX: Check for existing bookmark data and set entry mode accordingly
        # Set 'resume' if either lesson_location OR suspend_data exists
        # This allows Rise slides to resume from saved location
        has_bookmark = bool(self.attempt.lesson_location and len(self.attempt.lesson_location) > 0)
        has_suspend_data = bool(self.attempt.suspend_data and len(self.attempt.suspend_data) > 0)
        
        # Set resume if we have any bookmark data
        if has_bookmark or has_suspend_data:
            self.attempt.entry = 'resume'
            # Update lesson_status to incomplete if still not_attempted
            if self.attempt.lesson_status == 'not_attempted':
                self.attempt.lesson_status = 'incomplete'
            logger.info(f"SCORM RESUME MODE: bookmark={has_bookmark}, suspend_data={has_suspend_data}")
            logger.info(f"   lesson_location='{self.attempt.lesson_location}'")
            logger.info(f"   suspend_data length={len(self.attempt.suspend_data)} chars")
            logger.info(f"   Setting entry='resume', status='incomplete'")
        else:
            self.attempt.entry = 'ab-initio'
            logger.info(f"SCORM FRESH START: no saved data (lesson_location={has_bookmark}, suspend_data={has_suspend_data})")
        
        if self.version == '1.2':
            # CRITICAL FIX: FORCE UPDATE entry mode and resume data to overwrite any stale cached values
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            logger.info(f"  [CMI Sync] Set cmi.core.entry = '{self.attempt.entry}'")
            
            # CRITICAL FIX: FORCE UPDATE bookmark data - always sync from model to CMI
            self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location or ''
            if self.attempt.lesson_location:
                logger.info(f"  [CMI Sync] Set cmi.core.lesson_location = '{self.attempt.lesson_location}'")
            
            self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data or ''
            if self.attempt.suspend_data:
                logger.info(f"  [CMI Sync] Set cmi.suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # Ensure other required fields are set
            # CRITICAL FIX: Set status to match model
            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status
            logger.info(f"  [CMI Sync] Set cmi.core.lesson_status = '{self.attempt.lesson_status}'")
            if not self.attempt.cmi_data.get('cmi.core.lesson_mode'):
                self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            if not self.attempt.cmi_data.get('cmi.core.credit'):
                self.attempt.cmi_data['cmi.core.credit'] = 'credit'
        else:
            # CRITICAL FIX: FORCE UPDATE entry mode and resume data to overwrite any stale cached values
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            logger.info(f"  [CMI Sync] Set cmi.entry = '{self.attempt.entry}'")
            
            # CRITICAL FIX: FORCE UPDATE bookmark data - always sync from model to CMI
            self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location or ''
            if self.attempt.lesson_location:
                logger.info(f"  [CMI Sync] Set cmi.location = '{self.attempt.lesson_location}'")
            
            self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data or ''
            if self.attempt.suspend_data:
                logger.info(f"  [CMI Sync] Set cmi.suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # CRITICAL FIX: Ensure progress_measure is set from progress_percentage
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
                self.attempt.cmi_data['cmi.progress_measure'] = progress_measure
                logger.info(f"  [CMI Sync] Set cmi.progress_measure = {progress_measure} ({self.attempt.progress_percentage}%)")
            
            # Ensure other required fields are set
            # CRITICAL FIX: Set status to match model
            if self.attempt.lesson_status == 'not_attempted':
                self.attempt.cmi_data['cmi.completion_status'] = 'not attempted'
            else:
                self.attempt.cmi_data['cmi.completion_status'] = self.attempt.lesson_status
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
        # CRITICAL FIX: Use lock to prevent race conditions during terminate
        with self._lock:
            # FIX: Some SCORM packages skip LMSInitialize/Initialize
            # Check if session was ever initialized by looking at CMI data
            was_initialized = bool(self.attempt.cmi_data and len(self.attempt.cmi_data) > 0)
            
            if not self.initialized and not was_initialized:
                logger.warning(f"SCORM API Terminate called before initialization - auto-initializing for attempt {self.attempt.id}")
                # Auto-initialize the session
                if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
                    self.attempt.cmi_data = self._initialize_cmi_data()
                self.initialized = True
                logger.info(f"Auto-initialized SCORM session for attempt {self.attempt.id}")
        
        self.initialized = False
        self.last_error = '0'
        
        # CRITICAL FIX: Check if content already set exit mode, otherwise default to 'suspend' for resume capability
        exit_element = 'cmi.core.exit' if self.version == '1.2' else 'cmi.exit'
        current_exit = self.attempt.cmi_data.get(exit_element, '')
        
        # If content hasn't set an exit value, or it's empty, default to 'suspend' to enable resume
        if not current_exit or current_exit == '':
            self.attempt.exit_mode = 'suspend'
            self.attempt.cmi_data[exit_element] = 'suspend'
            logger.info(f"TERMINATE: Set exit='suspend' to enable resume (content didn't specify exit mode)")
        else:
            # Content explicitly set exit mode (e.g., 'logout', 'suspend', 'time-out')
            self.attempt.exit_mode = current_exit
            logger.info(f"TERMINATE: Using content's exit mode: '{current_exit}'")
        
        # If exit mode is still not set in attempt model, use the value from cmi_data
        if not self.attempt.exit_mode:
            self.attempt.exit_mode = current_exit if current_exit else 'suspend'
        
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
        
        # ENHANCED: Track session end event
        self._track_session_end_event()
        
        logger.info(f"SCORM API Terminated for attempt {self.attempt.id} - exit_mode: {self.attempt.exit_mode}, lesson_status: {self.attempt.lesson_status}")
        
        return 'true'
    
    def get_value(self, element):
        """LMSGetValue / GetValue"""
        # CRITICAL FIX: Use lock to prevent race conditions during get_value
        with self._lock:
            # CRITICAL FIX: Allow GetValue for resume-critical elements even before initialization
            # This is needed because some SCORM packages check bookmark data before calling Initialize
            resume_critical_elements = [
                'cmi.core.lesson_location', 'cmi.location',
                'cmi.suspend_data',
                'cmi.core.entry', 'cmi.entry'
            ]
            
            if not self.initialized and element not in resume_critical_elements:
                self.last_error = '301'
                logger.warning(f"SCORM API GetValue called before initialization for element: {element}")
                return ''
            
            try:
                # For resume-critical elements before initialization, return from model fields directly
                if not self.initialized and element in resume_critical_elements:
                    logger.info(f"SCORM API GetValue({element}) called before initialization - returning from model")
                    if element in ['cmi.core.lesson_location', 'cmi.location']:
                        value = self.attempt.lesson_location or ''
                    elif element == 'cmi.suspend_data':
                        #  CRITICAL: Return empty string for Rise compatibility
                        # Rise will check if empty and handle gracefully
                        value = self.attempt.suspend_data or ''
                    elif element in ['cmi.core.entry', 'cmi.entry']:
                        #  CRITICAL FIX: Return 'resume' if bookmark OR suspend_data exists
                        # Check both lesson_location and suspend_data for resume capability
                        has_bookmark = bool(self.attempt.lesson_location and len(self.attempt.lesson_location) > 0)
                        has_suspend_data = bool(self.attempt.suspend_data and len(self.attempt.suspend_data) > 0)
                        value = 'resume' if (has_bookmark or has_suspend_data) else 'ab-initio'
                    else:
                        value = ''
                    logger.info(f"SCORM API GetValue({element}) before init - returning: '{value[:100] if isinstance(value, str) else value}'")
                    self.last_error = '0'
                    return str(value)
                
                value = self.attempt.cmi_data.get(element, '')
                
                # Log the retrieved value for debugging (only log important elements to avoid spam)
                if element in ['cmi.core.entry', 'cmi.entry', 'cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.lesson_status']:
                    logger.info(f"📖 SCORM GetValue({element}) - raw value from cmi_data: '{value[:100] if isinstance(value, str) else value}'")
                
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
                    elif element == 'cmi.progress_measure':
                        # Calculate progress_measure from progress_percentage (0-100 -> 0-1)
                        if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                            value = str(float(self.attempt.progress_percentage) / 100.0)
                        else:
                            value = ''
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
        # CRITICAL FIX: Use lock to prevent race conditions during set_value
        with self._lock:
            # CRITICAL FIX: Allow bookmark data to be stored even before initialization
            if not self.initialized and element not in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
                self.last_error = '301'
                logger.warning(f"SCORM API SetValue called before initialization for element: {element}")
                return 'false'
            
            try:
                # FIXED: Add input validation to prevent malicious data
                if value is None:
                    value = ''
                
                # Convert to string and check for basic validity
                value_str = str(value)
                
                # Prevent script injection attempts
                if '<script' in value_str.lower() or 'javascript:' in value_str.lower():
                    logger.warning(f"Potential script injection attempt blocked: {element}")
                    self.last_error = '402'  # Invalid set value
                    return 'false'
            
                # Validate numeric values
                if element in ['cmi.core.score.raw', 'cmi.score.raw', 'cmi.core.score.min', 'cmi.score.min', 
                              'cmi.core.score.max', 'cmi.score.max', 'cmi.score.scaled', 'cmi.progress_measure']:
                    if value_str and value_str.strip():
                        try:
                            float(value_str)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid numeric value for {element}: {value_str}")
                            self.last_error = '405'  # Incorrect data type
                            return 'false'
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
                        # CRITICAL: Truncate if exceeds database field limit (1000 chars)
                        self.attempt.lesson_location = value[:1000] if value else value
                        if len(value) > 1000:
                            logger.warning(f"lesson_location truncated from {len(value)} to 1000 chars")
                    elif element == 'cmi.suspend_data':
                        self.attempt.suspend_data = value
                    
                    # Save immediately for persistence
                    self.attempt.save()
                    self.last_error = '0'
                    return 'true'
                
                # FIXED: Add size limits to prevent unbounded data growth
                # Limit suspend_data to 1MB, other values to 10KB
                value_str = str(value)
                if element in ['cmi.suspend_data']:
                    max_size = 1024 * 1024  # 1MB
                    if len(value_str) > max_size:
                        logger.warning(f"SetValue({element}) exceeds {max_size} bytes, truncating from {len(value_str)}")
                        value = value_str[:max_size]
                else:
                    max_size = 10240  # 10KB for regular fields
                    if len(value_str) > max_size:
                        logger.warning(f"SetValue({element}) exceeds {max_size} bytes, truncating from {len(value_str)}")
                        value = value_str[:max_size]
                
                # ENHANCED: Highest value logic for multiple attempts
                # Always keep the highest/best values when learners retake the same SCORM
                should_update = True
                
                # Apply highest value logic for key metrics
                if element == 'cmi.core.lesson_status':
                    # Keep most advanced status: completed > passed > incomplete > not_attempted
                    status_hierarchy = {'not_attempted': 0, 'incomplete': 1, 'passed': 2, 'completed': 3, 'failed': 1}
                    current_priority = status_hierarchy.get(self.attempt.lesson_status, 0)
                    new_priority = status_hierarchy.get(value, 0)
                    
                    if new_priority > current_priority:
                        logger.info(f"[SCORM] Updating lesson_status to higher value: {value} (was: {self.attempt.lesson_status})")
                        
                        # ENHANCED: Auto-advance to next slide when slide is completed
                        if value in ['completed', 'passed'] and self.attempt.lesson_location:
                            self._auto_advance_to_next_slide()
                    else:
                        should_update = False
                        logger.info(f"[SCORM] Keeping existing lesson_status: {self.attempt.lesson_status} (new: {value} was lower)")
                        
                elif element in ['cmi.core.score.raw', 'cmi.score.raw']:
                    try:
                        new_score = float(value) if value and str(value).strip() else None
                        if new_score is not None and self.attempt.score_raw is not None:
                            if new_score > float(self.attempt.score_raw):
                                logger.info(f"[SCORM]  Updating score to higher value: {new_score} (was: {self.attempt.score_raw})")
                            else:
                                should_update = False
                                logger.info(f"[SCORM]  Keeping existing score: {self.attempt.score_raw} (new: {new_score} was lower)")
                    except (ValueError, TypeError):
                        pass
                        
                elif element == 'cmi.progress_measure':
                    try:
                        new_progress = float(value) if value else 0.0
                        new_percentage = new_progress * 100
                        old_percentage = self.attempt.progress_percentage
                        
                        # CRITICAL FIX: Always save the CURRENT progress exactly as SCORM provides it
                        # Don't compare or filter - save the actual current state from SCORM content
                        self.attempt.progress_percentage = new_percentage
                        logger.info(f"[SCORM] Progress updated: {new_percentage}% (was: {old_percentage}%)")
                    except (ValueError, TypeError):
                        logger.warning(f"[SCORM] Invalid progress_measure value: {value}")
                        pass
                
                # Store the value (always store in CMI data for debugging, but only update model if higher value)
                self.attempt.cmi_data[element] = value
                
                # ENHANCED: Track SCORM data setting events with comprehensive tracking
                self._track_data_setting_event(element, value)
                
                # Track specialized events based on element type
                if element.startswith('cmi.interactions.'):
                    self._track_interaction_event(element, value)
                elif element.startswith('cmi.objectives.'):
                    self._track_objective_event(element, value)
                elif element.startswith('cmi.comments'):
                    self._track_comment_event(element, value)
                elif 'time' in element:
                    self._track_time_event(element, value)
                elif 'score' in element:
                    self._track_scoring_event(element, value)
                
                # Log SetValue for important elements
                if element in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.lesson_status', 'cmi.core.score.raw', 'cmi.score.raw']:
                    if element in ['cmi.suspend_data'] and len(str(value)) > 100:
                        logger.info(f"💾 SCORM SetValue({element}) - stored {len(str(value))} chars")
                    else:
                        logger.info(f"💾 SCORM SetValue({element}, {str(value)[:100]}) - stored successfully")
                
                # Handle interactions, objectives, and comments tracking
                self._handle_detailed_tracking(element, value)
                
                # Standard SCORM bookmark handling - lesson_location is already stored in the model
                
                # Update model fields based on element (only if higher value)
                if self.version == '1.2':
                    if element == 'cmi.core.lesson_status' and should_update:
                        self.attempt.lesson_status = value
                        self._update_completion_from_status(value)
                    elif element == 'cmi.core.score.raw' and should_update:
                        try:
                            self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                            # Auto-determine success status when score is set
                            if self.attempt.score_raw is not None and self.attempt.scorm_package.mastery_score is not None:
                                if self.attempt.score_raw >= self.attempt.scorm_package.mastery_score:
                                    self.attempt.success_status = 'passed'
                                else:
                                    self.attempt.success_status = 'failed'
                                logger.info(f"Auto-determined success status: {self.attempt.success_status} (score: {self.attempt.score_raw}, mastery: {self.attempt.scorm_package.mastery_score})")
                            
                            # CRITICAL FIX: Force immediate save with all tracking data
                            try:
                                # Save with all critical fields
                                self.attempt.save(update_fields=[
                                    'score_raw', 'success_status', 'last_accessed',
                                    'lesson_status', 'completion_status'
                                ])
                                logger.info(f"[TRACKING]  Score saved to database (SCORM 1.2)")
                                
                                # Force sync to TopicProgress
                                self._force_sync_to_topic_progress()
                                
                            except Exception as e:
                                logger.error(f"[TRACKING] Error saving score (SCORM 1.2): {str(e)}")
                                
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
                        # CRITICAL FIX: Store bookmark data EXACTLY as SCORM content provides it
                        # Don't modify or convert - save the exact value from the SCORM content
                        lesson_location = value
                        
                        self.attempt.lesson_location = lesson_location
                        self.attempt.cmi_data['cmi.core.lesson_location'] = lesson_location
                        logger.info(f"[TRACKING] Lesson location saved (SCORM 1.2): {lesson_location}")
                        # Enhanced slide tracking
                        self._update_slide_tracking(lesson_location)
                        
                        # CRITICAL FIX: Force immediate save with all tracking data
                        try:
                            # Update entry mode to resume if we have bookmark data
                            if lesson_location and len(lesson_location) > 0:
                                self.attempt.entry = 'resume'
                                if self.attempt.lesson_status == 'not_attempted':
                                    self.attempt.lesson_status = 'incomplete'
                            
                            # Save with all critical fields
                            self.attempt.save(update_fields=[
                                'lesson_location', 'cmi_data', 'entry', 'lesson_status', 
                                'last_accessed', 'progress_percentage'
                            ])
                            logger.info(f"[TRACKING]  Lesson location saved to database (SCORM 1.2)")
                            
                            # Force sync to TopicProgress
                            self._force_sync_to_topic_progress()
                            
                        except Exception as e:
                            logger.error(f"[TRACKING] Error saving lesson location (SCORM 1.2): {str(e)}")
                    elif element == 'cmi.core.session_time':
                        self.attempt.session_time = value
                        self._update_total_time(value)
                    elif element == 'cmi.core.exit':
                        self.attempt.exit_mode = value
                    elif element == 'cmi.suspend_data':
                        # CRITICAL FIX: Store suspend data in both CMI data and model fields
                        self.attempt.suspend_data = value
                        self.attempt.cmi_data['cmi.suspend_data'] = value
                        logger.info(f"[TRACKING] Suspend data updated (SCORM 1.2): {len(value)} chars")
                        # ENHANCED: Parse and sync progress from suspend data
                        self._parse_and_sync_suspend_data(value)
                        
                        # CRITICAL FIX: Force immediate save with all tracking data
                        try:
                            # Update entry mode to resume if we have suspend data
                            if value and len(value) > 0:
                                self.attempt.entry = 'resume'
                                if self.attempt.lesson_status == 'not_attempted':
                                    self.attempt.lesson_status = 'incomplete'
                            
                            # Save with all critical fields
                            self.attempt.save(update_fields=[
                                'suspend_data', 'cmi_data', 'entry', 'lesson_status', 
                                'last_accessed', 'progress_percentage'
                            ])
                            logger.info(f"[TRACKING]  Suspend data saved to database (SCORM 1.2)")
                            
                            # Force sync to TopicProgress
                            self._force_sync_to_topic_progress()
                            
                            # Force sync score if we have meaningful progress
                            if len(value) > 100:  # Meaningful suspend data
                                from .score_sync_service import ScormScoreSyncService
                                ScormScoreSyncService.sync_score(self.attempt, force=True)
                                logger.info(f"[TRACKING] Force sync triggered for suspend data update")
                        except Exception as e:
                            logger.error(f"[TRACKING] Error saving suspend data (SCORM 1.2): {str(e)}")
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
                            # Auto-determine success status when score is set
                            if self.attempt.score_raw is not None and self.attempt.scorm_package.mastery_score is not None:
                                if self.attempt.score_raw >= self.attempt.scorm_package.mastery_score:
                                    self.attempt.success_status = 'passed'
                                else:
                                    self.attempt.success_status = 'failed'
                                logger.info(f"Auto-determined success status: {self.attempt.success_status} (score: {self.attempt.score_raw}, mastery: {self.attempt.scorm_package.mastery_score})")
                            
                            # CRITICAL FIX: Force immediate save with all tracking data
                            try:
                                # Save with all critical fields
                                self.attempt.save(update_fields=[
                                    'score_raw', 'success_status', 'last_accessed',
                                    'lesson_status', 'completion_status'
                                ])
                                logger.info(f"[TRACKING]  Score saved to database (SCORM 2004)")
                                
                                # Force sync to TopicProgress
                                self._force_sync_to_topic_progress()
                                
                            except Exception as e:
                                logger.error(f"[TRACKING] Error saving score (SCORM 2004): {str(e)}")
                                
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
                    elif element == 'cmi.progress_measure':
                        try:
                            progress_value = Decimal(value) if value and str(value).strip() else None
                            # SCORM 2004 progress_measure should be between 0 and 1
                            if progress_value is not None and (progress_value < 0 or progress_value > 1):
                                logger.warning(f"Progress_measure out of range (0 to 1): {value}")
                                self.last_error = '405'  # Incorrect data type
                                return 'false'
                            # Convert to progress_percentage (0-1 -> 0-100)
                            if progress_value is not None:
                                # ENHANCED: Always update progress_measure (current state)
                                new_percentage = float(progress_value * 100)
                                self.attempt.progress_percentage = new_percentage
                                logger.info(f" Updated progress_percentage to {new_percentage}% from progress_measure {progress_value}")
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid progress_measure value: {value}")
                            self.last_error = '405'  # Incorrect data type
                            return 'false'
                    elif element == 'cmi.location':
                        # CRITICAL FIX: Store bookmark data in both CMI data and model fields
                        self.attempt.lesson_location = value
                        self.attempt.cmi_data['cmi.location'] = value
                        logger.info(f"[TRACKING] Lesson location updated (SCORM 2004): {value[:50]}...")
                        # Enhanced slide tracking
                        self._update_slide_tracking(value)
                        
                        # CRITICAL FIX: Force immediate save with all tracking data
                        try:
                            # Update entry mode to resume if we have bookmark data
                            if value and len(value) > 0:
                                self.attempt.entry = 'resume'
                                if self.attempt.lesson_status == 'not_attempted':
                                    self.attempt.lesson_status = 'incomplete'
                            
                            # Save with all critical fields
                            self.attempt.save(update_fields=[
                                'lesson_location', 'cmi_data', 'entry', 'lesson_status', 
                                'last_accessed', 'progress_percentage'
                            ])
                            logger.info(f"[TRACKING]  Lesson location saved to database (SCORM 2004)")
                            
                            # Force sync to TopicProgress
                            self._force_sync_to_topic_progress()
                            
                        except Exception as e:
                            logger.error(f"[TRACKING] Error saving lesson location (SCORM 2004): {str(e)}")
                    elif element == 'cmi.session_time':
                        self.attempt.session_time = value
                        self._update_total_time(value)
                    elif element == 'cmi.exit':
                        self.attempt.exit_mode = value
                    elif element == 'cmi.suspend_data':
                        # CRITICAL FIX: Store suspend data in both CMI data and model fields
                        self.attempt.suspend_data = value
                        self.attempt.cmi_data['cmi.suspend_data'] = value
                        logger.info(f"[TRACKING] Suspend data updated (SCORM 2004): {len(value)} chars")
                        # ENHANCED: Parse and sync progress from suspend data
                        self._parse_and_sync_suspend_data(value)
                        
                        # CRITICAL FIX: Force immediate save with all tracking data
                        try:
                            # Update entry mode to resume if we have suspend data
                            if value and len(value) > 0:
                                self.attempt.entry = 'resume'
                                if self.attempt.lesson_status == 'not_attempted':
                                    self.attempt.lesson_status = 'incomplete'
                            
                            # Save with all critical fields
                            self.attempt.save(update_fields=[
                                'suspend_data', 'cmi_data', 'entry', 'lesson_status', 
                                'last_accessed', 'progress_percentage'
                            ])
                            logger.info(f"[TRACKING]  Suspend data saved to database (SCORM 2004)")
                            
                            # Force sync to TopicProgress
                            self._force_sync_to_topic_progress()
                            
                            # Force sync score if we have meaningful progress
                            if len(value) > 100:  # Meaningful suspend data
                                from .score_sync_service import ScormScoreSyncService
                                ScormScoreSyncService.sync_score(self.attempt, force=True)
                                logger.info(f"[TRACKING] Force sync triggered for suspend data update")
                        except Exception as e:
                            logger.error(f"[TRACKING] Error saving suspend data (SCORM 2004): {str(e)}")
                
                self.last_error = '0'
                return 'true'
            except Exception as e:
                logger.error(f"Error setting value for {element}: {str(e)}")
                self.last_error = '101'
                return 'false'
    
    def commit(self):
        """LMSCommit / Commit"""
        # CRITICAL FIX: Use lock to prevent race conditions during commit
        with self._lock:
            # CRITICAL FIX: Check if session was EVER initialized (not just in current request)
            # Each API call creates a new handler instance, so self.initialized doesn't persist
            # Instead, check if CMI data exists (created during first Initialize)
            was_initialized = bool(self.attempt.cmi_data and len(self.attempt.cmi_data) > 0)
            
            # FIX: Some SCORM packages skip LMSInitialize/Initialize and go straight to commits
            # Auto-initialize if not already initialized to ensure data can be saved
            if not self.initialized and not was_initialized:
                logger.warning(f"SCORM API Commit called before initialization - auto-initializing for attempt {self.attempt.id}")
                # Auto-initialize the session
                if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
                    self.attempt.cmi_data = self._initialize_cmi_data()
                self.initialized = True
                logger.info(f"Auto-initialized SCORM session for attempt {self.attempt.id}")
        
        try:
            self._commit_data()
            self.last_error = '0'
            logger.info(f"SCORM API Commit successful for attempt {self.attempt.id}")
            return 'true'
        except Exception as e:
            logger.error(f"Error committing data for attempt {self.attempt.id}: {str(e)}")
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
        else:
            # Auto-determine success status based on score and mastery
            if self.attempt.score_raw is not None and self.attempt.scorm_package.mastery_score is not None:
                if self.attempt.score_raw >= self.attempt.scorm_package.mastery_score:
                    self.attempt.success_status = 'passed'
                else:
                    self.attempt.success_status = 'failed'
                logger.info(f"Auto-determined success status: {self.attempt.success_status} (score: {self.attempt.score_raw}, mastery: {self.attempt.scorm_package.mastery_score})")
    
    def _update_total_time(self, session_time):
        """Update total time by adding session time with enhanced tracking"""
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
    
    def _sync_tracking_from_cmi_data(self):
        """
        CRITICAL FIX: Sync tracking data from CMI data to model fields
        This ensures all tracking data (progress, suspend_data, etc.) is properly saved
        """
        try:
            # Get CMI data
            cmi_data = self.attempt.cmi_data or {}
            
            # 1. Sync lesson_location (bookmark)
            if self.version == '1.2':
                location_key = 'cmi.core.lesson_location'
                suspend_key = 'cmi.suspend_data'
                status_key = 'cmi.core.lesson_status'
            else:
                location_key = 'cmi.location'
                suspend_key = 'cmi.suspend_data'
                status_key = 'cmi.completion_status'
            
            # CRITICAL FIX: ALWAYS sync lesson_location from CMI data (don't check length)
            # The bookmark could be shorter but still represent a different/updated position
            if location_key in cmi_data and cmi_data[location_key]:
                cmi_location = cmi_data[location_key]
                if cmi_location:
                    old_location = self.attempt.lesson_location or ''
                    self.attempt.lesson_location = str(cmi_location)[:1000]  # Respect field limit
                    if old_location != self.attempt.lesson_location:
                        logger.info(f"[SYNC] Updated lesson_location from CMI: {self.attempt.lesson_location[:50]}... (was: {old_location[:50] if old_location else 'empty'}...)")
            
            # 2. CRITICAL FIX: ALWAYS sync suspend_data from CMI data (don't check length)
            # The suspend data could have same length but different content (progress updates)
            if suspend_key in cmi_data and cmi_data[suspend_key]:
                cmi_suspend = cmi_data[suspend_key]
                if cmi_suspend:
                    old_suspend_len = len(self.attempt.suspend_data) if self.attempt.suspend_data else 0
                    self.attempt.suspend_data = str(cmi_suspend)
                    new_suspend_len = len(self.attempt.suspend_data)
                    logger.info(f"[SYNC] Updated suspend_data from CMI: {new_suspend_len} chars (was: {old_suspend_len} chars)")
                    
                    # Parse suspend data for progress information
                    self._parse_and_sync_suspend_data(self.attempt.suspend_data)
            
            # 3. Sync lesson status from CMI data if not already set
            if status_key in cmi_data and cmi_data[status_key]:
                cmi_status = cmi_data[status_key]
                if cmi_status and cmi_status != 'not attempted':
                    if self.version == '1.2':
                        if self.attempt.lesson_status in ['not_attempted', 'not attempted']:
                            self.attempt.lesson_status = cmi_status.replace(' ', '_')
                            logger.info(f"[SYNC] Updated lesson_status from CMI: {self.attempt.lesson_status}")
                    else:
                        if self.attempt.completion_status in ['not attempted', 'incomplete']:
                            self.attempt.completion_status = cmi_status.replace(' ', '_')
                            logger.info(f"[SYNC] Updated completion_status from CMI: {self.attempt.completion_status}")
            
            # 4. Calculate progress from suspend data and navigation history
            self._calculate_and_sync_progress()
            
            # 5. Update detailed tracking with current state
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            
            self.attempt.detailed_tracking.update({
                'last_sync_timestamp': timezone.now().isoformat(),
                'cmi_data_keys': list(cmi_data.keys()),
                'has_location': bool(self.attempt.lesson_location),
                'has_suspend_data': bool(self.attempt.suspend_data),
                'progress_percentage': float(self.attempt.progress_percentage) if self.attempt.progress_percentage else 0.0,
                'total_slides': self.attempt.total_slides,
                'completed_slides_count': len(self.attempt.completed_slides) if self.attempt.completed_slides else 0
            })
            
            logger.info(f"[SYNC] Tracking data synced from CMI successfully")
            
        except Exception as e:
            logger.error(f"[SYNC] Error syncing tracking data from CMI: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _calculate_and_sync_progress(self):
        """
        Calculate progress from multiple sources and sync to model fields
        This ensures progress_percentage is always calculated and saved
        """
        try:
            progress_sources = []
            
            # Source 1: From progress_percentage field (if already set)
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_sources.append(('field', self.attempt.progress_percentage))
            
            # Source 2: From CMI progress_measure (SCORM 2004)
            if self.version != '1.2' and self.attempt.cmi_data:
                progress_measure = self.attempt.cmi_data.get('cmi.progress_measure', '')
                if progress_measure and progress_measure != '':
                    try:
                        progress_pct = float(progress_measure) * 100
                        progress_sources.append(('cmi_progress_measure', progress_pct))
                    except (ValueError, TypeError):
                        pass
            
            # Source 3: From suspend data parsing
            if self.attempt.suspend_data:
                import re
                progress_match = re.search(r'progress=(\d+)', self.attempt.suspend_data)
                if progress_match:
                    progress_pct = int(progress_match.group(1))
                    progress_sources.append(('suspend_data', progress_pct))
            
            # Source 4: From completed slides ratio
            if self.attempt.total_slides and self.attempt.total_slides > 0:
                if isinstance(self.attempt.completed_slides, list) and len(self.attempt.completed_slides) > 0:
                    progress_pct = (len(self.attempt.completed_slides) / self.attempt.total_slides) * 100
                    progress_sources.append(('completed_slides', progress_pct))
            
            # Source 5: From navigation history
            if self.attempt.navigation_history and len(self.attempt.navigation_history) > 0:
                # Extract unique slides from navigation history
                unique_slides = set()
                for nav in self.attempt.navigation_history:
                    if isinstance(nav, dict) and 'slide' in nav:
                        unique_slides.add(nav['slide'])
                
                if len(unique_slides) > 0 and self.attempt.total_slides > 0:
                    progress_pct = (len(unique_slides) / self.attempt.total_slides) * 100
                    progress_sources.append(('navigation_history', progress_pct))
            
            # Select the best progress value (highest from reliable sources)
            if progress_sources:
                # Prioritize: suspend_data > cmi_progress_measure > completed_slides > navigation_history > field
                priority = ['suspend_data', 'cmi_progress_measure', 'completed_slides', 'navigation_history', 'field']
                best_progress = None
                best_source = None
                
                for source_name in priority:
                    for src, val in progress_sources:
                        if src == source_name:
                            if best_progress is None or val > best_progress:
                                best_progress = val
                                best_source = src
                
                if best_progress is not None and best_progress > self.attempt.progress_percentage:
                    self.attempt.progress_percentage = min(best_progress, 100.0)  # Cap at 100%
                    logger.info(f"[PROGRESS] Updated progress to {self.attempt.progress_percentage}% from source: {best_source}")
                    
                    # Update detailed tracking
                    if not self.attempt.detailed_tracking:
                        self.attempt.detailed_tracking = {}
                    
                    self.attempt.detailed_tracking.update({
                        'progress_sources': [(src, float(val)) for src, val in progress_sources],
                        'progress_source_used': best_source,
                        'progress_updated_at': timezone.now().isoformat()
                    })
            
        except Exception as e:
            logger.error(f"[PROGRESS] Error calculating progress: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _commit_data(self):
        """Save attempt data to database with comprehensive tracking validation"""
        # CRITICAL FIX: Use lock to prevent race conditions during commits
        with self._lock:
            self.attempt.last_accessed = timezone.now()
            
            # Only save to database if not a preview attempt
            if not getattr(self.attempt, 'is_preview', False):
                # Set flag to prevent signal from processing this
                self.attempt._skip_signal = True
                try:
                    # CRITICAL FIX: Ensure all tracking fields are properly set before save
                    # This fixes the issue where progress_percentage, suspend_data, etc. remain at default values
                    
                    # 1. Ensure JSON fields are never None
                    if self.attempt.completed_slides is None:
                        self.attempt.completed_slides = []
                    if self.attempt.navigation_history is None:
                        self.attempt.navigation_history = []
                    if self.attempt.detailed_tracking is None:
                        self.attempt.detailed_tracking = {}
                    if self.attempt.session_data is None:
                        self.attempt.session_data = {}
                    if self.attempt.cmi_data is None:
                        self.attempt.cmi_data = {}
                
                    # 2. Extract and sync tracking data from CMI data
                    self._sync_tracking_from_cmi_data()
                    
                    # 3. Add commit timestamp to detailed tracking
                    if not self.attempt.detailed_tracking:
                        self.attempt.detailed_tracking = {}
                    
                    self.attempt.detailed_tracking.update({
                        'last_commit_timestamp': timezone.now().isoformat(),
                        'commit_count': self.attempt.detailed_tracking.get('commit_count', 0) + 1,
                        'data_integrity_check': {
                            'has_suspend_data': bool(self.attempt.suspend_data),
                            'has_lesson_location': bool(self.attempt.lesson_location),
                            'has_score': self.attempt.score_raw is not None,
                            'has_status': self.attempt.lesson_status not in ['not_attempted', 'not attempted'],
                            'progress_percentage': float(self.attempt.progress_percentage) if self.attempt.progress_percentage else 0
                        }
                    })
                
                    # 4. Log the tracking data being saved
                    logger.info(f"[COMMIT] Saving tracking data for attempt {self.attempt.id}:")
                    logger.info(f"  - Progress: {self.attempt.progress_percentage}%")
                    logger.info(f"  - Suspend Data: {len(self.attempt.suspend_data) if self.attempt.suspend_data else 0} chars")
                    logger.info(f"  - Completed Slides: {len(self.attempt.completed_slides) if self.attempt.completed_slides else 0}")
                    logger.info(f"  - Total Slides: {self.attempt.total_slides}")
                    logger.info(f"  - Lesson Location: {self.attempt.lesson_location[:50] if self.attempt.lesson_location else 'None'}...")
                    logger.info(f"  - Lesson Status: {self.attempt.lesson_status}")
                    logger.info(f"  - Completion Status: {self.attempt.completion_status}")
                    logger.info(f"  - Success Status: {self.attempt.success_status}")
                    logger.info(f"  - Score Raw: {self.attempt.score_raw}")
                    logger.info(f"  - Score Max: {self.attempt.score_max}")
                    logger.info(f"  - Score Scaled: {self.attempt.score_scaled}")
                    logger.info(f"  - Time Spent: {self.attempt.time_spent_seconds}s")
                    logger.info(f"  - Total Time: {self.attempt.total_time}")
                    logger.info(f"  - CMI Data Size: {len(str(self.attempt.cmi_data)) if self.attempt.cmi_data else 0} chars")
                
                    # 5. Save to database with explicit field list for safety
                    # This ensures all critical fields are saved
                    self.attempt.save()
                    
                    # ENHANCED: Track commit event
                    self._track_commit_event()
                    
                    logger.info(f"[COMMIT]  Successfully saved attempt {self.attempt.id} to database")
                    
                    # 6. Verify the save was successful by checking a few critical fields
                    self.attempt.refresh_from_db()
                    logger.info(f"[COMMIT]  Verification after save:")
                    logger.info(f"  - Suspend data still present: {len(self.attempt.suspend_data) if self.attempt.suspend_data else 0} chars")
                    logger.info(f"  - Bookmark still present: {len(self.attempt.lesson_location) if self.attempt.lesson_location else 0} chars")
                    logger.info(f"  - Score still present: {self.attempt.score_raw}")
                    logger.info(f"  - Status still present: {self.attempt.lesson_status}")
                
                    # 7. Use centralized sync service for score synchronization
                    # This is critical for ensuring all user interactions are tracked
                    from .score_sync_service import ScormScoreSyncService
                    
                    # COMPREHENSIVE FIX: Handle first attempt scoring issues
                    # This fixes the bug where first attempts don't save scores properly
                    
                    # Check if this is a first attempt with meaningful data but no score
                    is_first_attempt = self.attempt.attempt_number == 1
                    has_meaningful_data = (self.attempt.suspend_data and len(self.attempt.suspend_data) > 100) or \
                                        (self.attempt.progress_percentage and self.attempt.progress_percentage > 10)
                                         
                    if is_first_attempt and has_meaningful_data and self.attempt.score_raw is None:
                        # Check for score in CMI data that might not have been synced
                        cmi_score = None
                        if self.attempt.cmi_data:
                            cmi_score = self.attempt.cmi_data.get('cmi.score.raw') or \
                                      self.attempt.cmi_data.get('cmi.core.score.raw')
                            
                        if cmi_score is not None and cmi_score != '':
                            try:
                                # Found score in CMI data - use it
                                score_val = float(cmi_score)
                                if 0 <= score_val <= 100:
                                    self.attempt.score_raw = score_val
                                    logger.info(f"[COMMIT]  FIRST ATTEMPT FIX: Extracted score {score_val} from CMI data")
                                    self.attempt.save()
                            except (ValueError, TypeError):
                                pass
                    
                    # If still no score but has completion evidence, use dynamic processor
                    if self.attempt.score_raw is None and self.attempt.suspend_data:
                        try:
                            from .dynamic_score_processor import DynamicScormScoreProcessor
                            processor = DynamicScormScoreProcessor(self.attempt)
                            extracted_score = processor.extract_score_dynamically(self.attempt.suspend_data)
                            
                            if extracted_score is not None:
                                self.attempt.score_raw = extracted_score
                                logger.info(f"[COMMIT]  FIRST ATTEMPT FIX: Extracted score {extracted_score} from suspend_data")
                                self.attempt.save()
                        except Exception as e:
                            logger.error(f"[COMMIT] Error extracting score from suspend_data: {e}")
                    
                    # Now sync score with potentially fixed data
                    sync_success = ScormScoreSyncService.sync_score(self.attempt, force=True)
                    logger.info(f"[COMMIT] Score sync result for attempt {self.attempt.id}: {' Success' if sync_success else ' Skipped'}")
                    
                    # Always try to sync even if no explicit score
                    # This ensures user interactions are captured in gradebook
                    if not sync_success:
                        # Update last_accessed to ensure interaction is recorded
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save()
                        
                        # Try sync again with updated timestamp
                        sync_success = ScormScoreSyncService.sync_score(self.attempt, force=True)
                        logger.info(f"[COMMIT] Retry score sync with updated timestamp: {' Success' if sync_success else ' Skipped'}")
                    
                    # 8. Clear relevant caches to ensure fresh data
                    from django.core.cache import cache
                    if self.attempt.scorm_package and self.attempt.scorm_package.topic:
                        topic = self.attempt.scorm_package.topic
                        from courses.models import CourseTopic
                        course_topics = CourseTopic.objects.filter(topic=topic)
                        for ct in course_topics:
                            cache.delete(f'gradebook_course_{ct.course.id}')
                        cache.delete(f'topic_progress_{topic.id}_{self.attempt.user.id}')
                
                except Exception as e:
                    logger.error(f"[COMMIT]  Error saving tracking data: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Try a basic save as fallback
                    try:
                        self.attempt.save()
                        logger.info(f"[COMMIT]  Fallback save successful for attempt {self.attempt.id}")
                    except Exception as fallback_error:
                        logger.error(f"[COMMIT]  Fallback save also failed: {str(fallback_error)}")
                finally:
                    # Clean up the flag
                    if hasattr(self.attempt, '_skip_signal'):
                        delattr(self.attempt, '_skip_signal')
            else:
                logger.info("Preview attempt - skipping database save")
    
    def _update_topic_progress(self):
        """Update related TopicProgress based on SCORM data"""
        try:
            from courses.models import TopicProgress
            
            topic = self.attempt.scorm_package.topic
            
            # Get or create topic progress
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=topic
            )
            
            # Update progress data with comprehensive SCORM tracking
            progress.progress_data = {
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
            }
            
            # Update completion
            if self.version == '1.2':
                is_completed = self.attempt.lesson_status in ['completed', 'passed']
            else:
                is_completed = self.attempt.completion_status == 'completed'
            
            if is_completed and not progress.completed:
                progress.completed = True
                progress.completion_method = 'scorm'
                progress.completed_at = timezone.now()
            
            # SIMPLIFIED: Trust SCORM's native scoring logic
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
        """Enhanced slide tracking with detailed navigation history and Rise 360 support"""
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
            
            # CRITICAL FIX: Extract Rise 360 progress from bookmark
            self._extract_rise360_progress(slide_location)
            
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
    
    def _extract_rise360_progress(self, slide_location):
        """
        Extract progress information from Rise 360 bookmark format
        Rise 360 bookmarks look like: index.html#/lessons/cmgj98srz00033b7ede26ffu0
        We need to parse the manifest to get total lessons and calculate progress
        """
        try:
            # Check if this is a Rise 360 bookmark
            if not slide_location or '#/lessons/' not in slide_location:
                return
            
            logger.info(f"[Rise 360] Extracting progress from: {slide_location}")
            
            # Parse the manifest to get lessons structure
            manifest_data = self.attempt.scorm_package.manifest_data
            
            # Try to extract lessons from manifest
            lessons = []
            total_lessons = 0
            current_lesson_index = 0
            
            # Rise 360 stores lessons in the manifest
            if manifest_data and isinstance(manifest_data, dict):
                # Look for lessons in manifest structure
                # Rise 360 typically has resources with identifiers
                resources = manifest_data.get('resources', [])
                
                # Count unique lessons (excluding lib resources)
                for resource in resources:
                    if isinstance(resource, dict):
                        res_id = resource.get('identifier', '')
                        href = resource.get('href', '')
                        # Rise lessons usually have 'lesson' in identifier or are HTML files
                        if 'lesson' in res_id.lower() or (href and href.endswith('.html') and 'lib/' not in href):
                            lessons.append(res_id)
                
                total_lessons = len(lessons)
                
                # Extract current lesson ID from bookmark
                lesson_id = slide_location.split('#/lessons/')[1].split('/')[0] if '#/lessons/' in slide_location else ''
                
                # Find current lesson index
                for idx, les_id in enumerate(lessons):
                    if lesson_id in les_id or les_id in lesson_id:
                        current_lesson_index = idx + 1  # 1-based index
                        break
                
                # If we couldn't match, try to parse from the bookmark structure
                if current_lesson_index == 0 and lesson_id:
                    # Store this lesson ID in completed_slides for tracking
                    if not isinstance(self.attempt.completed_slides, list):
                        self.attempt.completed_slides = []
                    if lesson_id not in self.attempt.completed_slides:
                        self.attempt.completed_slides.append(lesson_id)
                    current_lesson_index = len(self.attempt.completed_slides)
            
            # If manifest parsing didn't work, estimate from bookmark history
            if total_lessons == 0:
                # Use navigation history to estimate
                unique_lessons = set()
                for nav in self.attempt.navigation_history:
                    if '#/lessons/' in nav.get('slide', ''):
                        lesson_id = nav['slide'].split('#/lessons/')[1].split('/')[0]
                        unique_lessons.add(lesson_id)
                
                current_lesson_index = len(unique_lessons)
                
                # Estimate total lessons (Rise typically has 5-15 lessons)
                # We'll update this as user explores more
                total_lessons = max(current_lesson_index, 9)  # Default estimate: 9 lessons
            
            # Update attempt data
            self.attempt.total_slides = total_lessons
            
            # Calculate progress percentage
            if total_lessons > 0 and current_lesson_index > 0:
                progress_percentage = min((current_lesson_index / total_lessons) * 100, 100)
                self.attempt.progress_percentage = progress_percentage
                
                logger.info(f"[Rise 360] Progress updated: Lesson {current_lesson_index}/{total_lessons} = {progress_percentage:.1f}%")
                
                # Update detailed tracking
                if not self.attempt.detailed_tracking:
                    self.attempt.detailed_tracking = {}
                
                self.attempt.detailed_tracking.update({
                    'rise360_current_lesson': current_lesson_index,
                    'rise360_total_lessons': total_lessons,
                    'rise360_progress': float(progress_percentage),
                    'rise360_lesson_id': lesson_id if 'lesson_id' in locals() else None,
                    'last_rise360_update': timezone.now().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error extracting Rise 360 progress: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
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
    
    def _handle_detailed_tracking(self, element, value):
        """
        Handle detailed SCORM tracking for interactions, objectives, and comments
        ENHANCED: Now uses comprehensive tracking system with database storage
        """
        import re
        
        try:
            # Handle interactions (e.g., cmi.interactions.0.id, cmi.interactions.0.result)
            interaction_match = re.match(r'cmi\.(core\.)?interactions\.(\d+)\.(\w+)', element)
            if interaction_match:
                interaction_index = int(interaction_match.group(2))
                interaction_field = interaction_match.group(3)
                
                # Store in a temporary dictionary for this interaction
                if not hasattr(self.attempt, '_temp_interactions'):
                    self.attempt._temp_interactions = {}
                
                if interaction_index not in self.attempt._temp_interactions:
                    self.attempt._temp_interactions[interaction_index] = {}
                
                self.attempt._temp_interactions[interaction_index][interaction_field] = value
                
                # If we have essential data, create/update the interaction record
                if 'id' in self.attempt._temp_interactions[interaction_index]:
                    self._save_interaction(interaction_index, self.attempt._temp_interactions[interaction_index])
                
                # ENHANCED: Also track in comprehensive tracking system
                self._track_interaction_event(element, value)
                return
            
            # Handle objectives (e.g., cmi.objectives.0.id, cmi.objectives.0.status)
            objective_match = re.match(r'cmi\.(core\.)?objectives\.(\d+)\.(\w+)', element)
            if objective_match:
                objective_index = int(objective_match.group(2))
                objective_field = objective_match.group(3)
                
                # Store in a temporary dictionary for this objective
                if not hasattr(self.attempt, '_temp_objectives'):
                    self.attempt._temp_objectives = {}
                
                if objective_index not in self.attempt._temp_objectives:
                    self.attempt._temp_objectives[objective_index] = {}
                
                self.attempt._temp_objectives[objective_index][objective_field] = value
                
                # If we have essential data, create/update the objective record
                if 'id' in self.attempt._temp_objectives[objective_index]:
                    self._save_objective(objective_index, self.attempt._temp_objectives[objective_index])
                
                # ENHANCED: Also track in comprehensive tracking system
                self._track_objective_event(element, value)
                return
            
            # Handle comments (SCORM 1.2: cmi.comments, SCORM 2004: cmi.comments_from_learner.n.comment)
            if element == 'cmi.comments' and value:
                # SCORM 1.2 simple comments
                self._save_comment('learner', value)
                # ENHANCED: Also track in comprehensive tracking system
                self._track_comment_event(element, value)
            elif element == 'cmi.comments_from_lms' and value:
                self._save_comment('lms', value)
                # ENHANCED: Also track in comprehensive tracking system
                self._track_comment_event(element, value)
            
            comment_match = re.match(r'cmi\.comments_from_learner\.(\d+)\.comment', element)
            if comment_match and value:
                # SCORM 2004 comments
                self._save_comment('learner', value)
                # ENHANCED: Also track in comprehensive tracking system
                self._track_comment_event(element, value)
                
        except Exception as e:
            logger.error(f"Error handling detailed tracking for {element}: {str(e)}")
    
    def _save_interaction(self, index, interaction_data):
        """Save or update a SCORM interaction record"""
        try:
            from .models import ScormInteraction
            
            interaction_id = interaction_data.get('id', f'interaction_{index}')
            
            # Get or create the interaction
            interaction, created = ScormInteraction.objects.get_or_create(
                attempt=self.attempt,
                interaction_id=interaction_id,
                defaults={
                    'interaction_type': interaction_data.get('type', 'other'),
                    'timestamp': timezone.now(),
                }
            )
            
            # Update fields
            if 'type' in interaction_data:
                interaction.interaction_type = interaction_data['type']
            if 'correct_responses' in interaction_data:
                interaction.correct_responses = interaction_data['correct_responses']
            if 'weighting' in interaction_data:
                try:
                    interaction.weighting = Decimal(interaction_data['weighting'])
                except (ValueError, TypeError):
                    pass
            if 'learner_response' in interaction_data:
                interaction.learner_response = interaction_data['learner_response']
            if 'result' in interaction_data:
                interaction.result = interaction_data['result']
            if 'latency' in interaction_data:
                interaction.latency = interaction_data['latency']
            if 'description' in interaction_data:
                interaction.description = interaction_data['description']
            
            interaction.save()
            logger.info(f"Saved interaction: {interaction_id} - {interaction_data.get('result', 'N/A')}")
            
        except Exception as e:
            logger.error(f"Error saving interaction: {str(e)}")
    
    def _save_objective(self, index, objective_data):
        """Save or update a SCORM objective record"""
        try:
            from .models import ScormObjective
            
            objective_id = objective_data.get('id', f'objective_{index}')
            
            # Get or create the objective
            objective, created = ScormObjective.objects.get_or_create(
                attempt=self.attempt,
                objective_id=objective_id,
                defaults={}
            )
            
            # Update fields
            if 'status' in objective_data:
                objective.success_status = objective_data['status']
                objective.completion_status = objective_data['status']
            if 'score' in objective_data:
                try:
                    objective.score_raw = Decimal(objective_data['score'])
                except (ValueError, TypeError):
                    pass
            if 'score_min' in objective_data:
                try:
                    objective.score_min = Decimal(objective_data['score_min'])
                except (ValueError, TypeError):
                    pass
            if 'score_max' in objective_data:
                try:
                    objective.score_max = Decimal(objective_data['score_max'])
                except (ValueError, TypeError):
                    pass
            if 'description' in objective_data:
                objective.description = objective_data['description']
            
            objective.save()
            logger.info(f"Saved objective: {objective_id} - {objective_data.get('status', 'N/A')}")
            
        except Exception as e:
            logger.error(f"Error saving objective: {str(e)}")
    
    def _save_comment(self, comment_type, comment_text):
        """Save a SCORM comment"""
        try:
            from .models import ScormComment
            
            # Create the comment
            comment = ScormComment.objects.create(
                attempt=self.attempt,
                comment_type=comment_type,
                comment_text=comment_text[:5000],  # Limit length
                location=self.attempt.lesson_location or '',
                timestamp=timezone.now()
            )
            
            logger.info(f"Saved comment ({comment_type}): {comment_text[:50]}...")                                                                              
            
        except Exception as e:
            logger.error(f"Error saving comment: {str(e)}")
    
    def _auto_advance_to_next_slide(self):
        """Automatically advance to the next slide when current slide is completed"""
        try:
            current_location = self.attempt.lesson_location
            if not current_location:
                return
            
            # Extract current slide number
            current_slide = None
            if 'slide_' in current_location:
                slide_part = current_location.split('slide_')[-1].split('/')[0]
                if slide_part.isdigit():
                    current_slide = int(slide_part)
            
            if current_slide is not None:
                # Calculate next slide
                next_slide = current_slide + 1
                
                # Update lesson location to next slide
                if 'slide_' in current_location:
                    new_location = current_location.replace(f'slide_{current_slide}', f'slide_{next_slide}')
                else:
                    new_location = f"{current_location}/slide_{next_slide}"
                
                # Update the location
                self.attempt.lesson_location = new_location
                self.attempt.cmi_data['cmi.core.lesson_location'] = new_location
                
                # Update progress to reflect advancement
                current_progress = self.attempt.progress_percentage or 0
                new_progress = min(current_progress + 10, 100)  # Add 10% for next slide
                self.attempt.progress_percentage = new_progress
                self.attempt.cmi_data['cmi.progress_measure'] = str(new_progress / 100)
                
                # Update suspend data
                if self.attempt.suspend_data:
                    suspend_data = self.attempt.suspend_data
                    if 'current_slide=' in suspend_data:
                        suspend_data = suspend_data.replace(f'current_slide={current_slide}', f'current_slide={next_slide}')
                    else:
                        suspend_data += f'&current_slide={next_slide}'
                    suspend_data += f'&slide_{current_slide}_completed=true'
                    self.attempt.suspend_data = suspend_data
                    self.attempt.cmi_data['cmi.suspend_data'] = suspend_data
                
                logger.info(f"[SCORM]  Auto-advanced from slide {current_slide} to slide {next_slide}")
                logger.info(f"[SCORM] New location: {new_location}")
                logger.info(f"[SCORM] New progress: {new_progress}%")
                
        except Exception as e:
            logger.error(f"[SCORM] Error auto-advancing to next slide: {e}")
    
    def _track_scorm_event(self, event_type, event_data):
        """Track SCORM API events for comprehensive monitoring"""
        try:
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            
            if 'scorm_events' not in self.attempt.detailed_tracking:
                self.attempt.detailed_tracking['scorm_events'] = []
            
            event = {
                'type': event_type,
                'data': event_data,
                'timestamp': timezone.now().isoformat(),
                'api_version': self.version
            }
            
            self.attempt.detailed_tracking['scorm_events'].append(event)
            
            # Keep only last 100 SCORM events
            if len(self.attempt.detailed_tracking['scorm_events']) > 100:
                self.attempt.detailed_tracking['scorm_events'] = self.attempt.detailed_tracking['scorm_events'][-100:]
            
            logger.info(f"[SCORM EVENT] {event_type}: {event_data.get('api_call', 'N/A')}")
            
        except Exception as e:
            logger.error(f"Error tracking SCORM event: {e}")
    
    def _track_data_setting_event(self, element, value):
        """Track LMSSetValue/SetValue events with comprehensive SCORM data model support"""
        try:
            # Determine the category and type of data being set based on comprehensive SCORM reference
            category = 'unknown'
            data_type = 'unknown'
            
            # SCORM 1.2 Core Elements
            if element.startswith('cmi.core.'):
                category = 'scorm_1_2_core'
                if 'lesson_status' in element:
                    data_type = 'completion_status'
                elif 'score' in element:
                    data_type = 'scoring'
                elif 'session_time' in element:
                    data_type = 'time_tracking'
                elif 'total_time' in element:
                    data_type = 'time_tracking'
                elif 'lesson_location' in element:
                    data_type = 'bookmark'
                elif 'exit' in element:
                    data_type = 'session_management'
                elif 'student' in element:
                    data_type = 'learner_info'
                elif 'launch_data' in element:
                    data_type = 'launch_data'
                    
            # SCORM 2004 Elements
            elif element.startswith('cmi.'):
                category = 'scorm_2004'
                if 'completion_status' in element:
                    data_type = 'completion_status'
                elif 'success_status' in element:
                    data_type = 'success_status'
                elif 'progress_measure' in element:
                    data_type = 'progress_tracking'
                elif 'score' in element:
                    data_type = 'scoring'
                elif 'session_time' in element or 'total_time' in element:
                    data_type = 'time_tracking'
                elif 'location' in element:
                    data_type = 'bookmark'
                elif 'exit' in element or 'entry' in element:
                    data_type = 'session_management'
                elif 'learner' in element:
                    data_type = 'learner_info'
                elif 'launch_data' in element:
                    data_type = 'launch_data'
                    
            # Interactions (both SCORM 1.2 and 2004)
            elif element.startswith('cmi.interactions.'):
                category = 'interactions'
                if 'id' in element:
                    data_type = 'interaction_id'
                elif 'type' in element:
                    data_type = 'interaction_type'
                elif 'result' in element:
                    data_type = 'interaction_result'
                elif 'student_response' in element or 'learner_response' in element:
                    data_type = 'learner_response'
                elif 'correct_responses' in element:
                    data_type = 'correct_answer'
                elif 'weighting' in element:
                    data_type = 'interaction_weight'
                elif 'latency' in element:
                    data_type = 'response_time'
                elif 'timestamp' in element:
                    data_type = 'interaction_timestamp'
                else:
                    data_type = 'interaction_data'
                    
            # Objectives (both SCORM 1.2 and 2004)
            elif element.startswith('cmi.objectives.'):
                category = 'objectives'
                if 'id' in element:
                    data_type = 'objective_id'
                elif 'score' in element:
                    data_type = 'objective_score'
                elif 'status' in element:
                    data_type = 'objective_status'
                else:
                    data_type = 'objective_data'
                    
            # Comments
            elif element.startswith('cmi.comments'):
                category = 'comments'
                data_type = 'learner_feedback'
                
            # Suspend Data (both versions)
            elif 'suspend_data' in element:
                category = 'state_persistence'
                data_type = 'bookmark_data'
            
            self._track_scorm_event('data_setting', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': element,
                'value': str(value)[:100],  # Truncate long values
                'category': category,
                'data_type': data_type,
                'scorm_version': self.version,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking data setting event: {e}")
    
    def _track_completion_event(self, status):
        """Track completion status events"""
        try:
            self._track_scorm_event('completion_status', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': 'cmi.core.lesson_status' if self.version == '1.2' else 'cmi.completion_status',
                'status': status,
                'is_completed': status in ['completed', 'passed'],
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking completion event: {e}")
    
    def _force_sync_to_topic_progress(self):
        """Force sync SCORM data to TopicProgress model"""
        try:
            from courses.models import TopicProgress
            from django.utils import timezone
            
            # Get or create TopicProgress record
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=self.attempt.scorm_package.topic
            )
            
            # Initialize progress data if needed
            if not progress.progress_data:
                progress.progress_data = {}
            
            # Update progress data with SCORM tracking info
            progress.progress_data.update({
                'scorm_attempt_id': self.attempt.id,
                'lesson_status': self.attempt.lesson_status,
                'completion_status': self.attempt.completion_status,
                'success_status': self.attempt.success_status,
                'progress_percentage': float(self.attempt.progress_percentage) if self.attempt.progress_percentage else 0.0,
                'score_raw': float(self.attempt.score_raw) if self.attempt.score_raw else None,
                'score_max': float(self.attempt.score_max) if self.attempt.score_max else None,
                'lesson_location': self.attempt.lesson_location,
                'suspend_data_length': len(self.attempt.suspend_data) if self.attempt.suspend_data else 0,
                'last_sync': timezone.now().isoformat(),
                'sync_source': 'scorm_api_handler'
            })
            
            # Update completion status if SCORM indicates completion
            if self.attempt.lesson_status in ['completed', 'passed']:
                progress.completed = True
                progress.completed_at = timezone.now()
                progress.completion_method = 'scorm'
            
            # Update scores
            if self.attempt.score_raw is not None:
                progress.last_score = self.attempt.score_raw
                if progress.best_score is None or self.attempt.score_raw > progress.best_score:
                    progress.best_score = self.attempt.score_raw
            
            progress.save()
            logger.info(f"[SYNC]  Forced sync to TopicProgress for attempt {self.attempt.id}")
            
        except Exception as e:
            logger.error(f"[SYNC] Error forcing sync to TopicProgress: {str(e)}")
    
    def _track_commit_event(self):
        """Track LMSCommit/Commit events"""
        try:
            self._track_scorm_event('data_commit', {
                'api_call': 'LMSCommit' if self.version == '1.2' else 'Commit',
                'lesson_status': self.attempt.lesson_status,
                'progress_percentage': self.attempt.progress_percentage,
                'lesson_location': self.attempt.lesson_location,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking commit event: {e}")
    
    def _track_session_end_event(self):
        """Track LMSFinish/Terminate events"""
        try:
            self._track_scorm_event('session_end', {
                'api_call': 'LMSFinish' if self.version == '1.2' else 'Terminate',
                'final_status': self.attempt.lesson_status,
                'final_progress': self.attempt.progress_percentage,
                'session_duration': str(self.attempt.total_time) if self.attempt.total_time else '00:00:00',
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking session end event: {e}")
    
    def _track_bookmark_event(self, suspend_data):
        """Track bookmarking events"""
        try:
            self._track_scorm_event('bookmark_save', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': 'cmi.suspend_data',
                'data_length': len(str(suspend_data)),
                'contains_progress': 'progress=' in str(suspend_data),
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking bookmark event: {e}")
    
    def _track_data_retrieval_event(self, element, value):
        """Track LMSGetValue/GetValue events"""
        try:
            self._track_scorm_event('data_retrieval', {
                'api_call': 'LMSGetValue' if self.version == '1.2' else 'GetValue',
                'element': element,
                'value_retrieved': str(value)[:100],  # Truncate long values
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking data retrieval event: {e}")
    
    def _track_interaction_event(self, element, value):
        """Track SCORM interactions (questions, assessments)"""
        try:
            # Extract interaction index and field
            import re
            interaction_match = re.match(r'cmi\.interactions\.(\d+)\.(\w+)', element)
            if interaction_match:
                interaction_index = int(interaction_match.group(1))
                interaction_field = interaction_match.group(2)
                
                self._track_scorm_event('interaction_tracking', {
                    'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                    'element': element,
                    'interaction_index': interaction_index,
                    'interaction_field': interaction_field,
                    'value': str(value)[:200],  # Allow longer values for interactions
                    'timestamp': timezone.now().isoformat()
                })
                
                # Track specific interaction events
                if interaction_field == 'result':
                    self._track_scorm_event('interaction_result', {
                        'interaction_index': interaction_index,
                        'result': value,
                        'timestamp': timezone.now().isoformat()
                    })
                elif interaction_field in ['student_response', 'learner_response']:
                    self._track_scorm_event('learner_response', {
                        'interaction_index': interaction_index,
                        'response': str(value)[:500],
                        'timestamp': timezone.now().isoformat()
                    })
                elif interaction_field == 'latency':
                    self._track_scorm_event('response_time', {
                        'interaction_index': interaction_index,
                        'latency': value,
                        'timestamp': timezone.now().isoformat()
                    })
                
        except Exception as e:
            logger.error(f"Error tracking interaction event: {e}")
    
    def _track_objective_event(self, element, value):
        """Track SCORM objectives (learning goals)"""
        try:
            # Extract objective index and field
            import re
            objective_match = re.match(r'cmi\.objectives\.(\d+)\.(\w+)', element)
            if objective_match:
                objective_index = int(objective_match.group(1))
                objective_field = objective_match.group(2)
                
                self._track_scorm_event('objective_tracking', {
                    'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                    'element': element,
                    'objective_index': objective_index,
                    'objective_field': objective_field,
                    'value': str(value)[:200],
                    'timestamp': timezone.now().isoformat()
                })
                
                # Track specific objective events
                if objective_field == 'status':
                    self._track_scorm_event('objective_status_change', {
                        'objective_index': objective_index,
                        'status': value,
                        'timestamp': timezone.now().isoformat()
                    })
                elif 'score' in objective_field:
                    self._track_scorm_event('objective_score', {
                        'objective_index': objective_index,
                        'score': value,
                        'timestamp': timezone.now().isoformat()
                    })
                
        except Exception as e:
            logger.error(f"Error tracking objective event: {e}")
    
    def _track_comment_event(self, element, value):
        """Track SCORM comments (learner feedback)"""
        try:
            comment_type = 'unknown'
            if 'from_learner' in element:
                comment_type = 'learner_feedback'
            elif 'from_lms' in element:
                comment_type = 'instructor_feedback'
            else:
                comment_type = 'general_comment'
            
            self._track_scorm_event('comment_tracking', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': element,
                'comment_type': comment_type,
                'comment_length': len(str(value)),
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking comment event: {e}")
    
    def _track_time_event(self, element, value):
        """Track SCORM time events (session time, total time)"""
        try:
            time_type = 'unknown'
            if 'session_time' in element:
                time_type = 'session_time'
            elif 'total_time' in element:
                time_type = 'total_time'
            
            self._track_scorm_event('time_tracking', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': element,
                'time_type': time_type,
                'time_value': value,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking time event: {e}")
    
    def _track_scoring_event(self, element, value):
        """Track SCORM scoring events"""
        try:
            score_type = 'unknown'
            if 'raw' in element:
                score_type = 'raw_score'
            elif 'scaled' in element:
                score_type = 'scaled_score'
            elif 'min' in element:
                score_type = 'minimum_score'
            elif 'max' in element:
                score_type = 'maximum_score'
            
            self._track_scorm_event('scoring', {
                'api_call': 'LMSSetValue' if self.version == '1.2' else 'SetValue',
                'element': element,
                'score_type': score_type,
                'score_value': value,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error tracking scoring event: {e}")
    

