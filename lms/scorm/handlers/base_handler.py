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
    
    def _sync_tracking_from_cmi_data(self):
        """
        CRITICAL FIX: Sync tracking data from CMI data to model fields
        This ensures all tracking data (progress, suspend_data, score, status, etc.) is properly saved
        """
        try:
            # Get CMI data
            cmi_data = self.attempt.cmi_data or {}
            
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
            
            # 3. Sync lesson status from CMI data if not already set
            if status_key in cmi_data and cmi_data[status_key]:
                cmi_status = cmi_data[status_key]
                if cmi_status and cmi_status not in ['not attempted', '']:
                    if self.version == '1.2':
                        if self.attempt.lesson_status in ['not_attempted', 'not attempted', '']:
                            self.attempt.lesson_status = cmi_status.replace(' ', '_')
                            logger.info(f"[SYNC] Updated lesson_status from CMI: {self.attempt.lesson_status}")
                    else:
                        if self.attempt.completion_status in ['not attempted', 'incomplete', '']:
                            self.attempt.completion_status = cmi_status.replace(' ', '_')
                            logger.info(f"[SYNC] Updated completion_status from CMI: {self.attempt.completion_status}")
            
            # 4. Sync score data from CMI
            if score_raw_key in cmi_data and cmi_data[score_raw_key]:
                cmi_score = cmi_data[score_raw_key]
                if cmi_score and str(cmi_score).strip() != '':
                    try:
                        score_value = Decimal(str(cmi_score))
                        if self.attempt.score_raw is None or score_value != self.attempt.score_raw:
                            self.attempt.score_raw = score_value
                            logger.info(f"[SYNC] Updated score_raw from CMI: {self.attempt.score_raw}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[SYNC] Could not convert score_raw '{cmi_score}': {e}")
            
            # Sync score_max
            if score_max_key in cmi_data and cmi_data[score_max_key]:
                cmi_score_max = cmi_data[score_max_key]
                if cmi_score_max and str(cmi_score_max).strip() != '':
                    try:
                        self.attempt.score_max = Decimal(str(cmi_score_max))
                    except (ValueError, TypeError):
                        pass
            
            # Sync score_min
            if score_min_key in cmi_data and cmi_data[score_min_key]:
                cmi_score_min = cmi_data[score_min_key]
                if cmi_score_min and str(cmi_score_min).strip() != '':
                    try:
                        self.attempt.score_min = Decimal(str(cmi_score_min))
                    except (ValueError, TypeError):
                        pass
            
            # 5. Sync progress_measure (SCORM 2004) to progress_percentage
            if self.version != '1.2' and 'cmi.progress_measure' in cmi_data:
                progress_measure = cmi_data['cmi.progress_measure']
                if progress_measure and str(progress_measure).strip() != '':
                    try:
                        progress_value = Decimal(str(progress_measure))
                        # Convert 0-1 to 0-100
                        if 0 <= progress_value <= 1:
                            progress_percentage = progress_value * 100
                            if progress_percentage > self.attempt.progress_percentage:
                                self.attempt.progress_percentage = progress_percentage
                                logger.info(f"[SYNC] Updated progress_percentage from CMI progress_measure: {progress_percentage}%")
                    except (ValueError, TypeError):
                        pass
            
            logger.info(f"[SYNC] Tracking data synced from CMI successfully")
            
        except Exception as e:
            logger.error(f"[SYNC] Error syncing tracking data from CMI: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_handler_name(self):
        """Get handler name for logging"""
        return self.__class__.__name__

