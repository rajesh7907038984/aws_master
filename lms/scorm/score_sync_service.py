"""
SCORM Score Sync Service - Simplified
Basic score synchronization for SCORM attempts
"""
import logging
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger(__name__)


class ScormScoreSyncService:
    """
    Simple service for SCORM score synchronization
    """
    
    @staticmethod
    def sync_score(attempt):
        """
        Synchronize SCORM score data
        
        Args:
            attempt: ScormAttempt instance
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Skip if no score data
            if not attempt.score_raw:
                return True
            
            # Use transaction to ensure atomicity
            with transaction.atomic():
                # Validate score
                score = Decimal(str(attempt.score_raw))
                if score < 0 or score > 100:
                    logger.warning(f"Invalid score {score} for attempt {attempt.id}")
                    return False
                
                # Update attempt
                attempt.save()
                logger.info(f"Score synchronized for attempt {attempt.id}: {score}")
                return True
                
        except Exception as e:
            logger.error(f"Error syncing score for attempt {attempt.id}: {e}")
            return False