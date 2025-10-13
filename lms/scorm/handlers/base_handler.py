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
            # Calculate progress_measure for SCORM 1.2 as well (custom extension)
            # This allows Rise 360 and other content to request progress via either API
            progress_measure = ''
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
            
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
                # Custom extension: progress_measure for SCORM 1.2 (for Rise 360 compatibility)
                'cmi.progress_measure': progress_measure,
                'cmi.core.progress_measure': progress_measure,
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
        
        # ENHANCED RESUME FUNCTIONALITY: Better detection of resume state
        # Check for all forms of resume data
        has_bookmark = bool(self.attempt.lesson_location and len(self.attempt.lesson_location) > 0)
        has_suspend_data = bool(self.attempt.suspend_data and len(self.attempt.suspend_data) > 0)
        has_progress = bool(self.attempt.progress_percentage and self.attempt.progress_percentage > 0)
        has_prior_activity = (self.attempt.lesson_status not in ['not_attempted', 'not attempted', ''] or
                              self.attempt.time_spent_seconds > 0)
        
        # Determine if we should resume
        should_resume = has_bookmark or has_suspend_data or has_progress or has_prior_activity
        
        if should_resume:
            self.attempt.entry = 'resume'
            
            # If status is still not_attempted but we have activity, update it
            if self.attempt.lesson_status in ['not_attempted', 'not attempted', '']:
                self.attempt.lesson_status = 'incomplete'
                
            # Extract extra resume info for logging
            resume_sources = []
            if has_bookmark:
                resume_sources.append('bookmark')
            if has_suspend_data:
                resume_sources.append('suspend_data')
            if has_progress:
                resume_sources.append('progress')
            if has_prior_activity:
                resume_sources.append('prior_activity')
                
            logger.info(f"🔄 SCORM RESUME MODE: {', '.join(resume_sources)}")
            
            if has_bookmark:
                logger.info(f"   lesson_location='{self.attempt.lesson_location[:50]}'")
            if has_suspend_data:
                logger.info(f"   suspend_data length={len(self.attempt.suspend_data)} chars")
            if has_progress:
                logger.info(f"   progress={self.attempt.progress_percentage}%")
                
            # Look for potential bookmark in suspend_data if we don't have one
            if has_suspend_data and not has_bookmark:
                self._extract_bookmark_from_suspend_data(self.attempt.suspend_data)
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
            # Add progress_measure for SCORM 1.2 (custom extension for Rise 360)
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
                self.attempt.cmi_data['cmi.progress_measure'] = progress_measure
                self.attempt.cmi_data['cmi.core.progress_measure'] = progress_measure
                logger.info(f"   SCORM 1.2: Set progress_measure to {progress_measure} ({self.attempt.progress_percentage}%)")
        else:
            self.attempt.cmi_data['cmi.entry'] = self.attempt.entry
            if self.attempt.lesson_location:
                self.attempt.cmi_data['cmi.location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                self.attempt.cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
            if self.attempt.progress_percentage and self.attempt.progress_percentage > 0:
                progress_measure = str(float(self.attempt.progress_percentage) / 100.0)
                self.attempt.cmi_data['cmi.progress_measure'] = progress_measure
                logger.info(f"   SCORM 2004: Set progress_measure to {progress_measure} ({self.attempt.progress_percentage}%)")
        
        # CRITICAL FIX: Force save and sync to ensure data persistence
        self.attempt.save()
        
        # Force progress calculation if not set
        if not self.attempt.progress_percentage or self.attempt.progress_percentage == 0:
            if self.attempt.lesson_status in ['incomplete', 'completed', 'passed']:
                self.attempt.progress_percentage = 25.0  # Default progress for started content
                self.attempt.save()
                logger.info(f"🔧 Set default progress to 25% for attempt {self.attempt.id}")
        
        logger.info(f"✅ SCORM API initialized for attempt {self.attempt.id} ({self.get_handler_name()})")
        logger.info(f"   Status: {self.attempt.lesson_status}, Progress: {self.attempt.progress_percentage}%")
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
            # FIXED: Add input validation
            if value is None:
                value = ''
            
            value_str = str(value)
            
            # Prevent script injection
            if '<script' in value_str.lower() or 'javascript:' in value_str.lower():
                logger.warning(f"Script injection attempt blocked: {element}")
                self.last_error = '402'
                return 'false'
            
            # Validate numeric values
            if element in ['cmi.core.score.raw', 'cmi.score.raw', 'cmi.core.score.min', 'cmi.score.min',
                          'cmi.core.score.max', 'cmi.score.max', 'cmi.score.scaled', 'cmi.progress_measure', 'cmi.core.progress_measure']:
                if value_str and value_str.strip():
                    try:
                        float(value_str)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid numeric value for {element}: {value_str}")
                        self.last_error = '405'
                        return 'false'
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
            
            # FIXED: Add size limits to prevent unbounded data growth
            value_str = str(value)
            if element in ['cmi.suspend_data']:
                max_size = 1024 * 1024  # 1MB
                if len(value_str) > max_size:
                    logger.warning(f"SetValue({element}) exceeds {max_size} bytes, truncating")
                    value = value_str[:max_size]
            else:
                max_size = 10240  # 10KB
                if len(value_str) > max_size:
                    logger.warning(f"SetValue({element}) exceeds {max_size} bytes, truncating")
                    value = value_str[:max_size]
            
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
                    
                    # CRITICAL FIX: Extract progress information from suspend_data
                    self._extract_progress_from_suspend_data(value)
                    
                    self.attempt.save()  # Immediate save for suspend data
            elif element in ['cmi.progress_measure', 'cmi.core.progress_measure']:
                # CRITICAL FIX: Support progress_measure for SCORM 1.2 (custom extension for Rise 360)
                # Convert progress_measure (0-1) to progress_percentage (0-100)
                try:
                    if value and str(value).strip():
                        progress_value = Decimal(str(value))
                        if 0 <= progress_value <= 1:
                            self.attempt.progress_percentage = progress_value * 100
                            self.attempt.save()
                            logger.info(f"💾 [SCORM 1.2 PROGRESS] Updated progress_percentage to {self.attempt.progress_percentage}% from progress_measure {progress_value}")
                except Exception as e:
                    logger.error(f"Error updating progress_percentage from progress_measure (SCORM 1.2): {e}")
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
                    
                    # CRITICAL FIX: Extract progress information from suspend_data
                    self._extract_progress_from_suspend_data(value)
                    
                    self.attempt.save()  # Immediate save for suspend data
            elif element == 'cmi.progress_measure':
                # CRITICAL FIX: Convert progress_measure (0-1) to progress_percentage (0-100)
                # This is essential for Rise 360 progress bar to persist correctly
                try:
                    if value and str(value).strip():
                        progress_value = Decimal(str(value))
                        if 0 <= progress_value <= 1:
                            self.attempt.progress_percentage = progress_value * 100
                            logger.info(f"💾 [PROGRESS] Updated progress_percentage to {self.attempt.progress_percentage}% from progress_measure {progress_value}")
                            self.attempt.save()  # Immediate save for progress
                except Exception as e:
                    logger.error(f"Error updating progress_percentage from progress_measure: {e}")
    
    def _commit_data(self):
        """Save attempt data to database"""
        self.attempt.last_accessed = timezone.now()
        
        if not getattr(self.attempt, 'is_preview', False):
            self.attempt._skip_signal = True
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
                
                # CRITICAL FIX: Sync tracking data from CMI data to model fields
                # This ensures all tracking data (score, status, progress, etc.) is properly saved
                self._sync_tracking_from_cmi_data()
                
                self.attempt.save()
                logger.info(f"[COMMIT] Saved attempt {self.attempt.id} - Status: {self.attempt.lesson_status}, Score: {self.attempt.score_raw}, Progress: {self.attempt.progress_percentage}%")
                
                # Sync score to gradebook
                from scorm.score_sync_service import ScormScoreSyncService
                sync_success = ScormScoreSyncService.sync_score(self.attempt, force=True)
                logger.info(f"[COMMIT] Score sync: {sync_success}")
            except Exception as e:
                logger.error(f"[COMMIT] Error: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                if hasattr(self.attempt, '_skip_signal'):
                    delattr(self.attempt, '_skip_signal')
    
    def _extract_bookmark_from_suspend_data(self, suspend_data):
        """
        CRITICAL FIX: Extract bookmark/location information from suspend_data
        This fixes resume functionality when bookmark is missing but suspend_data contains location info
        """
        try:
            if not suspend_data or not isinstance(suspend_data, str):
                return
                
            # Common patterns for bookmarks in suspend_data
            import re
            
            # Common bookmark patterns used by different SCORM authoring tools
            bookmark_patterns = [
                r'current_slide[=:]([^&]+)',         # current_slide=slide3
                r'current_location[=:]([^&]+)',      # current_location=slide3
                r'current_page[=:]([^&]+)',          # current_page=slide3
                r'bookmark[=:]([^&]+)',              # bookmark=slide3
                r'\"bookmark\"[=:]\"([^\"]+)\"',     # "bookmark":"slide3"
                r'\"slide\"[=:]\"([^\"]+)\"',        # "slide":"slide3"
                r'\"location\"[=:]\"([^\"]+)\"',     # "location":"slide3"
                r'currentSlide[=:]([^&]+)',          # currentSlide=slide3
                r'slideId[=:]([^&]+)',               # slideId=slide3
                r'lessonLocation[=:]([^&]+)',        # lessonLocation=slide3
                r'lesson_location[=:]([^&]+)',       # lesson_location=slide3
            ]
            
            # Try all patterns
            for pattern in bookmark_patterns:
                match = re.search(pattern, suspend_data)
                if match:
                    extracted_location = match.group(1).strip()
                    if extracted_location:
                        # Only update if we don't already have a bookmark
                        if not self.attempt.lesson_location:
                            self.attempt.lesson_location = extracted_location
                            logger.info(f"✅ RESUME FIX: Extracted bookmark '{extracted_location}' from suspend_data using pattern '{pattern}'")
                            return True
                        return False  # Already have a bookmark
                        
            # If no pattern matched but suspend_data is substantial
            # Try to extract slide number from progress data
            if len(suspend_data) > 500:
                # Look for any progress indication
                progress_match = re.search(r'progress[=:](\d+)', suspend_data)
                if progress_match:
                    progress = int(progress_match.group(1))
                    # Create slide estimate based on progress
                    if progress > 0:
                        slide_num = max(1, int(progress / 10))  # Estimate 10% per slide
                        default_slide = f"slide_{slide_num}"
                        self.attempt.lesson_location = default_slide
                        logger.info(f"✅ RESUME FIX: Created estimated bookmark '{default_slide}' from progress {progress}%")
                        return True
            
            return False
                
        except Exception as e:
            logger.error(f"Error extracting bookmark from suspend_data: {e}")
            return False
    
    def _extract_progress_from_suspend_data(self, suspend_data):
        """
        CRITICAL FIX: Extract progress information from suspend_data
        This fixes the bug where progress_percentage is not updated from suspend_data
        """
        try:
            if not suspend_data or not isinstance(suspend_data, str):
                return
                
            # Initialize progress tracking if needed
            if self.attempt.completed_slides is None:
                self.attempt.completed_slides = []
                
            # Common patterns for progress in suspend data
            import re
            
            # Look for progress percentage patterns
            progress_patterns = [
                # Direct progress indicators
                r'progress[=:]\s*(\d+)',               # progress=75
                r'progress["\s]*[=:]\s*(\d+)',        # progress="75" or progress: 75
                r'"progress"\s*:\s*(\d+)',           # "progress": 75
                r'completion[=:]\s*(\d+)',             # completion=75
                r'completion_percentage[=:]\s*(\d+)',  # completion_percentage=75
                
                # Slide/page completion patterns
                r'completed_slides[=:]([\d,]+).*?total_slides[=:](\d+)',  # completed_slides=1,2,3&total_slides=5
                r'completed[=:]([\d,]+).*?total[=:](\d+)',              # completed=1,2,3&total=5
            ]
            
            # Try to find direct progress percentage
            for pattern in progress_patterns[:5]:  # First 5 are direct percentage patterns
                match = re.search(pattern, suspend_data)
                if match:
                    try:
                        progress_value = int(match.group(1))
                        if 0 <= progress_value <= 100:
                            # Only update if the new value is higher (prevent regressions)
                            current_progress = self.attempt.progress_percentage or 0
                            if progress_value > current_progress:
                                self.attempt.progress_percentage = progress_value
                                logger.info(f"[PROGRESS] Extracted {progress_value}% from suspend_data using pattern '{pattern}'")
                                return
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Error parsing progress value: {e}")
            
            # Try slide completion patterns
            for pattern in progress_patterns[5:]:  # Last patterns are slide completion patterns
                match = re.search(pattern, suspend_data)
                if match:
                    try:
                        completed_str = match.group(1)
                        total_slides = int(match.group(2))
                        
                        if ',' in completed_str:
                            completed_slides = [s for s in completed_str.split(',') if s.strip()]
                            completed_count = len(completed_slides)
                        else:
                            completed_count = 1 if completed_str.strip() else 0
                            
                        if completed_count > 0 and total_slides > 0:
                            # Calculate progress percentage
                            progress_value = min(100, (completed_count / total_slides) * 100)
                            
                            # Update attempt data
                            current_progress = self.attempt.progress_percentage or 0
                            if progress_value > current_progress:
                                self.attempt.progress_percentage = progress_value
                                self.attempt.total_slides = total_slides
                                
                                # Update completed slides list
                                if isinstance(self.attempt.completed_slides, list):
                                    # Convert slide IDs to strings to ensure consistency
                                    slide_ids = [str(s) for s in completed_str.split(',') if s.strip()]
                                    self.attempt.completed_slides = slide_ids
                                    
                                logger.info(f"[PROGRESS] Calculated {progress_value:.1f}% from {completed_count}/{total_slides} slides")
                                return
                    except (ValueError, TypeError, IndexError) as e:
                        logger.debug(f"Error parsing slide completion: {e}")
            
            # Look for completion indicators
            if ('complete=true' in suspend_data.lower() or 
                '"complete":true' in suspend_data.lower() or 
                '"completion":"completed"' in suspend_data.lower()):
                
                # Content is marked as complete but no percentage - set to 100%
                self.attempt.progress_percentage = 100
                logger.info(f"[PROGRESS] Set progress to 100% based on completion indicator")
                return
                
            # Analyze suspend_data length to estimate progress
            if len(suspend_data) > 1000 and self.attempt.progress_percentage == 0:
                # If suspend_data is very large, the user has made significant progress
                # Set a reasonable default based on suspend_data size
                if len(suspend_data) > 5000:
                    self.attempt.progress_percentage = 80  # Very large suspend_data
                elif len(suspend_data) > 2500:
                    self.attempt.progress_percentage = 50  # Medium suspend_data
                else:
                    self.attempt.progress_percentage = 25  # Small but meaningful suspend_data
                    
                logger.info(f"[PROGRESS] Estimated {self.attempt.progress_percentage}% progress based on suspend_data length ({len(suspend_data)} chars)")
                
        except Exception as e:
            logger.error(f"[PROGRESS] Error extracting progress from suspend_data: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _sync_tracking_from_cmi_data(self):
        """
        COMPREHENSIVE FIX: Enhanced sync between CMI data and model fields
        This ensures all tracking data is properly synchronized in both directions,
        handling edge cases and preventing data loss
        """
        try:
            # Get CMI data with safety check
            if self.attempt.cmi_data is None:
                self.attempt.cmi_data = {}
                logger.warning(f"[SYNC] Found null cmi_data for attempt {self.attempt.id} - initializing empty dict")
            
            cmi_data = self.attempt.cmi_data
            
            # 1. Sync lesson_location (bookmark)
            if self.version == '1.2':
                location_key = 'cmi.core.lesson_location'
                suspend_key = 'cmi.suspend_data'
                status_key = 'cmi.core.lesson_status'
                score_raw_key = 'cmi.core.score.raw'
                score_max_key = 'cmi.core.score.max'
                score_min_key = 'cmi.core.score.min'
            else:
                location_key = 'cmi.location'
                suspend_key = 'cmi.suspend_data'
                status_key = 'cmi.completion_status'
                score_raw_key = 'cmi.score.raw'
                score_max_key = 'cmi.score.max'
                score_min_key = 'cmi.score.min'
            
            # Sync lesson_location from CMI data if not already set in model
            if location_key in cmi_data and cmi_data[location_key]:
                cmi_location = cmi_data[location_key]
                if cmi_location and (not self.attempt.lesson_location or len(str(cmi_location)) > len(str(self.attempt.lesson_location))):
                    self.attempt.lesson_location = str(cmi_location)[:1000]
                    logger.info(f"[SYNC] Updated lesson_location from CMI: {self.attempt.lesson_location[:50]}...")
            
            # 2. Sync suspend_data from CMI data if not already set in model
            if suspend_key in cmi_data and cmi_data[suspend_key]:
                cmi_suspend = cmi_data[suspend_key]
                if cmi_suspend and (not self.attempt.suspend_data or len(str(cmi_suspend)) > len(str(self.attempt.suspend_data))):
                    self.attempt.suspend_data = str(cmi_suspend)
                    logger.info(f"[SYNC] Updated suspend_data from CMI: {len(self.attempt.suspend_data)} chars")
            
            # 3. COMPREHENSIVE FIX: Better status synchronization with bidirectional updates
            # Handle lesson_status and completion_status with proper priority
            
            # First, sync from CMI to model fields
            if status_key in cmi_data and cmi_data[status_key]:
                cmi_status = str(cmi_data[status_key]).strip()
                if cmi_status and cmi_status.lower() not in ['not attempted', '']:
                    normalized_status = cmi_status.replace(' ', '_').lower()
                    
                    # Map common status values to standard values
                    status_mapping = {
                        'complete': 'completed',
                        'pass': 'passed',
                        'fail': 'failed',
                        'not_attempted': 'not_attempted',
                        'not attempted': 'not_attempted',
                        'notapplicable': 'not_attempted',
                    }
                    
                    if normalized_status in status_mapping:
                        normalized_status = status_mapping[normalized_status]
                    
                    if self.version == '1.2':
                        # For SCORM 1.2, prioritize meaningful statuses over generic ones
                        current_status = (self.attempt.lesson_status or '').lower()
                        
                        # Only update if new status is more meaningful
                        if (current_status in ['not_attempted', 'not attempted', '', 'unknown', 'incomplete'] or
                            (current_status == 'incomplete' and normalized_status in ['completed', 'passed', 'failed'])):
                            self.attempt.lesson_status = normalized_status
                            logger.info(f"[SYNC] Updated lesson_status from CMI: {self.attempt.lesson_status}")
                            
                            # Also update completion_status for consistency
                            if normalized_status in ['completed', 'passed']:
                                self.attempt.completion_status = 'completed'
                            elif normalized_status == 'failed':
                                self.attempt.completion_status = 'incomplete'
                            else:
                                self.attempt.completion_status = normalized_status
                    else:
                        # For SCORM 2004, handle completion_status and success_status separately
                        current_status = (self.attempt.completion_status or '').lower()
                        
                        # Only update if new status is more meaningful
                        if current_status in ['not attempted', 'unknown', '', 'incomplete']:
                            self.attempt.completion_status = normalized_status
                            logger.info(f"[SYNC] Updated completion_status from CMI: {self.attempt.completion_status}")
                        
                        # Also sync success_status if available
                        if 'cmi.success_status' in cmi_data and cmi_data['cmi.success_status']:
                            success_status = str(cmi_data['cmi.success_status']).strip().lower()
                            if success_status in ['passed', 'failed']:
                                self.attempt.success_status = success_status
                                logger.info(f"[SYNC] Updated success_status from CMI: {self.attempt.success_status}")
                                
                                # For consistency, also update lesson_status
                                if success_status == 'passed':
                                    self.attempt.lesson_status = 'passed'
                                elif success_status == 'failed':
                                    self.attempt.lesson_status = 'failed'
            
            # Now sync back from model fields to CMI data for consistency
            # This ensures CMI data always reflects the current model state
            if self.version == '1.2':
                if self.attempt.lesson_status and self.attempt.lesson_status not in ['not_attempted', '']:
                    cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status.replace('_', ' ')
            else:
                if self.attempt.completion_status and self.attempt.completion_status not in ['not_attempted', '']:
                    cmi_data['cmi.completion_status'] = self.attempt.completion_status.replace('_', ' ')
                if self.attempt.success_status and self.attempt.success_status not in ['unknown', '']:
                    cmi_data['cmi.success_status'] = self.attempt.success_status
            
            # 4. COMPREHENSIVE FIX: Enhanced score synchronization with validation and normalization
            # First, get all score components from CMI data
            score_raw = None
            score_max = None
            score_min = None
            score_scaled = None
            
            # Extract raw score with validation
            if score_raw_key in cmi_data and cmi_data[score_raw_key] is not None:
                cmi_score = cmi_data[score_raw_key]
                if cmi_score and str(cmi_score).strip() != '':
                    try:
                        score_raw = Decimal(str(cmi_score))
                        logger.info(f"[SYNC] Found valid score_raw in CMI: {score_raw}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Could not convert score_raw '{cmi_score}': {e}")
            
            # Extract max score with validation
            if score_max_key in cmi_data and cmi_data[score_max_key] is not None:
                cmi_score_max = cmi_data[score_max_key]
                if cmi_score_max and str(cmi_score_max).strip() != '':
                    try:
                        score_max = Decimal(str(cmi_score_max))
                        logger.info(f"[SYNC] Found valid score_max in CMI: {score_max}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Could not convert score_max '{cmi_score_max}': {e}")
            
            # Extract min score with validation
            if score_min_key in cmi_data and cmi_data[score_min_key] is not None:
                cmi_score_min = cmi_data[score_min_key]
                if cmi_score_min and str(cmi_score_min).strip() != '':
                    try:
                        score_min = Decimal(str(cmi_score_min))
                        logger.info(f"[SYNC] Found valid score_min in CMI: {score_min}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Could not convert score_min '{cmi_score_min}': {e}")
            
            # Extract scaled score for SCORM 2004
            if self.version != '1.2' and 'cmi.score.scaled' in cmi_data and cmi_data['cmi.score.scaled'] is not None:
                cmi_score_scaled = cmi_data['cmi.score.scaled']
                if cmi_score_scaled and str(cmi_score_scaled).strip() != '':
                    try:
                        score_scaled = Decimal(str(cmi_score_scaled))
                        logger.info(f"[SYNC] Found valid score_scaled in CMI: {score_scaled}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Could not convert score_scaled '{cmi_score_scaled}': {e}")
            
            # Now apply score components with validation and normalization
            
            # 1. Update score_raw if valid
            if score_raw is not None:
                # Check if score is within valid range
                if score_max is not None and score_raw > score_max:
                    logger.warning(f"[SYNC] Score {score_raw} exceeds max {score_max}, capping")
                    score_raw = score_max
                
                if score_min is not None and score_raw < score_min:
                    logger.warning(f"[SYNC] Score {score_raw} below min {score_min}, setting to min")
                    score_raw = score_min
                
                # Only update if different from current value
                if self.attempt.score_raw is None or score_raw != self.attempt.score_raw:
                    self.attempt.score_raw = score_raw
                    logger.info(f"[SYNC] Updated score_raw: {self.attempt.score_raw}")
                    
                    # Also update CMI data for consistency
                    cmi_data[score_raw_key] = str(score_raw)
            
            # 2. Update score_max if valid
            if score_max is not None:
                self.attempt.score_max = score_max
                # Also update CMI data for consistency
                cmi_data[score_max_key] = str(score_max)
            
            # 3. Update score_min if valid
            if score_min is not None:
                self.attempt.score_min = score_min
                # Also update CMI data for consistency
                cmi_data[score_min_key] = str(score_min)
                
            # 4. Update score_scaled if valid (SCORM 2004 only)
            if self.version != '1.2' and score_scaled is not None:
                # Validate scaled score is between 0 and 1
                if score_scaled < 0:
                    score_scaled = Decimal('0')
                elif score_scaled > 1:
                    score_scaled = Decimal('1')
                    
                self.attempt.score_scaled = score_scaled
                # Also update CMI data for consistency
                cmi_data['cmi.score.scaled'] = str(score_scaled)
                
            # 5. Calculate scaled score if not provided but we have raw and max (SCORM 2004)
            if self.version != '1.2' and score_scaled is None and score_raw is not None and score_max is not None and score_max > 0:
                calculated_scaled = score_raw / score_max
                if calculated_scaled > 1:
                    calculated_scaled = Decimal('1')
                elif calculated_scaled < 0:
                    calculated_scaled = Decimal('0')
                    
                self.attempt.score_scaled = calculated_scaled
                # Also update CMI data for consistency
                cmi_data['cmi.score.scaled'] = str(calculated_scaled)
                logger.info(f"[SYNC] Calculated and updated score_scaled: {calculated_scaled}")
            
            # 5. Enhanced progress tracking from multiple CMI data sources
            # Check various CMI fields for progress information
            progress_keys = [
                'cmi.progress_measure',       # SCORM 2004 standard
                'cmi.core.progress_measure',  # Custom extension for SCORM 1.2
                'cmi.progress',              # Common custom extension
                'cmi.completion-percentage', # Common custom extension
                'cmi.percent-complete'       # Common custom extension
            ]
            
            # Try all possible progress keys
            for key in progress_keys:
                if key in cmi_data and cmi_data[key] and str(cmi_data[key]).strip() != '':
                    try:
                        progress_value = Decimal(str(cmi_data[key]))
                        
                        # Handle both 0-1 and 0-100 formats
                        if 0 <= progress_value <= 1:  # 0-1 format
                            progress_percentage = progress_value * 100
                        elif 0 <= progress_value <= 100:  # 0-100 format
                            progress_percentage = progress_value
                        else:
                            # Invalid range, skip
                            continue
                            
                        # Only update if higher than current
                        current_progress = self.attempt.progress_percentage or 0
                        if progress_percentage > current_progress:
                            self.attempt.progress_percentage = progress_percentage
                            logger.info(f"[SYNC] Updated progress_percentage from {key}: {progress_percentage}%")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Invalid progress value in {key}: {cmi_data[key]} - {e}")
                        
            # Process suspend_data for progress information if we still don't have progress
            # or if progress is suspiciously low despite significant suspend_data
            if (self.attempt.suspend_data and 
                (not self.attempt.progress_percentage or 
                 self.attempt.progress_percentage < 10) and 
                len(self.attempt.suspend_data) > 100):
                
                self._extract_progress_from_suspend_data(self.attempt.suspend_data)
            
            logger.info(f"[SYNC] Tracking data synced from CMI successfully")
            
        except Exception as e:
            logger.error(f"[SYNC] Error syncing tracking data from CMI: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_handler_name(self):
        """Get handler name for logging"""
        return self.__class__.__name__

