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
        
        # Initialize CMI data if empty
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = self._initialize_cmi_data()
    
    def _initialize_cmi_data(self):
        """Initialize CMI data structure based on SCORM version"""
        if self.version == '1.2':
            return {
                'cmi.core.student_id': str(self.attempt.user.id),
                'cmi.core.student_name': self.attempt.user.get_full_name() or self.attempt.user.username,
                'cmi.core.lesson_location': self.attempt.lesson_location or '',
                'cmi.core.credit': 'credit',
                'cmi.core.lesson_status': self.attempt.lesson_status,
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
            return 'false'
        
        self.initialized = True
        self.last_error = '0'
        
        # Set entry mode
        if self.attempt.lesson_location or self.attempt.suspend_data:
            self.attempt.entry = 'resume'
        else:
            self.attempt.entry = 'ab-initio'
        
        if self.version == '1.2':
            self.attempt.cmi_data['cmi.core.entry'] = self.attempt.entry
        else:
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
        
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
        """LMSGetValue / GetValue"""
        if not self.initialized:
            self.last_error = '301'
            return ''
        
        try:
            value = self.attempt.cmi_data.get(element, '')
            self.last_error = '0'
            return str(value)
        except Exception as e:
            logger.error(f"Error getting value for {element}: {str(e)}")
            self.last_error = '101'
            return ''
    
    def set_value(self, element, value):
        """LMSSetValue / SetValue"""
        if not self.initialized:
            self.last_error = '301'
            return 'false'
        
        try:
            # Store the value
            self.attempt.cmi_data[element] = value
            
            # Update model fields based on element
            if self.version == '1.2':
                if element == 'cmi.core.lesson_status':
                    self.attempt.lesson_status = value
                    self._update_completion_from_status(value)
                elif element == 'cmi.core.score.raw':
                    self.attempt.score_raw = Decimal(value) if value else None
                elif element == 'cmi.core.score.max':
                    self.attempt.score_max = Decimal(value) if value else None
                elif element == 'cmi.core.score.min':
                    self.attempt.score_min = Decimal(value) if value else None
                elif element == 'cmi.core.lesson_location':
                    self.attempt.lesson_location = value
                elif element == 'cmi.core.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.core.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
            else:  # SCORM 2004
                if element == 'cmi.completion_status':
                    self.attempt.completion_status = value
                    if value == 'completed':
                        self.attempt.completed_at = timezone.now()
                elif element == 'cmi.success_status':
                    self.attempt.success_status = value
                elif element == 'cmi.score.raw':
                    self.attempt.score_raw = Decimal(value) if value else None
                elif element == 'cmi.score.max':
                    self.attempt.score_max = Decimal(value) if value else None
                elif element == 'cmi.score.min':
                    self.attempt.score_min = Decimal(value) if value else None
                elif element == 'cmi.score.scaled':
                    self.attempt.score_scaled = Decimal(value) if value else None
                elif element == 'cmi.location':
                    self.attempt.lesson_location = value
                elif element == 'cmi.session_time':
                    self.attempt.session_time = value
                    self._update_total_time(value)
                elif element == 'cmi.exit':
                    self.attempt.exit_mode = value
                elif element == 'cmi.suspend_data':
                    self.attempt.suspend_data = value
            
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
        return self.SCORM_12_ERRORS.get(error_code, 'Unknown error')
    
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
            
            # Format back to SCORM time
            self.attempt.total_time = self._format_scorm_time(new_total)
            
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
        except:
            return 0
    
    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration format (PT1H30M45S) to seconds"""
        try:
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
        except:
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
                'score_raw': float(self.attempt.score_raw) if self.attempt.score_raw else None,
                'total_time': self.attempt.total_time,
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
            
            # Update score
            if self.attempt.score_raw is not None:
                progress.score = float(self.attempt.score_raw)
            
            # Update time spent
            try:
                time_seconds = self._parse_scorm_time(self.attempt.total_time)
                progress.time_spent = int(time_seconds)
            except:
                pass
            
            progress.save()
            
        except Exception as e:
            logger.error(f"Error updating topic progress: {str(e)}")

