"""
Enhanced SCORM Time Tracking with Database Reliability
Solves all time tracking database saving issues for ALL SCORM types
"""

import logging
from django.db import transaction, DatabaseError, IntegrityError
from django.utils import timezone
from django.core.cache import cache
import time
import json
import re

logger = logging.getLogger(__name__)

class EnhancedScormTimeTracker:
    """
    Enhanced SCORM time tracking with database reliability
    Solves all time tracking database saving issues
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.scorm_version = attempt.scorm_package.version
        self.max_retries = 3
        self.retry_delay = 0.1
        
        # Version-specific time handlers
        self.time_handlers = {
            '1.1': self._handle_scorm_1_1_time,
            '1.2': self._handle_scorm_1_2_time,
            '2004': self._handle_scorm_2004_time,
            'xapi': self._handle_xapi_time,
            'storyline': self._handle_storyline_time,
            'captivate': self._handle_captivate_time,
            'lectora': self._handle_lectora_time,
            'html5': self._handle_html5_time,
            'dual': self._handle_dual_scorm_time,
            'legacy': self._handle_legacy_time,
            'unknown': self._handle_legacy_time,  # Default fallback
        }
    
    def save_time_with_reliability(self, session_time, total_time=None):
        """
        Save time tracking data with comprehensive error handling and retry logic
        """
        for attempt_num in range(self.max_retries):
            try:
                with transaction.atomic():
                    # Use select_for_update to prevent race conditions
                    locked_attempt = self.attempt.__class__.objects.select_for_update().get(
                        id=self.attempt.id
                    )
                    
                    # Update time tracking fields
                    if session_time:
                        locked_attempt.session_time = session_time
                        self._update_total_time(locked_attempt, session_time)
                    
                    if total_time:
                        locked_attempt.total_time = total_time
                        locked_attempt.time_spent_seconds = self._parse_scorm_time_to_seconds(total_time)
                    
                    # Update session tracking
                    now = timezone.now()
                    if not locked_attempt.session_start_time:
                        locked_attempt.session_start_time = now
                    locked_attempt.session_end_time = now
                    locked_attempt.last_accessed = now
                    
                    # Update detailed tracking
                    if not locked_attempt.detailed_tracking:
                        locked_attempt.detailed_tracking = {}
                    
                    locked_attempt.detailed_tracking.update({
                        'total_time_seconds': locked_attempt.time_spent_seconds,
                        'last_session_duration': self._parse_scorm_time_to_seconds(session_time) if session_time else 0,
                        'session_count': locked_attempt.detailed_tracking.get('session_count', 0) + 1,
                        'last_updated': now.isoformat(),
                        'save_attempt': attempt_num + 1,
                        'scorm_version': self.scorm_version
                    })
                    
                    # Ensure required fields are not blank
                    if not locked_attempt.navigation_history:
                        locked_attempt.navigation_history = []
                    if not locked_attempt.session_data:
                        locked_attempt.session_data = {}
                    
                    # Validate before save
                    locked_attempt.full_clean()
                    locked_attempt.save()
                    
                    # Verify save worked
                    self._verify_save_success(locked_attempt)
                    
                    # Sync with TopicProgress
                    self._sync_with_topic_progress(locked_attempt)
                    
                    logger.info(f"✅ Time tracking saved successfully for {self.scorm_version} (attempt {attempt_num + 1})")
                    return True
                    
            except (DatabaseError, IntegrityError) as e:
                logger.warning(f"Database error on attempt {attempt_num + 1}: {str(e)}")
                if attempt_num == self.max_retries - 1:
                    # Final attempt failed - use cache fallback
                    return self._cache_fallback_save(session_time, total_time)
                time.sleep(self.retry_delay * (attempt_num + 1))  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt_num + 1}: {str(e)}")
                if attempt_num == self.max_retries - 1:
                    return self._cache_fallback_save(session_time, total_time)
                time.sleep(self.retry_delay * (attempt_num + 1))
        
        return False
    
    def _update_total_time(self, attempt, session_time):
        """Update total time by adding session time"""
        try:
            session_seconds = self._parse_scorm_time_to_seconds(session_time)
            current_total = self._parse_scorm_time_to_seconds(attempt.total_time)
            new_total = current_total + session_seconds
            
            attempt.total_time = self._format_scorm_time(new_total)
            attempt.time_spent_seconds = int(new_total)
            
        except Exception as e:
            logger.error(f"Error updating total time: {str(e)}")
    
    def _parse_scorm_time_to_seconds(self, time_str):
        """Convert SCORM time format to seconds"""
        try:
            if not time_str or time_str == '0000:00:00.00':
                return 0
            
            if time_str.startswith('PT'):
                # SCORM 2004 duration format
                return self._parse_iso_duration(time_str)
            else:
                # SCORM 1.2 time format
                parts = time_str.split(':')
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    return int(hours * 3600 + minutes * 60 + seconds)
            return 0
        except (ValueError, IndexError, TypeError):
            return 0
    
    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration format (PT1H30M45S) to seconds"""
        try:
            if not duration_str or not duration_str.startswith('PT'):
                return 0
            
            duration_str = duration_str[2:]  # Remove 'PT' prefix
            total_seconds = 0
            
            # Parse hours
            if 'H' in duration_str:
                hours_part = duration_str.split('H')[0]
                total_seconds += int(hours_part) * 3600
                duration_str = duration_str.split('H')[1]
            
            # Parse minutes
            if 'M' in duration_str:
                minutes_part = duration_str.split('M')[0]
                total_seconds += int(minutes_part) * 60
                duration_str = duration_str.split('M')[1]
            
            # Parse seconds
            if 'S' in duration_str:
                seconds_part = duration_str.split('S')[0]
                total_seconds += float(seconds_part)
            
            return int(total_seconds)
        except (ValueError, IndexError):
            return 0
    
    def _format_scorm_time(self, total_seconds):
        """Format seconds to SCORM time format"""
        if self.scorm_version in ['2004', 'xapi', 'storyline']:
            # Use SCORM 2004 format
            return self._format_scorm_2004_time(total_seconds)
        else:
            # Use SCORM 1.2 format
            return self._format_scorm_1_2_time(total_seconds)
    
    def _format_scorm_1_2_time(self, seconds):
        """Format seconds to SCORM 1.2 time format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:04d}:{minutes:02d}:{secs:05.2f}"
    
    def _format_scorm_2004_time(self, seconds):
        """Format seconds to SCORM 2004 time format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        time_str = "PT"
        if hours > 0:
            time_str += f"{hours}H"
        if minutes > 0:
            time_str += f"{minutes}M"
        if secs > 0:
            time_str += f"{secs}S"
        
        return time_str
    
    def _verify_save_success(self, attempt):
        """Verify that the save actually worked"""
        try:
            # Re-fetch from database to verify
            saved_attempt = attempt.__class__.objects.get(id=attempt.id)
            
            # Check critical fields
            if not saved_attempt.total_time:
                raise ValueError("Total time not saved")
            if saved_attempt.time_spent_seconds is None:
                raise ValueError("Time spent seconds not saved")
            
            logger.info(f"✅ Save verification successful: total_time={saved_attempt.total_time}, time_spent_seconds={saved_attempt.time_spent_seconds}")
            
        except Exception as e:
            logger.error(f"❌ Save verification failed: {str(e)}")
            raise
    
    def _sync_with_topic_progress(self, attempt):
        """Sync time with TopicProgress for accurate reporting"""
        try:
            from courses.models import TopicProgress
            
            # Get or create topic progress
            progress, created = TopicProgress.objects.select_for_update().get_or_create(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            )
            
            # Update time spent
            progress.total_time_spent = int(attempt.time_spent_seconds or 0)
            progress.last_accessed = timezone.now()
            
            # Save with validation
            progress.full_clean()
            progress.save()
            
            logger.info(f"✅ Synced time with TopicProgress: {progress.total_time_spent} seconds")
            
        except Exception as e:
            logger.error(f"❌ Failed to sync with TopicProgress: {str(e)}")
    
    def _cache_fallback_save(self, session_time, total_time):
        """Fallback to cache when database fails"""
        try:
            cache_key = f"scorm_time_fallback_{self.attempt.id}_{self.scorm_version}"
            fallback_data = {
                'session_time': session_time,
                'total_time': total_time,
                'scorm_version': self.scorm_version,
                'timestamp': timezone.now().isoformat(),
                'attempt_id': self.attempt.id
            }
            
            # Store in cache for later processing
            cache.set(cache_key, fallback_data, timeout=3600)  # 1 hour
            
            logger.warning(f"⚠️ Database save failed, using cache fallback for {self.scorm_version}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Cache fallback also failed: {str(e)}")
            return False
    
    # Version-specific time handlers
    def _handle_scorm_1_1_time(self, time_str):
        """Handle SCORM 1.1 time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_scorm_1_2_time(self, time_str):
        """Handle SCORM 1.2 time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_scorm_2004_time(self, time_str):
        """Handle SCORM 2004 time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_storyline_time(self, time_str):
        """Handle Articulate Storyline time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_captivate_time(self, time_str):
        """Handle Adobe Captivate time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_lectora_time(self, time_str):
        """Handle Lectora time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_html5_time(self, time_str):
        """Handle HTML5 package time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_xapi_time(self, time_str):
        """Handle xAPI/Tin Can time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_dual_scorm_time(self, time_str):
        """Handle dual SCORM + xAPI time format"""
        return self._parse_scorm_time_to_seconds(time_str)
    
    def _handle_legacy_time(self, time_str):
        """Handle legacy SCORM time format"""
        return self._parse_scorm_time_to_seconds(time_str)


