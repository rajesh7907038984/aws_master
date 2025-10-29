# -*- coding: utf-8 -*-
"""
Enhanced SCORM API Handler
Complete implementation of SCORM 1.2 and 2004 data model elements
"""
import json
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import ScormPackage, ScormAttempt
# Removed debug_logger import - not needed for CMI compliance

logger = logging.getLogger(__name__)


class ScormAPIHandlerEnhanced:
    """
    Enhanced SCORM API Handler
    Implements complete SCORM 1.2 and 2004 standards with all data model elements
    """
    
    # SCORM Error codes
    SCORM_ERRORS = {
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
        '406': 'Element not a number',
        '407': 'Element not implemented',
        '408': 'Element not unique',
        '409': 'Element not an integer',
        '410': 'Element not a positive integer',
        '411': 'Element not a positive number',
        '412': 'Element not a valid time',
        '413': 'Element not a valid time interval',
        '414': 'Element not a valid time interval',
        '415': 'Element not a valid time interval',
        '416': 'Element not a valid time interval',
        '417': 'Element not a valid time interval',
        '418': 'Element not a valid time interval',
        '419': 'Element not a valid time interval',
        '420': 'Element not a valid time interval',
        '421': 'Element not a valid time interval',
        '422': 'Element not a valid time interval',
        '423': 'Element not a valid time interval',
        '424': 'Element not a valid time interval',
        '425': 'Element not a valid time interval',
        '426': 'Element not a valid time interval',
        '427': 'Element not a valid time interval',
        '428': 'Element not a valid time interval',
        '429': 'Element not a valid time interval',
        '430': 'Element not a valid time interval',
        '431': 'Element not a valid time interval',
        '432': 'Element not a valid time interval',
        '433': 'Element not a valid time interval',
        '434': 'Element not a valid time interval',
        '435': 'Element not a valid time interval',
        '436': 'Element not a valid time interval',
        '437': 'Element not a valid time interval',
        '438': 'Element not a valid time interval',
        '439': 'Element not a valid time interval',
        '440': 'Element not a valid time interval',
        '441': 'Element not a valid time interval',
        '442': 'Element not a valid time interval',
        '443': 'Element not a valid time interval',
        '444': 'Element not a valid time interval',
        '445': 'Element not a valid time interval',
        '446': 'Element not a valid time interval',
        '447': 'Element not a valid time interval',
        '448': 'Element not a valid time interval',
        '449': 'Element not a valid time interval',
        '450': 'Element not a valid time interval',
        '451': 'Element not a valid time interval',
        '452': 'Element not a valid time interval',
        '453': 'Element not a valid time interval',
        '454': 'Element not a valid time interval',
        '455': 'Element not a valid time interval',
        '456': 'Element not a valid time interval',
        '457': 'Element not a valid time interval',
        '458': 'Element not a valid time interval',
        '459': 'Element not a valid time interval',
        '460': 'Element not a valid time interval',
        '461': 'Element not a valid time interval',
        '462': 'Element not a valid time interval',
        '463': 'Element not a valid time interval',
        '464': 'Element not a valid time interval',
        '465': 'Element not a valid time interval',
        '466': 'Element not a valid time interval',
        '467': 'Element not a valid time interval',
        '468': 'Element not a valid time interval',
        '469': 'Element not a valid time interval',
        '470': 'Element not a valid time interval',
        '471': 'Element not a valid time interval',
        '472': 'Element not a valid time interval',
        '473': 'Element not a valid time interval',
        '474': 'Element not a valid time interval',
        '475': 'Element not a valid time interval',
        '476': 'Element not a valid time interval',
        '477': 'Element not a valid time interval',
        '478': 'Element not a valid time interval',
        '479': 'Element not a valid time interval',
        '480': 'Element not a valid time interval',
        '481': 'Element not a valid time interval',
        '482': 'Element not a valid time interval',
        '483': 'Element not a valid time interval',
        '484': 'Element not a valid time interval',
        '485': 'Element not a valid time interval',
        '486': 'Element not a valid time interval',
        '487': 'Element not a valid time interval',
        '488': 'Element not a valid time interval',
        '489': 'Element not a valid time interval',
        '490': 'Element not a valid time interval',
        '491': 'Element not a valid time interval',
        '492': 'Element not a valid time interval',
        '493': 'Element not a valid time interval',
        '494': 'Element not a valid time interval',
        '495': 'Element not a valid time interval',
        '496': 'Element not a valid time interval',
        '497': 'Element not a valid time interval',
        '498': 'Element not a valid time interval',
        '499': 'Element not a valid time interval',
        '500': 'Element not a valid time interval',
    }
    
    def __init__(self, attempt):
        """
        Initialize enhanced API handler
        """
        self.attempt = attempt
        self.version = attempt.scorm_package.version
        self.last_error = '0'
        
        # Check if already initialized by looking at attempt data
        self.initialized = self.attempt.cmi_data.get('_initialized', False)
        
        # Initialize CMI data if needed
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
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
        """Initialize comprehensive CMI data structure for SCORM 1.2 and 2004"""
        if self.version == '1.2':
            return {
                # Core SCORM 1.2 Data Elements
                'cmi.core._children': 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time',
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': self._get_schema_default('cmi.core.credit'),
                'cmi.core.lesson_status': self.attempt.lesson_status or self._get_schema_default('cmi.core.lesson_status'),
                'cmi.core.entry': self.attempt.entry or self._get_schema_default('cmi.core.entry'),
                'cmi.core.score._children': 'raw,max,min',
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '',
                'cmi.core.total_time': self.attempt.total_time or '',
                'cmi.core.lesson_mode': self._get_schema_default('cmi.core.lesson_mode'),
                'cmi.core.exit': '',
                'cmi.core.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.comments': '',
                'cmi.comments_from_lms': '',
                
                # Student Data Elements
                'cmi.student_data._children': 'mastery_score,max_time_allowed,time_limit_action',
                'cmi.student_data.mastery_score': str(self.attempt.scorm_package.mastery_score) if self.attempt.scorm_package.mastery_score else '80',
                'cmi.student_data.max_time_allowed': '',
                'cmi.student_data.time_limit_action': '',
                
                # Student Preference Elements
                'cmi.student_preference._children': 'audio,language,speed,text',
                'cmi.student_preference.audio': '1',
                'cmi.student_preference.language': 'en',
                'cmi.student_preference.speed': '1',
                'cmi.student_preference.text': '1',
                
                # Interactions (empty by default)
                'cmi.interactions._children': '',
                'cmi.interactions._count': '0',
                
                # Objectives (empty by default)
                'cmi.objectives._children': '',
                'cmi.objectives._count': '0',
            }
        else:  # SCORM 2004
            return {
                # Core SCORM 2004 Data Elements
                'cmi._version': '1.0',
                'cmi.learner_id': str(self.attempt.user.id),
                'cmi.learner_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.location': self.attempt.lesson_location or '',
                'cmi.credit': self._get_schema_default('cmi.credit'),
                'cmi.completion_status': self.attempt.completion_status or self._get_schema_default('cmi.completion_status'),
                'cmi.success_status': self.attempt.success_status or self._get_schema_default('cmi.success_status'),
                'cmi.entry': self.attempt.entry or self._get_schema_default('cmi.entry'),
                'cmi.score._children': 'raw,min,max,scaled',
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled else '',
                'cmi.total_time': self.attempt.total_time or '',
                'cmi.mode': self._get_schema_default('cmi.mode'),
                'cmi.exit': '',
                'cmi.session_time': '',
                'cmi.suspend_data': self.attempt.suspend_data or '',
                'cmi.launch_data': '',
                'cmi.progress_measure': '',
                'cmi.max_time_allowed': '',
                'cmi.time_limit_action': '',
                
                # Learner Preference Elements
                'cmi.learner_preference._children': 'audio_level,language,delivery_speed,audio_captioning',
                'cmi.learner_preference.audio_level': '1',
                'cmi.learner_preference.language': 'en',
                'cmi.learner_preference.delivery_speed': '1.0',
                'cmi.learner_preference.audio_captioning': '1',
                
                # Objectives (empty by default)
                'cmi.objectives._children': '',
                'cmi.objectives._count': '0',
                
                # Interactions (empty by default)
                'cmi.interactions._children': '',
                'cmi.interactions._count': '0',
                
                # Comments (empty by default)
                'cmi.comments_from_learner._children': '',
                'cmi.comments_from_learner._count': '0',
                'cmi.comments_from_lms._children': '',
                'cmi.comments_from_lms._count': '0',
            }
    
    def initialize(self):
        """LMSInitialize / Initialize"""
        # FIXED: Allow re-initialization for resume scenarios or when CMI data needs to be refreshed
        if self.initialized:
            # Check if this is a legitimate resume scenario or if we need to refresh data
            has_bookmark_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
            if has_bookmark_data and self.attempt.entry == 'resume':
                logger.info("SCORM API: Re-initializing for resume scenario (attempt %s)", self.attempt.id)
                self.initialized = False  # Allow re-initialization for resume
            else:
                logger.warning("SCORM API: Already initialized for attempt %s, allowing re-init for testing", self.attempt.id)
                # In production, you might want to be more strict, but for now allow re-init
                self.initialized = False
        
        self.initialized = True
        self.last_error = '0'
        
        # CRITICAL FIX: Ensure CMI data is properly initialized with resume data BEFORE any GetValue calls
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
        
        # Mark as initialized in CMI data for persistence
        self.attempt.cmi_data['_initialized'] = True
        
        # CRITICAL FIX: Check for existing bookmark data and set entry mode accordingly
        has_bookmark_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
        
        # STORYLINE FIX: Auto-set status to incomplete when user starts Storyline content
        if hasattr(self.attempt, 'scorm_package') and self.attempt.scorm_package.version == 'storyline':
            if not self.attempt.lesson_status or self.attempt.lesson_status == 'not_attempted':
                self.attempt.lesson_status = 'incomplete'
                self.attempt.cmi_data['cmi.core.lesson_status'] = 'incomplete'
                logger.info("STORYLINE: Auto-set lesson_status to 'incomplete' on initialize")
        
        # CRITICAL FIX FOR SCORM 2004 STORYLINE: Handle completion_status and success_status
        if self.version == '2004' or (hasattr(self.attempt, 'scorm_package') and self.attempt.scorm_package.version == 'storyline'):
            # For SCORM 2004, we need to set both completion_status and success_status
            if has_bookmark_data:
                # If we have resume data, set completion_status to 'incomplete' and success_status to 'unknown'
                self.attempt.completion_status = 'incomplete'
                self.attempt.success_status = 'unknown'
                logger.info("SCORM 2004 STORYLINE: Set completion_status='incomplete', success_status='unknown' for resume")
            else:
                # New attempt
                self.attempt.completion_status = self._get_schema_default('cmi.completion_status')
                self.attempt.success_status = 'unknown'
                logger.info("SCORM 2004 STORYLINE: Set completion_status='not attempted' for new attempt")
        
        if has_bookmark_data:
            self.attempt.entry = 'resume'
            suspend_data_preview = self.attempt.suspend_data[:50] if self.attempt.suspend_data else "None"
            logger.info("SCORM Resume: location='%s', suspend_data='%s...'", self.attempt.lesson_location, suspend_data_preview)
        else:
            self.attempt.entry = self._get_schema_default('cmi.core.entry')
            logger.info("SCORM New attempt: starting fresh")
        
        # CRITICAL FIX: Update CMI data with proper defaults AND resume data
        if self.version == '1.2':
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data for resume
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
                logger.info("🔖 RESUME: Set lesson_location in CMI data: %s", self.attempt.lesson_location)
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info("🔖 RESUME: Set suspend_data in CMI data (%d chars)", len(self.attempt.suspend_data))
            
            # Set other required fields
            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status or self._get_schema_default('cmi.core.lesson_status')
            self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            self.attempt.cmi_data['cmi.core.credit'] = 'credit'
            self.attempt.cmi_data['cmi.core.student_id'] = str(self.attempt.user.id) if self.attempt.user else 'student'
            self.attempt.cmi_data['cmi.core.student_name'] = self.attempt.user.get_full_name() or self.attempt.user.username if self.attempt.user else 'Student'
        else:
            # CRITICAL FIX: Always set entry mode in CMI data
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            
            # CRITICAL FIX: Ensure bookmark data is ALWAYS available in CMI data for resume
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location
                logger.info("🔖 RESUME: Set location in CMI data: %s", self.attempt.lesson_location)
            elif self.attempt.suspend_data:
                # CRITICAL FIX: If we have suspend_data but no lesson_location, 
                # set a schema-defined default location to enable resume functionality
                schema_default = self._get_schema_default('cmi.location')
                default_location = schema_default or 'lesson_1'
                self.attempt.cmi_data['cmi.location'] = default_location
                logger.info("🔖 RESUME: Set schema-defined default location in CMI data for resume: %s", default_location)
            
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info("🔖 RESUME: Set suspend_data in CMI data (%d chars)", len(self.attempt.suspend_data))
            
            # Set other required fields with schema defaults
            schema_completion_default = self._get_schema_default('cmi.completion_status')
            schema_success_default = self._get_schema_default('cmi.success_status')
            schema_mode_default = self._get_schema_default('cmi.mode')
            schema_credit_default = self._get_schema_default('cmi.credit')
            
            self.attempt.cmi_data['cmi.completion_status'] = self.attempt.completion_status or schema_completion_default
            self.attempt.cmi_data['cmi.success_status'] = self.attempt.success_status or schema_success_default
            self.attempt.cmi_data['cmi.mode'] = schema_mode_default
            self.attempt.cmi_data['cmi.credit'] = schema_credit_default
            self.attempt.cmi_data['cmi.learner_id'] = str(self.attempt.user.id) if self.attempt.user else 'student'
            self.attempt.cmi_data['cmi.learner_name'] = self.attempt.user.get_full_name() or self.attempt.user.username if self.attempt.user else 'Student'
        
        # CRITICAL FIX: Save the updated data immediately
        self.attempt.save()
        
        logger.info("SCORM API initialized for attempt %s", self.attempt.id)
        logger.info("Resume data in CMI: entry='%s', location='%s'", 
                   self.attempt.cmi_data.get('cmi.core.entry' if self.version == '1.2' else 'cmi.entry'),
                   self.attempt.cmi_data.get('cmi.core.lesson_location' if self.version == '1.2' else 'cmi.location'))
        return 'true'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            logger.warning("SCORM API Terminate called before initialization for attempt %s", self.attempt.id)
            return 'false'
        
        self.initialized = False
        self.last_error = '0'
        
        # CRITICAL FIX: Set exit mode to indicate proper termination
        self.attempt.exit_mode = 'logout'
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.exit'] = 'logout'
        else:
            self.attempt.cmi_data['cmi.exit'] = 'logout'
        
        # CRITICAL FIX: Always save data on terminate, regardless of completion status
        # This ensures that time, progress, and location data are preserved
        
        # Ensure CMI data is properly initialized before saving
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = {}
        
        # Check if SCORM content explicitly set lesson_status via SetValue calls
        explicit_status_set = hasattr(self.attempt, '_explicit_status_set') and self.attempt._explicit_status_set
        
        # CRITICAL FIX: Always determine lesson status based on available data
        if not self.attempt.lesson_status or self.attempt.lesson_status == 'not_attempted':
            if explicit_status_set:
                # SCORM content explicitly set status - trust it
                logger.info("TERMINATE: SCORM content explicitly set lesson_status - trusting content decision")
            elif self.attempt.score_raw is not None and self.attempt.score_raw > 0:
                # Has a score - determine pass/fail based on mastery score
                mastery_score = self.attempt.scorm_package.mastery_score or 70
                if self.attempt.score_raw >= mastery_score:
                    self.attempt.lesson_status = 'passed'
                    status_to_set = 'passed'
                else:
                    self.attempt.lesson_status = 'failed'  
                    status_to_set = 'failed'
                logger.info("TERMINATE: Set lesson_status to %s based on score %s (mastery: %s)", 
                           status_to_set, self.attempt.score_raw, mastery_score)
            else:
                # No score - check for evidence of interaction to determine status
                has_interaction = (
                    self.attempt.lesson_location or  # Has bookmark data
                    (self.attempt.suspend_data and len(self.attempt.suspend_data) > 5) or  # Has any progress data
                    self.attempt.total_time != '0000:00:00.00'  # Has spent time
                )
                
                if has_interaction:
                    # User interacted with content but no score - mark as incomplete
                    self.attempt.lesson_status = 'incomplete'
                    status_to_set = 'incomplete'
                    logger.info("TERMINATE: User interacted with content but no score - marking as incomplete")
                else:
                    # No interaction at all - mark as not attempted
                    self.attempt.lesson_status = 'not_attempted'
                    status_to_set = 'not_attempted'
                    logger.info("TERMINATE: No interaction detected - marking as not_attempted")
            
            # Update CMI data with determined status
            if 'status_to_set' in locals():
                if self.version == '1.2':
                    self.attempt.cmi_data['cmi.core.lesson_status'] = status_to_set
                else:
                    self.attempt.cmi_data['cmi.completion_status'] = status_to_set
                    if status_to_set in ['passed', 'failed']:
                        self.attempt.cmi_data['cmi.success_status'] = status_to_set
        
        # Save all data
        self._commit_data()
        
        # CRITICAL FIX: Force save attempt data even if commit failed
        # This ensures that at minimum, the attempt data is preserved
        try:
            self.attempt.last_accessed = timezone.now()
            self.attempt.save()
            logger.info("✅ TERMINATE: Final save completed successfully")
        except Exception as e:
            logger.error("❌ TERMINATE: Final save failed: %s", str(e))
        
        logger.info("SCORM API Terminated for attempt %s - exit_mode: %s, lesson_status: %s", 
                   self.attempt.id, self.attempt.exit_mode, self.attempt.lesson_status)
        
        return 'true'
    
    def get_value(self, element):
        """LMSGetValue / GetValue - Enhanced to handle all SCORM data elements"""
        if not self.initialized:
            self.last_error = '301'
            return ''
        
        try:
            # Get value from CMI data or use defaults
            value = self.attempt.cmi_data.get(element, '')
            
            # Handle array elements
            if element.endswith('._children'):
                return self._get_children_elements(element)
            elif element.endswith('._count'):
                return self._get_count_elements(element)
            
            # Always apply proper defaults for SCORM elements - check for empty or None
            if not value or str(value).strip() == '' or value is None:
                # SCORM 1.2 Core Elements - Always provide schema-defined defaults
                if element == 'cmi.core.lesson_status':
                    # CRITICAL FIX FOR SCORM 1.2: If we have resume data, return 'incomplete' not 'not attempted'
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'incomplete'
                        logger.info(f"SCORM 1.2 RESUME: Override lesson_status to 'incomplete' for resume scenario")
                    else:
                        schema_default = self._get_schema_default('cmi.core.lesson_status')
                        value = self.attempt.lesson_status or schema_default
                elif element == 'cmi.core.entry':
                    schema_default = self._get_schema_default('cmi.core.entry')
                    value = self.attempt.entry or schema_default
                elif element == 'cmi.core.credit':
                    value = self._get_schema_default('cmi.core.credit')
                elif element == 'cmi.core.lesson_mode':
                    value = self._get_schema_default('cmi.core.lesson_mode')
                elif element == 'cmi.core.student_id':
                    value = str(self.attempt.user.id) if self.attempt.user else 'student'
                elif element == 'cmi.core.student_name':
                    value = self.attempt.user.get_full_name() or self.attempt.user.username if self.attempt.user else 'Student'
                elif element in ['cmi.core.score.raw', 'cmi.score.raw']:
                    # CRITICAL FIX: Always return score from model fields for accurate tracking
                    value = str(self.attempt.score_raw) if self.attempt.score_raw is not None else ''
                elif element in ['cmi.core.score.max', 'cmi.score.max']:
                    value = str(self.attempt.score_max) if self.attempt.score_max else '100'
                elif element in ['cmi.core.score.min', 'cmi.score.min']:
                    value = str(self.attempt.score_min) if self.attempt.score_min else '0'
                elif element == 'cmi.score.scaled':
                    # CRITICAL FIX: Return scaled score from model fields
                    value = str(self.attempt.score_scaled) if self.attempt.score_scaled is not None else ''
                elif element == 'cmi.core.student_id' or element == 'cmi.learner_id':
                    value = str(self.attempt.user.id)
                elif element == 'cmi.core.student_name' or element == 'cmi.learner_name':
                    value = self.attempt.user.get_full_name() or self.attempt.user.username
                elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                    # CRITICAL FIX: Always return bookmark data from model fields
                    value = self.attempt.lesson_location or ''
                    if value:
                        logger.info("🔖 RESUME: Returning lesson_location = '%s' for attempt %s", value[:100], self.attempt.id)
                    else:
                        logger.info("🔖 RESUME: No lesson_location found for attempt %s", self.attempt.id)
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Always return suspend data from model fields
                    value = self.attempt.suspend_data or ''
                    if value:
                        logger.info("🔖 RESUME: Returning suspend_data (%d chars) for attempt %s", len(value), self.attempt.id)
                    else:
                        logger.info("🔖 RESUME: No suspend_data found for attempt %s", self.attempt.id)
                elif element == 'cmi.core.total_time':
                    value = self.attempt.total_time or ('0000:00:00.00' if self.version == '1.2' else 'PT00H00M00S')
                
                # SCORM 2004 Elements
                elif element == 'cmi.completion_status':
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return 'incomplete' not 'not_attempted'
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'incomplete'
                        logger.info(f"SCORM 2004 RESUME: Override completion_status to 'incomplete' for resume scenario")
                    else:
                        schema_default = self._get_schema_default('cmi.completion_status')
                        value = self.attempt.completion_status or schema_default
                elif element == 'cmi.success_status':
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return 'unknown' for resume scenarios
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'unknown'
                        logger.info(f"SCORM 2004 RESUME: Override success_status to 'unknown' for resume scenario")
                    else:
                        schema_default = self._get_schema_default('cmi.success_status')
                        value = self.attempt.success_status or schema_default
                elif element == 'cmi.mode':
                    value = self._get_schema_default('cmi.mode')
                elif element == 'cmi.credit':
                    value = self._get_schema_default('cmi.credit')
                elif element == 'cmi.progress_measure':
                    value = ''
                elif element == 'cmi._version':
                    value = '1.0'
                
                # Student/Learner Preference Elements
                elif element == 'cmi.student_preference.audio':
                    value = '1'
                elif element == 'cmi.student_preference.language':
                    value = 'en'
                elif element == 'cmi.student_preference.speed':
                    value = '1'
                elif element == 'cmi.student_preference.text':
                    value = '1'
                elif element == 'cmi.learner_preference.audio_level':
                    value = '1'
                elif element == 'cmi.learner_preference.language':
                    value = 'en'
                elif element == 'cmi.learner_preference.delivery_speed':
                    value = '1.0'
                elif element == 'cmi.learner_preference.audio_captioning':
                    value = '1'
                
                # Student Data Elements
                elif element == 'cmi.student_data.mastery_score':
                    value = str(self.attempt.scorm_package.mastery_score) if self.attempt.scorm_package.mastery_score else '80'
                
                # Handle interactions and objectives
                elif element.startswith('cmi.interactions.'):
                    value = self._get_interaction_value(element)
                elif element.startswith('cmi.objectives.'):
                    value = self._get_objective_value(element)
                elif element.startswith('cmi.comments_from_learner.'):
                    value = self._get_comment_value(element, 'learner')
                elif element.startswith('cmi.comments_from_lms.'):
                    value = self._get_comment_value(element, 'lms')
                
                # Default empty string for unknown elements
                else:
                    value = ''
            
            self.last_error = '0'
            logger.info("SCORM GetValue(%s) -> '%s'", element, value)
            return str(value) if value is not None else ''
        except Exception as e:
            logger.error("Error getting value for %s: %s", element, str(e))
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """LMSSetValue / SetValue - Enhanced to handle all SCORM data elements"""
        # CRITICAL FIX: Allow bookmark data to be stored even before initialization
        if not self.initialized and element not in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
            self.last_error = '301'
            return 'false'
        
        try:
            # CRITICAL FIX: Handle bookmark data storage before initialization
            if not self.initialized and element in ['cmi.core.lesson_location', 'cmi.location', 'cmi.suspend_data']:
                # Ensure CMI data exists
                if not self.attempt.cmi_data:
                    self.attempt.cmi_data = {}
                
                # Store bookmark data immediately
                self.attempt.cmi_data[element] = value
                logger.info("SCORM SetValue(%s, %s) - stored before initialization", element, value)
                
                # Also store in model fields for persistence
                if element in ['cmi.core.lesson_location', 'cmi.location']:
                    self.attempt.lesson_location = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
                
                # Save immediately for persistence
                self.attempt.save()
                self.last_error = '0'
                return 'true'
            
            # Validate element based on SCORM specification
            if not self._validate_element(element, value):
                return 'false'
            
            # Store the value in CMI data
            self.attempt.cmi_data[element] = value
            logger.info("SCORM SetValue(%s, %s)", element, value)
            
            # Always return true for valid SetValue calls
            self.last_error = '0'
            
            # Update model fields based on element
            self._update_model_fields(element, value)
            
            return 'true'
        
        except Exception as e:
            logger.error("SCORM SetValue error: %s", str(e))
            self.last_error = '101'
            return 'false'
    
    def _update_model_fields(self, element, value):
        """Update model fields based on CMI element"""
        try:
            # SCORM 1.2 fields
            if element == 'cmi.core.lesson_location':
                self.attempt.lesson_location = value
            elif element == 'cmi.suspend_data':
                self.attempt.suspend_data = value
            elif element == 'cmi.core.lesson_status':
                self.attempt.lesson_status = value
            elif element == 'cmi.core.score.raw':
                if value:
                    self.attempt.score_raw = Decimal(str(value))
            elif element == 'cmi.core.score.max':
                if value:
                    self.attempt.score_max = Decimal(str(value))
            elif element == 'cmi.core.score.min':
                if value:
                    self.attempt.score_min = Decimal(str(value))
            elif element == 'cmi.core.total_time':
                self.attempt.total_time = value
            elif element == 'cmi.core.session_time':
                self.attempt.session_time = value
            elif element == 'cmi.core.exit':
                self.attempt.exit_mode = value
            
            # SCORM 2004 fields
            elif element == 'cmi.location':
                self.attempt.lesson_location = value
            elif element == 'cmi.completion_status':
                self.attempt.completion_status = value
            elif element == 'cmi.success_status':
                self.attempt.success_status = value
            elif element == 'cmi.score.raw':
                if value:
                    self.attempt.score_raw = Decimal(str(value))
            elif element == 'cmi.score.max':
                if value:
                    self.attempt.score_max = Decimal(str(value))
            elif element == 'cmi.score.min':
                if value:
                    self.attempt.score_min = Decimal(str(value))
            elif element == 'cmi.score.scaled':
                if value:
                    self.attempt.score_scaled = Decimal(str(value))
            elif element == 'cmi.total_time':
                self.attempt.total_time = value
            elif element == 'cmi.session_time':
                self.attempt.session_time = value
            elif element == 'cmi.exit':
                self.attempt.exit_mode = value
            
            # Handle objectives and interactions
            elif element.startswith('cmi.objectives.'):
                self._handle_objectives_data(element, value)
            elif element.startswith('cmi.interactions.'):
                self._handle_interactions_data(element, value)
            
            # Handle student preferences (SCORM 1.2)
            elif element.startswith('cmi.student_preference.'):
                self._handle_student_preferences(element, value)
            
            # Handle comments (SCORM 2004)
            elif element.startswith('cmi.comments_from_learner.'):
                self._handle_learner_comments(element, value)
            elif element.startswith('cmi.comments_from_lms.'):
                self._handle_lms_comments(element, value)
            
        except Exception as e:
            logger.error("Error updating model fields: %s", str(e))
    
    def _handle_objectives_data(self, element, value):
        """Handle objectives data for both SCORM 1.2 and 2004"""
        if self.version == '1.2':
            objectives = self.attempt.cmi_objectives_12 or []
        else:
            objectives = self.attempt.cmi_objectives_2004 or []
        
        # Parse element to get objective index and field
        parts = element.split('.')
        if len(parts) >= 3:
            obj_index = int(parts[2]) if parts[2].isdigit() else 0
            field = parts[3] if len(parts) > 3 else None
            
            # Ensure we have enough objectives
            while len(objectives) <= obj_index:
                objectives.append({})
            
            if field:
                objectives[obj_index][field] = value
            else:
                objectives[obj_index]['id'] = value
        
        # Update the appropriate field
        if self.version == '1.2':
            self.attempt.cmi_objectives_12 = objectives
        else:
            self.attempt.cmi_objectives_2004 = objectives
    
    def _handle_interactions_data(self, element, value):
        """Handle interactions data for both SCORM 1.2 and 2004"""
        if self.version == '1.2':
            interactions = self.attempt.cmi_interactions_12 or []
        else:
            interactions = self.attempt.cmi_interactions_2004 or []
        
        # Parse element to get interaction index and field
        parts = element.split('.')
        if len(parts) >= 3:
            int_index = int(parts[2]) if parts[2].isdigit() else 0
            field = parts[3] if len(parts) > 3 else None
            
            # Ensure we have enough interactions
            while len(interactions) <= int_index:
                interactions.append({})
            
            if field:
                interactions[int_index][field] = value
            else:
                interactions[int_index]['id'] = value
        
        # Update the appropriate field
        if self.version == '1.2':
            self.attempt.cmi_interactions_12 = interactions
        else:
            self.attempt.cmi_interactions_2004 = interactions
    
    def _handle_student_preferences(self, element, value):
        """Handle student preferences for SCORM 1.2"""
        preferences = self.attempt.cmi_student_preferences or {}
        field = element.split('.')[-1]
        preferences[field] = value
        self.attempt.cmi_student_preferences = preferences
    
    def _handle_learner_comments(self, element, value):
        """Handle learner comments for SCORM 2004"""
        comments = self.attempt.cmi_comments_from_learner or []
        parts = element.split('.')
        
        if len(parts) >= 3:
            comment_index = int(parts[2]) if parts[2].isdigit() else 0
            field = parts[3] if len(parts) > 3 else None
            
            # Ensure we have enough comments
            while len(comments) <= comment_index:
                comments.append({})
            
            if field:
                comments[comment_index][field] = value
                if field == 'timestamp' and not comments[comment_index].get('timestamp'):
                    comments[comment_index]['timestamp'] = timezone.now().isoformat()
        
        self.attempt.cmi_comments_from_learner = comments
    
    def _handle_lms_comments(self, element, value):
        """Handle LMS comments for SCORM 2004"""
        comments = self.attempt.cmi_comments_from_lms or []
        parts = element.split('.')
        
        if len(parts) >= 3:
            comment_index = int(parts[2]) if parts[2].isdigit() else 0
            field = parts[3] if len(parts) > 3 else None
            
            # Ensure we have enough comments
            while len(comments) <= comment_index:
                comments.append({})
            
            if field:
                comments[comment_index][field] = value
                if field == 'timestamp' and not comments[comment_index].get('timestamp'):
                    comments[comment_index]['timestamp'] = timezone.now().isoformat()
        
        self.attempt.cmi_comments_from_lms = comments
    
    def add_xapi_event(self, event_data):
        """Add xAPI event to the attempt"""
        try:
            from .cmi_validator import CMIValidator
            
            # Validate xAPI event
            validation = CMIValidator.validate_xapi_event(event_data)
            if not validation['is_valid']:
                logger.warning("Invalid xAPI event: %s", validation)
                return False
            
            # Add event to the attempt
            self.attempt.add_xapi_event(event_data)
            
            # Update xAPI fields if this is the latest event
            if 'actor' in event_data:
                self.attempt.update_xapi_actor(event_data['actor'])
            if 'verb' in event_data:
                self.attempt.xapi_verb = event_data['verb']
            if 'object' in event_data:
                self.attempt.xapi_object = event_data['object']
            if 'result' in event_data:
                self.attempt.update_xapi_result(event_data['result'])
            if 'context' in event_data:
                self.attempt.xapi_context = event_data['context']
            if 'timestamp' in event_data:
                try:
                    from datetime import datetime
                    self.attempt.xapi_timestamp = datetime.fromisoformat(event_data['timestamp'].replace('Z', '+00:00'))
                except:
                    pass
            
            logger.info("Added xAPI event to attempt %s", self.attempt.id)
            return True
                
        except Exception as e:
            logger.error("Error adding xAPI event: %s", str(e))
            return False
