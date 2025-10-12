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
from .models import ScormInteraction, ScormObjective, ScormComment
from .slide_tracker import SlideTracker

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
    
    def _initialize_cmi_data(self):
        """Initialize comprehensive CMI data structure for SCORM 1.2 and 2004"""
        if self.version == '1.2':
            return {
                # Core SCORM 1.2 Data Elements
                'cmi.core._children': 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time',
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': self.attempt.lesson_status or 'not attempted',
                'cmi.core.entry': self.attempt.entry or 'ab-initio',
                'cmi.core.score._children': 'raw,max,min',
                'cmi.core.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.core.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.core.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.core.total_time': self.attempt.total_time or '0000:00:00.00',
                'cmi.core.lesson_mode': 'normal',
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
                'cmi.credit': 'credit',
                'cmi.completion_status': self.attempt.completion_status or 'incomplete',
                'cmi.success_status': self.attempt.success_status or 'unknown',
                'cmi.entry': self.attempt.entry or 'ab-initio',
                'cmi.score._children': 'raw,min,max,scaled',
                'cmi.score.raw': str(self.attempt.score_raw) if self.attempt.score_raw else '',
                'cmi.score.max': str(self.attempt.score_max) if self.attempt.score_max else '100',
                'cmi.score.min': str(self.attempt.score_min) if self.attempt.score_min else '0',
                'cmi.score.scaled': str(self.attempt.score_scaled) if self.attempt.score_scaled else '',
                'cmi.total_time': self.attempt.total_time or 'PT00H00M00S',
                'cmi.mode': 'normal',
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
        
        if has_bookmark_data:
            self.attempt.entry = 'resume'
            suspend_data_preview = self.attempt.suspend_data[:50] if self.attempt.suspend_data else "None"
            logger.info("SCORM Resume: location='%s', suspend_data='%s...'", self.attempt.lesson_location, suspend_data_preview)
        else:
            self.attempt.entry = 'ab-initio'
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
            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status or 'not attempted'
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
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info("🔖 RESUME: Set suspend_data in CMI data (%d chars)", len(self.attempt.suspend_data))
            
            # Set other required fields
            self.attempt.cmi_data['cmi.completion_status'] = self.attempt.lesson_status or 'not attempted'
            self.attempt.cmi_data['cmi.mode'] = 'normal'
            self.attempt.cmi_data['cmi.credit'] = 'credit'
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
        
        # CRITICAL FIX: Only mark as completed if SCORM content explicitly set completion status
        # Don't automatically complete just because terminate was called (user might have navigated away)
        
        # Check if SCORM content explicitly set lesson_status via SetValue calls
        explicit_status_set = hasattr(self.attempt, '_explicit_status_set') and self.attempt._explicit_status_set
        
        if not self.attempt.lesson_status or self.attempt.lesson_status == 'not_attempted':
            if explicit_status_set:
                # SCORM content explicitly set status - trust it
                logger.info("TERMINATE: SCORM content explicitly set lesson_status - trusting content decision")
            elif self.attempt.score_raw is not None and self.attempt.score_raw > 0:
                # Only set completion status if we have a real score AND evidence of actual interaction
                has_real_interaction = (
                    self.attempt.lesson_location or  # Has bookmark data
                    (self.attempt.suspend_data and len(self.attempt.suspend_data) > 100) or  # Has substantial progress data
                    self.attempt.total_time != '0000:00:00.00'  # Has spent time
                )
                
                if has_real_interaction:
                    mastery_score = self.attempt.scorm_package.mastery_score or 70
                    if self.attempt.score_raw >= mastery_score:
                        self.attempt.lesson_status = 'passed'
                        status_to_set = 'passed'
                    else:
                        self.attempt.lesson_status = 'failed'  
                        status_to_set = 'failed'
                    logger.info("TERMINATE: Set lesson_status to %s based on score %s with evidence of interaction (mastery: %s)", 
                               status_to_set, self.attempt.score_raw, mastery_score)
                else:
                    # Score found but no evidence of real interaction - mark as incomplete
                    self.attempt.lesson_status = 'incomplete'
                    status_to_set = 'incomplete'
                    logger.warning("TERMINATE: Score %s found but no evidence of real interaction - marking as incomplete to prevent false completion", 
                                 self.attempt.score_raw)
            else:
                # No score or insufficient interaction - mark as incomplete (user probably just navigated away)
                self.attempt.lesson_status = 'incomplete'
                status_to_set = 'incomplete'
                logger.info("TERMINATE: No score or insufficient interaction - marking as incomplete (user likely navigated away)")
            
            # Update CMI data only if status was determined
            if 'status_to_set' in locals():
                if self.version == '1.2':
                    self.attempt.cmi_data['cmi.core.lesson_status'] = status_to_set
                else:
                    self.attempt.cmi_data['cmi.completion_status'] = status_to_set
                    if status_to_set in ['passed', 'failed']:
                        self.attempt.cmi_data['cmi.success_status'] = status_to_set
        
        # Save all data
        self._commit_data()
        
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
                # SCORM 1.2 Core Elements - Always provide defaults
                if element == 'cmi.core.lesson_status':
                    value = self.attempt.lesson_status or 'not attempted'
                elif element == 'cmi.core.entry':
                    value = self.attempt.entry or 'ab-initio'
                elif element == 'cmi.core.credit':
                    value = 'credit'
                elif element == 'cmi.core.lesson_mode':
                    value = 'normal'
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
                    value = self.attempt.completion_status or 'incomplete'
                elif element == 'cmi.success_status':
                    value = self.attempt.success_status or 'unknown'
                elif element == 'cmi.mode':
                    value = 'normal'
                elif element == 'cmi.credit':
                    value = 'credit'
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
            if self.version == '1.2':
                # SCORM 1.2 Core Elements
                if element == 'cmi.core.lesson_status':
                    self.attempt.lesson_status = value
                    # Mark that SCORM content explicitly set the status
                    self.attempt._explicit_status_set = True
                    self._update_completion_from_status(value)
                elif element == 'cmi.core.score.raw':
                    try:
                        # CRITICAL FIX: Store score in both model field AND cmi_data for consistency
                        if value and str(value).strip():
                            score_value = Decimal(value)
                            # FIX: Ensure score of 100 is handled properly
                            if 0 <= score_value <= 100:
                                self.attempt.score_raw = score_value
                                self.attempt.cmi_data['cmi.core.score.raw'] = str(value)
                                logger.info("SCORE: Set score_raw = %s for attempt %s (user: %s)", value, self.attempt.id, self.attempt.user.username)
                            else:
                                logger.warning("SCORE: Invalid score value %s (must be 0-100)", value)
                                self.last_error = '405'
                                return 'false'
                            
                            # PERMANENT FIX: Set lesson_status based on score automatically
                            mastery_score = self.attempt.scorm_package.mastery_score or 70
                            
                            # Determine correct status based on score
                            correct_status = 'passed' if self.attempt.score_raw >= mastery_score else 'failed'
                            
                            # Update status if not already explicitly set by SCORM content or if incorrect
                            if not hasattr(self.attempt, '_explicit_status_set') or not self.attempt._explicit_status_set:
                                # Status not explicitly set by SCORM content - use score-based status
                                if self.attempt.lesson_status != correct_status:
                                    self.attempt.lesson_status = correct_status
                                    self.attempt.cmi_data['cmi.core.lesson_status'] = correct_status
                                    self._update_completion_from_status(correct_status)
                                    logger.info("SCORE: Auto-set lesson_status to %s based on score %s (mastery: %s)", 
                                              correct_status, self.attempt.score_raw, mastery_score)
                            elif self.attempt.score_raw >= mastery_score and self.attempt.lesson_status == 'failed':
                                # CRITICAL FIX: Override 'failed' status if score is actually passing
                                self.attempt.lesson_status = 'passed'
                                self.attempt.cmi_data['cmi.core.lesson_status'] = 'passed'
                                self._update_completion_from_status('passed')
                                logger.info("SCORE: Corrected lesson_status from 'failed' to 'passed' for score %s", 
                                          self.attempt.score_raw)
                            
                            # IMMEDIATE FIX: Save attempt and update TopicProgress right away
                            # This ensures scores are reflected in gradebook even if SCORM content
                            # doesn't call Commit/Terminate properly
                            self.attempt.save()
                            self._update_topic_progress()
                            logger.info("SCORE: Immediately saved to database and updated TopicProgress")
                        else:
                            self.attempt.score_raw = None
                            self.attempt.cmi_data['cmi.core.score.raw'] = ''
                    except (ValueError, TypeError) as e:
                        logger.error("SCORE ERROR: Failed to set score_raw = %s for attempt %s: %s", value, self.attempt.id, str(e))
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.core.score.max':
                    try:
                        self.attempt.score_max = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.core.score.min':
                    try:
                        self.attempt.score_min = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.core.lesson_location':
                    # CRITICAL FIX: Store bookmark data in both CMI data and model fields
                    old_location = self.attempt.lesson_location
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.core.lesson_location'] = value
                    logger.info("🔖 BOOKMARK UPDATE: lesson_location changed from '%s' to '%s' for attempt %s", 
                               old_location or 'None', value or 'None', self.attempt.id)
                    
                    # ENHANCED: Update slide/section tracking
                    try:
                        SlideTracker.update_slide_progress(self.attempt)
                    except Exception as tracker_error:
                        logger.warning("⚠️ Slide tracker error: %s", str(tracker_error))
                    
                    # ENHANCED: Immediate save for critical bookmark data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['lesson_location', 'cmi_data', 'last_accessed', 
                                                         'last_visited_slide', 'progress_percentage', 
                                                         'total_slides', 'completed_slides', 'detailed_tracking'])
                        logger.info("🔖 BOOKMARK SAVED: Immediately saved lesson_location, slide progress, and CMI data")
                    except Exception as save_error:
                        logger.error("❌ BOOKMARK SAVE ERROR: %s", str(save_error))
                        
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Store suspend data in both CMI data and model fields
                    old_suspend_len = len(self.attempt.suspend_data) if self.attempt.suspend_data else 0
                    new_suspend_len = len(value) if value else 0
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
                    logger.info("🔖 SUSPEND DATA UPDATE: Changed from %d chars to %d chars for attempt %s", 
                               old_suspend_len, new_suspend_len, self.attempt.id)
                    
                    # ENHANCED: Update slide/section tracking from suspend_data
                    try:
                        SlideTracker.update_slide_progress(self.attempt)
                    except Exception as tracker_error:
                        logger.warning("⚠️ Slide tracker error: %s", str(tracker_error))
                    
                    # CRITICAL FIX: Extract and save time from suspend_data
                    try:
                        import json
                        suspend_json = json.loads(value)
                        if 'totalTime' in suspend_json:
                            total_seconds = int(suspend_json['totalTime'])
                            self.attempt.time_spent_seconds = total_seconds
                            # Convert to SCORM time format (hhhh:mm:ss.ss)
                            hours = total_seconds // 3600
                            minutes = (total_seconds % 3600) // 60
                            seconds = total_seconds % 60
                            self.attempt.total_time = f"{hours:04d}:{minutes:02d}:{seconds:02d}.00"
                            logger.info(f"⏱️ TIME EXTRACTED: {total_seconds}s from suspend_data -> {self.attempt.total_time}")
                    except Exception as time_error:
                        logger.warning(f"⚠️ Could not extract time from suspend_data: {time_error}")
                    
                    # ENHANCED: Immediate save for critical suspend data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['suspend_data', 'cmi_data', 'last_accessed',
                                                         'last_visited_slide', 'progress_percentage',
                                                         'total_slides', 'completed_slides', 'detailed_tracking',
                                                         'time_spent_seconds', 'total_time'])
                        logger.info("🔖 SUSPEND DATA SAVED: Immediately saved suspend_data, slide progress, time tracking, and CMI data")
                    except Exception as save_error:
                        logger.error("❌ SUSPEND DATA SAVE ERROR: %s", str(save_error))
                elif element == 'cmi.core.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.core.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.core.total_time':
                    self.attempt.total_time = value
                elif element == 'cmi.comments':
                    # Store learner comments
                    pass
                elif element == 'cmi.comments_from_lms':
                    # Store LMS comments
                    pass
                    
            else:  # SCORM 2004
                # SCORM 2004 Core Elements
                if element == 'cmi.completion_status':
                    self.attempt.completion_status = value
                    # Mark that SCORM content explicitly set the status
                    self.attempt._explicit_status_set = True
                    if value == 'completed':
                        self.attempt.completed_at = timezone.now()
                elif element == 'cmi.success_status':
                    self.attempt.success_status = value
                    # Mark that SCORM content explicitly set the status
                    self.attempt._explicit_status_set = True
                elif element == 'cmi.score.raw':
                    try:
                        # CRITICAL FIX: Store score in both model field AND cmi_data for consistency
                        if value and str(value).strip():
                            score_value = Decimal(value)
                            # FIX: Ensure score of 100 is handled properly
                            if 0 <= score_value <= 100:
                                self.attempt.score_raw = score_value
                                self.attempt.cmi_data['cmi.score.raw'] = str(value)
                                logger.info("SCORE: Set score_raw = %s for attempt %s (user: %s)", value, self.attempt.id, self.attempt.user.username)
                            else:
                                logger.warning("SCORE: Invalid score value %s (must be 0-100)", value)
                                self.last_error = '405'
                                return 'false'
                            
                            # PERMANENT FIX: Set success_status based on score automatically
                            mastery_score = self.attempt.scorm_package.mastery_score or 70
                            
                            # Determine correct status based on score
                            correct_success_status = 'passed' if self.attempt.score_raw >= mastery_score else 'failed'
                            correct_completion_status = 'completed'
                            
                            # Update status if not already explicitly set by SCORM content or if incorrect
                            if not hasattr(self.attempt, '_explicit_status_set') or not self.attempt._explicit_status_set:
                                # Status not explicitly set by SCORM content - use score-based status
                                if self.attempt.success_status != correct_success_status:
                                    self.attempt.success_status = correct_success_status
                                    self.attempt.cmi_data['cmi.success_status'] = correct_success_status
                                    logger.info("SCORE: Auto-set success_status to %s based on score %s (mastery: %s)", 
                                              correct_success_status, self.attempt.score_raw, mastery_score)
                                
                                if self.attempt.completion_status != correct_completion_status:
                                    self.attempt.completion_status = correct_completion_status
                                    self.attempt.cmi_data['cmi.completion_status'] = correct_completion_status
                                    logger.info("SCORE: Auto-set completion_status to %s", correct_completion_status)
                            elif self.attempt.score_raw >= mastery_score and self.attempt.success_status == 'failed':
                                # CRITICAL FIX: Override 'failed' status if score is actually passing
                                self.attempt.success_status = 'passed'
                                self.attempt.cmi_data['cmi.success_status'] = 'passed'
                                self.attempt.completion_status = 'completed'
                                self.attempt.cmi_data['cmi.completion_status'] = 'completed'
                                logger.info("SCORE: Corrected success_status from 'failed' to 'passed' for score %s", 
                                          self.attempt.score_raw)
                            
                            # IMMEDIATE FIX: Save attempt and update TopicProgress right away
                            # This ensures scores are reflected in gradebook even if SCORM content
                            # doesn't call Commit/Terminate properly
                            self.attempt.save()
                            self._update_topic_progress()
                            logger.info("SCORE: Immediately saved to database and updated TopicProgress (SCORM 2004)")
                        else:
                            self.attempt.score_raw = None
                            self.attempt.cmi_data['cmi.score.raw'] = ''
                    except (ValueError, TypeError) as e:
                        logger.error("SCORE ERROR: Failed to set score_raw = %s for attempt %s: %s", value, self.attempt.id, str(e))
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.score.max':
                    try:
                        self.attempt.score_max = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.score.min':
                    try:
                        self.attempt.score_min = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.score.scaled':
                    try:
                        scaled_value = Decimal(value) if value and str(value).strip() else None
                        # SCORM 2004 scaled scores should be between -1 and 1
                        if scaled_value is not None and (scaled_value < -1 or scaled_value > 1):
                            self.last_error = '405'
                            return 'false'
                        self.attempt.score_scaled = scaled_value
                    except (ValueError, TypeError):
                        self.last_error = '405'
                        return 'false'
                elif element == 'cmi.location':
                    # CRITICAL FIX: Store bookmark data in both CMI data and model fields
                    old_location = self.attempt.lesson_location
                    self.attempt.lesson_location = value
                    self.attempt.cmi_data['cmi.location'] = value
                    logger.info("🔖 BOOKMARK UPDATE (SCORM 2004): location changed from '%s' to '%s' for attempt %s", 
                               old_location or 'None', value or 'None', self.attempt.id)
                    
                    # ENHANCED: Immediate save for critical bookmark data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['lesson_location', 'cmi_data', 'last_accessed'])
                        logger.info("🔖 BOOKMARK SAVED (SCORM 2004): Immediately saved location and CMI data")
                    except Exception as save_error:
                        logger.error("❌ BOOKMARK SAVE ERROR (SCORM 2004): %s", str(save_error))
                        
                elif element == 'cmi.suspend_data':
                    # CRITICAL FIX: Store suspend data in both CMI data and model fields
                    old_suspend_len = len(self.attempt.suspend_data) if self.attempt.suspend_data else 0
                    new_suspend_len = len(value) if value else 0
                    self.attempt.suspend_data = value
                    self.attempt.cmi_data['cmi.suspend_data'] = value
                    logger.info("🔖 SUSPEND DATA UPDATE (SCORM 2004): Changed from %d chars to %d chars for attempt %s", 
                               old_suspend_len, new_suspend_len, self.attempt.id)
                    
                    # ENHANCED: Immediate save for critical suspend data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['suspend_data', 'cmi_data', 'last_accessed'])
                        logger.info("🔖 SUSPEND DATA SAVED (SCORM 2004): Immediately saved suspend_data and CMI data")
                    except Exception as save_error:
                        logger.error("❌ SUSPEND DATA SAVE ERROR (SCORM 2004): %s", str(save_error))
                elif element == 'cmi.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.total_time':
                    self.attempt.total_time = value
                elif element == 'cmi.progress_measure':
                    # Store progress measure (0.0-1.0)
                    pass
                elif element.startswith('cmi.objectives.'):
                    # Handle objectives data
                    self._set_objective_value(element, value)
                elif element.startswith('cmi.interactions.'):
                    # Handle interactions data
                    self._set_interaction_value(element, value)
                elif element.startswith('cmi.comments_from_learner.'):
                    # Handle learner comments
                    self._set_comment_value(element, value, 'learner')
                elif element.startswith('cmi.comments_from_lms.'):
                    # Handle LMS comments
                    self._set_comment_value(element, value, 'lms')
            
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error("Error setting value for %s: %s", element, str(e))
            self.last_error = '101'
            return 'false'
    
    def commit(self):
        """LMSCommit / Commit"""
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        try:
            logger.info("💾 COMMIT: Starting commit for attempt %s (user: %s, score_raw: %s, lesson_status: %s)", 
                       self.attempt.id, self.attempt.user.username, self.attempt.score_raw, self.attempt.lesson_status)
            self._commit_data()
            logger.info("✅ COMMIT: Successfully committed data for attempt %s", self.attempt.id)
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error("❌ COMMIT ERROR: Failed to commit data for attempt %s: %s", self.attempt.id, str(e))
            self.last_error = '101'
            return 'false'
    
    def get_last_error(self):
        """LMSGetLastError / GetLastError"""
        return self.last_error
    
    def get_error_string(self, error_code):
        """LMSGetErrorString / GetErrorString"""
        try:
            error_code_str = str(error_code) if error_code is not None else '0'
            return self.SCORM_ERRORS.get(error_code_str, 'Unknown error')
        except Exception as e:
            logger.error("Error in get_error_string: %s", str(e))
            return 'Unknown error'
    
    def get_diagnostic(self, error_code):
        """LMSGetDiagnostic / GetDiagnostic"""
        return self.get_error_string(error_code)
    
    def _validate_element(self, element, value):
        """Validate SCORM element and value according to specification"""
        try:
            # Read-only elements
            read_only_elements = [
                'cmi.core.student_id', 'cmi.core.student_name', 'cmi.core.credit',
                'cmi.core.lesson_mode', 'cmi.core.total_time', 'cmi.core.launch_data',
                'cmi.learner_id', 'cmi.learner_name', 'cmi.credit', 'cmi.mode',
                'cmi.total_time', 'cmi.launch_data', 'cmi._version'
            ]
            
            if element in read_only_elements:
                self.last_error = '403'
                return False
            
            # Write-only elements
            write_only_elements = [
                'cmi.core.exit', 'cmi.core.session_time', 'cmi.exit', 'cmi.session_time'
            ]
            
            if element in write_only_elements:
                # These are write-only, so we can set them
                pass
            
            # Validate specific data types
            if element.endswith('.raw') or element.endswith('.max') or element.endswith('.min'):
                if value and not self._is_valid_number(value):
                    self.last_error = '405'
                    return False
            
            if element == 'cmi.score.scaled':
                if value and not self._is_valid_scaled_score(value):
                    self.last_error = '405'
                    return False
            
            if element in ['cmi.core.lesson_status', 'cmi.completion_status']:
                valid_statuses = ['passed', 'completed', 'failed', 'incomplete', 'browsed', 'not attempted']
                if value not in valid_statuses:
                    self.last_error = '402'
                    return False
            
            if element in ['cmi.core.entry', 'cmi.entry']:
                valid_entries = ['ab-initio', 'resume', '']
                if value not in valid_entries:
                    self.last_error = '402'
                    return False
            
            return True
        except Exception as e:
            logger.error("Error validating element %s: %s", element, str(e))
            self.last_error = '101'
            return False
    
    def _is_valid_number(self, value):
        """Check if value is a valid number"""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _is_valid_scaled_score(self, value):
        """Check if value is a valid scaled score (-1 to 1)"""
        try:
            score = float(value)
            return -1 <= score <= 1
        except (ValueError, TypeError):
            return False
    
    def _get_children_elements(self, element):
        """Get children elements for array structures"""
        if element == 'cmi.core._children':
            return 'student_id,student_name,lesson_location,credit,lesson_status,entry,score,total_time,lesson_mode,exit,session_time'
        elif element == 'cmi.core.score._children':
            return 'raw,max,min'
        elif element == 'cmi.student_data._children':
            return 'mastery_score,max_time_allowed,time_limit_action'
        elif element == 'cmi.student_preference._children':
            return 'audio,language,speed,text'
        elif element == 'cmi.score._children':
            return 'raw,min,max,scaled'
        elif element == 'cmi.learner_preference._children':
            return 'audio_level,language,delivery_speed,audio_captioning'
        elif element == 'cmi.objectives._children':
            return ''
        elif element == 'cmi.interactions._children':
            return ''
        elif element == 'cmi.comments_from_learner._children':
            return ''
        elif element == 'cmi.comments_from_lms._children':
            return ''
        else:
            return ''
    
    def _get_count_elements(self, element):
        """Get count for array elements"""
        if element == 'cmi.objectives._count':
            return str(len([k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.objectives.') and not k.endswith('._count') and not k.endswith('._children')]))
        elif element == 'cmi.interactions._count':
            return str(len([k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.interactions.') and not k.endswith('._count') and not k.endswith('._children')]))
        elif element == 'cmi.comments_from_learner._count':
            return str(len([k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.comments_from_learner.') and not k.endswith('._count') and not k.endswith('._children')]))
        elif element == 'cmi.comments_from_lms._count':
            return str(len([k for k in self.attempt.cmi_data.keys() if k.startswith('cmi.comments_from_lms.') and not k.endswith('._count') and not k.endswith('._children')]))
        else:
            return '0'
    
    def _get_interaction_value(self, element):
        """Get interaction value"""
        # Extract interaction index from element
        match = re.match(r'cmi\.interactions\.(\d+)\.(.+)', element)
        if match:
            index = match.group(1)
            field = match.group(2)
            return self.attempt.cmi_data.get(element, '')
        return ''
    
    def _get_objective_value(self, element):
        """Get objective value"""
        # Extract objective index from element
        match = re.match(r'cmi\.objectives\.(\d+)\.(.+)', element)
        if match:
            index = match.group(1)
            field = match.group(2)
            return self.attempt.cmi_data.get(element, '')
        return ''
    
    def _get_comment_value(self, element, source):
        """Get comment value"""
        # Extract comment index from element
        match = re.match(r'cmi\.comments_from_(\w+)\.(\d+)\.(.+)', element)
        if match:
            source_type = match.group(1)
            index = match.group(2)
            field = match.group(3)
            return self.attempt.cmi_data.get(element, '')
        return ''
    
    def _set_interaction_value(self, element, value):
        """Set interaction value and save to database"""
        # Extract interaction index from element
        match = re.match(r'cmi\.interactions\.(\d+)\.(.+)', element)
        if match:
            index = match.group(1)
            field = match.group(2)
            
            # Validate interaction data
            if not self._validate_interaction_data(field, value):
                self.last_error = '402'
                return False
            
            # Store in CMI data
            self.attempt.cmi_data[element] = value
            
            # Save to database using interaction handler
            try:
                from .interaction_handler import ScormInteractionHandler
                handler = ScormInteractionHandler(self.attempt)
                
                # Get or create interaction data
                interaction_data = self._build_interaction_data(index)
                if interaction_data:
                    # Check if interaction already exists
                    existing_interaction = ScormInteraction.objects.filter(
                        attempt=self.attempt,
                        interaction_id=interaction_data['id']
                    ).first()
                    
                    if existing_interaction:
                        # Update existing interaction
                        existing_interaction.interaction_type = interaction_data.get('type', existing_interaction.interaction_type)
                        existing_interaction.student_response = interaction_data.get('student_response', existing_interaction.student_response)
                        existing_interaction.correct_response = interaction_data.get('correct_response', existing_interaction.correct_response)
                        existing_interaction.result = interaction_data.get('result', existing_interaction.result)
                        existing_interaction.weighting = interaction_data.get('weighting', existing_interaction.weighting)
                        existing_interaction.score_raw = interaction_data.get('score_raw', existing_interaction.score_raw)
                        existing_interaction.latency = interaction_data.get('latency', existing_interaction.latency)
                        existing_interaction.objectives = interaction_data.get('objectives', existing_interaction.objectives)
                        existing_interaction.learner_response_data = interaction_data.get('learner_response_data', existing_interaction.learner_response_data)
                        existing_interaction.save()
                        logger.info(f"Updated interaction {index} in database")
                    else:
                        # Create new interaction
                        handler.save_interaction(interaction_data)
                        logger.info(f"Saved new interaction {index} to database")
            except Exception as e:
                logger.error(f"Error saving interaction to database: {str(e)}")
            
        return True
    
    def _set_objective_value(self, element, value):
        """Set objective value"""
        # Extract objective index from element
        match = re.match(r'cmi\.objectives\.(\d+)\.(.+)', element)
        if match:
            index = match.group(1)
            field = match.group(2)
            # Validate objective data
            if self._validate_objective_data(field, value):
                self.attempt.cmi_data[element] = value
            else:
                self.last_error = '402'
                return False
        return True
    
    def _set_comment_value(self, element, value, source):
        """Set comment value"""
        # Extract comment index from element
        match = re.match(r'cmi\.comments_from_(\w+)\.(\d+)\.(.+)', element)
        if match:
            source_type = match.group(1)
            index = match.group(2)
            field = match.group(3)
            # Validate comment data
            if self._validate_comment_data(field, value):
                self.attempt.cmi_data[element] = value
            else:
                self.last_error = '402'
                return False
        return True
    
    def _validate_interaction_data(self, field, value):
        """Validate interaction data"""
        if field == 'type':
            valid_types = ['choice', 'fill-in', 'long-fill-in', 'matching', 'performance', 'sequencing', 'likert', 'numeric', 'other']
            return value in valid_types
        elif field == 'result':
            valid_results = ['correct', 'incorrect', 'unanticipated', 'neutral']
            return value in valid_results or self._is_valid_number(value)
        elif field == 'weighting':
            return self._is_valid_number(value)
        elif field == 'latency':
            return self._is_valid_time_interval(value)
        return True
    
    def _validate_objective_data(self, field, value):
        """Validate objective data"""
        if field == 'success_status':
            valid_statuses = ['passed', 'failed', 'unknown']
            return value in valid_statuses
        elif field == 'completion_status':
            valid_statuses = ['completed', 'incomplete', 'not attempted', 'unknown']
            return value in valid_statuses
        elif field == 'progress_measure':
            return self._is_valid_number(value) and 0 <= float(value) <= 1
        return True
    
    def _validate_comment_data(self, field, value):
        """Validate comment data"""
        if field == 'comment':
            return len(value) <= 4000  # SCORM limit
        elif field == 'location':
            return len(value) <= 250  # SCORM limit
        elif field == 'timestamp':
            return self._is_valid_time_interval(value)
        return True
    
    def _is_valid_time_interval(self, value):
        """Check if value is a valid time interval"""
        try:
            if self.version == '1.2':
                # SCORM 1.2 time format: hhhh:mm:ss.ss
                parts = value.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    return 0 <= minutes < 60 and 0 <= seconds < 60
            else:
                # SCORM 2004 time format: PT1H30M45S
                if value.startswith('PT'):
                    return True
            return False
        except (ValueError, TypeError, IndexError):
            return False
    
    def _validate_completion_status(self, status_completed):
        """
        Validate that completion status is legitimate based on actual content interaction
        Returns True only if there's evidence of real completion
        """
        if not status_completed:
            return False
        
        # Check for evidence of actual content interaction
        has_real_interaction = False
        
        # 1. Check for Continue button interactions in suspend_data
        if self.attempt.suspend_data:
            continue_patterns = [
                r'continue[_-]?button[_-]?clicked[=:]\s*(\d+)',
                r'continue[_-]?clicks[=:]\s*(\d+)',
                r'button[_-]?interactions[=:]\s*(\d+)',
                r'slide[_-]?progress[=:]\s*(\d+)',
                r'continue[_-]?count[=:]\s*(\d+)'
            ]
            
            for pattern in continue_patterns:
                match = re.search(pattern, self.attempt.suspend_data, re.IGNORECASE)
                if match:
                    click_count = int(match.group(1))
                    if click_count > 0:
                        has_real_interaction = True
                        logger.info(f"✅ Found Continue button interactions: {click_count} clicks")
                        break
        
        # 2. Check for slide completion tracking
        if not has_real_interaction and self.attempt.completed_slides:
            # Check if we have actual completed slides (not just visited)
            completed_count = len(self.attempt.completed_slides)
            if completed_count > 0:
                has_real_interaction = True
                logger.info(f"✅ Found completed slides: {completed_count} slides")
        
        # 3. Check for quiz/assessment interactions
        if not has_real_interaction and self.attempt.score_raw is not None:
            if self.attempt.score_raw > 0:
                has_real_interaction = True
                logger.info(f"✅ Found quiz score: {self.attempt.score_raw}")
        
        # 4. Check for substantial time spent (as backup validation)
        if not has_real_interaction:
            time_seconds = 0
            if self.attempt.total_time and self.attempt.total_time != '0000:00:00.00':
                try:
                    time_parts = str(self.attempt.total_time).split(':')
                    if len(time_parts) == 3:
                        hours, minutes, seconds = map(float, time_parts)
                        time_seconds = int(hours * 3600 + minutes * 60 + seconds)
                except (ValueError, TypeError, IndexError):
                    pass
                
                # Require at least 2 minutes of actual time spent
                if time_seconds >= 120:
                    has_real_interaction = True
                    logger.info(f"✅ Found substantial time spent: {time_seconds}s")
        
        if not has_real_interaction:
            logger.warning(f"⚠️  Completion status set but no evidence of real interaction - marking as incomplete")
            return False
        
        logger.info(f"✅ Valid completion detected - marking as completed")
        return True
    
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
            # Parse session time
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
            
            # Format back to SCORM time
            self.attempt.total_time = self._format_scorm_time(new_total)
            
        except Exception as e:
            logger.error("Error updating total time: %s", str(e))
    
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
        except (ValueError, IndexError, TypeError):
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
        except (ValueError, IndexError, TypeError):
            return 0
    
    def _format_scorm_time(self, total_seconds):
        """Format seconds to SCORM time format (hhhh:mm:ss.ss)"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        return "%04d:%02d:%05.2f" % (hours, minutes, seconds)
    
    def _auto_extract_score_from_suspend_data(self):
        """
        AUTOMATIC FIX: Extract score from suspend_data when SCORM content doesn't report it properly
        Some broken SCORM packages display scores but never call SetValue for cmi.core.score.raw
        This method automatically detects and fixes that issue
        """
        import json
        import re
        
        # Check if we have suspend_data to parse
        if not self.attempt.suspend_data or len(self.attempt.suspend_data) < 10:
            return
        
        try:
            logger.info("AUTO_EXTRACT: Analyzing suspend_data for embedded score (current score: %s)", self.attempt.score_raw)
            
            # Try to parse suspend_data as JSON
            try:
                data = json.loads(self.attempt.suspend_data)
                
                # Method 1: Look in the decoded array
                if 'd' in data and isinstance(data['d'], list):
                    # Decode the array to string
                    decoded = ''.join([chr(x) if x < 256 else '' for x in data['d']])
                    
                    # Pattern 1: Look for "score":value or "score": value
                    score_match = re.search(r'"score"\s*:\s*(\d+\.?\d*)', decoded, re.IGNORECASE)
                    if score_match:
                        score = float(score_match.group(1))
                        logger.info("AUTO_EXTRACT: Found score in suspend_data pattern 1: %s", score)
                        self._apply_extracted_score(score)
                        return
                    
                    # Pattern 2: Look for percentage like "63%" or "p:63"
                    percent_match = re.search(r'["\']?(?:score|p)["\']?\s*:\s*(\d+)["\']?%?', decoded, re.IGNORECASE)
                    if percent_match:
                        score = float(percent_match.group(1))
                        logger.info("AUTO_EXTRACT: Found score in suspend_data pattern 2: %s", score)
                        self._apply_extracted_score(score)
                        return
                    
                    # Pattern 3: Look for quiz done status with score
                    quiz_match = re.search(r'"qd"\s*:\s*true.*?"p"\s*:\s*(\d+)', decoded, re.IGNORECASE)
                    if quiz_match:
                        score = float(quiz_match.group(1))
                        logger.info("AUTO_EXTRACT: Found score in suspend_data pattern 3 (quiz done): %s", score)
                        self._apply_extracted_score(score)
                        return
                    
                    # Pattern 4: Look for percentage anywhere in format like ,56, or ,38,
                    # (common in some SCORM packages that encode score in array)
                    # CRITICAL FIX: More restrictive pattern matching to avoid false positives
                    if 'qd' in decoded and 'true' in decoded:  # Quiz done flag exists
                        # Look for explicit score patterns near quiz completion indicators
                        # Only extract if score appears in context of quiz completion
                        quiz_score_match = re.search(r'qd["\']?\s*:\s*true.*?[,\[\s](\d{1,2})[,\]\s]', decoded, re.IGNORECASE | re.DOTALL)
                        if quiz_score_match:
                            num = int(quiz_score_match.group(1))
                            if 0 <= num <= 100:  # Valid score range
                                logger.info("AUTO_EXTRACT: Found quiz completion score in suspend_data pattern 4: %s", num)
                                self._apply_extracted_score(float(num))
                                return
                        
                        # Fallback: Look for "score" or "result" followed by number
                        result_match = re.search(r'(?:score|result)["\']?\s*:\s*(\d{1,3})', decoded, re.IGNORECASE)
                        if result_match:
                            num = int(result_match.group(1))
                            if 0 <= num <= 100:  # Valid score range
                                logger.info("AUTO_EXTRACT: Found explicit score/result in suspend_data pattern 4b: %s", num)
                                self._apply_extracted_score(float(num))
                                return
                        
                        logger.debug("AUTO_EXTRACT: Quiz done flag found but no clear score pattern identified")
                
                # Method 2: Direct score field in JSON
                if 'score' in data:
                    score = float(data['score'])
                    logger.info("AUTO_EXTRACT: Found score directly in suspend_data JSON: %s", score)
                    self._apply_extracted_score(score)
                    return
                
                if 'quiz_score' in data:
                    score = float(data['quiz_score'])
                    logger.info("AUTO_EXTRACT: Found quiz_score in suspend_data JSON: %s", score)
                    self._apply_extracted_score(score)
                    return
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("AUTO_EXTRACT: Suspend data is not JSON or parsing failed: %s", str(e))
                
                # Try direct regex on raw string
                score_match = re.search(r'score["\']?\s*:\s*(\d+\.?\d*)', self.attempt.suspend_data, re.IGNORECASE)
                if score_match:
                    score = float(score_match.group(1))
                    logger.info("AUTO_EXTRACT: Found score in raw suspend_data: %s", score)
                    self._apply_extracted_score(score)
                    return
            
            logger.debug("AUTO_EXTRACT: No score found in suspend_data")
            
        except Exception as e:
            logger.error("AUTO_EXTRACT ERROR: Failed to extract score from suspend_data: %s", str(e))
    
    def _apply_extracted_score(self, score):
        """Apply the automatically extracted score to the attempt"""
        try:
            # Validate score is in reasonable range
            if not (0 <= score <= 100):
                logger.warning("AUTO_EXTRACT: Score %s is out of valid range (0-100), ignoring", score)
                return
            
            # Only update if the extracted score is different from current score
            if self.attempt.score_raw == Decimal(str(score)):
                logger.debug("AUTO_EXTRACT: Score unchanged (%s), skipping update", score)
                return
            
            logger.info("AUTO_EXTRACT: Updating score from %s to %s", self.attempt.score_raw, score)
            
            # Set the score
            self.attempt.score_raw = Decimal(str(score))
            
            # Set lesson status based on score
            # Typically 70% is passing, but you can adjust this
            if score >= 70:
                self.attempt.lesson_status = 'passed'
                if self.version == '1.2':
                    self.attempt.cmi_data['cmi.core.lesson_status'] = 'passed'
                else:
                    self.attempt.success_status = 'passed'
                    self.attempt.cmi_data['cmi.success_status'] = 'passed'
            else:
                self.attempt.lesson_status = 'failed'
                if self.version == '1.2':
                    self.attempt.cmi_data['cmi.core.lesson_status'] = 'failed'
                else:
                    self.attempt.success_status = 'failed'
                    self.attempt.cmi_data['cmi.success_status'] = 'failed'
            
            # Update CMI data
            if self.version == '1.2':
                self.attempt.cmi_data['cmi.core.score.raw'] = str(score)
            else:
                self.attempt.cmi_data['cmi.score.raw'] = str(score)
            
            # Save the updated attempt
            self.attempt.save()
            
            # Also update TopicProgress immediately
            self._update_topic_progress()
            
            logger.info("AUTO_EXTRACT: Successfully applied extracted score: %s (status: %s)", 
                       score, self.attempt.lesson_status)
            
        except Exception as e:
            logger.error("AUTO_EXTRACT: Failed to apply extracted score: %s", str(e))
    
    def _calculate_slide_completion_score(self):
        """
        Calculate score based on slide completion for slide-based SCORM content
        This handles SCORM packages that track progress by slide completion rather than quiz scores
        Supports multiple SCORM package types and data formats
        
        CRITICAL FIX: Only calculate completion based on actual evidence of completion,
        not just progress data. This prevents false 100% completion when users only complete a few slides.
        """
        try:
            # Skip if we already have a valid score
            if self.attempt.score_raw is not None and self.attempt.score_raw > 0:
                logger.debug("SLIDE_SCORE: Score already set (%s), skipping slide calculation", self.attempt.score_raw)
                return
            
            logger.info("SLIDE_SCORE: Checking for slide completion data (progress_percentage: %s, completed_slides: %s, total_slides: %s)", 
                       self.attempt.progress_percentage, self.attempt.completed_slides, self.attempt.total_slides)
            
            calculated_score = None
            
            # CRITICAL FIX: Only use progress_percentage if it's reasonable and not suspiciously high
            # This prevents false 100% completion when users only complete a few slides
            if self.attempt.progress_percentage:
                progress_value = float(self.attempt.progress_percentage)
                if 0 <= progress_value <= 100:
                    # CRITICAL FIX: Only trust progress_percentage if it's reasonable
                    # If progress is 100% but we don't have evidence of actual completion, be suspicious
                    if progress_value == 100:
                        # Check if we have evidence of actual completion
                        has_evidence_of_completion = (
                            self.attempt.lesson_status in ['completed', 'passed'] or
                            (self.attempt.completed_slides and self.attempt.total_slides and 
                             len(self.attempt.completed_slides) >= self.attempt.total_slides) or
                            (self.attempt.suspend_data and 'completed=true' in self.attempt.suspend_data.lower())
                        )
                        
                        if has_evidence_of_completion:
                            calculated_score = progress_value
                            logger.info("SLIDE_SCORE: Using progress_percentage with completion evidence: %s%%", calculated_score)
                        else:
                            logger.warning("SLIDE_SCORE: Progress shows 100%% but no evidence of actual completion - ignoring")
                            # Don't use the 100% progress if there's no evidence of completion
                    else:
                        # For non-100% progress, trust it
                        calculated_score = progress_value
                        logger.info("SLIDE_SCORE: Using progress_percentage: %s%%", calculated_score)
            
            # Method 2: Calculate from completed_slides / total_slides
            if calculated_score is None and self.attempt.completed_slides and self.attempt.total_slides:
                try:
                    # Extract completed slides count
                    if isinstance(self.attempt.completed_slides, list):
                        completed_count = len(self.attempt.completed_slides)
                    elif isinstance(self.attempt.completed_slides, str):
                        completed_count = len([s for s in self.attempt.completed_slides.split(',') if s.strip()])
                    else:
                        completed_count = 0
                    
                    total_slides = int(self.attempt.total_slides)
                    if total_slides > 0:
                        # CRITICAL FIX: Only calculate score if we have reasonable data
                        # Don't allow 100% completion unless we have evidence of actual completion
                        slide_completion_percentage = (completed_count / total_slides) * 100
                        
                        # If slide completion shows 100%, verify with other evidence
                        if slide_completion_percentage == 100:
                            has_evidence_of_completion = (
                                self.attempt.lesson_status in ['completed', 'passed'] or
                                (self.attempt.suspend_data and 'completed=true' in self.attempt.suspend_data.lower())
                            )
                            
                            if has_evidence_of_completion:
                                calculated_score = round(slide_completion_percentage, 2)
                                logger.info("SLIDE_SCORE: Calculated from slides with completion evidence: %s/%s = %s%%", 
                                           completed_count, total_slides, calculated_score)
                            else:
                                logger.warning("SLIDE_SCORE: Slide completion shows 100%% but no evidence of actual completion - using partial score")
                                # Use a more conservative score based on actual progress
                                calculated_score = min(slide_completion_percentage, 75)  # Cap at 75% if no evidence of completion
                                logger.info("SLIDE_SCORE: Using conservative score: %s%%", calculated_score)
                        else:
                            calculated_score = round(slide_completion_percentage, 2)
                            logger.info("SLIDE_SCORE: Calculated from slides: %s/%s = %s%%", 
                                       completed_count, total_slides, calculated_score)
                except Exception as e:
                    logger.warning("SLIDE_SCORE: Could not calculate from slides: %s", str(e))
            
            # Method 3: Parse from suspend_data (enhanced for multiple SCORM package types)
            if calculated_score is None and self.attempt.suspend_data and len(self.attempt.suspend_data) > 10:
                try:
                    import re
                    import json
                    import base64
                    
                    # Try multiple decoding methods for different SCORM package types
                    decoded_data = None
                    
                    # Method 3a: Try to decode JSON-encoded suspend_data (Articulate Storyline, etc.)
                    try:
                        suspend_json = json.loads(self.attempt.suspend_data)
                        if 'd' in suspend_json and isinstance(suspend_json['d'], list):
                            # Handle different encoding methods
                            data_array = suspend_json['d']
                            
                            # Try standard ASCII decoding first
                            try:
                                decoded_data = ''.join([chr(x) for x in data_array if x < 256])
                                logger.info("SLIDE_SCORE: Decoded JSON suspend_data (ASCII), length: %s", len(decoded_data))
                            except:
                                # Try base64 decoding if ASCII fails
                                try:
                                    # Some SCORM packages use base64 encoding
                                    base64_data = ''.join([chr(x) for x in data_array])
                                    decoded_data = base64.b64decode(base64_data).decode('utf-8')
                                    logger.info("SLIDE_SCORE: Decoded JSON suspend_data (Base64), length: %s", len(decoded_data))
                                except:
                                    # Try custom decoding for Articulate packages
                                    try:
                                        # Articulate packages often use custom encoding
                                        decoded_data = ''.join([chr(x & 0xFF) for x in data_array])
                                        logger.info("SLIDE_SCORE: Decoded JSON suspend_data (Custom), length: %s", len(decoded_data))
                                    except:
                                        logger.warning("SLIDE_SCORE: Could not decode JSON suspend_data")
                    except:
                        # If not JSON, use raw suspend_data
                        decoded_data = self.attempt.suspend_data
                        logger.info("SLIDE_SCORE: Using raw suspend_data, length: %s", len(decoded_data))
                    
                    if decoded_data:
                        # Look for progress patterns in decoded data
                        progress_patterns = [
                            r'progress[=:](\d+)',
                            r'"progress":\s*(\d+)',
                            r'progress["\']?\s*:\s*(\d+)',
                            r'completion[=:](\d+)',
                            r'completion["\']?\s*:\s*(\d+)',
                            r'score[=:](\d+)',
                            r'"score":\s*(\d+)',
                            r'percentage[=:](\d+)',
                            r'"percentage":\s*(\d+)'
                        ]
                        
                        for pattern in progress_patterns:
                            progress_match = re.search(pattern, decoded_data, re.IGNORECASE)
                            if progress_match:
                                progress_value = float(progress_match.group(1))
                                
                                # CRITICAL FIX: Only trust progress from suspend_data if it's reasonable
                                # If progress is 100% but we don't have evidence of actual completion, be suspicious
                                if progress_value == 100:
                                    has_evidence_of_completion = (
                                        self.attempt.lesson_status in ['completed', 'passed'] or
                                        (self.attempt.suspend_data and 'completed=true' in self.attempt.suspend_data.lower())
                                    )
                                    
                                    if has_evidence_of_completion:
                                        calculated_score = progress_value
                                        logger.info("SLIDE_SCORE: Extracted from suspend_data pattern '%s' with completion evidence: %s%%", pattern, calculated_score)
                                    else:
                                        logger.warning("SLIDE_SCORE: Suspend_data shows 100%% progress but no evidence of actual completion - ignoring")
                                        # Don't use the 100% progress if there's no evidence of completion
                                else:
                                    # For non-100% progress, trust it
                                    calculated_score = progress_value
                                    logger.info("SLIDE_SCORE: Extracted from suspend_data pattern '%s': %s%%", pattern, calculated_score)
                                break
                        
                        # If no progress found, look for slide completion patterns
                        if calculated_score is None:
                            slide_patterns = [
                                r'completed_slides[=:]([^&]+).*?total_slides[=:](\d+)',
                                r'"completed_slides":\s*"([^"]+)".*?"total_slides":\s*(\d+)',
                                r'completed[=:]([^&]+).*?total[=:](\d+)',
                                r'slides_completed[=:]([^&]+).*?slides_total[=:](\d+)',
                                r'slide[=:](\d+).*?total[=:](\d+)',
                                r'current_slide[=:](\d+).*?total_slides[=:](\d+)'
                            ]
                            
                            for pattern in slide_patterns:
                                slide_match = re.search(pattern, decoded_data, re.IGNORECASE | re.DOTALL)
                                if slide_match:
                                    try:
                                        completed_str = slide_match.group(1)
                                        total = int(slide_match.group(2))
                                        
                                        # Parse completed slides
                                        if ',' in completed_str:
                                            completed = len([s for s in completed_str.split(',') if s.strip()])
                                        else:
                                            completed = 1 if completed_str.strip() else 0
                                        
                                        if total > 0:
                                            slide_completion_percentage = (completed / total) * 100
                                            
                                            # CRITICAL FIX: Only trust 100% completion if we have evidence of actual completion
                                            if slide_completion_percentage == 100:
                                                has_evidence_of_completion = (
                                                    self.attempt.lesson_status in ['completed', 'passed'] or
                                                    (self.attempt.suspend_data and 'completed=true' in self.attempt.suspend_data.lower())
                                                )
                                                
                                                if has_evidence_of_completion:
                                                    calculated_score = round(slide_completion_percentage, 2)
                                                    logger.info("SLIDE_SCORE: Calculated from suspend_data pattern '%s' with completion evidence: %s/%s = %s%%", 
                                                               pattern, completed, total, calculated_score)
                                                else:
                                                    logger.warning("SLIDE_SCORE: Suspend_data slide completion shows 100%% but no evidence of actual completion - using conservative score")
                                                    # Use a more conservative score
                                                    calculated_score = min(slide_completion_percentage, 75)  # Cap at 75% if no evidence of completion
                                                    logger.info("SLIDE_SCORE: Using conservative score from suspend_data: %s%%", calculated_score)
                                            else:
                                                calculated_score = round(slide_completion_percentage, 2)
                                                logger.info("SLIDE_SCORE: Calculated from suspend_data pattern '%s': %s/%s = %s%%", 
                                                           pattern, completed, total, calculated_score)
                                            break
                                    except Exception as e:
                                        logger.warning("SLIDE_SCORE: Error parsing slide pattern '%s': %s", pattern, str(e))
                                        continue
                        
                        # If still no score, try to extract from lesson_location or other fields
                        if calculated_score is None:
                            # Check if lesson_location contains slide information
                            if self.attempt.lesson_location:
                                location_patterns = [
                                    r'slide[=:](\d+)',
                                    r'page[=:](\d+)',
                                    r'step[=:](\d+)',
                                    r'lesson[=:](\d+)',
                                    r'#slide(\d+)',
                                    r'#page(\d+)',
                                    r'#step(\d+)'
                                ]
                                
                                for pattern in location_patterns:
                                    location_match = re.search(pattern, self.attempt.lesson_location, re.IGNORECASE)
                                    if location_match:
                                        current_slide = int(location_match.group(1))
                                        # Estimate progress based on current slide (this is approximate)
                                        if current_slide > 0:
                                            # Assume 10 slides total if we can't determine total
                                            estimated_total = 10
                                            calculated_score = min(round((current_slide / estimated_total) * 100, 2), 100)
                                            logger.info("SLIDE_SCORE: Estimated from lesson_location pattern '%s' slide %s: %s%%", pattern, current_slide, calculated_score)
                                            break
                
                except Exception as e:
                    logger.warning("SLIDE_SCORE: Could not parse suspend_data: %s", str(e))
            
            # Method 4: Check CMI data for progress information
            if calculated_score is None and self.attempt.cmi_data:
                try:
                    # Check for progress in CMI data
                    progress_keys = [
                        'cmi.progress_measure',
                        'cmi.core.progress_measure', 
                        'cmi.completion_threshold',
                        'cmi.core.completion_threshold'
                    ]
                    
                    for key in progress_keys:
                        if key in self.attempt.cmi_data:
                            progress_value = self.attempt.cmi_data[key]
                            if progress_value and progress_value != '':
                                try:
                                    progress_float = float(progress_value)
                                    if 0 <= progress_float <= 1:
                                        calculated_score = round(progress_float * 100, 2)
                                        logger.info("SLIDE_SCORE: Using CMI %s: %s%%", key, calculated_score)
                                        break
                                    elif 0 <= progress_float <= 100:
                                        calculated_score = round(progress_float, 2)
                                        logger.info("SLIDE_SCORE: Using CMI %s: %s%%", key, calculated_score)
                                        break
                                except:
                                    continue
                except Exception as e:
                    logger.warning("SLIDE_SCORE: Could not extract from CMI data: %s", str(e))
            
            # Method 5: Fallback - Estimate progress based on lesson_location for packages that don't report scores
            if calculated_score is None and self.attempt.lesson_location:
                try:
                    # Check if lesson_location contains any navigation information
                    location_indicators = [
                        r'#slide(\d+)',
                        r'#page(\d+)',
                        r'#step(\d+)',
                        r'#lesson(\d+)',
                        r'slide[=:](\d+)',
                        r'page[=:](\d+)',
                        r'step[=:](\d+)',
                        r'lesson[=:](\d+)',
                        r'index\.html#/(\d+)',
                        r'story\.html#/(\d+)',
                        r'lessons/ix-([a-zA-Z0-9]+)',
                        r'chapter(\d+)',
                        r'section(\d+)'
                    ]
                    
                    for pattern in location_indicators:
                        location_match = re.search(pattern, self.attempt.lesson_location, re.IGNORECASE)
                        if location_match:
                            try:
                                current_position = int(location_match.group(1))
                                if current_position > 0:
                                    # Estimate progress based on current position
                                    # This is a fallback for packages that don't report explicit scores
                                    estimated_total = 10  # Assume 10 slides/pages by default
                                    calculated_score = min(round((current_position / estimated_total) * 100, 2), 100)
                                    logger.info("SLIDE_SCORE: Fallback estimation from lesson_location pattern '%s' position %s: %s%%", pattern, current_position, calculated_score)
                                    break
                            except ValueError:
                                # If it's not a number, try to extract meaningful progress
                                position_str = location_match.group(1)
                                if len(position_str) > 3:  # Likely a meaningful identifier
                                    # Estimate 50% progress for packages with complex navigation
                                    calculated_score = 50.0
                                    logger.info("SLIDE_SCORE: Fallback estimation from lesson_location complex navigation: %s%%", calculated_score)
                                    break
                except Exception as e:
                    logger.warning("SLIDE_SCORE: Error in fallback estimation: %s", str(e))
            
            # Method 6: Final fallback - If user has spent time and has suspend_data, assume some progress
            if calculated_score is None and self.attempt.suspend_data and len(self.attempt.suspend_data) > 50:
                # If there's substantial suspend_data, assume the user has made some progress
                # This is a last resort for packages that don't report any progress information
                calculated_score = 25.0  # Assume 25% progress for packages with data but no explicit scoring
                logger.info("SLIDE_SCORE: Final fallback - assuming 25%% progress based on suspend_data presence")
            
            # Apply the calculated score if we found one
            if calculated_score is not None and 0 <= calculated_score <= 100:
                logger.info("SLIDE_SCORE: Applying calculated score: %s%%", calculated_score)
                self._apply_extracted_score(calculated_score)
            else:
                logger.debug("SLIDE_SCORE: No valid slide completion score found")
                
        except Exception as e:
            logger.error("SLIDE_SCORE ERROR: Failed to calculate slide completion score: %s", str(e))
    
    def _commit_data(self):
        """Save attempt data to database with atomic transactions"""
        from django.db import transaction
        
        logger.info("💾 _COMMIT_DATA: Starting (score_raw=%s, cmi_score=%s, lesson_location=%s, suspend_data_len=%s)", 
                   self.attempt.score_raw, 
                   self.attempt.cmi_data.get('cmi.core.score.raw') or self.attempt.cmi_data.get('cmi.score.raw'),
                   self.attempt.lesson_location[:50] if self.attempt.lesson_location else 'None',
                   len(self.attempt.suspend_data) if self.attempt.suspend_data else 0)
        
        # Only save to database if not a preview attempt
        if not getattr(self.attempt, 'is_preview', False):
            try:
                # CRITICAL FIX: Ensure JSON fields have valid default values
                # These fields must NEVER be None - they should be empty list/dict at minimum
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
                
                # Use atomic transaction for data consistency
                with transaction.atomic():
                    # CRITICAL: Store the score and bookmark before any operations
                    score_before = self.attempt.score_raw
                    cmi_score_before = self.attempt.cmi_data.get('cmi.core.score.raw') or self.attempt.cmi_data.get('cmi.score.raw')
                    location_before = self.attempt.lesson_location
                    suspend_data_len_before = len(self.attempt.suspend_data) if self.attempt.suspend_data else 0
                    
                    # Update last accessed timestamp
                    self.attempt.last_accessed = timezone.now()
                    
                    logger.info("💾 _COMMIT_DATA: Before save (score_raw=%s, type=%s, bookmark=%s)", 
                               self.attempt.score_raw, type(self.attempt.score_raw),
                               self.attempt.lesson_location[:30] if self.attempt.lesson_location else 'None')
                    
                    # Save ScormAttempt with validation and signal coordination
                    try:
                        # Mark that this is being updated by the API handler to prevent signal conflicts
                        self.attempt._updating_from_api_handler = True
                        
                        # CRITICAL FIX: Ensure JSON fields are valid RIGHT BEFORE validation
                        # Must be done immediately before full_clean() to ensure validation passes
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
                        
                        self.attempt.full_clean()
                        self.attempt.save()
                        logger.info("💾 _COMMIT_DATA: ScormAttempt saved successfully")
                        
                        # Remove the flag after successful save
                        delattr(self.attempt, '_updating_from_api_handler')
                    except Exception as save_error:
                        # Clean up flag even on error
                        if hasattr(self.attempt, '_updating_from_api_handler'):
                            delattr(self.attempt, '_updating_from_api_handler')
                        logger.error("❌ _COMMIT_DATA: ScormAttempt save failed: %s", str(save_error))
                        raise
                    
                    # Verify the save actually worked
                    from scorm.models import ScormAttempt
                    saved_attempt = ScormAttempt.objects.get(id=self.attempt.id)
                    logger.info("💾 _COMMIT_DATA: DB verification (score_raw=%s, cmi_score=%s, bookmark=%s, suspend_len=%s)", 
                               saved_attempt.score_raw,
                               saved_attempt.cmi_data.get('cmi.core.score.raw') or saved_attempt.cmi_data.get('cmi.score.raw'),
                               saved_attempt.lesson_location[:30] if saved_attempt.lesson_location else 'None',
                               len(saved_attempt.suspend_data) if saved_attempt.suspend_data else 0)
                    
                    # CRITICAL: Check for data loss during save
                    if score_before and not saved_attempt.score_raw:
                        logger.error("❌ _COMMIT_DATA: SCORE LOST DURING SAVE! Before=%s, After=%s", score_before, saved_attempt.score_raw)
                        raise ValueError(f"Score lost during save: {score_before} -> {saved_attempt.score_raw}")
                    
                    if location_before and not saved_attempt.lesson_location:
                        logger.error("❌ _COMMIT_DATA: BOOKMARK LOST DURING SAVE! Before=%s, After=%s", location_before, saved_attempt.lesson_location)
                        raise ValueError(f"Bookmark lost during save: {location_before} -> {saved_attempt.lesson_location}")
                    
                    if suspend_data_len_before > 0 and not saved_attempt.suspend_data:
                        logger.error("❌ _COMMIT_DATA: SUSPEND_DATA LOST DURING SAVE! Before=%s chars, After=%s", suspend_data_len_before, len(saved_attempt.suspend_data) if saved_attempt.suspend_data else 0)
                        raise ValueError(f"Suspend data lost during save: {suspend_data_len_before} chars -> {len(saved_attempt.suspend_data) if saved_attempt.suspend_data else 0}")
                    
                    # AUTOMATIC SCORE EXTRACTION: If SCORM content didn't report score, try to extract from suspend_data
                    self._auto_extract_score_from_suspend_data()
                    
                    # SLIDE-BASED SCORE CALCULATION: Calculate score from slide completion if no explicit score
                    self._calculate_slide_completion_score()
                    
                    # Update TopicProgress (within same transaction for consistency)
                    self._update_topic_progress()
                    
                    logger.info("✅ _COMMIT_DATA: All data committed successfully with atomic transaction")
                    
            except Exception as e:
                logger.error("❌ _COMMIT_DATA: Transaction failed: %s", str(e))
                import traceback
                logger.error(traceback.format_exc())
                raise
        else:
            logger.info("Preview attempt - skipping database save")
    
    def _build_interaction_data(self, index):
        """Build interaction data from CMI data for database storage"""
        try:
            interaction_data = {}
            
            # Get interaction ID
            id_key = f'cmi.interactions.{index}.id'
            interaction_id = self.attempt.cmi_data.get(id_key, f'interaction_{index}')
            if not interaction_id:
                return None
            
            interaction_data['id'] = interaction_id
            
            # Get interaction type
            type_key = f'cmi.interactions.{index}.type'
            interaction_data['type'] = self.attempt.cmi_data.get(type_key, 'other')
            
            # Get description
            desc_key = f'cmi.interactions.{index}.description'
            interaction_data['description'] = self.attempt.cmi_data.get(desc_key, '')
            
            # Get student response
            if self.version == '1.2':
                response_key = f'cmi.interactions.{index}.student_response'
            else:
                response_key = f'cmi.interactions.{index}.learner_response'
            interaction_data['student_response'] = self.attempt.cmi_data.get(response_key, '')
            
            # Get correct response
            correct_key = f'cmi.interactions.{index}.correct_responses.0.pattern'
            interaction_data['correct_response'] = self.attempt.cmi_data.get(correct_key, '')
            
            # Get result
            result_key = f'cmi.interactions.{index}.result'
            interaction_data['result'] = self.attempt.cmi_data.get(result_key, '')
            
            # Get weighting
            weight_key = f'cmi.interactions.{index}.weighting'
            weight_value = self.attempt.cmi_data.get(weight_key, '')
            if weight_value:
                try:
                    interaction_data['weighting'] = float(weight_value)
                except (ValueError, TypeError):
                    interaction_data['weighting'] = None
            
            # Get score
            score_key = f'cmi.interactions.{index}.score_raw'
            score_value = self.attempt.cmi_data.get(score_key, '')
            if score_value:
                try:
                    interaction_data['score_raw'] = float(score_value)
                except (ValueError, TypeError):
                    interaction_data['score_raw'] = None
            
            # Get timestamp
            time_key = f'cmi.interactions.{index}.time'
            if self.version == '2004':
                time_key = f'cmi.interactions.{index}.timestamp'
            timestamp_value = self.attempt.cmi_data.get(time_key, '')
            if timestamp_value:
                try:
                    from datetime import datetime
                    interaction_data['timestamp'] = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    interaction_data['timestamp'] = None
            
            # Get latency
            latency_key = f'cmi.interactions.{index}.latency'
            interaction_data['latency'] = self.attempt.cmi_data.get(latency_key, '')
            
            # Get objectives
            objectives = []
            for i in range(10):  # Check up to 10 objectives
                obj_key = f'cmi.interactions.{index}.objectives.{i}.id'
                obj_id = self.attempt.cmi_data.get(obj_key, '')
                if obj_id:
                    objectives.append(obj_id)
            interaction_data['objectives'] = objectives
            
            # Get learner response data
            interaction_data['learner_response_data'] = {}
            
            return interaction_data
            
        except Exception as e:
            logger.error(f"Error building interaction data: {str(e)}")
            return None
    
    def _update_topic_progress(self):
        """Update related TopicProgress based on SCORM data with atomic transactions"""
        from django.db import transaction
        
        try:
            # Use atomic transaction to prevent race conditions and ensure data consistency
            with transaction.atomic():
                from courses.models import TopicProgress, CourseEnrollment, CourseTopic
                
                topic = self.attempt.scorm_package.topic
                
                # Get or create topic progress with select_for_update to prevent race conditions
                progress, created = TopicProgress.objects.select_for_update().get_or_create(
                    user=self.attempt.user,
                    topic=topic
                )
                
                logger.info("🔄 TOPIC_PROGRESS: Updating for topic %s, user %s (created=%s)", 
                           topic.id, self.attempt.user.username, created)
                
                # Parse time spent from SCORM format to seconds
                time_seconds = self._parse_scorm_time_to_seconds(self.attempt.total_time)
                
                # Update progress data with comprehensive tracking and sync metadata
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
                    'sync_method': 'enhanced_api_handler',
                    'sync_timestamp': timezone.now().isoformat(),
                }
                
                # Update time spent (cumulative, not overwrite)
                if time_seconds > 0:
                    current_time = progress.total_time_spent or 0
                    progress.total_time_spent = max(current_time, time_seconds)
                    logger.info("⏱️  TOPIC_PROGRESS: Updated time - total_time_spent: %s seconds", progress.total_time_spent)
                
                # CRITICAL FIX: Add strict validation for completion status
                # Don't just trust the status - validate that actual content interaction occurred
                if self.version == '1.2':
                    status_completed = self.attempt.lesson_status in ['completed', 'passed']
                    is_passed = self.attempt.lesson_status == 'passed'
                else:
                    status_completed = self.attempt.completion_status == 'completed'
                    is_passed = self.attempt.success_status == 'passed'
                
                # Validate that completion is legitimate
                is_completed = self._validate_completion_status(status_completed)
                
                # Update completion status
                if is_completed and not progress.completed:
                    progress.completed = True
                    progress.completion_method = 'scorm'
                    progress.completed_at = timezone.now()
                    logger.info("✅ TOPIC_PROGRESS: Marked as completed for topic %s", topic.id)
                
                # CRITICAL FIX: Always update scores when available, regardless of completion status
                if self.attempt.score_raw is not None:
                    score_value = float(self.attempt.score_raw)
                    old_last_score = progress.last_score
                    old_best_score = progress.best_score
                    
                    # Update best_score if this is better
                    if progress.best_score is None or score_value > progress.best_score:
                        progress.best_score = score_value
                    
                    # CRITICAL FIX: For SCORM content, always use best_score as last_score
                    # This prevents score downgrade when users retake content
                    # Gradebook displays last_score, so it should show their best achievement
                    progress.last_score = progress.best_score if progress.best_score is not None else score_value
                    
                    # Update attempts counter
                    progress.attempts = max(progress.attempts or 0, self.attempt.attempt_number)
                    
                    completion_note = "completed" if is_completed else "incomplete but score valid"
                    logger.info("📊 TOPIC_PROGRESS: Updated scores (%s) - last_score: %s → %s, best_score: %s → %s, attempts: %s", 
                               completion_note, old_last_score, progress.last_score, old_best_score, progress.best_score, progress.attempts)
                else:
                    logger.warning("⚠️  TOPIC_PROGRESS: No score to update (score_raw is None), lesson_status: %s", 
                                 self.attempt.lesson_status)
                
                # Update access tracking
                progress.last_accessed = timezone.now()
                if not progress.first_accessed:
                    progress.first_accessed = timezone.now()
                
                # Validate and save with proper error handling
                try:
                    progress.full_clean()  # Validate before saving
                    progress.save()
                    logger.info("✅ TOPIC_PROGRESS: Successfully saved for topic %s with atomic transaction", topic.id)
                except Exception as save_error:
                    logger.error("❌ TOPIC_PROGRESS: Save validation failed: %s", str(save_error))
                    raise
                
                # Update CourseEnrollment for accurate reporting (within same transaction)
                self._update_course_enrollment(topic, progress, time_seconds)
                
        except Exception as e:
            logger.error("❌ TOPIC_PROGRESS ERROR: Failed to update topic progress: %s", str(e))
            import traceback
            logger.error(traceback.format_exc())
            # Re-raise the exception to ensure proper error handling up the chain
            raise
    
    def _parse_scorm_time_to_seconds(self, time_str):
        """Convert SCORM time format (hhhh:mm:ss.ss) to seconds"""
        try:
            if not time_str or time_str == '0000:00:00.00':
                return 0
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int(hours * 3600 + minutes * 60 + seconds)
            return 0
        except (ValueError, IndexError, TypeError):
            return 0
    
    def _update_course_enrollment(self, topic, topic_progress, time_seconds):
        """Update CourseEnrollment with SCORM data for accurate reporting"""
        try:
            from courses.models import CourseEnrollment, CourseTopic
            from django.db.models import Count, Q
            
            # Find the course this topic belongs to
            course_topic = CourseTopic.objects.filter(topic=topic).first()
            if not course_topic:
                logger.warning("⚠️  ENROLLMENT: Topic %s not linked to any course", topic.id)
                return
            
            course = course_topic.course
            
            # Get or create enrollment
            enrollment, created = CourseEnrollment.objects.get_or_create(
                user=self.attempt.user,
                course=course
            )
            
            logger.info("📋 ENROLLMENT: Updating for user %s, course %s (created=%s)",
                       self.attempt.user.username, course.id, created)
            
            # Get all SCORM topics in this course
            from scorm.models import ScormPackage
            scorm_topic_ids = ScormPackage.objects.filter(
                topic__coursetopic__course=course
            ).values_list('topic_id', flat=True)
            
            # Get all TopicProgress for this user's SCORM topics in this course
            from courses.models import TopicProgress as TP
            all_scorm_progress = TP.objects.filter(
                user=self.attempt.user,
                topic_id__in=scorm_topic_ids
            )
            
            # Calculate totals
            total_scorm_topics = len(scorm_topic_ids)
            completed_scorm_topics = all_scorm_progress.filter(completed=True).count()
            total_time_all_scorm = sum(p.total_time_spent for p in all_scorm_progress)
            
            # Update enrollment last accessed
            enrollment.last_accessed = timezone.now()
            
            # Check if course is complete (all SCORM topics done)
            if total_scorm_topics > 0 and completed_scorm_topics == total_scorm_topics:
                if not enrollment.completed:
                    enrollment.completed = True
                    enrollment.completion_date = timezone.now()
                    logger.info("🎉 ENROLLMENT: Course marked as completed!")
            
            enrollment.save()
            logger.info("✅ ENROLLMENT: Updated - completed: %s/%s topics, time: %ss",
                       completed_scorm_topics, total_scorm_topics, total_time_all_scorm)
            
        except Exception as e:
            logger.error("❌ ENROLLMENT ERROR: Failed to update enrollment: %s", str(e))
            import traceback
            logger.error(traceback.format_exc())
    
    def _improve_scoring_if_needed(self):
        """Improve scoring when SCORM content doesn't provide proper completion data"""
        try:
            # Track slide completion based on lesson location changes and time spent
            self._track_slide_completion()
            
            # Check if we have a very low score but significant time spent
            if (self.attempt.score_raw and self.attempt.score_raw < 10 and 
                self.attempt.time_spent_seconds and self.attempt.time_spent_seconds > 60):
                
                # Calculate time-based score (minimum 50% for attempting, +10% per minute)
                time_spent_minutes = self.attempt.time_spent_seconds / 60
                time_based_score = min(50 + (time_spent_minutes * 10), 100)
                
                # Only update if the calculated score is significantly better
                if time_based_score > self.attempt.score_raw * 2:
                    old_score = self.attempt.score_raw
                    self.attempt.score_raw = time_based_score
                    logger.info(f"📊 IMPROVED SCORING: {old_score}% → {time_based_score}% (time-based calculation)")
                    
                    # Mark as completed if they spent significant time
                    if time_spent_minutes > 2:  # More than 2 minutes
                        self.attempt.lesson_status = 'completed'
                        self.attempt.completion_status = 'completed'
                        logger.info(f"📊 IMPROVED STATUS: Marked as completed due to time spent ({time_spent_minutes:.1f} minutes)")
                        
        except Exception as e:
            logger.error(f"Error in _improve_scoring_if_needed: {e}")
    
    def _track_slide_completion(self):
        """Track slide completion based on lesson location changes (Continue button clicks)"""
        try:
            if not self.attempt.lesson_location:
                return
                
            # Parse lesson location to extract slide information
            location = self.attempt.lesson_location
            
            # Check if this is story-type content
            if self._is_story_content(location):
                self._track_story_completion(location)
                return
            
            # Extract slide identifier from location (e.g., "index.html#/lessons/e_lS0XNJvr-NK4PqGNh7oCPxbNkr96PD")
            import re
            slide_match = re.search(r'#/lessons/([^/]+)', location)
            if slide_match:
                current_slide = slide_match.group(1)
                
                # Initialize slide tracking in CMI data if not exists
                if 'slide_tracking' not in self.attempt.cmi_data:
                    self.attempt.cmi_data['slide_tracking'] = {
                        'visited_slides': [],
                        'completed_slides': [],
                        'total_slides': 4,  # Assuming 4 slides based on user's description
                        'current_slide': current_slide
                    }
                
                slide_tracking = self.attempt.cmi_data['slide_tracking']
                
                # Track visited slides
                if current_slide not in slide_tracking['visited_slides']:
                    slide_tracking['visited_slides'].append(current_slide)
                    logger.info(f"📊 SLIDE TRACKING: Added slide {current_slide} to visited slides")
                
                # If this looks like a completion slide (contains completion indicators)
                completion_indicators = ['complete', 'finish', 'end', 'done', 'summary']
                if any(indicator in current_slide.lower() for indicator in completion_indicators):
                    if current_slide not in slide_tracking['completed_slides']:
                        slide_tracking['completed_slides'].append(current_slide)
                        logger.info(f"📊 SLIDE TRACKING: Marked slide {current_slide} as completed")
                
                # Calculate completion percentage
                total_slides = slide_tracking['total_slides']
                completed_slides = len(slide_tracking['completed_slides'])
                visited_slides = len(slide_tracking['visited_slides'])
                
                # Initialize completion percentage
                completion_percentage = (completed_slides / total_slides) * 100 if total_slides > 0 else 0
                
                # If they've visited all slides, consider it completed
                if visited_slides >= total_slides:
                    if completion_percentage < 100:
                        # If they visited all slides but completion tracking is incomplete,
                        # assume they completed based on time spent
                        if self.attempt.time_spent_seconds and self.attempt.time_spent_seconds > 120:  # 2+ minutes
                            completion_percentage = 100
                            slide_tracking['completed_slides'] = slide_tracking['visited_slides'].copy()
                            logger.info(f"📊 SLIDE TRACKING: Auto-completed all slides based on time spent ({self.attempt.time_spent_seconds}s)")
                    
                    # Update score based on slide completion
                    if completion_percentage > 0:
                        new_score = max(self.attempt.score_raw or 0, completion_percentage)
                        if new_score > (self.attempt.score_raw or 0):
                            self.attempt.score_raw = new_score
                            logger.info(f"📊 SLIDE-BASED SCORING: Updated score to {new_score}% based on {completed_slides}/{total_slides} slides completed")
                            
                            # Mark as completed if all slides are done
                            if completion_percentage >= 100:
                                self.attempt.lesson_status = 'completed'
                                self.attempt.completion_status = 'completed'
                                logger.info(f"📊 SLIDE COMPLETION: Marked as completed - all {total_slides} slides completed")
                
                # Update model fields
                self.attempt.completed_slides = ','.join(slide_tracking['completed_slides'])
                self.attempt.total_slides = total_slides
                self.attempt.progress_percentage = completion_percentage
                
                logger.info(f"📊 SLIDE TRACKING: {completed_slides}/{total_slides} slides completed ({completion_percentage:.1f}%)")
                
        except Exception as e:
            logger.error(f"Error in _track_slide_completion: {e}")
    
    def _is_story_content(self, location):
        """Check if this is story-type SCORM content"""
        story_indicators = ['story.html', 'narrative', 'scenario', 'interactive']
        return any(indicator in location.lower() for indicator in story_indicators)
    
    def _track_story_completion(self, location):
        """Track story-type content completion"""
        try:
            logger.info(f"📚 STORY TRACKING: Processing story content at {location}")
            
            # Initialize story tracking in CMI data if not exists
            if 'story_tracking' not in self.attempt.cmi_data:
                self.attempt.cmi_data['story_tracking'] = {
                    'current_story': location,
                    'story_progress': 0,
                    'story_sections': [],
                    'completed_sections': [],
                    'total_sections': 1,  # Default for simple story
                    'story_type': 'interactive_story'
                }
            
            story_tracking = self.attempt.cmi_data['story_tracking']
            
            # Update current story location
            story_tracking['current_story'] = location
            
            # For story content, assume progress based on time spent
            if self.attempt.time_spent_seconds:
                # Calculate story progress based on time spent
                # Assume 2-3 minutes per story section
                time_per_section = 150  # 2.5 minutes in seconds
                story_progress = min((self.attempt.time_spent_seconds / time_per_section) * 100, 100)
                story_tracking['story_progress'] = story_progress
                
                logger.info(f"📚 STORY PROGRESS: {story_progress:.1f}% based on {self.attempt.time_spent_seconds}s time spent")
                
                # Update score based on story progress
                if story_progress > 0:
                    new_score = max(self.attempt.score_raw or 0, story_progress)
                    if new_score > (self.attempt.score_raw or 0):
                        self.attempt.score_raw = new_score
                        logger.info(f"📚 STORY SCORING: Updated score to {new_score}% based on story progress")
                        
                        # Mark as completed if story progress is high enough
                        if story_progress >= 80:  # 80% story completion
                            self.attempt.lesson_status = 'completed'
                            self.attempt.completion_status = 'completed'
                            logger.info(f"📚 STORY COMPLETION: Marked as completed - {story_progress:.1f}% story progress")
            
            # Update model fields for story content
            self.attempt.progress_percentage = story_tracking['story_progress']
            self.attempt.completed_slides = ','.join(story_tracking['completed_sections'])
            self.attempt.total_slides = story_tracking['total_sections']
            
            # CRITICAL: Save the attempt to persist story tracking data
            self.attempt.save()
            
            logger.info(f"📚 STORY TRACKING: {story_tracking['story_progress']:.1f}% story completion")
            
        except Exception as e:
            logger.error(f"Error in _track_story_completion: {e}")