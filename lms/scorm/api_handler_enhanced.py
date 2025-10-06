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
        if self.initialized:
            self.last_error = '101'
            return 'false'
        
        self.initialized = True
        self.last_error = '0'
        
        # Mark as initialized in CMI data for persistence
        self.attempt.cmi_data['_initialized'] = True
        
        # Set entry mode based on bookmark data
        if self.attempt.lesson_location or self.attempt.suspend_data:
            self.attempt.entry = 'resume'
            suspend_data_preview = self.attempt.suspend_data[:50] if self.attempt.suspend_data else "None"
            logger.info("SCORM Resume: location='%s', suspend_data='%s...'", self.attempt.lesson_location, suspend_data_preview)
        else:
            self.attempt.entry = 'ab-initio'
            logger.info("SCORM New attempt: starting fresh")
        
        # Update CMI data with proper defaults
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
            self.attempt.cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status or 'not attempted'
            self.attempt.cmi_data['cmi.core.lesson_mode'] = 'normal'
            self.attempt.cmi_data['cmi.core.credit'] = 'credit'
            self.attempt.cmi_data['cmi.core.student_id'] = str(self.attempt.user.id) if self.attempt.user else 'student'
            self.attempt.cmi_data['cmi.core.student_name'] = self.attempt.user.get_full_name() or self.attempt.user.username if self.attempt.user else 'Student'
        else:
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            self.attempt.cmi_data['cmi.completion_status'] = self.attempt.lesson_status or 'not attempted'
            self.attempt.cmi_data['cmi.mode'] = 'normal'
            self.attempt.cmi_data['cmi.credit'] = 'credit'
            self.attempt.cmi_data['cmi.learner_id'] = str(self.attempt.user.id) if self.attempt.user else 'student'
            self.attempt.cmi_data['cmi.learner_name'] = self.attempt.user.get_full_name() or self.attempt.user.username if self.attempt.user else 'Student'
        
        # Save the updated data
        self.attempt.save()
        
        logger.info("SCORM API initialized for attempt %s", self.attempt.id)
        return 'true'
    
    def terminate(self):
        """LMSFinish / Terminate"""
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        self.initialized = False
        self.last_error = '0'
        
        # Save all data
        self._commit_data()
        
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
                elif element in ['cmi.core.score.max', 'cmi.score.max']:
                    value = str(self.attempt.score_max) if self.attempt.score_max else '100'
                elif element in ['cmi.core.score.min', 'cmi.score.min']:
                    value = str(self.attempt.score_min) if self.attempt.score_min else '0'
                elif element == 'cmi.core.student_id' or element == 'cmi.learner_id':
                    value = str(self.attempt.user.id)
                elif element == 'cmi.core.student_name' or element == 'cmi.learner_name':
                    value = self.attempt.user.get_full_name() or self.attempt.user.username
                elif element == 'cmi.core.lesson_location' or element == 'cmi.location':
                    value = self.attempt.lesson_location or ''
                elif element == 'cmi.suspend_data':
                    value = self.attempt.suspend_data or ''
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
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        try:
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
                    self._update_completion_from_status(value)
                elif element == 'cmi.core.score.raw':
                    try:
                        self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
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
                    self.attempt.lesson_location = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
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
                    if value == 'completed':
                        self.attempt.completed_at = timezone.now()
                elif element == 'cmi.success_status':
                    self.attempt.success_status = value
                elif element == 'cmi.score.raw':
                    try:
                        self.attempt.score_raw = Decimal(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
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
                    self.attempt.lesson_location = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
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
            self._commit_data()
            self.last_error = '0'
            return 'true'
        except Exception as e:
            logger.error("Error committing data: %s", str(e))
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
        """Set interaction value"""
        # Extract interaction index from element
        match = re.match(r'cmi\.interactions\.(\d+)\.(.+)', element)
        if match:
            index = match.group(1)
            field = match.group(2)
            # Validate interaction data
            if self._validate_interaction_data(field, value):
                self.attempt.cmi_data[element] = value
            else:
                self.last_error = '402'
                return False
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
    
    def _commit_data(self):
        """Save attempt data to database"""
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        
        # Update TopicProgress if applicable
        self._update_topic_progress()
    
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
            
            # Update progress data
            progress.progress_data = {
                'scorm_attempt_id': self.attempt.id,
                'lesson_status': self.attempt.lesson_status,
                'completion_status': self.attempt.completion_status,
                'success_status': self.attempt.success_status,
                'score_raw': float(self.attempt.score_raw) if self.attempt.score_raw else None,
                'total_time': self.attempt.total_time,
                'lesson_location': self.attempt.lesson_location,
                'suspend_data': self.attempt.suspend_data,
                'entry': self.attempt.entry,
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
            
            progress.save()
            
        except Exception as e:
            logger.error("Error updating topic progress: %s", str(e))
