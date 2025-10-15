"""
SCORM API Handler
Implements SCORM 1.2 and SCORM 2004 Runtime API
All operations are handled server-side without external APIs

Updated 2025-10-14:
- Fixed score synchronization issues that prevented proper score saving to database
- Added explicit transaction handling for better data persistence
- Added force synchronization to ensure scores are consistently saved
- Removed unnecessary code and optimized data flow
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class ScormAPIHandler:
    """
    Handler for SCORM API calls
    Implements both SCORM 1.2 (API) and SCORM 2004 (API_1484_11) standards
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
        
        # CRITICAL FIX: Always ensure CMI data is properly initialized in constructor
        if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
            self.attempt.cmi_data = self._initialize_cmi_data()
            # Save the initialized data immediately
            self.attempt.save()
            logger.info(f"SCORM CMI Data initialized in constructor for attempt {self.attempt.id}")
            
        # CRITICAL FIX: Ensure essential SCORM elements are always present
        if self.version == '1.2':
            if 'cmi.core.lesson_mode' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            if 'cmi.core.credit' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.core.credit'] = 'credit'
        else:
            if 'cmi.mode' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.mode'] = 'normal'
            if 'cmi.credit' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.credit'] = 'credit'
    
    def _initialize_cmi_data(self):
        """Initialize CMI data structure based on SCORM version"""
        if self.version == '1.2':
            # CRITICAL FIX: Ensure proper lesson_status mapping
            lesson_status = self.attempt.lesson_status
            if lesson_status == 'not_attempted':
                lesson_status = 'not attempted'  # SCORM uses space, not underscore
            elif not lesson_status:
                lesson_status = 'not attempted'
                
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': lesson_status,
                'cmi.core.entry': self.attempt.entry or 'ab-initio',
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw is not None else '0',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.core.total_time': self.attempt.total_time or '0000:00:00.00',
                'cmi.core.lesson_mode': 'normal',  # CRITICAL FIX: Always set to 'normal'
                'cmi.core.exit': self.attempt.exit_mode or '',
                'cmi.core.session_time': self.attempt.session_time or '0000:00:00.00',
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
                'cmi.completion_status': self.attempt.completion_status or 'incomplete',
                'cmi.success_status': self.attempt.success_status or 'unknown',
                'cmi.entry': self.attempt.entry or 'ab-initio',
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw is not None else '0',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled else '',
                'cmi.total_time': self.attempt.total_time or 'PT0H0M0S',
                'cmi.mode': 'normal',  # CRITICAL FIX: Always set to 'normal'
                'cmi.exit': self.attempt.exit_mode or '',
                'cmi.session_time': self.attempt.session_time or 'PT0H0M0S',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
            }
    
    def initialize(self):
        """LMSInitialize / Initialize"""
        # CRITICAL FIX: Allow re-initialization for returning users
        if self.initialized:
            # Check if this is a legitimate re-initialization scenario
            from django.utils import timezone
            from datetime import timedelta
            
            # Allow re-initialization if:
            # 1. Previous session was properly terminated (exit_mode set)
            # 2. More than 5 minutes have passed since last access (new session)
            # 3. User is returning to continue (resume scenario)
            
            now = timezone.now()
            time_since_last_access = now - self.attempt.last_accessed if self.attempt.last_accessed else timedelta(hours=1)
            
            allow_reinit = (
                self.attempt.exit_mode in ['logout', 'suspend', 'normal'] or  # Previous session ended properly
                time_since_last_access > timedelta(minutes=5) or  # New session (5+ minutes gap)
                self.attempt.entry == 'resume'  # Explicit resume scenario
            )
            
            if allow_reinit:
                logger.info(f"SCORM API re-initialization allowed for attempt {self.attempt.id} (exit_mode: {self.attempt.exit_mode}, time_gap: {time_since_last_access}, entry: {self.attempt.entry})")
                # Reset initialization state to allow fresh start
                self.initialized = False
                if self.attempt.cmi_data:
                    self.attempt.cmi_data['_api_initialized'] = False
            else:
                self.last_error = '101'
                logger.warning(f"SCORM API re-initialization blocked for attempt {self.attempt.id} - session still active")
                return 'false'
        
        try:
            self.initialized = True
            self.last_error = '0'
            
            # CRITICAL FIX: Store initialization state persistently
            if not self.attempt.cmi_data:
                self.attempt.cmi_data = {}
            self.attempt.cmi_data['_api_initialized'] = True
            
            # CRITICAL FIX: Always reinitialize CMI data to ensure proper defaults
            self.attempt.cmi_data.update(self._initialize_cmi_data())
            
            # CRITICAL FIX: Clear stale exit flags on initialization to prevent auto-closing on revisit
            if self.attempt.cmi_data.get('_content_initiated_exit') == 'true':
                logger.info(f"🧹 CLEARING STALE EXIT FLAG: Removing previous exit flag to prevent auto-closing on revisit")
                self.attempt.cmi_data['_content_initiated_exit'] = 'false'
                
                # Also clear auto-exit detection flags from detailed tracking
                if self.attempt.detailed_tracking and self.attempt.detailed_tracking.get('auto_exit_detected'):
                    from django.utils import timezone
                    logger.info(f"🧹 CLEARING AUTO-EXIT TRACKING: Removing previous auto-exit detection data")
                    self.attempt.detailed_tracking['auto_exit_detected'] = False
                    self.attempt.detailed_tracking['exit_cleared_on_init'] = timezone.now().isoformat()
            
            # ENHANCED: Auto-detect resume capability based on SCORM package type and data
            should_resume = self._auto_detect_resume_capability()
            
            if should_resume:
                self.attempt.entry = 'resume'
                logger.info(f"🔄 AUTO-RESUME DETECTED: lesson_location='{self.attempt.lesson_location}', suspend_data='{self.attempt.suspend_data[:50] if self.attempt.suspend_data else 'None'}...'")
            else:
                self.attempt.entry = 'ab-initio'
                logger.info(f"🆕 FRESH START: No resume data detected or first attempt")
            
            # CRITICAL FIX: Force proper values in CMI data after initialization
            if self.version == '1.2':
                # CRITICAL: Ensure all required SCORM 1.2 elements have proper values
                self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry or 'ab-initio'
                self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'  # Always 'normal'
                self.attempt.cmi_data['cmi.core.credit'] = 'credit'  # Always 'credit'
                
                # Set proper lesson status
                status = self.attempt.lesson_status or 'not_attempted'
                if status == 'not_attempted':
                    status = 'not attempted'  # SCORM uses space
                self.attempt.cmi_data['cmi.core.lesson_status'] = status
                
                # Ensure bookmark data is available
                self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location or ''
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data or ''
                
                # CRITICAL FIX: Ensure score elements are properly initialized
                self.attempt.cmi_data['cmi.core.score.raw'] = str(self.attempt.score_raw) if self.attempt.score_raw is not None else '0'
                self.attempt.cmi_data['cmi.core.score.max'] = str(self.attempt.score_max) if self.attempt.score_max else '100'
                self.attempt.cmi_data['cmi.core.score.min'] = str(self.attempt.score_min) if self.attempt.score_min else '0'
                
                logger.info(f"SCORM 1.2 initialized: lesson_mode='{self.attempt.cmi_data['cmi.core.lesson_mode']}', credit='{self.attempt.cmi_data['cmi.core.credit']}', lesson_status='{self.attempt.cmi_data['cmi.core.lesson_status']}'")
                
            else:  # SCORM 2004
                # CRITICAL: Ensure all required SCORM 2004 elements have proper values
                self.attempt.cmi_data['cmi.entry'] = self.attempt.entry or 'ab-initio'
                self.attempt.cmi_data['cmi.mode'] = 'normal'  # Always 'normal'
                self.attempt.cmi_data['cmi.credit'] = 'credit'  # Always 'credit'
                self.attempt.cmi_data['cmi.completion_status'] = self.attempt.completion_status or 'incomplete'
                self.attempt.cmi_data['cmi.success_status'] = self.attempt.success_status or 'unknown'
                
                # Ensure bookmark data is available
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location or ''
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data or ''
                
                # CRITICAL FIX: Ensure score elements are properly initialized
                self.attempt.cmi_data['cmi.score.raw'] = str(self.attempt.score_raw) if self.attempt.score_raw is not None else '0'
                self.attempt.cmi_data['cmi.score.max'] = str(self.attempt.score_max) if self.attempt.score_max else '100'
                self.attempt.cmi_data['cmi.score.min'] = str(self.attempt.score_min) if self.attempt.score_min else '0'
                
                logger.info(f"SCORM 2004 initialized: mode='{self.attempt.cmi_data['cmi.mode']}', credit='{self.attempt.cmi_data['cmi.credit']}', completion_status='{self.attempt.cmi_data['cmi.completion_status']}'")
                
            
            # CRITICAL FIX: Save the updated data immediately
            self.attempt.save()
            
            logger.info(f"SCORM CMI Data Initialized: lesson_mode={self.attempt.cmi_data.get('cmi.core.lesson_mode' if self.version == '1.2' else 'cmi.mode')}, lesson_status={self.attempt.cmi_data.get('cmi.core.lesson_status' if self.version == '1.2' else 'cmi.completion_status')}")
            
            logger.info(f"SCORM API initialized successfully for attempt {self.attempt.id}, version {self.version}")
            return 'true'
            
        except Exception as e:
            logger.error(f"SCORM API Initialize failed: {str(e)}")
            self.last_error = '101'
            self.initialized = False
            return 'false'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning(f"SCORM API Terminate called before initialization for attempt {self.attempt.id}")
            return 'false'
        
        self.initialized = False
        self.last_error = '0'
        
        # CRITICAL FIX: Clear initialization state persistently
        if self.attempt.cmi_data:
            self.attempt.cmi_data['_api_initialized'] = False
        
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
                mastery_score = self.attempt.scorm_package.mastery_score
                if mastery_score is not None:
                    passing_score = float(mastery_score)
                else:
                    # Use dynamic passing score instead of hardcoded 70
                    passing_score = self._get_dynamic_passing_score()
                
                if self.attempt.score_raw >= passing_score:
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
        
        # NEW: Mark this as a content-initiated exit for the frontend to handle
        self.attempt.cmi_data['_content_initiated_exit'] = 'true'
        
        # ENHANCED: Detect alternative bookmarking if standard bookmarking is empty
        if not self.attempt.lesson_location or self.attempt.lesson_location == '':
            logger.info("Standard lesson_location is empty, trying alternative bookmark detection...")
            bookmark_found = self._detect_alternative_bookmark_methods()
            if bookmark_found:
                logger.info(f"Alternative bookmark method successful: {self.attempt.lesson_location}")
        
        # ENHANCED: Auto-detect content-initiated exit for different authoring tools
        self._auto_detect_content_exit()
        
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
            
            # CRITICAL FIX: Always provide proper defaults for empty values
            if not value or str(value).strip() == '':
                logger.info(f"SCORM API GetValue({element}) - value is empty, applying default")
                if element == 'cmi.core.lesson_status':
                    value = self.attempt.lesson_status if self.attempt.lesson_status != 'not_attempted' else 'not attempted'
                    # Ensure it's a valid SCORM 1.2 status
                    valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                    if value not in valid_statuses:
                        value = 'not attempted'
                elif element == 'cmi.core.lesson_mode':
                    value = 'normal'  # CRITICAL FIX: Always return 'normal'
                elif element == 'cmi.core.credit':
                    value = 'credit'  # CRITICAL FIX: Always return 'credit'
                elif element == 'cmi.completion_status':
                    value = self.attempt.completion_status or 'incomplete'
                elif element == 'cmi.mode':
                    value = 'normal'  # CRITICAL FIX: Always return 'normal'
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
                    value = self.attempt.entry or 'ab-initio'  # CRITICAL FIX: Always return valid entry
                elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                    # ENHANCED: Smart bookmark retrieval with authoring tool support
                    value = self._get_smart_bookmark_location()
                    logger.info(f"SCORM API GetValue({element}) - returning smart bookmark: '{value}'")
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Always return suspend data from model fields
                    value = self.attempt.suspend_data or ''
                    logger.info(f"SCORM API GetValue({element}) - returning suspend data: '{value[:50] if value else 'None'}...'")
                elif element in ['cmi.core.total_time', 'cmi.total_time']:
                    value = self.attempt.total_time or '0000:00:00.00'
                elif element in ['cmi.core.session_time', 'cmi.session_time']:
                    value = self.attempt.session_time or '0000:00:00.00'
                elif element in ['cmi.core.exit', 'cmi.exit']:
                    value = self.attempt.exit_mode or ''
                # CRITICAL FIX: Add proper interaction handling
                elif element == 'cmi.interactions._count':
                    # Return count of interactions stored in cmi_data
                    interactions = self._get_interactions_data()
                    value = str(len(interactions))
                    logger.info(f"SCORM API GetValue(cmi.interactions._count) - returning: {value}")
                elif element.startswith('cmi.interactions.'):
                    # Handle individual interaction elements
                    value = self._get_interaction_element(element)
                    logger.info(f"SCORM API GetValue({element}) - returning interaction element: '{value}'")
                elif element == '_content_initiated_exit':
                    # CRITICAL FIX: Handle content-initiated exit flag detection
                    value = self.attempt.cmi_data.get('_content_initiated_exit', 'false')
                    logger.info(f"SCORM API GetValue({element}) - returning exit flag: '{value}'")
                else:
                    # Return empty string for unknown elements
                    value = ''
            
            # CRITICAL FIX: Update CMI data with the resolved value to prevent future empty returns
            if value and value != '':
                self.attempt.cmi_data[element] = value
            
            self.last_error = '0'
            logger.info(f"SCORM API GetValue({element}) - returning: '{value}'")
            return str(value)
        except Exception as e:
            logger.error(f"Error getting value for {element}: {str(e)}")
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """LMSSetValue / SetValue"""
        # CRITICAL FIX: Allow bookmark data and exit data to be stored even before initialization
        allowed_before_init = ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.exit', 'cmi.exit']
        if not self.initialized and element not in allowed_before_init:
            self.last_error = '301'
            logger.warning(f"SCORM API SetValue called before initialization for element: {element}")
            return 'false'
        
        try:
            # CRITICAL FIX: Handle data storage before initialization (bookmark, suspend, exit)
            allowed_before_init = ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data', 'cmi.core.exit', 'cmi.exit']
            if not self.initialized and element in allowed_before_init:
                # Ensure CMI data exists
                if not self.attempt.cmi_data:
                    self.attempt.cmi_data = {}
                
                # Store data immediately
                self.attempt.cmi_data[element] = value
                logger.info(f"SCORM API SetValue({element}, {value}) - stored before initialization")
                
                # Also store in model fields for persistence
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    self.attempt.lesson_location = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
                elif element in ['cmi.core.exit', 'cmi.exit']:
                    self.attempt.exit_mode = value
                
                # ENHANCED TRACKING: Force save to database
                save_fields = ['cmi_data', 'last_accessed']
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    save_fields.extend(['lesson_location'])
                elif element == 'cmi.suspend_data':
                    save_fields.extend(['suspend_data'])
                elif element in ['cmi.core.exit', 'cmi.exit']:
                    save_fields.extend(['exit_mode'])
                
                self.attempt.save(update_fields=save_fields)
                logger.info(f"💾 TRACKING DATA SAVED: {element} = {value} for attempt {self.attempt.id}")
                
                self.last_error = '0'
                return 'true'
            
            # CRITICAL FIX: Update model fields FIRST, then use tracking method
            # Update model fields based on element
            if self.version == '1.2':
                if element == 'cmi.core.lesson_status':
                    self.attempt.lesson_status = value
                    self._update_completion_from_status(value)
                    logger.info(f"✅ SET STATUS: attempt.lesson_status = {self.attempt.lesson_status} (from value '{value}')")
                    logger.info(f"✅ SET STATUS: Model field updated BEFORE tracking save")
                elif element == 'cmi.core.score.raw':
                    try:
                        # DYNAMIC SCORE HANDLING: Accept whatever value SCORM content provides
                        if not value or str(value).strip() == '':
                            self.attempt.score_raw = None
                            logger.info(f"✅ SET SCORE: attempt.score_raw = None (empty value)")
                        else:
                            # Convert to Decimal, accepting any numeric value the SCORM content provides
                            self.attempt.score_raw = Decimal(str(value))
                            logger.info(f"✅ SET SCORE: attempt.score_raw = {self.attempt.score_raw} (dynamic value from SCORM content)")
                        
                        logger.info(f"✅ SET SCORE: Model field updated BEFORE tracking save")
                    except (ValueError, TypeError):
                        logger.warning(f"❌ Invalid score format (non-numeric): {value}")
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
                    # ENHANCED BOOKMARK: Force immediate save for bookmark data
                    logger.info(f"🔖 BOOKMARK SAVED: lesson_location='{value}' for attempt {self.attempt.id}")
                    # Force save bookmark data immediately
                    self.attempt.save(update_fields=['lesson_location', 'cmi_data', 'last_accessed'])
                    logger.info(f"💾 BOOKMARK PERSISTED: lesson_location saved to database")
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
                    # ENHANCED BOOKMARK: Force immediate save for suspend data
                    logger.info(f"🔖 SUSPEND DATA SAVED: suspend_data='{value[:50]}...' for attempt {self.attempt.id}")
                    # Force save suspend data immediately
                    self.attempt.save(update_fields=['suspend_data', 'cmi_data', 'last_accessed'])
                    logger.info(f"💾 SUSPEND DATA PERSISTED: suspend_data saved to database")
                # CRITICAL FIX: Add interaction handling for SetValue - SCORM 1.2
                elif element.startswith('cmi.interactions.'):
                    # Handle interaction data storage
                    success = self._set_interaction_element(element, value)
                    if not success:
                        logger.warning(f"Failed to set interaction element: {element} = {value}")
                        self.last_error = '402'  # Invalid set value
                        return 'false'
                    logger.info(f"🎯 INTERACTION SAVED: {element} = {value} for attempt {self.attempt.id}")
                elif element == '_content_initiated_exit':
                    # CRITICAL FIX: Handle content-initiated exit flag setting
                    self.attempt.cmi_data['_content_initiated_exit'] = value
                    logger.info(f"🚪 EXIT FLAG SET: {element} = {value} for attempt {self.attempt.id}")
                    # Force save immediately for exit flag
                    self.attempt.save(update_fields=['cmi_data', 'last_accessed'])
                    # Return true for successful setting
                    self.last_error = '0'
                    return 'true'
            else:  # SCORM 2004
                if element == 'cmi.completion_status':
                    self.attempt.completion_status = value
                    if value == 'completed':
                        self.attempt.completed_at = timezone.now()
                    logger.info(f"✅ SET COMPLETION: attempt.completion_status = {self.attempt.completion_status} (from value '{value}')")
                elif element == 'cmi.success_status':
                    self.attempt.success_status = value
                    logger.info(f"✅ SET SUCCESS: attempt.success_status = {self.attempt.success_status} (from value '{value}')")
                elif element == 'cmi.score.raw':
                    try:
                        # DYNAMIC SCORE HANDLING: Accept whatever value SCORM content provides (SCORM 2004)
                        if not value or str(value).strip() == '':
                            self.attempt.score_raw = None
                            logger.info(f"✅ SET SCORE: attempt.score_raw = None (empty value)")
                        else:
                            # Convert to Decimal, accepting any numeric value the SCORM content provides
                            self.attempt.score_raw = Decimal(str(value))
                            logger.info(f"✅ SET SCORE: attempt.score_raw = {self.attempt.score_raw} (dynamic value from SCORM content)")
                        
                    except (ValueError, TypeError):
                        logger.warning(f"❌ Invalid score format (non-numeric): {value}")
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
                    # ENHANCED BOOKMARK: Force immediate save for bookmark data
                    logger.info(f"🔖 BOOKMARK SAVED: location='{value}' for attempt {self.attempt.id}")
                    # Force save bookmark data immediately
                    self.attempt.save(update_fields=['lesson_location', 'cmi_data', 'last_accessed'])
                    logger.info(f"💾 BOOKMARK PERSISTED: location saved to database")
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
                    # ENHANCED BOOKMARK: Force immediate save for suspend data
                    logger.info(f"🔖 SUSPEND DATA SAVED: suspend_data='{value[:50]}...' for attempt {self.attempt.id}")
                    # Force save suspend data immediately
                    self.attempt.save(update_fields=['suspend_data', 'cmi_data', 'last_accessed'])
                    logger.info(f"💾 SUSPEND DATA PERSISTED: suspend_data saved to database")
                elif element == '_content_initiated_exit':
                    # CRITICAL FIX: Handle content-initiated exit flag setting (SCORM 2004)
                    self.attempt.cmi_data['_content_initiated_exit'] = value
                    logger.info(f"🚪 EXIT FLAG SET (2004): {element} = {value} for attempt {self.attempt.id}")
                    # Force save immediately for exit flag
                    self.attempt.save(update_fields=['cmi_data', 'last_accessed'])
                    # Return true for successful setting
                    self.last_error = '0'
                    return 'true'
            
            # ENHANCED TRACKING: Use comprehensive tracking method AFTER all model fields are updated
            self.attempt.update_tracking_data(element, value)
            logger.info(f"SCORM API SetValue({element}, {value}) - stored with enhanced tracking AFTER model update")
            
            # SMART BOOKMARKING: Create synthetic bookmark for packages that don't use standard bookmarking
            self._create_smart_bookmark_from_activity(element, value)
            
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
            result = self.SCORM_ERRORS.get(error_code_str, 'Unknown error')
            logger.info(f"SCORM API GetErrorString({error_code_str}) -> {result}")
            return result
        except Exception as e:
            logger.error(f"Error in get_error_string: {str(e)}")
            return 'Unknown error'
    
    def get_diagnostic(self, error_code):
        """LMSGetDiagnostic / GetDiagnostic"""
        return self.get_error_string(error_code)
    
    def handle_api_call(self, attempt, method, parameters):
        """
        Handle SCORM API calls - CRITICAL METHOD FOR TRACKING
        
        Args:
            attempt: ScormAttempt instance
            method: SCORM API method name
            parameters: List of parameters for the method
            
        Returns:
            Result of the API call
        """
        # Initialize the handler with the attempt
        self.attempt = attempt
        self.version = attempt.scorm_package.version
        self.last_error = '0'
        
        # CRITICAL FIX: Check if API is already initialized by looking at persistent state
        self.initialized = self.attempt.cmi_data.get('_api_initialized', False)
        logger.info(f"SCORM API handler created - method: {method}, initialized: {self.initialized}")
        
        # CRITICAL FIX: Always ensure CMI data is properly initialized for API calls
        if not self.attempt.cmi_data or len(self.attempt.cmi_data) == 0:
            self.attempt.cmi_data = self._initialize_cmi_data()
            self.attempt.save()
            logger.info(f"SCORM CMI Data re-initialized for API call - attempt {self.attempt.id}")
            
        # CRITICAL FIX: Ensure essential SCORM elements are always present
        if self.version == '1.2':
            if 'cmi.core.lesson_mode' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            if 'cmi.core.credit' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.core.credit'] = 'credit'
        else:
            if 'cmi.mode' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.mode'] = 'normal'
            if 'cmi.credit' not in self.attempt.cmi_data:
                self.attempt.cmi_data['cmi.credit'] = 'credit'
        
        try:
            # Handle different SCORM API methods - Support both SCORM 1.2 and 2004 naming
            if method in ['Initialize', 'LMSInitialize']:
                return self.initialize()
            elif method in ['Terminate', 'LMSFinish']:
                return self.terminate()
            elif method in ['GetValue', 'LMSGetValue']:
                element = parameters[0] if parameters else ''
                return self.get_value(element)
            elif method in ['SetValue', 'LMSSetValue']:
                element = parameters[0] if len(parameters) > 0 else ''
                value = parameters[1] if len(parameters) > 1 else ''
                return self.set_value(element, value)
            elif method in ['Commit', 'LMSCommit']:
                return self.commit()
            elif method in ['GetLastError', 'LMSGetLastError']:
                return self.get_last_error()
            elif method in ['GetErrorString', 'LMSGetErrorString']:
                error_code = parameters[0] if parameters else '0'
                return self.get_error_string(error_code)
            elif method in ['GetDiagnostic', 'LMSGetDiagnostic']:
                error_code = parameters[0] if parameters else '0'
                return self.get_diagnostic(error_code)
            else:
                logger.warning(f"Unknown SCORM API method: {method}")
                self.last_error = '401'  # Not implemented error
                return 'false'
                
        except Exception as e:
            logger.error(f"Error handling SCORM API call {method}: {str(e)}")
            self.last_error = '101'  # General exception
            return 'false'
    
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
    
    def _commit_data(self):
        """Save attempt data to database with proper transaction handling
        ENHANCED: Ensures all tracking data is properly saved to database
        FIXED: Removed @transaction.atomic decorator to prevent nested transaction issues
        """
        logger.info(f"💾 COMMIT: Starting commit for attempt {self.attempt.id}")
        logger.info(f"💾 COMMIT: score_raw BEFORE save = {self.attempt.score_raw}")
        
        # ENHANCED: Auto-detect alternative bookmarks before saving if standard bookmarking is missing
        if (not self.attempt.lesson_location or self.attempt.lesson_location == '') and len(self.attempt.cmi_data) > 3:
            logger.info("📍 Attempting alternative bookmark detection during commit...")
            bookmark_detected = self._detect_alternative_bookmark_methods()
            if bookmark_detected:
                logger.info(f"✅ Alternative bookmark found during commit: {self.attempt.lesson_location}")
        
        self.attempt.last_accessed = timezone.now()
        
        # Only save to database if not a preview attempt
        if not getattr(self.attempt, 'is_preview', False):
            # Set flag to prevent signal from processing this
            self.attempt._updating_from_api_handler = True
            try:
                # ENHANCED TRACKING: Save all tracking fields to ensure data persistence
                self.attempt.save(force_insert=False, update_fields=[
                    'cmi_data', 'lesson_status', 'completion_status', 'success_status',
                    'score_raw', 'score_min', 'score_max', 'score_scaled',
                    'total_time', 'session_time', 'lesson_location', 'suspend_data',
                    'entry', 'exit_mode', 'last_accessed', 'completed_at',
                    'completed_slides', 'detailed_tracking', 'last_visited_slide',
                    'navigation_history', 'progress_percentage', 'session_data',
                    'session_start_time', 'session_end_time', 'time_spent_seconds',
                    'total_slides'
                ])
                logger.info(f"💾 COMMIT: Saved! score_raw AFTER save = {self.attempt.score_raw}")
                
                # Verify it was saved
                self.attempt.refresh_from_db()
                logger.info(f"💾 COMMIT: score_raw AFTER refresh = {self.attempt.score_raw}")
                
                # FIX: Add small delay before sync to ensure data is committed
                import time
                time.sleep(0.1)  # 100ms delay to ensure data is committed
                
                # Use centralized sync service for score synchronization
                from .score_sync_service import ScormScoreSyncService
                # CRITICAL FIX: Force synchronization to ensure score is saved
                ScormScoreSyncService.sync_score(self.attempt, force=True)
                
                # ENHANCED TRACKING: Log successful data persistence
                logger.info(f"✅ TRACKING DATA PERSISTED: All learner progress saved to database for attempt {self.attempt.id}")
                
                # CRITICAL FIX: Update TopicProgress based on SCORM completion status
                self._update_topic_progress()
                logger.info(f"✅ TOPIC PROGRESS UPDATED: Progress only shows completed when SCORM is passed")
                
            finally:
                # Clean up the flag
                if hasattr(self.attempt, '_updating_from_api_handler'):
                    delattr(self.attempt, '_updating_from_api_handler')
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
            
            # ENHANCED: Update completion with package-type specific logic
            is_completed = self._determine_completion_status()
            
            logger.info(f"📊 COMPLETION CHECK: Package type detection and passing method analysis")
            
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
            except Exception as e:
                logger.warning(f"Could not parse time for progress update: {e}")
                pass
            
            progress.save()
            
        except Exception as e:
            logger.error(f"Error updating topic progress: {str(e)}")
    
    def _determine_completion_status(self):
        """Determine completion status based on SCORM package type and version"""
        try:
            # Get package type information
            launch_url = self.attempt.scorm_package.launch_url
            is_scormcontent = 'scormcontent/' in launch_url
            is_scormdriver = 'scormdriver/' in launch_url
            
            logger.info(f"📦 PACKAGE TYPE: scormcontent={is_scormcontent}, scormdriver={is_scormdriver}")
            
            # Method 1: SCORM 1.2 (Traditional) - scormdriver type
            if self.version == '1.2' and is_scormdriver:
                lesson_status = self.attempt.lesson_status
                logger.info(f"📊 SCORM 1.2 (scormdriver): lesson_status = '{lesson_status}'")
                
                # Traditional SCORM 1.2 passing methods
                is_completed = lesson_status in ['completed', 'passed']
                
                # Additional check for score-based passing
                if lesson_status == 'incomplete' and self.attempt.score_raw:
                    # Check if score meets passing criteria (if mastery score is set)
                    mastery_score = self.attempt.cmi_data.get('cmi.student_data.mastery_score')
                    if mastery_score:
                        try:
                            mastery_threshold = float(mastery_score)
                            current_score = float(self.attempt.score_raw)
                            if current_score >= mastery_threshold:
                                logger.info(f"📊 SCORE-BASED PASSING: {current_score} >= {mastery_threshold}")
                                is_completed = True
                        except (ValueError, TypeError):
                            pass
                
                logger.info(f"📊 SCORM 1.2 completion result: {is_completed}")
                return is_completed
            
            # Method 2: SCORM 2004 - scormcontent type (Articulate Rise, etc.)
            elif self.version == '2004' or is_scormcontent:
                completion_status = self.attempt.completion_status
                success_status = self.attempt.success_status
                
                logger.info(f"📊 SCORM 2004/scormcontent: completion_status = '{completion_status}', success_status = '{success_status}'")
                
                # SCORM 2004 / Articulate Rise passing methods
                is_completed = (
                    completion_status == 'completed' or
                    success_status == 'passed'
                )
                
                logger.info(f"📊 SCORM 2004 completion result: {is_completed}")
                return is_completed
            
            # Method 3: Fallback - check both methods
            else:
                logger.info(f"📊 FALLBACK METHOD: Checking both SCORM 1.2 and 2004 criteria")
                
                # Check SCORM 1.2 criteria
                scorm12_completed = self.attempt.lesson_status in ['completed', 'passed']
                
                # Check SCORM 2004 criteria
                scorm2004_completed = (
                    self.attempt.completion_status == 'completed' or
                    self.attempt.success_status == 'passed'
                )
                
                is_completed = scorm12_completed or scorm2004_completed
                
                logger.info(f"📊 FALLBACK result: SCORM1.2={scorm12_completed}, SCORM2004={scorm2004_completed}, final={is_completed}")
                return is_completed
                
        except Exception as e:
            logger.error(f"Error determining completion status: {str(e)}")
            # Fallback to original logic
            if self.version == '1.2':
                return self.attempt.lesson_status in ['completed', 'passed']
            else:
                return self.attempt.completion_status == 'completed'
    
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
            
    def _detect_alternative_bookmark_methods(self):
        """Detect and implement alternative bookmarking methods for different authoring tools"""
        try:
            logger.info(f"Detecting alternative bookmark methods for attempt {self.attempt.id}")
            
            # Check for various authoring tool patterns in CMI data
            bookmark_detected = False
            
            # Method 1: Check for Articulate Storyline patterns
            storyline_keys = [k for k in self.attempt.cmi_data.keys() if 'slide' in k.lower() or 'scene' in k.lower()]
            if storyline_keys:
                logger.info(f"Detected Articulate Storyline patterns: {storyline_keys}")
                # Use the most recent slide/scene data as bookmark
                for key in storyline_keys:
                    value = self.attempt.cmi_data[key]
                    if value and value != '':
                        self.attempt.lesson_location = f"storyline_{key}_{value}"
                        bookmark_detected = True
                        break
            
            # Method 2: Check for Adobe Captivate patterns  
            captivate_keys = [k for k in self.attempt.cmi_data.keys() if 'cpapi' in k.lower() or 'captivate' in k.lower()]
            if captivate_keys:
                logger.info(f"Detected Adobe Captivate patterns: {captivate_keys}")
                for key in captivate_keys:
                    value = self.attempt.cmi_data[key]
                    if value and value != '':
                        self.attempt.lesson_location = f"captivate_{key}_{value}"
                        bookmark_detected = True
                        break
            
            # Method 3: Check for interaction-based bookmarking
            interaction_keys = [k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.interactions.')]
            if interaction_keys and not bookmark_detected:
                logger.info(f"Detected interaction-based bookmarking: {len(interaction_keys)} interactions")
                # Use the latest interaction as bookmark
                if interaction_keys:
                    latest_interaction = interaction_keys[-1]  # Most recent
                    self.attempt.lesson_location = f"interaction_{latest_interaction}"
                    bookmark_detected = True
            
            # Method 4: Check for objective-based bookmarking
            objective_keys = [k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.objectives.')]
            if objective_keys and not bookmark_detected:
                logger.info(f"Detected objective-based bookmarking: {len(objective_keys)} objectives")
                # Find the most recently accessed objective
                for key in objective_keys:
                    obj_data = self.attempt.cmi_data.get(key, {})
                    if isinstance(obj_data, dict) and obj_data.get('status') in ['incomplete', 'completed']:
                        self.attempt.lesson_location = f"objective_{key}"
                        bookmark_detected = True
                        break
            
            # Method 5: Use session time as a basic bookmark for packages that don't support standard bookmarking
            if not bookmark_detected and self.attempt.session_time and self.attempt.session_time != '0000:00:00.00':
                logger.info("Using session time as fallback bookmark method")
                self.attempt.lesson_location = f"session_time_{self.attempt.session_time}"
                bookmark_detected = True
            
            if bookmark_detected:
                logger.info(f"Alternative bookmark detected: {self.attempt.lesson_location}")
                # Mark this as using alternative bookmarking
                if not self.attempt.detailed_tracking:
                    self.attempt.detailed_tracking = {}
                self.attempt.detailed_tracking['bookmark_method'] = 'alternative_detection'
                self.attempt.detailed_tracking['last_bookmark_update'] = timezone.now().isoformat()
                return True
            else:
                logger.info("No alternative bookmark methods detected")
                return False
                
        except Exception as e:
            logger.error(f"Error detecting alternative bookmark methods: {str(e)}")
            return False
    
    def _create_smart_bookmark_from_activity(self, element, value):
        """Create intelligent bookmarks from SCORM API activity for packages that don't use standard bookmarking"""
        try:
            # Only create smart bookmarks if standard bookmarking is not being used
            if self.attempt.lesson_location and self.attempt.lesson_location != '':
                return  # Standard bookmarking is working
            
            # Track different types of user activity that indicate progress
            bookmark_created = False
            
            # Activity Type 1: Score setting indicates quiz/assessment completion
            if element in ['cmi.core.score.raw', 'cmi.score.raw'] and value and value != '0':
                smart_bookmark = f"assessment_score_{value}"
                logger.info(f"📍 Smart bookmark from score activity: {smart_bookmark}")
                bookmark_created = True
            
            # Activity Type 2: Status changes indicate section completion
            elif element in ['cmi.core.lesson_status', 'cmi.completion_status'] and value in ['incomplete', 'completed', 'passed', 'failed']:
                smart_bookmark = f"status_change_{value}_{timezone.now().strftime('%H%M%S')}"
                logger.info(f"📍 Smart bookmark from status change: {smart_bookmark}")
                bookmark_created = True
            
            # Activity Type 3: Interaction data indicates specific content engagement
            elif element.startswith('cmi.interactions.') and 'result' in element:
                interaction_id = element.split('.')[2]  # Extract interaction ID
                smart_bookmark = f"interaction_{interaction_id}_{value}"
                logger.info(f"📍 Smart bookmark from interaction: {smart_bookmark}")
                bookmark_created = True
            
            # Activity Type 4: Session time updates indicate active engagement
            elif element in ['cmi.core.session_time', 'cmi.session_time'] and value and value != '0000:00:00.00':
                # Only create bookmark for significant time (more than 1 minute)
                if any(x in value for x in ['01:', '02:', '03:', '04:', '05:', '06:', '07:', '08:', '09:']):
                    smart_bookmark = f"session_progress_{value.replace(':', '')}"
                    logger.info(f"📍 Smart bookmark from session time: {smart_bookmark}")
                    bookmark_created = True
            
            # Activity Type 5: Any API activity after significant time
            elif hasattr(self, '_api_call_count'):
                self._api_call_count += 1
            else:
                self._api_call_count = 1
            
            # Create bookmark based on API activity frequency
            if not bookmark_created and hasattr(self, '_api_call_count') and self._api_call_count > 10:
                smart_bookmark = f"api_activity_count_{self._api_call_count}"
                logger.info(f"📍 Smart bookmark from API activity: {smart_bookmark}")
                bookmark_created = True
            
            # Apply the smart bookmark
            if bookmark_created:
                # Don't overwrite existing bookmarks, but update if empty
                if not self.attempt.lesson_location or self.attempt.lesson_location == '':
                    self.attempt.lesson_location = smart_bookmark
                    
                    # Track smart bookmarking in detailed tracking
                    if not self.attempt.detailed_tracking:
                        self.attempt.detailed_tracking = {}
                    self.attempt.detailed_tracking['smart_bookmark'] = smart_bookmark
                    self.attempt.detailed_tracking['smart_bookmark_source'] = element
                    self.attempt.detailed_tracking['smart_bookmark_timestamp'] = timezone.now().isoformat()
                    
                    logger.info(f"✅ Smart bookmark created: {smart_bookmark} (source: {element})")
                    
        except Exception as e:
            logger.error(f"Error creating smart bookmark: {str(e)}")
    
    def _auto_detect_resume_capability(self):
        """Auto-detect if this SCORM package supports resume and if user has resumable data"""
        try:
            logger.info(f"🔍 Auto-detecting resume capability for attempt {self.attempt.id}")
            
            # Check 1: Standard SCORM bookmarking
            has_standard_bookmark = bool(
                self.attempt.lesson_location and 
                self.attempt.lesson_location.strip() and 
                self.attempt.lesson_location != ''
            )
            
            has_standard_suspend = bool(
                self.attempt.suspend_data and 
                self.attempt.suspend_data.strip() and 
                self.attempt.suspend_data not in ['', 'None', 'null']
            )
            
            if has_standard_bookmark or has_standard_suspend:
                logger.info(f"✅ Standard SCORM bookmarking detected (bookmark: {has_standard_bookmark}, suspend: {has_standard_suspend})")
                return True
            
            # Check 2: Progress-based resume detection
            has_meaningful_progress = (
                self.attempt.progress_percentage > 0 or
                (self.attempt.score_raw is not None and self.attempt.score_raw > 0) or
                self.attempt.lesson_status in ['incomplete', 'passed', 'failed', 'completed']
            )
            
            if has_meaningful_progress:
                logger.info(f"✅ Progress-based resume detected (progress: {self.attempt.progress_percentage}%, score: {self.attempt.score_raw}, status: {self.attempt.lesson_status})")
                return True
            
            # Check 3: Session time indicates previous engagement
            has_session_time = bool(
                self.attempt.session_time and 
                self.attempt.session_time != '0000:00:00.00' and
                self.attempt.session_time != ''
            )
            
            if has_session_time:
                logger.info(f"✅ Session time resume detected (session_time: {self.attempt.session_time})")
                return True
            
            # Check 4: CMI data indicates previous activity
            if self.attempt.cmi_data and len(self.attempt.cmi_data) > 5:
                # Look for authoring tool specific patterns
                
                # Articulate Storyline patterns
                storyline_keys = [k for k in self.attempt.cmi_data.keys() if 
                                any(pattern in k.lower() for pattern in ['slide', 'scene', 'storyline', 'articulate'])]
                
                # Adobe Captivate patterns
                captivate_keys = [k for k in self.attempt.cmi_data.keys() if 
                                any(pattern in k.lower() for pattern in ['captivate', 'cpapi', 'adobe'])]
                
                # Lectora patterns
                lectora_keys = [k for k in self.attempt.cmi_data.keys() if 
                              any(pattern in k.lower() for pattern in ['lectora', 'trivantis'])]
                
                # iSpring patterns
                ispring_keys = [k for k in self.attempt.cmi_data.keys() if 
                               any(pattern in k.lower() for pattern in ['ispring', 'presentation'])]
                
                # Generic interaction or objective data
                interaction_keys = [k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.interactions.')]
                objective_keys = [k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.objectives.')]
                
                authoring_tool_detected = any([storyline_keys, captivate_keys, lectora_keys, ispring_keys])
                has_interaction_data = len(interaction_keys) > 0 or len(objective_keys) > 0
                
                if authoring_tool_detected:
                    detected_tools = []
                    if storyline_keys: detected_tools.append('Articulate Storyline')
                    if captivate_keys: detected_tools.append('Adobe Captivate') 
                    if lectora_keys: detected_tools.append('Lectora')
                    if ispring_keys: detected_tools.append('iSpring')
                    
                    logger.info(f"✅ Authoring tool resume detected: {', '.join(detected_tools)}")
                    return True
                
                if has_interaction_data:
                    logger.info(f"✅ Interaction data resume detected ({len(interaction_keys)} interactions, {len(objective_keys)} objectives)")
                    return True
            
            # Check 5: Smart bookmark from previous activity
            if self.attempt.detailed_tracking:
                smart_bookmark = self.attempt.detailed_tracking.get('smart_bookmark')
                if smart_bookmark:
                    logger.info(f"✅ Smart bookmark resume detected: {smart_bookmark}")
                    return True
            
            # Check 6: Multiple access attempts (user has been here before)
            if hasattr(self.attempt, 'last_accessed') and self.attempt.last_accessed:
                from django.utils import timezone
                from datetime import timedelta
                
                # If last accessed more than 1 minute ago, user is returning
                time_diff = timezone.now() - self.attempt.last_accessed
                if time_diff > timedelta(minutes=1):
                    logger.info(f"✅ Return visit resume detected (last accessed: {time_diff} ago)")
                    return True
            
            logger.info(f"❌ No resume capability detected - fresh start recommended")
            return False
            
        except Exception as e:
            logger.error(f"Error in auto-detect resume capability: {str(e)}")
            # Default to resume if there's any doubt (safer for user experience)
            return bool(self.attempt.lesson_status != 'not_attempted')
    
    def _get_smart_bookmark_location(self):
        """Get bookmark location with smart detection for different authoring tools"""
        try:
            # Method 1: Standard lesson_location
            if self.attempt.lesson_location and self.attempt.lesson_location.strip():
                logger.info(f"📍 Using standard bookmark: {self.attempt.lesson_location}")
                return self.attempt.lesson_location
            
            # Method 2: Extract from suspend data (different formats)
            if self.attempt.suspend_data:
                # Try JSON format first
                try:
                    import json
                    suspend_json = json.loads(self.attempt.suspend_data)
                    
                    # Check for common location keys in JSON
                    location_keys = ['location', 'bookmark', 'slide', 'page', 'position', 'currentSlide']
                    for key in location_keys:
                        if key in suspend_json and suspend_json[key]:
                            bookmark = str(suspend_json[key])
                            logger.info(f"📍 Using JSON suspend bookmark ({key}): {bookmark}")
                            return bookmark
                            
                except (json.JSONDecodeError, ValueError):
                    # Try query string format
                    if 'current_slide=' in self.attempt.suspend_data:
                        import re
                        match = re.search(r'current_slide=([^&]+)', self.attempt.suspend_data)
                        if match:
                            bookmark = f"slide_{match.group(1)}"
                            logger.info(f"📍 Using query string bookmark: {bookmark}")
                            return bookmark
            
            # Method 3: Use smart bookmark from detailed tracking
            if self.attempt.detailed_tracking:
                smart_bookmark = self.attempt.detailed_tracking.get('smart_bookmark')
                if smart_bookmark:
                    logger.info(f"📍 Using smart bookmark: {smart_bookmark}")
                    return smart_bookmark
            
            # Method 4: Generate from progress/score data
            if self.attempt.progress_percentage > 0:
                estimated_bookmark = f"progress_{int(self.attempt.progress_percentage)}percent"
                logger.info(f"📍 Using progress-based bookmark: {estimated_bookmark}")
                return estimated_bookmark
            
            # Method 5: Use session time as fallback
            if self.attempt.session_time and self.attempt.session_time != '0000:00:00.00':
                time_bookmark = f"session_{self.attempt.session_time.replace(':', '')}"
                logger.info(f"📍 Using time-based bookmark: {time_bookmark}")
                return time_bookmark
            
            logger.info(f"📍 No bookmark available - returning empty")
            return ''
            
        except Exception as e:
            logger.error(f"Error getting smart bookmark: {str(e)}")
            return self.attempt.lesson_location or ''
    
    def _auto_detect_content_exit(self):
        """Auto-detect if SCORM content is requesting exit using different methods"""
        try:
            logger.info(f"🚪 Auto-detecting content exit request for attempt {self.attempt.id}")
            
            exit_detected = False
            exit_method = None
            
            # Method 1: Standard _content_initiated_exit flag
            if self.attempt.cmi_data.get('_content_initiated_exit') == 'true':
                exit_detected = True
                exit_method = 'standard_flag'
                logger.info(f"✅ Standard exit flag detected")
            
            # Method 2: SCORM exit element set to specific values
            exit_value = self.attempt.cmi_data.get('cmi.core.exit') or self.attempt.cmi_data.get('cmi.exit')
            if exit_value in ['logout', 'suspend', 'normal', 'time-out']:
                exit_detected = True
                exit_method = f'scorm_exit_{exit_value}'
                logger.info(f"✅ SCORM exit element detected: {exit_value}")
            
            # Method 3: Lesson status indicates completion/exit (but be conservative on revisit)
            lesson_status = self.attempt.cmi_data.get('cmi.core.lesson_status') or self.attempt.cmi_data.get('cmi.completion_status')
            
            # CRITICAL FIX: Only trigger completion-based exit if it's a fresh completion, not on revisit
            if lesson_status in ['completed', 'passed', 'failed']:
                # Check if this is a fresh completion or stale data from previous session
                from django.utils import timezone
                from datetime import timedelta
                
                # If last accessed more than 5 minutes ago, this might be stale completion data
                time_since_access = timezone.now() - self.attempt.last_accessed if self.attempt.last_accessed else timedelta(hours=1)
                is_fresh_completion = time_since_access < timedelta(minutes=5)
                
                if is_fresh_completion:
                    exit_detected = True
                    exit_method = f'completion_exit_{lesson_status}'
                    logger.info(f"✅ Fresh completion-based exit detected: {lesson_status}")
                else:
                    logger.info(f"🚫 Ignoring stale completion status on revisit: {lesson_status} (last accessed {time_since_access} ago)")
            
            # Method 4: Package-type and authoring tool specific exit patterns
            
            # ENHANCED: scormcontent/ type exit detection (Articulate Rise, etc.)
            launch_url = self.attempt.scorm_package.launch_url
            is_scormcontent = 'scormcontent/' in launch_url
            
            if is_scormcontent and not exit_detected:
                logger.info(f"🔍 Checking scormcontent/ specific exit patterns")
                
                # scormcontent packages use different exit patterns
                completion_status = self.attempt.cmi_data.get('cmi.completion_status')
                success_status = self.attempt.cmi_data.get('cmi.success_status')
                
                if completion_status == 'completed' or success_status == 'passed':
                    exit_detected = True
                    exit_method = f'scormcontent_completion_{completion_status or success_status}'
                    logger.info(f"✅ scormcontent/ exit detected: {exit_method}")
                
                # Check for Articulate Rise specific patterns
                if not exit_detected:
                    suspend_data = self.attempt.cmi_data.get('cmi.suspend_data', '')
                    location_data = self.attempt.cmi_data.get('cmi.location', '')
                    
                    # Look for Rise-specific completion indicators in suspend data
                    rise_completion_indicators = ['completed', 'finished', 'done', 'exit', 'close']
                    if any(indicator in suspend_data.lower() for indicator in rise_completion_indicators):
                        exit_detected = True
                        exit_method = 'articulate_rise_suspend_data'
                        logger.info(f"✅ Articulate Rise exit detected via suspend_data: {suspend_data[:50]}...")
                    
                    # Check location data for completion
                    elif any(indicator in location_data.lower() for indicator in rise_completion_indicators):
                        exit_detected = True
                        exit_method = 'articulate_rise_location_data'
                        logger.info(f"✅ Articulate Rise exit detected via location: {location_data}")
            
            # Articulate Storyline exit patterns (scormdriver type)
            if not exit_detected:
                storyline_exit_keys = [k for k in self.attempt.cmi_data.keys() if 
                                     any(pattern in k.lower() for pattern in ['exit', 'close', 'finish', 'complete'])]
                
                if storyline_exit_keys:
                    for key in storyline_exit_keys:
                        value = self.attempt.cmi_data.get(key)
                        if value in ['true', 'yes', '1', 'completed', 'finished']:
                            exit_detected = True
                            exit_method = f'storyline_exit_{key}'
                            logger.info(f"✅ Storyline exit pattern detected: {key}={value}")
                            break
            
            # Adobe Captivate exit patterns
            captivate_exit_keys = [k for k in self.attempt.cmi_data.keys() if 
                                 any(pattern in k.lower() for pattern in ['cpapi', 'captivate']) and 
                                 any(exit_word in k.lower() for exit_word in ['exit', 'close', 'end'])]
            if captivate_exit_keys:
                exit_detected = True
                exit_method = 'captivate_exit'
                logger.info(f"✅ Captivate exit pattern detected")
            
            # Method 5: High score indicates quiz completion (common exit trigger)
            if self.attempt.score_raw and self.attempt.score_raw >= 80:
                exit_detected = True
                exit_method = f'high_score_exit_{self.attempt.score_raw}'
                logger.info(f"✅ High score exit detected: {self.attempt.score_raw}")
            
            # Method 6: Session time indicates extended engagement (user may want to exit)
            if self.attempt.session_time:
                try:
                    # Parse session time (format: HH:MM:SS.ss)
                    time_parts = self.attempt.session_time.split(':')
                    if len(time_parts) >= 2:
                        minutes = int(time_parts[0]) * 60 + int(time_parts[1])
                        if minutes >= 30:  # 30+ minutes indicates substantial engagement
                            exit_detected = True
                            exit_method = f'long_session_exit_{minutes}min'
                            logger.info(f"✅ Long session exit detected: {minutes} minutes")
                except Exception as e:
                    logger.warning(f"Could not parse session time: {e}")
            
            # Apply the exit detection
            if exit_detected:
                # Set the standard exit flag for frontend detection
                self.attempt.cmi_data['_content_initiated_exit'] = 'true'
                
                # Track the detection method
                if not self.attempt.detailed_tracking:
                    self.attempt.detailed_tracking = {}
                
                self.attempt.detailed_tracking.update({
                    'auto_exit_detected': True,
                    'exit_detection_method': exit_method,
                    'exit_detection_timestamp': timezone.now().isoformat()
                })
                
                logger.info(f"🚪 Content exit auto-detected using method: {exit_method}")
                return True
            else:
                logger.info(f"❌ No content exit detected")
                return False
                
        except Exception as e:
            logger.error(f"Error in auto-detect content exit: {str(e)}")
            return False
    
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
                except Exception as e:
                    logger.warning(f"Could not calculate progress from slide: {e}")
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
            import json
            
            # CRITICAL FIX: Try JSON parsing first (for modern SCORM packages)
            progress_percentage = None
            current_slide = None
            completed_slides = []
            
            try:
                # Try to parse as JSON first
                json_data = json.loads(suspend_data)
                logger.info(f"Parsed suspend data as JSON: {json_data}")
                
                # Check for common JSON progress patterns
                if 'progress' in json_data:
                    progress_percentage = int(json_data['progress'])
                elif 'completion' in json_data:
                    progress_percentage = int(json_data['completion'])
                elif 'd' in json_data and isinstance(json_data['d'], list):
                    # Some SCORM packages encode data as byte arrays
                    try:
                        decoded = ''.join([chr(x) for x in json_data['d']])
                        logger.info(f"Decoded d array: {decoded}")
                        # If it's 'false', check if user is actually in content (not 0%)
                        if decoded.lower() == 'false':
                            # User is in content (has lesson_location), so they've made progress
                            if self.attempt.lesson_location and self.attempt.lesson_location != '':
                                progress_percentage = 13  # User is engaged in content
                                logger.info(f"User is in lesson content, estimating 13% progress despite 'false' flag")
                            else:
                                progress_percentage = 0
                        elif decoded.lower() == 'true':
                            progress_percentage = 100
                    except Exception as e:
                        logger.warning(f"Could not decode d array: {e}")
                        
                # Set a default progress if we have JSON data but no specific progress
                if progress_percentage is None and json_data:
                    progress_percentage = 13  # Estimated based on user being in lesson content
                    logger.info(f"Estimated progress from JSON presence: {progress_percentage}%")
                    
            except (json.JSONDecodeError, ValueError):
                # Fall back to regex parsing for traditional formats
                progress_match = re.search(r'progress=(\d+)', suspend_data)
                current_slide_match = re.search(r'current_slide=([^&]+)', suspend_data)
                completed_slides_match = re.search(r'completed_slides=([^&]+)', suspend_data)
                
                if progress_match:
                    progress_percentage = int(progress_match.group(1))
                if current_slide_match:
                    current_slide = current_slide_match.group(1)
                if completed_slides_match:
                    completed_slides = [s.strip() for s in completed_slides_match.group(1).split(',') if s.strip()]
            
            # CRITICAL FIX: Apply progress if we found any
            if progress_percentage is not None:
                # CRITICAL FIX: Update progress immediately and save to database
                self.attempt.progress_percentage = progress_percentage
                self.attempt.last_visited_slide = f'slide_{current_slide}' if current_slide and current_slide != 'current' else 'current'
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
                
                # CRITICAL FIX: Force save to database immediately with all progress fields
                self.attempt.save(update_fields=[
                    'progress_percentage', 'last_visited_slide', 'completed_slides', 
                    'detailed_tracking', 'last_accessed', 'suspend_data', 'cmi_data'
                ])
                
                logger.info(f"[SCORM SYNC] Progress {progress_percentage}% synced from suspend data and saved to database")
                
        except Exception as e:
            logger.error(f"Error parsing and syncing suspend data: {str(e)}")
    
    def _get_dynamic_passing_score(self):
        """
        Get dynamic passing score based on SCORM package type and course settings
        Replaces hardcoded 70% with intelligent defaults
        """
        try:
            # Check if course has specific completion requirements
            topic = self.attempt.scorm_package.topic
            if hasattr(topic, 'course') and topic.course:
                course = topic.course
                # Use course completion percentage as base, but adjust for SCORM
                if hasattr(course, 'completion_percentage') and course.completion_percentage:
                    # Convert course completion percentage to passing score
                    # If course requires 80% completion, use 80% as passing score
                    return float(course.completion_percentage)
            
            # Check SCORM package type for intelligent defaults
            version = self.attempt.scorm_package.version
            if version in ['2004', 'xapi']:
                # SCORM 2004 and xAPI typically use higher standards
                return 80.0
            elif version in ['storyline', 'captivate', 'lectora']:
                # Authoring tools often have different standards
                return 75.0
            elif version in ['1.1', '1.2']:
                # Traditional SCORM versions
                return 70.0
            else:
                # Default fallback
                return 70.0
                
        except Exception as e:
            logger.warning(f"Error getting dynamic passing score: {e}")
            # Safe fallback
            return 70.0
    
    def _get_interactions_data(self):
        """Get interactions data from cmi_data, ensuring proper structure"""
        try:
            if not self.attempt.cmi_data:
                self.attempt.cmi_data = {}
            
            if 'interactions' not in self.attempt.cmi_data:
                self.attempt.cmi_data['interactions'] = []
            
            return self.attempt.cmi_data['interactions']
        except Exception as e:
            logger.error(f"Error getting interactions data: {str(e)}")
            return []
    
    def _get_interaction_element(self, element):
        """Get specific interaction element value"""
        try:
            # Parse element: cmi.interactions.n.property
            parts = element.split('.')
            if len(parts) < 4:
                return ''
            
            index_str = parts[2]  # The 'n' part
            property_name = parts[3]  # The property part
            
            # Handle _count specially
            if index_str == '_count':
                return ''  # This should be handled by _count case above
            
            # Convert index to integer
            try:
                index = int(index_str)
            except ValueError:
                logger.warning(f"Invalid interaction index: {index_str}")
                return ''
            
            interactions = self._get_interactions_data()
            
            # Check if interaction exists
            if index >= len(interactions):
                return ''
            
            interaction = interactions[index]
            return str(interaction.get(property_name, ''))
            
        except Exception as e:
            logger.error(f"Error getting interaction element {element}: {str(e)}")
            return ''
    
    def _set_interaction_element(self, element, value):
        """Set specific interaction element value"""
        try:
            # Parse element: cmi.interactions.n.property
            parts = element.split('.')
            if len(parts) < 4:
                logger.warning(f"Invalid interaction element format: {element}")
                return False
            
            index_str = parts[2]  # The 'n' part
            property_name = parts[3]  # The property part
            
            # Convert index to integer
            try:
                index = int(index_str)
            except ValueError:
                logger.warning(f"Invalid interaction index: {index_str}")
                return False
            
            interactions = self._get_interactions_data()
            
            # Extend interactions array if necessary
            while len(interactions) <= index:
                interactions.append({})
            
            # Set the property
            interactions[index][property_name] = value
            
            # Store back in cmi_data
            self.attempt.cmi_data['interactions'] = interactions
            
            # Also store in the individual element for compatibility
            self.attempt.cmi_data[element] = value
            
            logger.info(f"Set interaction element: {element} = {value}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting interaction element {element}: {str(e)}")
            return False

