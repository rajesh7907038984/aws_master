"""
Simple SCORM Data Handler - Robust and Clean
Replaces all the complex old methods with a simple, reliable approach
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from typing import Optional

logger = logging.getLogger(__name__)


class ScormDataHandler:
    """
    Simple, robust SCORM data handler
    Handles all score, progress, and time saving in one place
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.topic = attempt.scorm_package.topic
        
    @transaction.atomic
    def save_data(self, element: str, value: str) -> bool:
        """
        Simple method to save any SCORM data element
        Returns True if data was saved successfully
        """
        try:
            logger.info(f"SAVING: {element} = {value} for attempt {self.attempt.id}")
            
            # Update the attempt based on element type
            updated = False
            
            if element in ['cmi.core.score.raw', 'cmi.score.raw']:
                updated = self._save_score(value)
                
            elif element in ['cmi.core.lesson_status', 'cmi.completion_status', 'cmi.success_status']:
                updated = self._save_status(element, value)
                
            elif element in ['cmi.core.lesson_location', 'cmi.location']:
                updated = self._save_location(value)
                
            elif element == 'cmi.suspend_data':
                updated = self._save_suspend_data(value)
                
            elif element in ['cmi.core.session_time', 'cmi.session_time']:
                updated = self._save_time(value)
                
            # Always update CMI data
            if not self.attempt.cmi_data:
                self.attempt.cmi_data = {}
            self.attempt.cmi_data[element] = value
            updated = True
            
            if updated:
                # Save attempt
                self.attempt.last_accessed = timezone.now()
                self.attempt.save()
                
                # Update topic progress
                self._update_topic_progress()
                
                logger.info(f"SAVED: {element} = {value} for attempt {self.attempt.id}")
                return True
                
        except Exception as e:
            logger.error(f"SAVE ERROR: Failed to save {element} = {value}: {str(e)}")
            
        return False
    
    def _save_score(self, value: str) -> bool:
        """Save score data"""
        try:
            if not value or value == '':
                return False
                
            score = Decimal(str(value))
            self.attempt.score_raw = score
            logger.info(f"Score saved: {score}")
            return True
            
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid score value: {value} - {str(e)}")
            return False
    
    def _save_status(self, element: str, value: str) -> bool:
        """Save status data"""
        try:
            if 'lesson_status' in element or 'completion_status' in element:
                self.attempt.lesson_status = value
                
                # Auto-complete if status indicates completion
                if value in ['completed', 'passed']:
                    self.attempt.completion_status = 'completed'
                    if not self.attempt.completed_at:
                        self.attempt.completed_at = timezone.now()
                        
            elif 'success_status' in element:
                self.attempt.success_status = value
                
            logger.info(f"Status saved: {element} = {value}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving status: {str(e)}")
            return False
    
    def _save_location(self, value: str) -> bool:
        """Save bookmark location"""
        try:
            self.attempt.lesson_location = value
            logger.info(f"Location saved: {value}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving location: {str(e)}")
            return False
    
    def _save_suspend_data(self, value: str) -> bool:
        """Save suspend data"""
        try:
            self.attempt.suspend_data = value
            
            # Try to extract progress from suspend data
            progress = self._extract_progress_from_suspend_data(value)
            if progress is not None:
                self.attempt.progress_percentage = progress
                logger.info(f"Progress extracted from suspend data: {progress}%")
                
            logger.info(f"Suspend data saved (length: {len(value)})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving suspend data: {str(e)}")
            return False
    
    def _save_time(self, value: str) -> bool:
        """Save time data"""
        try:
            self.attempt.session_time = value
            
            # Update total time
            current_total = self._parse_time_to_seconds(self.attempt.total_time or '0000:00:00')
            session_seconds = self._parse_time_to_seconds(value)
            new_total_seconds = current_total + session_seconds
            
            self.attempt.total_time = self._seconds_to_time_format(new_total_seconds)
            self.attempt.time_spent_seconds = int(new_total_seconds)
            
            logger.info(f"Time saved: session={value}, total={self.attempt.total_time}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving time: {str(e)}")
            return False
    
    def _extract_progress_from_suspend_data(self, suspend_data: str) -> Optional[float]:
        """Extract progress percentage from suspend data"""
        try:
            import re
            
            # Look for progress patterns
            patterns = [
                r'progress[=:](\d+)',
                r'"progress":\s*(\d+)',
                r'completion[=:](\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, suspend_data, re.IGNORECASE)
                if match:
                    progress = float(match.group(1))
                    if 0 <= progress <= 100:
                        return progress
                        
        except Exception as e:
            logger.debug(f"Could not extract progress: {str(e)}")
            
        return None
    
    def _parse_time_to_seconds(self, time_str: str) -> int:
        """Parse SCORM time format to seconds"""
        try:
            if not time_str:
                return 0
                
            # Handle PT format (SCORM 2004)
            if time_str.startswith('PT'):
                # Simple PT parsing
                import re
                hours = re.search(r'(\d+)H', time_str)
                minutes = re.search(r'(\d+)M', time_str)
                seconds = re.search(r'(\d+(?:\.\d+)?)S', time_str)
                
                total = 0
                if hours:
                    total += int(hours.group(1)) * 3600
                if minutes:
                    total += int(minutes.group(1)) * 60
                if seconds:
                    total += float(seconds.group(1))
                    
                return int(total)
            
            # Handle standard format (hhhh:mm:ss)
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return int(hours * 3600 + minutes * 60 + seconds)
                
        except Exception as e:
            logger.warning(f"Could not parse time '{time_str}': {str(e)}")
            
        return 0
    
    def _seconds_to_time_format(self, total_seconds: int) -> str:
        """Convert seconds to SCORM time format"""
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:04d}:{minutes:02d}:{seconds:02d}.00"
    
    @transaction.atomic
    def _update_topic_progress(self):
        """Update TopicProgress with simple logic"""
        try:
            from courses.models import TopicProgress
            
            # Get or create topic progress
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=self.topic,
                defaults={
                    'attempts': 1,
                    'last_accessed': timezone.now()
                }
            )
            
            # Update score if we have one
            if self.attempt.score_raw is not None:
                score_value = float(self.attempt.score_raw)
                progress.last_score = score_value
                
                # Update best score
                if progress.best_score is None or score_value > progress.best_score:
                    progress.best_score = score_value
                    
                logger.info(f"TopicProgress score updated: {score_value}")
            
            # Update completion status
            is_completed = (
                self.attempt.lesson_status in ['completed', 'passed'] or
                self.attempt.completion_status == 'completed'
            )
            
            if is_completed and not progress.completed:
                progress.completed = True
                progress.completion_method = 'scorm'
                progress.completed_at = timezone.now()
                logger.info(f"TopicProgress marked as completed")
            
            # Update time
            if self.attempt.time_spent_seconds:
                progress.total_time_spent = max(
                    progress.total_time_spent or 0,
                    self.attempt.time_spent_seconds
                )
            
            # Update attempts count
            progress.attempts = max(progress.attempts or 0, self.attempt.attempt_number)
            progress.last_accessed = timezone.now()
            
            # Save progress
            progress.save()
            
            logger.info(f"TopicProgress updated for user {self.attempt.user.id}, topic {self.topic.id}")
                
        except Exception as e:
            logger.error(f"Error updating TopicProgress: {str(e)}")
    
    def force_sync(self) -> bool:
        """Force a complete sync of all data"""
        try:
            logger.info(f"FORCE SYNC: Starting for attempt {self.attempt.id}")
            
            # Refresh from database
            self.attempt.refresh_from_db()
            
            # Update topic progress
            self._update_topic_progress()
            
            logger.info(f"FORCE SYNC: Completed for attempt {self.attempt.id}")
            return True
            
        except Exception as e:
            logger.error(f"FORCE SYNC ERROR: {str(e)}")
            return False
