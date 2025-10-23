"""
Dynamic SCORM Score Processor
Automatically detects and handles different SCORM formats and score reporting patterns.
This runs in real-time to prevent score synchronization issues.
"""
import logging
import re
import json
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache

logger = logging.getLogger(__name__)


class DynamicScormScoreProcessor:
    """
    Dynamic processor that automatically adapts to different SCORM package formats
    and ensures scores are properly synchronized in real-time.
    """
    
    # Define patterns for different SCORM authoring tools and formats
    SCORE_PATTERNS = {
        'articulate_storyline': [
            r'scors(\d+)',                    # Storyline: scors88
            r'scor["\s]*(\d+)',              # Storyline: scor"88 
            r'quiz_score["\s:]*(\d+)',       # quiz_score:88
            r'final_score["\s:]*(\d+)',      # final_score:88
            r'user_score["\s:]*(\d+)',       # user_score:88
            # STORYLINE FIX: Add more comprehensive score patterns
            r'(?<!p)scors(\d+)',             # scors88 but not pscors88
            r'(?<!p)scor["\s]*(\d+)',        # scor"88 but not pscor
            r'actual_score["\s:]*(\d+)',     # actual_score patterns
            r'earned_score["\s:]*(\d+)',     # earned_score patterns
            r'earned["\s:]*(\d+)',           # earned patterns
            r'result["\s:]*(\d+)',           # result patterns
            r'score["\s:]*(\d+)',             # generic score patterns
        ],
        'adobe_captivate': [
            r'"score"\s*:\s*(\d+\.?\d*)',    # Captivate JSON format
            r'cmi\.score\.raw["\s:]*(\d+)',  # Direct CMI score
            r'userScore["\s:]*(\d+)',        # userScore format
        ],
        'lectora': [
            r'quiz_points["\s:]*(\d+)',      # Lectora quiz points
            r'earned_points["\s:]*(\d+)',    # earned_points
            r'total_score["\s:]*(\d+)',      # total_score
        ],
        'generic_scorm': [
            r'"score"["\s:]*(\d+\.?\d*)',    # Generic score field
            r'percentage["\s:]*(\d+)',       # percentage field
            r'result["\s:]*(\d+)',           # result field
        ]
    }
    
    COMPLETION_PATTERNS = {
        'articulate_storyline': [
            r'"qd"["\s]*true',               # Quiz done = true (format 1)
            r'qd"["\s]*true',                # Quiz done = true (format 2) 
            r'"qd"true',                     # Quiz done = true (format 3)
            r'qd"true',                      # Quiz done = true (format 4)
            r'quiz_done["\s:]*true',         # quiz_done: true
            r'assessment_complete["\s:]*true', # assessment_complete: true
            r'lesson_complete["\s:]*true',   # lesson_complete: true
            # STORYLINE FIX: Add more comprehensive completion patterns
            r'qd":true',                     # qd":true format
            r'qd"true',                      # qd"true format
            r'quiz_done":true',              # quiz_done":true format
            r'assessment_done":true',        # assessment_done":true format
            r'lesson_done":true',            # lesson_done":true format
            r'complete":true',               # complete":true format
            r'finished":true',              # finished":true format
        ],
        'adobe_captivate': [
            r'lesson_status["\s:]*"completed"',  # lesson_status: "completed"
            r'completion_status["\s:]*"completed"', # completion_status: "completed"
            r'success_status["\s:]*"passed"',    # success_status: "passed"
        ],
        'lectora': [
            r'course_complete["\s:]*true',   # course_complete: true
            r'lesson_complete["\s:]*true',   # lesson_complete: true
            r'quiz_passed["\s:]*true',       # quiz_passed: true
        ],
        'generic_scorm': [
            r'complete["\s:]*true',          # complete: true
            r'finished["\s:]*true',          # finished: true
            r'passed["\s:]*true',            # passed: true
        ]
    }
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.package = attempt.scorm_package
        self.detected_format = None
        
    def auto_detect_format(self, suspend_data):
        """
        Automatically detect the SCORM authoring tool format based on suspend data patterns
        """
        if not suspend_data:
            return 'generic_scorm'
            
        # Check package filename for clues
        filename = self.package.package_file.name.lower() if self.package.package_file else ''
        
        # Check for Articulate Storyline indicators
        if ('storyline' in filename or 
            'scors' in suspend_data or 
            'qd"true' in suspend_data or
            'ps' in suspend_data[:100]):  # Passing score indicator
            return 'articulate_storyline'
            
        # Check for Adobe Captivate indicators  
        if ('captivate' in filename or
            'cmi.score.raw' in suspend_data or
            'lesson_status' in suspend_data):
            return 'adobe_captivate'
            
        # Check for Lectora indicators
        if ('lectora' in filename or
            'quiz_points' in suspend_data or
            'course_complete' in suspend_data):
            return 'lectora'
            
        # Default to generic SCORM
        return 'generic_scorm'
    
    def extract_score_dynamically(self, suspend_data):
        """
        Dynamically extract score based on detected format
        """
        if not suspend_data:
            return None
            
        try:
            # Decode suspend data if needed
            decoded_data = self._decode_suspend_data(suspend_data)
            if not decoded_data:
                return None
                
            # Auto-detect format
            self.detected_format = self.auto_detect_format(decoded_data)
            logger.info(f"Dynamic Processor: Detected SCORM format '{self.detected_format}' for attempt {self.attempt.id}")
            
            # Check for completion evidence first
            has_completion = self._has_completion_evidence(decoded_data)
            if not has_completion:
                logger.info(f"Dynamic Processor: No completion evidence found for format '{self.detected_format}'")
                return None
            
            # Extract score using format-specific patterns
            score = self._extract_score_by_format(decoded_data, self.detected_format)
            
            if score is not None:
                logger.info(f"Dynamic Processor: Extracted score {score} using '{self.detected_format}' format")
                return score
            
            # CRITICAL FIX: Handle case where quiz is complete but score field is empty
            # This happens when score is 100% in some SCORM packages (especially Articulate Storyline)
            if has_completion and self._is_score_field_empty(decoded_data):
                logger.info(f"Dynamic Processor: Quiz complete with empty score field - assuming 100% score")
                return 100.0
            
            # Fallback: Try all formats if the detected one doesn't work
            for format_name, patterns in self.SCORE_PATTERNS.items():
                if format_name != self.detected_format:
                    score = self._extract_score_by_format(decoded_data, format_name)
                    if score is not None:
                        logger.info(f"Dynamic Processor: Extracted score {score} using fallback format '{format_name}'")
                        return score
            
            return None
            
        except Exception as e:
            logger.error(f"Dynamic Processor: Error extracting score: {str(e)}")
            return None
    
    def _decode_suspend_data(self, suspend_data):
        """Decode compressed suspend_data from various formats"""
        try:
            # Try JSON decode first
            data = json.loads(suspend_data)
            
            # Check if it's Storyline compressed format
            if 'v' in data and 'd' in data:
                chars = data['d']
                decoded = ''
                i = 0
                
                while i < len(chars):
                    if chars[i] > 255:
                        # Reference to previous character
                        decoded += decoded[chars[i] - 256]
                    else:
                        # New character
                        decoded += chr(chars[i])
                    i += 1
                
                return decoded
            
            # Already decoded or different format
            return str(data)
            
        except Exception:
            # Not JSON, might be plain text
            return suspend_data
    
    def _has_completion_evidence(self, decoded_data):
        """Check if there's evidence of actual completion based on detected format"""
        format_patterns = self.COMPLETION_PATTERNS.get(self.detected_format, []).copy()
        
        # Add generic completion patterns
        format_patterns.extend(self.COMPLETION_PATTERNS['generic_scorm'])
        
        # CRITICAL FIX: Add the working patterns for the specific format we're seeing
        if self.detected_format == 'articulate_storyline':
            format_patterns.extend([
                r'qd"["\s]*true',                # The pattern that actually works
                r'qd["\s:]*true',                # Variations
                r'"qd"["\s:]*true',              # More variations
            ])
        
        for pattern in format_patterns:
            try:
                if re.search(pattern, decoded_data, re.IGNORECASE):
                    logger.info(f"Dynamic Processor: Found completion evidence using pattern: {pattern}")
                    return True
            except re.error as e:
                logger.warning(f"Dynamic Processor: Invalid regex pattern '{pattern}': {e}")
                continue
        
        # Additional manual checks for problematic formats
        manual_checks = [
            'qd"true' in decoded_data,
            '"qd"true' in decoded_data,
            'quiz_done' in decoded_data.lower(),
            'assessment_complete' in decoded_data.lower(),
        ]
        
        for i, check in enumerate(manual_checks):
            if check:
                logger.info(f"Dynamic Processor: Found completion evidence via manual check #{i+1}")
                return True
        
        return False
    
    def _get_effective_mastery_score(self):
        """
        Get the effective mastery score with proper hierarchy:
        1. SCORM package mastery score (from manifest)
        2. Course-level passing score (if set)
        3. System default (70%)
        """
        # First priority: SCORM package mastery score
        if self.package.mastery_score is not None:
            return float(self.package.mastery_score)
        
        # Second priority: Course-level passing score
        try:
            from courses.models import CourseTopic
            course_topic = CourseTopic.objects.filter(topic=self.package.topic).first()
            if course_topic and course_topic.course:
                # Check if course has a default passing score
                if hasattr(course_topic.course, 'default_passing_score'):
                    return float(course_topic.course.default_passing_score)
        except Exception as e:
            logger.debug(f"Could not get course passing score: {str(e)}")
        
        # Third priority: System default
        return 70.0
    
    def _is_score_field_empty(self, decoded_data):
        """
        Check if the score field exists but is empty
        This is a specific issue with some SCORM packages when score is 100%
        """
        try:
            # Check for empty score patterns
            empty_patterns = [
                r'scors"[\s]*[,}]',      # scors" followed by comma or closing brace
                r'scor"[\s]*[,}]',       # scor" followed by comma or closing brace
                r'"score"[\s]*:[\s]*""',  # "score": ""
                r'"score"[\s]*:[\s]*[,}]', # "score": followed by comma or closing brace
                r'quiz_score"[\s]*:[\s]*""', # "quiz_score": ""
                r'user_score"[\s]*:[\s]*""', # "user_score": ""
            ]
            
            for pattern in empty_patterns:
                if re.search(pattern, decoded_data, re.IGNORECASE):
                    logger.info(f"Dynamic Processor: Found empty score field with pattern: {pattern}")
                    return True
            
            # Additional check for Storyline specific format
            # Look for 'scor"' at the end of the string or followed by }
            if 'scor"' in decoded_data:
                pos = decoded_data.find('scor"')
                # Check what comes after 'scor"'
                next_chars = decoded_data[pos+5:pos+6] if pos+5 < len(decoded_data) else ''
                if not next_chars or next_chars in ['}', ',', ']', ' ']:
                    logger.info(f"Dynamic Processor: Found empty score field (scor\" with no value)")
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Dynamic Processor: Error checking for empty score field: {str(e)}")
            return False
    
    def _extract_score_by_format(self, decoded_data, format_name):
        """Extract score using format-specific patterns"""
        patterns = self.SCORE_PATTERNS.get(format_name, [])
        
        for pattern in patterns:
            match = re.search(pattern, decoded_data, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    
                    # Validate score range
                    if 0 <= score <= 100:
                        return score
                    elif score <= 10 and format_name == 'articulate_storyline':
                        # Storyline sometimes reports scores out of 10
                        return score * 10
                        
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def process_and_sync_score(self):
        """
        Process the attempt and automatically sync score if completion is detected
        """
        try:
            with transaction.atomic():
                # Check if score is already properly set
                if self.attempt.score_raw and self.attempt.lesson_status in ['completed', 'passed']:
                    logger.info(f"Dynamic Processor: Attempt {self.attempt.id} already has valid score and completion")
                    return True
                
                # Try to extract score from suspend data
                if not self.attempt.suspend_data:
                    logger.info(f"Dynamic Processor: No suspend data for attempt {self.attempt.id}")
                    return False
                
                extracted_score = self.extract_score_dynamically(self.attempt.suspend_data)
                
                if extracted_score is not None:
                    logger.info(f"Dynamic Processor: Processing score {extracted_score} for attempt {self.attempt.id}")
                    
                    # Update ScormAttempt with extracted score
                    old_score = self.attempt.score_raw
                    old_status = self.attempt.lesson_status
                    
                    self.attempt.score_raw = Decimal(str(extracted_score))
                    
                    # Set appropriate lesson status based on score and mastery
                    # Priority: 1. Package mastery score, 2. Course passing score, 3. Default
                    mastery_score = self._get_effective_mastery_score()
                    if extracted_score >= mastery_score:
                        self.attempt.lesson_status = 'passed'
                    else:
                        self.attempt.lesson_status = 'failed'
                    
                    # Set completion timestamp if not already set
                    if not self.attempt.completed_at:
                        self.attempt.completed_at = timezone.now()
                    
                    self.attempt.save()
                    
                    logger.info(f"Dynamic Processor: Updated attempt {self.attempt.id} - score: {old_score} → {extracted_score}, status: {old_status} → {self.attempt.lesson_status}")
                    
                    # Update TopicProgress
                    self._sync_topic_progress(extracted_score)
                    
                    # Clear relevant caches
                    self._clear_caches()
                    
                    return True
                else:
                    logger.info(f"Dynamic Processor: No valid score found for attempt {self.attempt.id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Dynamic Processor: Error processing attempt {self.attempt.id}: {str(e)}")
            return False
    
    def _sync_topic_progress(self, score_value):
        """Sync score to TopicProgress"""
        try:
            from courses.models import TopicProgress
            
            progress, created = TopicProgress.objects.get_or_create(
                user=self.attempt.user,
                topic=self.package.topic
            )
            
            old_last_score = progress.last_score
            old_best_score = progress.best_score
            
            # Update scores
            progress.last_score = float(score_value)
            
            if progress.best_score is None or float(score_value) > progress.best_score:
                progress.best_score = float(score_value)
            
            # Mark as completed
            if not progress.completed:
                progress.completed = True
                progress.completion_method = 'scorm'
                progress.completed_at = timezone.now()
            
            # Update progress data
            progress.progress_data = {
                'scorm_attempt_id': self.attempt.id,
                'lesson_status': self.attempt.lesson_status,
                'score_raw': float(score_value),
                'detected_format': self.detected_format,
                'auto_processed': True,
                'sync_method': 'dynamic_processor',
                'sync_timestamp': timezone.now().isoformat(),
            }
            
            progress.last_accessed = timezone.now()
            progress.save()
            
            logger.info(f"Dynamic Processor: Synced TopicProgress - last_score: {old_last_score} → {progress.last_score}, best_score: {old_best_score} → {progress.best_score}")
            
        except Exception as e:
            logger.error(f"Dynamic Processor: Error syncing TopicProgress: {str(e)}")
    
    def _clear_caches(self):
        """Clear relevant caches for immediate UI updates"""
        cache_keys = [
            f'scorm_attempt_{self.attempt.id}',
            f'topic_progress_{self.attempt.user.id}_{self.package.topic.id}',
            f'gradebook_scores_{self.attempt.user.id}',
            f'course_progress_{self.attempt.user.id}',
        ]
        
        cache.delete_many(cache_keys)
        logger.info(f"Dynamic Processor: Cleared caches for immediate UI update")


def auto_process_scorm_score(attempt):
    """
    Main entry point for dynamic SCORM score processing
    """
    processor = DynamicScormScoreProcessor(attempt)
    return processor.process_and_sync_score()
