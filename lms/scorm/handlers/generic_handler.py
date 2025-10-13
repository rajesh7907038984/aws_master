"""
Generic SCORM Handler
Fallback handler for unknown or standard SCORM packages
"""
import logging
from .base_handler import BaseScormAPIHandler

logger = logging.getLogger(__name__)


class GenericHandler(BaseScormAPIHandler):
    """
    Generic handler for standard SCORM packages
    
    Features:
    - Standard SCORM 1.2 / 2004 compliance
    - Basic bookmark and suspend_data support
    - No package-specific optimizations
    """
    
    def initialize(self):
        """
        Initialize with standard SCORM resume support
        """
        result = super().initialize()
        
        if result == 'true':
            logger.info(f"📦 Generic SCORM Handler initialized for attempt {self.attempt.id}")
            
            if self.attempt.lesson_location or self.attempt.suspend_data:
                logger.info(f"   Resume data available")
        
        return result
    
    def terminate(self):
        """
        Standard SCORM termination
        """
        logger.info(f"📦 [Generic] Terminating SCORM session...")
        return super().terminate()
    
    def get_handler_name(self):
        return "GenericHandler"

