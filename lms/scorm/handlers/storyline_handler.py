"""
Articulate Storyline SCORM Handler
Optimized for Storyline-specific features and quirks
"""
import logging
from .base_handler import BaseScormAPIHandler

logger = logging.getLogger(__name__)


class StorylineHandler(BaseScormAPIHandler):
    """
    Handler optimized for Articulate Storyline packages
    
    Storyline-specific features:
    - Heavy use of suspend_data for quiz state
    - Frequent commits needed
    - Specific bookmark format
    - Quiz results stored in interactions
    """
    
    def initialize(self):
        """
        Initialize with Storyline-specific resume support
        """
        result = super().initialize()
        
        if result == 'true':
            logger.info(f"📘 Storyline Handler initialized for attempt {self.attempt.id}")
            
            # Storyline-specific: Ensure suspend_data is available for quiz resume
            if self.attempt.suspend_data:
                logger.info(f"   Quiz state available: {len(self.attempt.suspend_data)} chars")
        
        return result
    
    def set_value(self, element, value):
        """
        Storyline SetValue with enhanced suspend_data handling
        """
        # Storyline stores quiz answers in suspend_data - save immediately
        if element == 'cmi.suspend_data':
            logger.info(f" [Storyline] Saving quiz state: {len(str(value))} chars")
            # Log first 200 chars of suspend_data for debugging
            logger.debug(f"   [Storyline] Suspend data preview: {str(value)[:200]}...")
        
        result = super().set_value(element, value)
        
        # Storyline quiz state: Auto-commit on critical saves
        if element in ['cmi.suspend_data', 'cmi.core.score.raw'] and result == 'true':
            logger.info(f"   [Storyline] Auto-saving critical data to database...")
            self._commit_data()
            logger.info(f"   [Storyline] Auto-save complete")
        
        return result
    
    def terminate(self):
        """
        Storyline Terminate - ensure quiz state is saved
        """
        logger.info(f"📘 [Storyline] Terminating - saving final quiz state...")
        
        # Force a final commit before terminating
        self._commit_data()
        
        # Ensure all quiz data is saved
        if self.attempt.suspend_data:
            logger.info(f"   Final quiz state: {len(self.attempt.suspend_data)} chars saved")
            logger.debug(f"   Quiz state preview: {self.attempt.suspend_data[:200]}...")
        else:
            logger.warning(f"   WARNING: No suspend_data found on terminate!")
        
        return super().terminate()
    
    def commit(self):
        """
        Enhanced commit for Storyline to handle multiple rapid commits
        """
        logger.info(f"📘 [Storyline] Commit called - ensuring quiz state is saved")
        
        # Log current suspend_data length
        if self.attempt.suspend_data:
            logger.info(f"   Current suspend_data: {len(self.attempt.suspend_data)} chars")
        else:
            logger.warning(f"   WARNING: No suspend_data in commit!")
        
        result = super().commit()
        
        if result == 'true':
            logger.info(f"   [Storyline] Commit successful, data persisted")
        else:
            logger.error(f"   [Storyline] Commit failed!")
        
        return result
    
    def get_handler_name(self):
        return "StorylineHandler"

