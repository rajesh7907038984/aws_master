"""
SCORM Authoring Tool Handler
Handles different tracking methods for various SCORM authoring tools
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

class AuthoringToolHandler:
    """
    Handles tracking data for different SCORM authoring tools
    Each tool has unique tracking patterns and data structures
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.cmi_data = attempt.cmi_data or {}
        
    def detect_authoring_tool(self):
        """
        Enhanced detection of authoring tool based on CMI data, launch URL, and suspend data patterns
        """
        # Get launch URL and suspend data for better detection
        launch_url = str(self.attempt.scorm_package.launch_url).lower() if self.attempt.scorm_package else ''
        suspend_data = self.attempt.suspend_data or ''
        lesson_location = self.attempt.lesson_location or ''
        
        # Enhanced Articulate Storyline detection
        storyline_patterns = [
            any('slide' in k.lower() for k in self.cmi_data.keys()),
            any('scene' in k.lower() for k in self.cmi_data.keys()),
            any('storyline' in k.lower() for k in self.cmi_data.keys()),
            'story.html' in launch_url,
            'story_html5.html' in launch_url,
            'version_str' in suspend_data,
            '6fOEl' in suspend_data  # Common Storyline marker
        ]
        
        if any(storyline_patterns):
            logger.info("Detected Articulate Storyline package")
            return 'storyline'
            
        # Enhanced Articulate Rise detection
        rise_patterns = [
            'scormcontent/' in launch_url,
            'scormdriver/' in launch_url,
            'index_lms.html' in launch_url,
            'index_lms_html5.html' in launch_url,
            any('rise' in k.lower() for k in self.cmi_data.keys()),
            '"c":[' in suspend_data,  # Rise completion tracking
            'lessons' in suspend_data  # Rise lessons structure
        ]
        
        if any(rise_patterns):
            logger.info("Detected Articulate Rise 360 package")
            return 'rise'
            
        # Enhanced Adobe Captivate detection
        captivate_patterns = [
            any('cpapi' in k.lower() for k in self.cmi_data.keys()),
            any('captivate' in k.lower() for k in self.cmi_data.keys()),
            any('adobe' in k.lower() for k in self.cmi_data.keys()),
            'multiscreen.html' in launch_url,
            'cpMobileCommand' in suspend_data,
            'cpQuizInfoStudentID' in suspend_data
        ]
        
        if any(captivate_patterns):
            logger.info("Detected Adobe Captivate package")
            return 'captivate'
            
        # Enhanced Lectora detection
        lectora_patterns = [
            any('lectora' in k.lower() for k in self.cmi_data.keys()),
            any('trivantis' in k.lower() for k in self.cmi_data.keys()),
            'a001index.html' in launch_url,
            'TrivantisTracking' in suspend_data
        ]
        
        if any(lectora_patterns):
            logger.info("Detected Lectora package")
            return 'lectora'
            
        # Enhanced iSpring detection
        ispring_patterns = [
            any('ispring' in k.lower() for k in self.cmi_data.keys()),
            any('presentation' in k.lower() for k in self.cmi_data.keys()),
            'presentation.html' in launch_url,
            lesson_location.startswith('slide'),
            'iSpring' in suspend_data
        ]
        
        if any(ispring_patterns):
            logger.info("Detected iSpring package")
            return 'ispring'
        
        # H5P detection
        if 'h5p' in launch_url or 'H5P' in suspend_data:
            logger.info("Detected H5P package")
            return 'h5p'
        
        # Articulate Presenter detection
        if 'presenter.html' in launch_url or 'player.html' in launch_url:
            logger.info("Detected Articulate Presenter package")
            return 'presenter'
        
        # Camtasia detection
        if 'camtasia' in launch_url or 'TechSmith' in suspend_data:
            logger.info("Detected Camtasia package")
            return 'camtasia'
            
        logger.info("Using standard SCORM handler")
        return 'standard'
    
    def update_tracking_data(self, element, value):
        """
        Update tracking data based on authoring tool type with automatic bookmarking and progress
        """
        tool_type = self.detect_authoring_tool()
        
        logger.info(f"Updating tracking data for {tool_type} tool: {element} = {value}")
        
        # Automatically save suspend data for resume capability
        if element in ['cmi.suspend_data', 'cmi.core.suspend_data']:
            self.attempt.suspend_data = value
            self.attempt.save(update_fields=['suspend_data', 'last_accessed'])
            logger.info("Suspend data auto-saved for resume capability")
        
        # Automatically save lesson location for bookmarking
        if element in ['cmi.core.lesson_location', 'cmi.location']:
            self.attempt.lesson_location = value
            self.attempt.save(update_fields=['lesson_location', 'last_accessed'])
            logger.info(f"Bookmark auto-saved: {value}")
        
        # Route to specific handler based on tool type
        if tool_type == 'storyline':
            return self._update_storyline_tracking(element, value)
        elif tool_type == 'rise':
            return self._update_rise_tracking(element, value)
        elif tool_type == 'captivate':
            return self._update_captivate_tracking(element, value)
        elif tool_type == 'lectora':
            return self._update_lectora_tracking(element, value)
        elif tool_type == 'ispring':
            return self._update_ispring_tracking(element, value)
        elif tool_type == 'h5p':
            return self._update_h5p_tracking(element, value)
        elif tool_type == 'presenter':
            return self._update_presenter_tracking(element, value)
        elif tool_type == 'camtasia':
            return self._update_camtasia_tracking(element, value)
        else:
            return self._update_standard_tracking(element, value)
    
    def _update_storyline_tracking(self, element, value):
        """
        Handle Articulate Storyline specific tracking
        - Uses slide/scene based navigation
        - Specific completion patterns
        - Custom variables
        """
        logger.info(f"Processing Storyline tracking: {element} = {value}")
        
        # Storyline status mapping
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
            if value in ['completed', 'passed']:
                self.attempt.completion_status = 'completed'
                self.attempt.success_status = 'passed' if value == 'passed' else 'unknown'
        
        # Storyline score handling
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
                # Auto-determine pass/fail based on score
                if self.attempt.score_raw >= Decimal('70'):  # Default passing score
                    self.attempt.success_status = 'passed'
                    if self.attempt.lesson_status != 'failed':
                        self.attempt.lesson_status = 'passed'
                else:
                    self.attempt.success_status = 'failed'
                    self.attempt.lesson_status = 'failed'
            except (ValueError, TypeError):
                pass
        
        # Storyline bookmark handling (slide/scene tracking)
        elif 'slide' in element.lower() or 'scene' in element.lower():
            self.attempt.lesson_location = f"storyline_{element}_{value}"
        
        # Storyline session time
        elif element == 'cmi.core.session_time':
            self.attempt.session_time = value
            # Add to total time
            if self.attempt.total_time:
                # Parse and add session time to total time
                try:
                    self._add_session_to_total_time(value)
                except:
                    pass
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_rise_tracking(self, element, value):
        """
        Handle Articulate Rise specific tracking
        - Uses scormcontent/scormdriver structure
        - Different completion indicators
        """
        logger.info(f"Processing Rise tracking: {element} = {value}")
        
        # Rise uses both SCORM 1.2 and 2004 patterns
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
            if value == 'completed':
                self.attempt.completion_status = 'completed'
        elif element == 'cmi.completion_status':
            self.attempt.completion_status = value
            if value == 'completed':
                self.attempt.lesson_status = 'completed'
        
        # Rise score handling
        elif element in ['cmi.core.score.raw', 'cmi.score.raw']:
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        # Rise suspend data often contains completion indicators
        elif element == 'cmi.suspend_data':
            self.attempt.suspend_data = value
            # Check for completion indicators in suspend data
            if value and any(indicator in value.lower() for indicator in ['completed', 'finished', 'done']):
                if self.attempt.lesson_status == 'not attempted':
                    self.attempt.lesson_status = 'completed'
                    self.attempt.completion_status = 'completed'
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_captivate_tracking(self, element, value):
        """
        Handle Adobe Captivate specific tracking
        - Uses cpapi patterns
        - Quiz-focused tracking
        """
        logger.info(f"Processing Captivate tracking: {element} = {value}")
        
        # Captivate status
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
        
        # Captivate score (often quiz-based)
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
                # Captivate often has strict pass/fail logic
                passing_score = Decimal('80.0')  # Captivate default
                if self.attempt.score_raw >= passing_score:
                    self.attempt.success_status = 'passed'
                    self.attempt.lesson_status = 'passed'
                else:
                    self.attempt.success_status = 'failed'  
                    self.attempt.lesson_status = 'failed'
            except (ValueError, TypeError):
                pass
        
        # Captivate interaction tracking
        elif 'cpapi' in element.lower():
            # Store Captivate-specific data
            if not self.attempt.detailed_tracking:
                self.attempt.detailed_tracking = {}
            self.attempt.detailed_tracking[f'captivate_{element}'] = value
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_lectora_tracking(self, element, value):
        """
        Handle Lectora specific tracking
        """
        logger.info(f"Processing Lectora tracking: {element} = {value}")
        
        # Lectora uses standard SCORM with some variations
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_ispring_tracking(self, element, value):
        """
        Handle iSpring specific tracking
        """
        logger.info(f"Processing iSpring tracking: {element} = {value}")
        
        # iSpring presentation tracking
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_standard_tracking(self, element, value):
        """
        Handle standard SCORM tracking (SCORM 1.2/2004 compliant)
        """
        logger.info(f"Processing standard SCORM tracking: {element} = {value}")
        
        # Standard SCORM 1.2
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
            if value in ['completed', 'passed']:
                self.attempt.completion_status = 'completed'
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        # Standard SCORM 2004  
        elif element == 'cmi.completion_status':
            self.attempt.completion_status = value
            if value == 'completed' and self.attempt.lesson_status in ['not attempted', 'incomplete']:
                self.attempt.lesson_status = 'completed'
        elif element == 'cmi.success_status':
            self.attempt.success_status = value
        elif element == 'cmi.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        # Common elements
        elif element in ['cmi.core.lesson_location', 'cmi.location']:
            self.attempt.lesson_location = value
        elif element == 'cmi.suspend_data':
            self.attempt.suspend_data = value
        elif element in ['cmi.core.session_time', 'cmi.session_time']:
            self.attempt.session_time = value
        
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _add_session_to_total_time(self, session_time):
        """
        Add session time to total time (SCORM time format: HH:MM:SS.SS)
        """
        try:
            # Parse session time
            parts = session_time.split(':')
            if len(parts) >= 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                
                session_seconds = hours * 3600 + minutes * 60 + seconds
                
                # Parse existing total time or start at 0
                total_seconds = 0
                if self.attempt.total_time:
                    total_parts = self.attempt.total_time.split(':')
                    if len(total_parts) >= 3:
                        total_seconds = int(total_parts[0]) * 3600 + int(total_parts[1]) * 60 + float(total_parts[2])
                
                # Add session to total
                new_total_seconds = total_seconds + session_seconds
                
                # Convert back to SCORM format
                new_hours = int(new_total_seconds // 3600)
                new_minutes = int((new_total_seconds % 3600) // 60)
                new_seconds = new_total_seconds % 60
                
                self.attempt.total_time = f"{new_hours:04d}:{new_minutes:02d}:{new_seconds:05.2f}"
                
        except Exception as e:
            logger.warning(f"Could not parse session time {session_time}: {e}")
    
    def _update_h5p_tracking(self, element, value):
        """
        Handle H5P specific tracking with automatic progress
        """
        logger.info(f"Processing H5P tracking: {element} = {value}")
        
        # H5P specific tracking
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
            if value in ['completed', 'passed']:
                self.attempt.completion_status = 'completed'
                self.attempt.progress_percentage = 100
        
        # H5P uses standard SCORM elements
        elif element == 'cmi.core.score.raw':
            try:
                from decimal import Decimal
                self.attempt.score_raw = Decimal(str(value))
            except (ValueError, TypeError):
                pass
        
        # Auto-save for persistence
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_presenter_tracking(self, element, value):
        """
        Handle Articulate Presenter specific tracking with slide progress
        """
        logger.info(f"Processing Articulate Presenter tracking: {element} = {value}")
        
        # Presenter specific tracking
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
        
        # Presenter uses slide-based navigation
        elif element == 'cmi.core.lesson_location':
            self.attempt.lesson_location = value
            # Auto-calculate progress based on slide location
            if value and '/' in value:
                try:
                    current, total = value.split('/')
                    progress = (int(current) / int(total)) * 100
                    self.attempt.progress_percentage = progress
                    logger.info(f"Presenter progress: {progress}% (slide {current}/{total})")
                except:
                    pass
        
        # Auto-save for persistence
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
    
    def _update_camtasia_tracking(self, element, value):
        """
        Handle Camtasia specific tracking with video progress
        """
        logger.info(f"Processing Camtasia tracking: {element} = {value}")
        
        # Camtasia video-based tracking
        if element == 'cmi.core.lesson_status':
            self.attempt.lesson_status = value
            if value == 'completed':
                self.attempt.completion_status = 'completed'
                self.attempt.progress_percentage = 100
        
        # Camtasia uses time-based progress
        elif element == 'cmi.core.lesson_location':
            self.attempt.lesson_location = value
            # Parse time-based location for video progress
            if value and ':' in value:
                logger.info(f"Camtasia video position: {value}")
                # Store video position for resume
                if not self.attempt.detailed_tracking:
                    self.attempt.detailed_tracking = {}
                self.attempt.detailed_tracking['video_position'] = value
        
        # Auto-save for persistence
        self.attempt.last_accessed = timezone.now()
        self.attempt.save()
        return True
