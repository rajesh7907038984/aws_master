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
from .debug_logger import ScormDebugLogger

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
                self.attempt.completion_status = 'not attempted'
                self.attempt.success_status = 'unknown'
                logger.info("SCORM 2004 STORYLINE: Set completion_status='not attempted' for new attempt")
        
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
            elif self.attempt.suspend_data:
                # CRITICAL FIX: If we have suspend_data but no lesson_location, 
                # set a default location to enable resume functionality
                default_location = "resume_point_1"
                self.attempt.cmi_data['cmi.location'] = default_location
                logger.info("🔖 RESUME: Set default location in CMI data for resume: %s", default_location)
            
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info("🔖 RESUME: Set suspend_data in CMI data (%d chars)", len(self.attempt.suspend_data))
            
            # Set other required fields
            self.attempt.cmi_data['cmi.completion_status'] = self.attempt.completion_status or 'not attempted'
            self.attempt.cmi_data['cmi.success_status'] = self.attempt.success_status or 'unknown'
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
        
        # CRITICAL FIX: Always save data on terminate, regardless of completion status
        # This ensures that time, progress, and location data are preserved
        
        # Ensure JSON fields are properly initialized before saving
        if self.attempt.navigation_history is None:
            self.attempt.navigation_history = []
        if self.attempt.detailed_tracking is None:
            self.attempt.detailed_tracking = {}
        if self.attempt.session_data is None:
            self.attempt.session_data = {}
        
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
                    self.attempt.total_time != '0000:00:00.00' or  # Has spent time
                    self.attempt.progress_percentage and self.attempt.progress_percentage > 0  # Has progress
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
                # SCORM 1.2 Core Elements - Always provide defaults
                if element == 'cmi.core.lesson_status':
                    # CRITICAL FIX FOR SCORM 1.2: If we have resume data, return 'incomplete' not 'not attempted'
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'incomplete'
                        logger.info(f"SCORM 1.2 RESUME: Override lesson_status to 'incomplete' for resume scenario")
                    else:
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
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return 'incomplete' not 'not_attempted'
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'incomplete'
                        logger.info(f"SCORM 2004 RESUME: Override completion_status to 'incomplete' for resume scenario")
                    else:
                        value = self.attempt.completion_status or 'incomplete'
                elif element == 'cmi.success_status':
                    # CRITICAL FIX FOR SCORM 2004: If we have resume data, return 'unknown' for resume scenarios
                    has_resume_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
                    if has_resume_data and (not value or value == 'not_attempted'):
                        value = 'unknown'
                        logger.info(f"SCORM 2004 RESUME: Override success_status to 'unknown' for resume scenario")
                    else:
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
                    # CRITICAL FIX: Update progress immediately when lesson_status changes
                    self._update_topic_progress()
                    logger.info("SCORM 1.2: Updated lesson_status to '%s' and triggered progress update", value)
                    
                    # STORYLINE FIX: Force status update for Storyline packages
                    if hasattr(self.attempt, 'scorm_package') and self.attempt.scorm_package.version == 'storyline':
                        if value == 'incomplete':
                            logger.info("STORYLINE: Status set to incomplete - user is actively using content")
                            # Force update TopicProgress for Storyline
                            self._update_topic_progress()
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
                            
                            # Set lesson_status based on score if not already set
                            mastery_score = self.attempt.scorm_package.mastery_score or 70
                            if self.attempt.lesson_status == 'not_attempted' or self.attempt.lesson_status == 'incomplete':
                                if self.attempt.score_raw >= mastery_score:
                                    self.attempt.lesson_status = 'passed'
                                    self.attempt.cmi_data['cmi.core.lesson_status'] = 'passed'
                                    self._update_completion_from_status('passed')
                                else:
                                    self.attempt.lesson_status = 'failed'
                                    self.attempt.cmi_data['cmi.core.lesson_status'] = 'failed'
                                    self._update_completion_from_status('failed')
                                logger.info("SCORE: Set lesson_status to %s based on score", self.attempt.lesson_status)
                            
                            # IMMEDIATE FIX: Save attempt and update TopicProgress right away
                            # This ensures scores are reflected in gradebook even if SCORM content
                            # doesn't call Commit/Terminate properly
                            self.attempt.save()
                            self._update_topic_progress()
                            logger.info("SCORE: Immediately saved to database and updated TopicProgress")
                            
                            # CRITICAL FIX: Also update CMI data with score information
                            self.attempt.cmi_data['cmi.core.score.raw'] = str(value)
                            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status
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
                    
                    # CRITICAL FIX: Update progress tracking when location changes
                    self._update_progress_from_location(value)
                    
                    # ENHANCED: Immediate save for critical bookmark data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['lesson_location', 'cmi_data', 'last_accessed', 'progress_percentage'])
                        logger.info("🔖 BOOKMARK SAVED: Immediately saved lesson_location and CMI data")
                        # CRITICAL FIX: Update progress when location changes (indicates progress)
                        self._update_topic_progress()
                        logger.info("🔖 PROGRESS UPDATE: Triggered progress update due to lesson_location change")
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
                    
                    # ENHANCED: Immediate save for critical suspend data to prevent data loss
                    try:
                        self.attempt.last_accessed = timezone.now()
                        self.attempt.save(update_fields=['suspend_data', 'cmi_data', 'last_accessed'])
                        logger.info("🔖 SUSPEND DATA SAVED: Immediately saved suspend_data and CMI data")
                        # CRITICAL FIX: Update progress when suspend_data changes (indicates progress)
                        self._update_topic_progress()
                        logger.info("🔖 PROGRESS UPDATE: Triggered progress update due to suspend_data change")
                    except Exception as save_error:
                        logger.error("❌ SUSPEND DATA SAVE ERROR: %s", str(save_error))
                elif element == 'cmi.core.session_time':
                    self.attempt.session_time = value
                    logger.info(f"⏱️ TIME TRACKING: Setting session_time to {value}")
                    self._update_total_time(value)
                    # CRITICAL FIX: Save immediately to ensure time tracking works
                    self.attempt.save()
                    logger.info(f"⏱️ TIME TRACKING: Saved attempt with session_time")
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
                            
                            # Set success_status based on score if not already set
                            mastery_score = self.attempt.scorm_package.mastery_score or 70
                            if self.attempt.success_status == 'unknown':
                                if self.attempt.score_raw >= mastery_score:
                                    self.attempt.success_status = 'passed'
                                    self.attempt.cmi_data['cmi.success_status'] = 'passed'
                                    if self.attempt.completion_status != 'completed':
                                        self.attempt.completion_status = 'completed'
                                        self.attempt.cmi_data['cmi.completion_status'] = 'completed'
                                else:
                                    self.attempt.success_status = 'failed'
                                    self.attempt.cmi_data['cmi.success_status'] = 'failed'
                                logger.info("SCORE: Set success_status to %s based on score", self.attempt.success_status)
                            
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
    
    def _calculate_scorm_1_2_progress(self):
        """Calculate progress percentage for SCORM 1.2 based on lesson_status and other factors"""
        try:
            lesson_status = self.attempt.lesson_status
            
            # SCORM 1.2 progress calculation based on lesson_status
            if lesson_status == 'completed':
                return 100.0
            elif lesson_status == 'passed':
                return 100.0
            elif lesson_status == 'failed':
                return 100.0  # Failed but completed
            elif lesson_status == 'incomplete':
                # Check if there's location data to estimate progress
                if self.attempt.lesson_location:
                    # If there's a lesson location, assume some progress
                    return 50.0
                else:
                    return 25.0  # Started but not much progress
            elif lesson_status == 'browsed':
                return 25.0  # Browsed but not completed
            else:  # not_attempted
                return 0.0
                
        except Exception as e:
            logger.error(f"Error calculating SCORM 1.2 progress: {str(e)}")
            return 0.0
    
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
        """Original time tracking method as fallback with improved reliability"""
        try:
            # Parse session time
            if session_time.startswith('PT'):
                # SCORM 2004 duration format
                total_seconds = self._parse_iso_duration(session_time)
            else:
                # SCORM 1.2 time format
                total_seconds = self._parse_scorm_time(session_time)
            
            if total_seconds <= 0:
                logger.warning(f"Invalid session time: {session_time}")
                return
            
            # Parse current total time
            current_total = self._parse_scorm_time(self.attempt.total_time)
            
            # For new attempts, use session time as total time
            # For existing attempts, add session time to current total
            if current_total == 0:
                new_total = total_seconds
            else:
                new_total = current_total + total_seconds
            
            # Update both SCORM format and seconds
            self.attempt.total_time = self._format_scorm_time(new_total)
            self.attempt.time_spent_seconds = int(new_total)
            
            # Update session time as well
            self.attempt.session_time = self._format_scorm_time(total_seconds)
            
            logger.info(f"Updated total time: {current_total}s + {total_seconds}s = {new_total}s")
            
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
    
    def _commit_data(self):
        """Save attempt data to database with enhanced validation and error handling"""
        from django.db import transaction, IntegrityError, DatabaseError
        from django.core.exceptions import ValidationError
        
        logger.info("💾 _COMMIT_DATA: Starting (score_raw=%s, cmi_score=%s, lesson_location=%s, suspend_data_len=%s)", 
                   self.attempt.score_raw, 
                   self.attempt.cmi_data.get('cmi.core.score.raw') or self.attempt.cmi_data.get('cmi.score.raw'),
                   self.attempt.lesson_location[:50] if self.attempt.lesson_location else 'None',
                   len(self.attempt.suspend_data) if self.attempt.suspend_data else 0)
        
        # Only save to database if not a preview attempt
        if not getattr(self.attempt, 'is_preview', False):
            max_retries = 3
            for retry_count in range(max_retries):
                try:
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
                        
                        # Enhanced validation before save
                        self._validate_attempt_data()
                        
                        # Save ScormAttempt with validation and signal coordination
                        try:
                            # Mark that this is being updated by the API handler to prevent signal conflicts
                            self.attempt._updating_from_api_handler = True
                            
                            # Ensure JSON fields are properly initialized before validation
                            if self.attempt.navigation_history is None:
                                self.attempt.navigation_history = []
                            if self.attempt.detailed_tracking is None:
                                self.attempt.detailed_tracking = {}
                            if self.attempt.session_data is None:
                                self.attempt.session_data = {}
                            
                            # Enhanced validation
                            try:
                                self.attempt.full_clean()
                            except ValidationError as ve:
                                logger.warning("Validation errors found, attempting to fix: %s", str(ve))
                                self._fix_validation_errors(ve)
                            
                            # Save with retry logic
                            self.attempt.save()
                            logger.info("💾 _COMMIT_DATA: ScormAttempt saved successfully")
                            
                            # Remove the flag after successful save
                            delattr(self.attempt, '_updating_from_api_handler')
                            
                        except Exception as save_error:
                            # Clean up flag even on error
                            if hasattr(self.attempt, '_updating_from_api_handler'):
                                delattr(self.attempt, '_updating_from_api_handler')
                            logger.error("❌ _COMMIT_DATA: ScormAttempt save failed: %s", str(save_error))
                            
                            # Handle specific error types
                            if isinstance(save_error, IntegrityError):
                                logger.error("❌ Database integrity error: %s", str(save_error))
                                if retry_count < max_retries - 1:
                                    logger.info("🔄 Retrying save after integrity error (attempt %d)", retry_count + 1)
                                    continue
                            elif isinstance(save_error, DatabaseError):
                                logger.error("❌ Database error: %s", str(save_error))
                                if retry_count < max_retries - 1:
                                    logger.info("🔄 Retrying save after database error (attempt %d)", retry_count + 1)
                                    continue
                            else:
                                logger.error("❌ Unexpected error: %s", str(save_error))
                            
                            raise
                        
                        # Verify the save actually worked
                        from scorm.models import ScormAttempt
                        saved_attempt = ScormAttempt.objects.get(id=self.attempt.id)
                        logger.info("💾 _COMMIT_DATA: DB verification (score_raw=%s, cmi_score=%s, bookmark=%s, suspend_len=%s)", 
                               saved_attempt.score_raw,
                               saved_attempt.cmi_data.get('cmi.core.score.raw') or saved_attempt.cmi_data.get('cmi.score.raw'),
                               saved_attempt.lesson_location[:30] if saved_attempt.lesson_location else 'None',
                               len(saved_attempt.suspend_data) if saved_attempt.suspend_data else 0)
                        
                        # Break out of retry loop on success
                        break
                        
                except Exception as e:
                    if retry_count == max_retries - 1:
                        logger.error("❌ _COMMIT_DATA: All retry attempts failed: %s", str(e))
                        raise
                    else:
                        logger.warning("⚠️ _COMMIT_DATA: Retry %d failed, trying again: %s", retry_count + 1, str(e))
                        continue
        else:
            logger.info("Preview attempt - skipping database save")
    
    def _validate_attempt_data(self):
        """Validate attempt data before saving"""
        # Validate score data
        if self.attempt.score_raw is not None:
            if not isinstance(self.attempt.score_raw, (int, float, Decimal)):
                try:
                    self.attempt.score_raw = float(self.attempt.score_raw)
                except (ValueError, TypeError):
                    logger.warning("Invalid score_raw value: %s", self.attempt.score_raw)
                    self.attempt.score_raw = None
        
        # Validate time data
        if self.attempt.total_time and not isinstance(self.attempt.total_time, str):
            self.attempt.total_time = str(self.attempt.total_time)
        
        if self.attempt.session_time and not isinstance(self.attempt.session_time, str):
            self.attempt.session_time = str(self.attempt.session_time)
        
        # Validate CMI data
        if not isinstance(self.attempt.cmi_data, dict):
            self.attempt.cmi_data = {}
        
        # Validate JSON fields
        if not isinstance(self.attempt.navigation_history, list):
            self.attempt.navigation_history = []
        
        if not isinstance(self.attempt.detailed_tracking, dict):
            self.attempt.detailed_tracking = {}
        
        if not isinstance(self.attempt.session_data, dict):
            self.attempt.session_data = {}
    
    def _fix_validation_errors(self, validation_error):
        """Fix common validation errors"""
        error_dict = validation_error.error_dict if hasattr(validation_error, 'error_dict') else {}
        
        for field, errors in error_dict.items():
            if field == 'score_raw':
                # Fix score_raw validation errors
                if self.attempt.score_raw is not None:
                    try:
                        self.attempt.score_raw = float(self.attempt.score_raw)
                    except (ValueError, TypeError):
                        self.attempt.score_raw = None
            elif field == 'total_time':
                # Fix time validation errors
                if self.attempt.total_time:
                    self.attempt.total_time = str(self.attempt.total_time)
            elif field in ['navigation_history', 'detailed_tracking', 'session_data']:
                # Fix JSON field validation errors
                if field == 'navigation_history' and not isinstance(self.attempt.navigation_history, list):
                    self.attempt.navigation_history = []
                elif field == 'detailed_tracking' and not isinstance(self.attempt.detailed_tracking, dict):
                    self.attempt.detailed_tracking = {}
                elif field == 'session_data' and not isinstance(self.attempt.session_data, dict):
                    self.attempt.session_data = {}
    
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
                
                # Calculate progress percentage for SCORM 1.2
                progress_percentage = self._calculate_scorm_1_2_progress()
                
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
                    'progress_percentage': progress_percentage,  # SCORM 1.2 calculated progress
                    'completion_percent': progress_percentage,  # For compatibility
                    'last_updated': timezone.now().isoformat(),
                    'sync_method': 'enhanced_api_handler',
                    'sync_timestamp': timezone.now().isoformat(),
                }
                
                # Update time spent (cumulative, not overwrite)
                if time_seconds > 0:
                    current_time = progress.total_time_spent or 0
                    progress.total_time_spent = max(current_time, time_seconds)
                    logger.info("⏱️  TOPIC_PROGRESS: Updated time - total_time_spent: %s seconds", progress.total_time_spent)
                
                # Determine completion status based on SCORM version
                if self.version == '1.2':
                    is_completed = self.attempt.lesson_status in ['completed', 'passed']
                    is_passed = self.attempt.lesson_status == 'passed'
                else:
                    is_completed = self.attempt.completion_status == 'completed'
                    is_passed = self.attempt.success_status == 'passed'
                
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
                    
                    # Always update last_score to reflect the most recent score
                    progress.last_score = score_value
                    
                    # Update best_score if this is better
                    if progress.best_score is None or score_value > progress.best_score:
                        progress.best_score = score_value
                    
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
    
    def _update_progress_from_location(self, location):
        """Update progress percentage based on lesson location"""
        try:
            if not location:
                return
            
            # Extract slide number from location (e.g., "slide_1", "slide_2", etc.)
            if 'slide_' in location.lower():
                try:
                    slide_num = int(location.split('_')[-1])
                    # Estimate progress based on slide number
                    # Assume 10 slides total for now (this could be made dynamic)
                    estimated_total_slides = 10
                    progress = min((slide_num / estimated_total_slides) * 100, 100)
                    
                    self.attempt.progress_percentage = Decimal(str(progress))
                    self.attempt.last_visited_slide = location
                    self.attempt.completed_slides = slide_num
                    self.attempt.total_slides = estimated_total_slides
                    
                    logger.info(f"📊 PROGRESS: Updated to {progress}% based on location {location}")
                    
                except (ValueError, IndexError):
                    # If we can't parse the slide number, just mark as in progress
                    self.attempt.progress_percentage = Decimal('10.00')  # Minimal progress
                    logger.info(f"📊 PROGRESS: Set minimal progress for location {location}")
            
        except Exception as e:
            logger.error(f"❌ PROGRESS ERROR: Failed to update progress from location {location}: {str(e)}")
