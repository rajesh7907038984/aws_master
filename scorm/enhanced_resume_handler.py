"""
Enhanced SCORM Resume Handler
Handles resume functionality for different SCORM package types with improved logic
"""
import logging
from typing import Optional, Dict, Any
from .models import ScormAttempt, ScormPackage

logger = logging.getLogger(__name__)


class EnhancedScormResumeHandler:
    """
    Enhanced handler for SCORM resume functionality
    Handles different package types and resume scenarios
    """
    
    def __init__(self, attempt: ScormAttempt):
        self.attempt = attempt
        self.package = attempt.scorm_package
        self.user = attempt.user
    
    def can_resume(self) -> bool:
        """
        Enhanced check if this attempt can be resumed with format-specific logic
        """
        # Check if attempt is in a resumable state
        if self.attempt.lesson_status in ['completed', 'passed', 'failed']:
            logger.info(f"RESUME: Cannot resume - attempt status: {self.attempt.lesson_status}")
            return False
        
        # Enhanced progress detection with format-specific logic
        has_progress = (
            self.attempt.lesson_location or 
            self.attempt.suspend_data or 
            self.attempt.lesson_status in ['incomplete', 'not_attempted'] or
            self.attempt.entry == 'resume'
        )
        
        # Format-specific resume logic
        package_type = self.detect_package_type()
        
        if package_type == 'storyline':
            # Storyline can resume even with minimal data
            has_progress = has_progress or (
                self.attempt.cmi_data and 
                len(self.attempt.cmi_data) > 0
            )
        elif package_type == 'captivate':
            # Captivate requires more specific data
            has_progress = has_progress and (
                self.attempt.lesson_location or 
                self.attempt.suspend_data
            )
        elif package_type == 'lectora':
            # Lectora has specific resume requirements
            has_progress = has_progress and (
                self.attempt.lesson_location or
                self.attempt.detailed_tracking
            )
        
        logger.info(f"RESUME: Can resume check - has_progress: {has_progress}, package_type: {package_type}")
        return has_progress
    
    def prepare_resume_data(self) -> Dict[str, Any]:
        """
        Enhanced resume data preparation with format-specific handling
        """
        # Ensure CMI data is initialized
        if not self.attempt.cmi_data:
            self.attempt.cmi_data = {}
        
        if not self.can_resume():
            logger.info("RESUME: Cannot resume, preparing restart data")
            return self._prepare_restart_resume()
        
        package_type = self.detect_package_type()
        logger.info(f"RESUME: Preparing resume data for package type: {package_type}")
        
        # Determine if this is a true resume (with bookmark data) or a restart
        has_bookmark_data = bool(self.attempt.lesson_location or self.attempt.suspend_data)
        
        if has_bookmark_data:
            logger.info(f"RESUME: Found bookmark data for attempt {self.attempt.id}")
            # Format-specific resume data preparation
            if package_type == 'storyline':
                return self._prepare_storyline_resume()
            elif package_type == 'captivate':
                return self._prepare_captivate_resume()
            elif package_type == 'lectora':
                return self._prepare_lectora_resume()
            else:
                return self._prepare_bookmark_resume()
        else:
            logger.info(f"RESUME: No bookmark data for attempt {self.attempt.id} - preparing restart resume")
            return self._prepare_restart_resume()
    
    def _prepare_bookmark_resume(self) -> Dict[str, Any]:
        """
        Prepare resume data when bookmark data is available
        """
        cmi_data = self.attempt.cmi_data.copy()
        
        # Set entry mode to resume
        self.attempt.entry = 'resume'
        
        # CRITICAL FIX: Initialize required fields to prevent validation errors
        if not self.attempt.navigation_history:
            self.attempt.navigation_history = []
        if not self.attempt.detailed_tracking:
            self.attempt.detailed_tracking = {}
        if not self.attempt.session_data:
            self.attempt.session_data = {}
        
        if self.package.version == '1.2':
            cmi_data['cmi.core.entry'] = 'resume'
            
            # Set bookmark data
            if self.attempt.lesson_location:
                cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
                logger.info(f"RESUME: Set lesson_location: {self.attempt.lesson_location}")
            
            if self.attempt.suspend_data:
                cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info(f"RESUME: Set suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # Set other required fields
            cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status or 'not attempted'
            cmi_data['cmi.core.lesson_mode'] = 'normal'
            cmi_data['cmi.core.credit'] = 'credit'
            cmi_data['cmi.core.student_id'] = str(self.user.id) if self.user else 'student'
            cmi_data['cmi.core.student_name'] = self.user.get_full_name() or self.user.username if self.user else 'Student'
            
        else:  # SCORM 2004
            cmi_data['cmi.entry'] = 'resume'
            
            # Set bookmark data
            if self.attempt.lesson_location:
                cmi_data['cmi.location'] = self.attempt.lesson_location
                logger.info(f"RESUME: Set location: {self.attempt.lesson_location}")
            elif self.attempt.suspend_data:
                # CRITICAL FIX: If we have suspend_data but no lesson_location, 
                # set a default location to enable resume functionality
                default_location = "resume_point_1"
                cmi_data['cmi.location'] = default_location
                logger.info(f"RESUME: Set default location for resume: {default_location}")
            
            if self.attempt.suspend_data:
                cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
                logger.info(f"RESUME: Set suspend_data ({len(self.attempt.suspend_data)} chars)")
            
            # CRITICAL FIX FOR SCORM 2004 STORYLINE: Set proper status for resume
            if self.attempt.lesson_location or self.attempt.suspend_data:
                # If we have bookmark data, this is a resume - set completion_status to 'incomplete'
                cmi_data['cmi.completion_status'] = 'incomplete'
                cmi_data['cmi.success_status'] = 'unknown'
                logger.info("SCORM 2004 STORYLINE: Resume detected - set completion_status='incomplete'")
            else:
                # No bookmark data, use existing status
                cmi_data['cmi.completion_status'] = self.attempt.completion_status or 'not attempted'
                cmi_data['cmi.success_status'] = self.attempt.success_status or 'unknown'
            
            cmi_data['cmi.learner_id'] = str(self.user.id) if self.user else 'student'
            cmi_data['cmi.learner_name'] = self.user.get_full_name() or self.user.username if self.user else 'Student'
        
        return cmi_data
    
    def _prepare_storyline_resume(self) -> Dict[str, Any]:
        """Prepare Storyline-specific resume data"""
        cmi_data = self.attempt.cmi_data.copy()
        
        # Set entry mode to resume
        self.attempt.entry = 'resume'
        
        if self.package.version == '1.2':
            cmi_data['cmi.core.entry'] = 'resume'
            # Storyline 1.2 specific handling
            if self.attempt.lesson_location:
                cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
        else:  # SCORM 2004
            cmi_data['cmi.entry'] = 'resume'
            # Storyline 2004 specific handling
            if self.attempt.lesson_location:
                cmi_data['cmi.location'] = self.attempt.lesson_location
            if self.attempt.suspend_data:
                cmi_data['cmi.suspend_data'] = self.attempt.suspend_data
        
        logger.info("RESUME: Prepared Storyline-specific resume data")
        return cmi_data
    
    def _prepare_captivate_resume(self) -> Dict[str, Any]:
        """Prepare Captivate-specific resume data"""
        cmi_data = self.attempt.cmi_data.copy()
        
        # Set entry mode to resume
        self.attempt.entry = 'resume'
        
        if self.package.version == '1.2':
            cmi_data['cmi.core.entry'] = 'resume'
            # Captivate requires specific lesson_location format
            if self.attempt.lesson_location:
                cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
        else:  # SCORM 2004
            cmi_data['cmi.entry'] = 'resume'
            if self.attempt.lesson_location:
                cmi_data['cmi.location'] = self.attempt.lesson_location
        
        logger.info("RESUME: Prepared Captivate-specific resume data")
        return cmi_data
    
    def _prepare_lectora_resume(self) -> Dict[str, Any]:
        """Prepare Lectora-specific resume data"""
        cmi_data = self.attempt.cmi_data.copy()
        
        # Set entry mode to resume
        self.attempt.entry = 'resume'
        
        if self.package.version == '1.2':
            cmi_data['cmi.core.entry'] = 'resume'
            # Lectora specific handling
            if self.attempt.lesson_location:
                cmi_data['cmi.core.lesson_location'] = self.attempt.lesson_location
        else:  # SCORM 2004
            cmi_data['cmi.entry'] = 'resume'
            if self.attempt.lesson_location:
                cmi_data['cmi.location'] = self.attempt.lesson_location
        
        logger.info("RESUME: Prepared Lectora-specific resume data")
        return cmi_data
    
    def _prepare_restart_resume(self) -> Dict[str, Any]:
        """
        Prepare resume data when no bookmark data is available
        This handles cases where the user started but the content didn't save bookmark data
        """
        cmi_data = self.attempt.cmi_data.copy()
        
        # Set entry mode to resume (content will determine positioning)
        self.attempt.entry = 'resume'
        
        # CRITICAL FIX: Initialize required fields to prevent validation errors
        if not self.attempt.navigation_history:
            self.attempt.navigation_history = []
        if not self.attempt.detailed_tracking:
            self.attempt.detailed_tracking = {}
        if not self.attempt.session_data:
            self.attempt.session_data = {}
        
        if self.package.version == '1.2':
            cmi_data['cmi.core.entry'] = 'resume'
            
            # Set basic CMI data
            cmi_data['cmi.core.lesson_status'] = self.attempt.lesson_status or 'not attempted'
            cmi_data['cmi.core.lesson_mode'] = 'normal'
            cmi_data['cmi.core.credit'] = 'credit'
            cmi_data['cmi.core.student_id'] = str(self.user.id) if self.user else 'student'
            cmi_data['cmi.core.student_name'] = self.user.get_full_name() or self.user.username if self.user else 'Student'
            
        else:  # SCORM 2004
            cmi_data['cmi.entry'] = 'resume'
            
            # CRITICAL FIX FOR SCORM 2004 STORYLINE: Set proper status for restart resume
            # For restart resume (no bookmark data), set completion_status to 'incomplete' to indicate progress
            cmi_data['cmi.completion_status'] = 'incomplete'
            cmi_data['cmi.success_status'] = 'unknown'
            cmi_data['cmi.learner_id'] = str(self.user.id) if self.user else 'student'
            cmi_data['cmi.learner_name'] = self.user.get_full_name() or self.user.username if self.user else 'Student'
        
        logger.info(f"RESUME: Set entry mode to 'resume' with basic CMI data")
        return cmi_data
    
    def apply_resume_data(self) -> bool:
        """
        Apply the prepared resume data to the attempt
        Returns True if successful, False otherwise
        """
        try:
            # Prepare the resume data
            cmi_data = self.prepare_resume_data()
            
            # Update the attempt with the prepared data
            self.attempt.cmi_data = cmi_data
            self.attempt.save()
            
            logger.info(f"RESUME: Applied resume data for attempt {self.attempt.id}: entry='{self.attempt.entry}', location='{self.attempt.lesson_location or 'None'}', suspend_data='{self.attempt.suspend_data[:50] if self.attempt.suspend_data else 'None'}...'")
            
            return True
            
        except Exception as e:
            logger.error(f"RESUME: Error applying resume data for attempt {self.attempt.id}: {str(e)}")
            return False
    
    def detect_package_type(self) -> str:
        """
        Detect the specific type of SCORM package for specialized handling
        """
        # Check package filename for clues
        filename = self.package.package_file.name.lower() if self.package.package_file else ''
        
        # Check for specific authoring tool indicators
        if 'storyline' in filename:
            return 'storyline'
        elif 'captivate' in filename:
            return 'captivate'
        elif 'lectora' in filename:
            return 'lectora'
        elif 'rise' in filename:
            return 'rise'
        else:
            return 'generic'
    
    def handle_package_specific_resume(self) -> bool:
        """
        Handle resume logic specific to the detected package type
        """
        package_type = self.detect_package_type()
        
        if package_type == 'storyline':
            return self._handle_storyline_resume()
        elif package_type == 'captivate':
            return self._handle_captivate_resume()
        elif package_type == 'lectora':
            return self._handle_lectora_resume()
        else:
            return self.apply_resume_data()
    
    def _handle_storyline_resume(self) -> bool:
        """
        Handle resume for Articulate Storyline packages
        Storyline packages often have complex suspend data structures
        """
        logger.info(f"RESUME: Handling Storyline-specific resume for attempt {self.attempt.id}")
        
        # Storyline packages may need special handling for suspend data
        if self.attempt.suspend_data:
            # Check if suspend data contains Storyline-specific patterns
            if 'qd"true' in self.attempt.suspend_data or 'scors' in self.attempt.suspend_data:
                logger.info(f"RESUME: Found Storyline-specific suspend data patterns")
        
        return self.apply_resume_data()
    
    def _handle_captivate_resume(self) -> bool:
        """
        Handle resume for Adobe Captivate packages
        """
        logger.info(f"RESUME: Handling Captivate-specific resume for attempt {self.attempt.id}")
        
        # Captivate packages may need special handling for lesson_location
        if self.attempt.lesson_location:
            logger.info(f"RESUME: Found Captivate lesson_location: {self.attempt.lesson_location}")
        
        return self.apply_resume_data()
    
    def _handle_lectora_resume(self) -> bool:
        """
        Handle resume for Lectora packages
        """
        logger.info(f"RESUME: Handling Lectora-specific resume for attempt {self.attempt.id}")
        
        # Lectora packages may need special handling
        return self.apply_resume_data()


def handle_scorm_resume(attempt: ScormAttempt) -> bool:
    """
    Main function to handle SCORM resume functionality
    This is the entry point for resume logic
    """
    try:
        handler = EnhancedScormResumeHandler(attempt)
        
        # Check if this attempt can be resumed
        if not handler.can_resume():
            logger.info(f"RESUME: Attempt {attempt.id} cannot be resumed (status: {attempt.lesson_status})")
            return False
        
        # Handle package-specific resume logic
        return handler.handle_package_specific_resume()
        
    except Exception as e:
        logger.error(f"RESUME: Error handling resume for attempt {attempt.id}: {str(e)}")
        return False
