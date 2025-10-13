"""
Articulate Rise 360 SCORM Handler
Optimized for Rise 360-specific features and quirks
"""
import logging
from .base_handler import BaseScormAPIHandler

logger = logging.getLogger(__name__)


class Rise360Handler(BaseScormAPIHandler):
    """
    Handler optimized for Articulate Rise 360 packages
    
    Rise 360-specific features:
    - Bookmark format: index.html#/lessons/[lesson-id]
    - Progress tracked via lesson navigation
    - Minimal suspend_data usage
    - Lesson completion tracking
    - CRITICAL: Rise calculates its own progress - DO NOT pre-populate progress_measure
    """
    
    def initialize(self):
        """
        Initialize with Rise 360-specific resume support
        CRITICAL FIX: Clear progress_measure to let Rise calculate its own progress
        """
        result = super().initialize()
        
        if result == 'true':
            logger.info(f"📗 Rise 360 Handler initialized for attempt {self.attempt.id}")
            
            # CRITICAL BUG FIX: Rise 360 calculates its own internal progress for the "X% COMPLETE" bar
            # We MUST return empty string for progress_measure to let Rise calculate from scratch
            # If we return a pre-calculated value, Rise will display stale/incorrect progress
            if self.version != '1.2':
                # Clear progress_measure for SCORM 2004
                self.attempt.cmi_data['cmi.progress_measure'] = ''
                logger.info(f"   [Rise 360] Cleared progress_measure - Rise will calculate its own")
            
            # Rise 360-specific: Log lesson bookmark for resume
            if self.attempt.lesson_location and '#/lessons/' in self.attempt.lesson_location:
                lesson_id = self.attempt.lesson_location.split('#/lessons/')[1].split('/')[0] if '#/lessons/' in self.attempt.lesson_location else 'unknown'
                logger.info(f"   Resume at lesson: {lesson_id[:20]}...")
        
        return result
    
    def get_value(self, element):
        """
        Rise 360 GetValue with progress_measure fix
        CRITICAL: Always return empty string for progress_measure so Rise calculates its own
        """
        # CRITICAL BUG FIX: Rise 360 displays "X% COMPLETE" cosmetic bar based on progress_measure
        # If we return a pre-calculated value, it shows stale/incorrect progress
        # Return empty string so Rise calculates fresh progress from lesson navigation
        if element == 'cmi.progress_measure':
            logger.info(f"📗 [Rise 360] GetValue(progress_measure) -> '' (letting Rise calculate)")
            return ''
        
        # For all other elements, use parent implementation
        return super().get_value(element)
    
    def set_value(self, element, value):
        """
        Rise 360 SetValue with enhanced lesson_location handling
        """
        # Rise 360 uses lesson_location for bookmarking
        if element in ['cmi.core.lesson_location', 'cmi.location']:
            if '#/lessons/' in str(value):
                logger.info(f"💾 [Rise 360] Bookmark saved: {str(value)[:80]}...")
                # Extract lesson progress
                self._extract_rise360_progress(value)
        
        # CRITICAL: Accept progress_measure from Rise 360 (it calculates its own)
        # Store it so we can sync to backend, but don't interfere with Rise's calculation
        if element == 'cmi.progress_measure' and value:
            logger.info(f"💾 [Rise 360] Progress measure received from Rise: {value}")
        
        result = super().set_value(element, value)
        
        # Rise 360: Auto-save bookmarks immediately
        if element in ['cmi.core.lesson_location', 'cmi.location'] and result == 'true':
            logger.info(f"   [Rise 360] Auto-saving bookmark...")
        
        return result
    
    def _extract_rise360_progress(self, bookmark):
        """
        Extract progress from Rise 360 bookmark format
        Format: index.html#/lessons/[lesson-id]
        """
        try:
            if not bookmark or '#/lessons/' not in bookmark:
                return
            
            # Parse lesson ID
            lesson_id = bookmark.split('#/lessons/')[1].split('/')[0] if '#/lessons/' in bookmark else ''
            
            if lesson_id:
                # Track visited lessons
                if not isinstance(self.attempt.completed_slides, list):
                    self.attempt.completed_slides = []
                
                if lesson_id not in self.attempt.completed_slides:
                    self.attempt.completed_slides.append(lesson_id)
                    logger.info(f"   [Rise 360] Lesson {len(self.attempt.completed_slides)} visited: {lesson_id[:20]}...")
                
                # Update progress if total lessons known
                if self.attempt.total_slides and self.attempt.total_slides > 0:
                    progress = (len(self.attempt.completed_slides) / self.attempt.total_slides) * 100
                    self.attempt.progress_percentage = min(progress, 100)
                    logger.info(f"   [Rise 360] Progress: {self.attempt.progress_percentage:.1f}%")
        
        except Exception as e:
            logger.error(f"Error extracting Rise 360 progress: {str(e)}")
    
    def terminate(self):
        """
        Rise 360 Terminate - ensure lesson bookmark is saved
        """
        logger.info(f"📗 [Rise 360] Terminating - saving lesson progress...")
        
        if self.attempt.lesson_location:
            logger.info(f"   Final bookmark: {self.attempt.lesson_location[:80]}...")
        
        if self.attempt.completed_slides:
            logger.info(f"   Lessons visited: {len(self.attempt.completed_slides)}")
        
        return super().terminate()
    
    def get_handler_name(self):
        return "Rise360Handler"

