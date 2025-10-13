"""
SCORM Preview API Handler
Handles SCORM API calls in preview mode without database persistence
"""
import logging
from datetime import datetime
from django.utils import timezone
from .api_handler import ScormAPIHandler

logger = logging.getLogger(__name__)


class ScormPreviewHandler(ScormAPIHandler):
    """
    Preview-only SCORM API handler that logs actions but doesn't save to database
    Used for instructor preview mode
    """
    
    def __init__(self, attempt):
        """Initialize preview handler"""
        super().__init__(attempt)
        self.preview_data = {}
        logger.info(f"SCORM Preview Handler initialized for user: {attempt.user.username}")
    
    def _commit_data(self):
        """Preview mode: Log data but don't save to database"""
        logger.info(f"[PREVIEW] SCORM data would be saved: {self.attempt.cmi_data}")
        logger.info(f"[PREVIEW] Lesson status: {self.attempt.lesson_status}")
        logger.info(f"[PREVIEW] Score: {self.attempt.score_raw}")
        logger.info(f"[PREVIEW] Total time: {self.attempt.total_time}")
        
        # Store data in preview_data for logging but don't save to database
        self.preview_data = {
            'cmi_data': self.attempt.cmi_data.copy(),
            'lesson_status': self.attempt.lesson_status,
            'completion_status': self.attempt.completion_status,
            'score_raw': self.attempt.score_raw,
            'total_time': self.attempt.total_time,
            'last_accessed': timezone.now().isoformat(),
        }
        
        # DON'T call attempt.save() - this is preview mode
        logger.info("[PREVIEW] Data logged but not saved to database")
    
    def _update_topic_progress(self):
        """Preview mode: Don't update topic progress"""
        logger.info("[PREVIEW] Topic progress update skipped (preview mode)")
        
    def get_preview_summary(self):
        """Get a summary of preview session data"""
        return {
            'preview_mode': True,
            'user': self.attempt.user.username,
            'data_tracked': self.preview_data,
            'api_calls_made': True,
            'database_saved': False,
        }