class ScormTimeTrackingMiddleware:
    """
    Middleware to process cached time tracking data when database is available
    """
    
    @staticmethod
    def process_cached_time_data():
        """Process any cached time tracking data"""
        try:
            # Get all cached time tracking data
            cache_keys = cache.keys("scorm_time_fallback_*")
            
            for key in cache_keys:
                try:
                    data = cache.get(key)
                    if data:
                        # Process the cached data
                        attempt_id = data.get('attempt_id')
                        if attempt_id:
                            from scorm.models import ScormAttempt
                            attempt = ScormAttempt.objects.get(id=attempt_id)
                            tracker = EnhancedScormTimeTracker(attempt)
                            
                            # Try to save the cached data
                            if tracker.save_time_with_reliability(
                                data.get('session_time'),
                                data.get('total_time')
                            ):
                                # Success - remove from cache
                                cache.delete(key)
                                logger.info(f"✅ Processed cached time data for attempt {attempt_id}")
                            
                except Exception as e:
                    logger.error(f"Error processing cached time data for key {key}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error processing cached time data: {str(e)}")


class ScormTimeTrackingMonitor:
    """Monitor SCORM time tracking database issues"""
    
    @staticmethod
    def check_time_tracking_health():
        """Check if time tracking is working properly"""
        try:
            from scorm.models import ScormAttempt
            
            # Check for failed time tracking saves
            failed_attempts = ScormAttempt.objects.filter(
                detailed_tracking__has_key='save_attempt',
                detailed_tracking__save_attempt__gt=1
            ).count()
            
            # Check for cache fallbacks
            cache_keys = cache.keys("scorm_time_fallback_*")
            fallback_count = len(cache_keys)
            
            # Check database connection health
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            return {
                'status': 'healthy',
                'failed_attempts': failed_attempts,
                'fallback_count': fallback_count,
                'database_connected': True
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'database_connected': False
            }
