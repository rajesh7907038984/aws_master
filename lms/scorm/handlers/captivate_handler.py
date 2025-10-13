"""
Adobe Captivate SCORM Handler
Optimized for Captivate-specific features and quirks
"""
import logging
from .base_handler import BaseScormAPIHandler

logger = logging.getLogger(__name__)


class CaptivateHandler(BaseScormAPIHandler):
    """
    Handler optimized for Adobe Captivate packages
    
    Captivate-specific features:
    - multiscreen.html or index.html entry point
    - Slide-based navigation
    - Variable tracking in suspend_data
    - Quiz results management
    """
    
    def initialize(self):
        """
        Initialize with Captivate-specific resume support
        """
        result = super().initialize()
        
        if result == 'true':
            logger.info(f"🎬 Captivate Handler initialized for attempt {self.attempt.id}")
            
            # Captivate-specific: Log slide bookmark
            if self.attempt.lesson_location:
                logger.info(f"   Resume at slide: {self.attempt.lesson_location}")
        
        return result
    
    def set_value(self, element, value):
        """
        Captivate SetValue with enhanced slide tracking
        """
        # Captivate uses lesson_location for slide position
        if element in ['cmi.core.lesson_location', 'cmi.location']:
            logger.info(f" [Captivate] Slide position: {value}")
        
        result = super().set_value(element, value)
        
        # Captivate: Track slide progress
        if element in ['cmi.core.lesson_location', 'cmi.location'] and result == 'true':
            self._update_captivate_progress(value)
        
        return result
    
    def _update_captivate_progress(self, slide_location):
        """
        Update progress based on Captivate slide navigation
        """
        try:
            # Captivate typically uses numeric slide identifiers
            # Try to extract slide number
            import re
            slide_match = re.search(r'(\d+)', str(slide_location))
            
            if slide_match:
                current_slide = int(slide_match.group(1))
                
                # Update progress based on slide number
                if self.attempt.total_slides and self.attempt.total_slides > 0:
                    progress = (current_slide / self.attempt.total_slides) * 100
                    self.attempt.progress_percentage = min(progress, 100)
                    logger.info(f"   [Captivate] Progress: {self.attempt.progress_percentage:.1f}% (Slide {current_slide}/{self.attempt.total_slides})")
        
        except Exception as e:
            logger.error(f"Error updating Captivate progress: {str(e)}")
    
    def terminate(self):
        """
        Captivate Terminate - ensure slide position is saved
        """
        logger.info(f"🎬 [Captivate] Terminating - saving slide progress...")
        
        if self.attempt.lesson_location:
            logger.info(f"   Final slide: {self.attempt.lesson_location}")
        
        return super().terminate()
    
    def get_handler_name(self):
        return "CaptivateHandler"

