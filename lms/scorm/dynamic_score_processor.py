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
    # COMPREHENSIVE FIX: More precise regex patterns to avoid matching configuration values
    # Common configuration values to avoid: 70, 80, 100 (passing thresholds)
    # These patterns are more precise to match only actual earned scores, not configuration
    SCORE_PATTERNS = {
        'articulate_storyline': [
            # Articulate Storyline - more precise patterns
            r'scors"?:?"?(\d+)',                       # Storyline: scors:88 (stored score)
            r'scor"?:?"?(\d+)',                        # Storyline: scor:88 (earned score)
            r'quiz_score"?:?"?(\d+)',                  # quiz_score:88
            r'score_earned"?:?"?(\d+)',                # score_earned:88 (preferred)
            r'user_score"?:?"?(\d+)',                  # user_score:88
            r'earned_score"?:?"?(\d+)',                # earned_score:88
            
            # Avoid configuration patterns by using context
            r'final_score"?:?"?(\d+)[^"]*?"qd"?:?"?true', # final_score near quiz_done flag
        ],
        'adobe_captivate': [
            # Adobe Captivate - only match raw score with context
            r'"score"\s*:\s*(\d+\.?\d*)',              # Captivate JSON format
            r'cmi\.score\.raw"?:?"?(\d+\.?\d*)',       # Direct CMI score
            r'userScore"?:?"?(\d+\.?\d*)',             # userScore format
            r'correct_questions"?:?"?(\d+)\D+total_questions"?:?"?(\d+)', # Calculate from correct/total
        ],
        'lectora': [
            # Lectora - more specific patterns with context
            r'quiz_points"?:?"?(\d+)[^"]*?total_points"?:?"?\d+', # quiz_points with total context
            r'earned_points"?:?"?(\d+)[^"]*?total_points"?:?"?\d+', # earned with total context
            r'points_earned"?:?"?(\d+)',               # points_earned
            r'score_obtained"?:?"?(\d+)',              # score_obtained
        ],
        'rise360': [
            # Rise 360 specific patterns
            r'score:\s*(\d+\.?\d*)',                   # score: 88
            r'"quizResult":\s*(\d+\.?\d*)',            # "quizResult": 88
            r'"assessmentScore":\s*(\d+\.?\d*)',       # "assessmentScore": 88
            r'"percentageScore":\s*(\d+\.?\d*)',       # "percentageScore": 88
        ],
        'generic_scorm': [
            # Generic SCORM - more selective patterns with context
            r'"score"["\s:]*(\d+\.?\d*)[^"]*?"passed"["\s:]*true', # score with passed context
            r'"percentage"["\s:]*(\d+)[^"]*?"completed"["\s:]*true', # percentage with completed context
            r'"result"["\s:]*(\d+)[^"]*?"finished"["\s:]*true',   # result with finished context
            r'user_score["\s:]*(\d+)',                 # clear user_score field
            r'earned["\s:]*(\d+)',                     # clear earned field
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
        ENHANCED FORMAT DETECTION: More precise SCORM authoring tool detection 
        using filename and content patterns, with confidence scoring
        """
        if not suspend_data:
            return 'generic_scorm'
        
        # Set up confidence scoring system
        format_confidence = {
            'articulate_storyline': 0,
            'adobe_captivate': 0,
            'lectora': 0,
            'rise360': 0,
            'generic_scorm': 0
        }
            
        # Check package filename for clues
        filename = self.package.package_file.name.lower() if self.package.package_file else ''
        
        # Filename-based detection (strongest evidence)
        if 'storyline' in filename:
            format_confidence['articulate_storyline'] += 100
        elif 'captivate' in filename:
            format_confidence['adobe_captivate'] += 100
        elif 'lectora' in filename:
            format_confidence['lectora'] += 100
        elif 'rise' in filename or 'articulate' in filename:
            format_confidence['rise360'] += 50
        
        # Check for Articulate Storyline indicators
        if 'scors' in suspend_data:
            format_confidence['articulate_storyline'] += 80
        if 'scor' in suspend_data:
            format_confidence['articulate_storyline'] += 60
        if 'qd"true' in suspend_data or '"qd"true' in suspend_data:
            format_confidence['articulate_storyline'] += 90
        if 'ps' in suspend_data[:100]:  # Passing score indicator
            format_confidence['articulate_storyline'] += 40
        if 'storyline' in suspend_data.lower():
            format_confidence['articulate_storyline'] += 100
            
        # Check for Rise 360 specific indicators
        if 'rise-' in suspend_data.lower():
            format_confidence['rise360'] += 90
        if 'quizResult' in suspend_data:
            format_confidence['rise360'] += 80
        if 'assessmentScore' in suspend_data:
            format_confidence['rise360'] += 80
        if 'rise' in suspend_data.lower():
            format_confidence['rise360'] += 70
            
        # Check for Adobe Captivate indicators
        if 'cmi.score.raw' in suspend_data:
            format_confidence['adobe_captivate'] += 60
        if 'lesson_status' in suspend_data:
            format_confidence['adobe_captivate'] += 40
        if 'captivate' in suspend_data.lower():
            format_confidence['adobe_captivate'] += 90
        if 'userScore' in suspend_data:
            format_confidence['adobe_captivate'] += 70
        if 'slideCount' in suspend_data:
            format_confidence['adobe_captivate'] += 60
            
        # Check for Lectora indicators
        if 'quiz_points' in suspend_data:
            format_confidence['lectora'] += 80
        if 'course_complete' in suspend_data:
            format_confidence['lectora'] += 60
        if 'earned_points' in suspend_data:
            format_confidence['lectora'] += 70
        if 'lectora' in suspend_data.lower():
            format_confidence['lectora'] += 90
        
        # Determine the most likely format
        max_confidence = 0
        detected_format = 'generic_scorm'
        
        for format_name, confidence in format_confidence.items():
            if confidence > max_confidence:
                max_confidence = confidence
                detected_format = format_name
        
        # If confidence is very low, fall back to generic
        if max_confidence < 30:
            detected_format = 'generic_scorm'
            
        logger.info(f"Format detection: {detected_format} (confidence: {max_confidence})")
        logger.debug(f"Confidence scores: {format_confidence}")
            
        return detected_format
    
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
            
            # COMPREHENSIVE FIX: Handle case where quiz is complete but score field is empty
            # This happens when score is 100% in many SCORM packages (especially Articulate Storyline and Rise 360)
            if has_completion:
                # Check for empty score fields
                if self._is_score_field_empty(decoded_data):
                    logger.info(f"Dynamic Processor: Quiz complete with empty score field - assuming 100% score")
                    
                    # Check if there's a mastery score in the package
                    mastery_score = None
                    if self.attempt.mastery_score is not None:
                        try:
                            mastery_score = float(self.attempt.mastery_score)
                        except (ValueError, TypeError):
                            pass
                    
                    # If there's a mastery score, use it as the minimum passing score
                    # Otherwise, assume 100% for completed content with empty score
                    if mastery_score is not None:
                        logger.info(f"Dynamic Processor: Using mastery score {mastery_score} as minimum passing score")
                        return max(mastery_score, 100.0)  # Use at least the mastery score
                    else:
                        return 100.0  # Default to 100% for completed content
            
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
        """
        ENHANCED COMPLETION DETECTION: More comprehensive and reliable checks
        for evidence of course completion in suspend_data
        """
        format_patterns = self.COMPLETION_PATTERNS.get(self.detected_format, []).copy()
        
        # Add generic completion patterns for all formats
        format_patterns.extend(self.COMPLETION_PATTERNS['generic_scorm'])
        
        # FIXED: Safer regex patterns with proper escaping and simpler patterns
        # to avoid potential false negatives from invalid regex
        cross_format_patterns = [
            # Common completion indicators across formats - simplified patterns
            r'completion["\'\\s:=]+true',
            r'completed["\'\\s:=]+true',
            r'success["\'\\s:=]+true',
            r'passed["\'\\s:=]+true',
            r'finished["\'\\s:=]+true',
            r'done["\'\\s:=]+true',
            r'lesson_status["\'\\s:=]+completed',
            r'lesson_status["\'\\s:=]+passed',
            r'status["\'\\s:=]+completed',
            r'status["\'\\s:=]+passed',
            
            # Status field patterns - simplified
            r'"status"\s*:\s*"completed"',
            r'"status"\s*:\s*"passed"',
            r'"status"\s*:\s*"success"',
            
            # Completion indicators - simplified
            r'isComplete["\'\\s:=]+true',
            r'is_complete["\'\\s:=]+true',
            r'completion_status["\'\\s:=]+completed',
            r'completion_status["\'\\s:=]+passed',
            
            # Progress indicators - simplified
            r'progress["\'\\s:=]+100',
            r'progress_measure["\'\\s:=]+1',
            r'percentComplete["\'\\s:=]+100',
            
            # Numeric indicators
            r'"complete"\s*:\s*1',
            r'"completed"\s*:\s*1',
            r'"finished"\s*:\s*1',
        ]
        format_patterns.extend(cross_format_patterns)
        
        # FIXED: Format-specific patterns with safer regex
        if self.detected_format == 'articulate_storyline':
            format_patterns.extend([
                # Storyline specific completion indicators - simplified
                r'qd["\'\\s:=]*true',               # Quiz done = true (basic)
                r'"qd"["\'\\s:=]*true',             # Quiz done with quotes
                r'quiz_done["\'\\s:=]*true',        # Explicit quiz_done
                r'quiz_passed["\'\\s:=]*true',      # Quiz passed
                r'quiz_complete["\'\\s:=]*true',    # Quiz complete
            ])
        elif self.detected_format == 'rise360':
            format_patterns.extend([
                # Rise 360 specific patterns - simplified
                r'courseComplete["\'\\s:=]*true',
                r'module_complete["\'\\s:=]*true',
                r'"complete"\s*:\s*true',
                r'course_complete["\'\\s:=]*true',
                r'lesson_complete["\'\\s:=]*true',
            ])
        elif self.detected_format == 'adobe_captivate':
            # Captivate patterns - split into simpler patterns
            format_patterns.extend([
                r'quiz_complete["\'\\s:=]*true',
                r'slide_view_completion["\'\\s:=]*true',
                r'module_completion["\'\\s:=]*true',
                r'"completionStatus"\s*:\s*"completed"',
            ])
            
            # Add simpler manual check for slide completion
            try:
                # Extract slideCount and currentSlide values
                slide_count_match = re.search(r'slideCount["\'\\s:=]*(\d+)', decoded_data)
                current_slide_match = re.search(r'currentSlide["\'\\s:=]*(\d+)', decoded_data)
                
                if slide_count_match and current_slide_match:
                    slide_count = int(slide_count_match.group(1))
                    current_slide = int(current_slide_match.group(1))
                    
                    # If current slide equals total slides, it's completed
                    if slide_count > 0 and current_slide >= slide_count:
                        logger.info(f"Dynamic Processor: Found completion evidence via slide count check: {current_slide}/{slide_count}")
                        return True
            except Exception as e:
                logger.debug(f"Error in slide count check: {e}")
        elif self.detected_format == 'lectora':
            format_patterns.extend([
                # Lectora specific patterns
                r'course_complete["\'\\s:=]*true',
                r'course_completed["\'\\s:=]*true',
                r'module_complete["\'\\s:=]*true',
                r'page_viewed_all["\'\\s:=]*true',
            ])
        
        # Try each pattern
        for pattern in format_patterns:
            try:
                if re.search(pattern, decoded_data, re.IGNORECASE):
                    logger.info(f"Dynamic Processor: Found completion evidence using pattern: {pattern}")
                    return True
            except re.error as e:
                logger.warning(f"Dynamic Processor: Invalid regex pattern '{pattern}': {e}")
                continue
        
        # COMPREHENSIVE MANUAL CHECKS: More reliable and thorough
        # These are direct string checks that don't use regex for maximum reliability
        manual_checks = [
            # Articulate Storyline/Rise specific
            'qd"true' in decoded_data,
            '"qd"true' in decoded_data,
            '"qd":true' in decoded_data,
            'quiz_done' in decoded_data.lower(),
            'assessment_complete' in decoded_data.lower(),
            
            # Common completion indicators
            '"completed":true' in decoded_data.lower(),
            '"complete":true' in decoded_data.lower(),
            '"finished":true' in decoded_data.lower(),
            '"passed":true' in decoded_data.lower(),
            '"success":true' in decoded_data.lower(),
            
            # Status indicators
            '"status":"completed"' in decoded_data.lower(),
            '"status":"passed"' in decoded_data.lower(),
            '"lesson_status":"completed"' in decoded_data.lower(),
            '"lesson_status":"passed"' in decoded_data.lower(),
            
            # Progress indicators
            '"progress":100' in decoded_data,
            '"progress":"100"' in decoded_data,
            '"progress_measure":1' in decoded_data,
            '"progress_measure":"1"' in decoded_data,
        ]
        
        for i, check in enumerate(manual_checks):
            if check:
                logger.info(f"Dynamic Processor: Found completion evidence via manual check #{i+1}")
                return True
        
        # Final check: Look for high progress percentage
        try:
            # Check for progress indicators without regex
            if '"progress":' in decoded_data or '"progress_measure":' in decoded_data:
                progress_match = re.search(r'"progress":\s*(\d+)', decoded_data)
                if progress_match:
                    progress = int(progress_match.group(1))
                    if progress >= 95:  # Very high progress is effectively completion
                        logger.info(f"Dynamic Processor: Found high progress indicator: {progress}%")
                        return True
                        
                progress_measure_match = re.search(r'"progress_measure":\s*(0\.\d+)', decoded_data)
                if progress_measure_match:
                    progress = float(progress_measure_match.group(1))
                    if progress >= 0.95:  # Very high progress measure is effectively completion
                        logger.info(f"Dynamic Processor: Found high progress_measure: {progress}")
                        return True
        except Exception as e:
            logger.debug(f"Error in progress check: {e}")
        
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
        COMPREHENSIVE FIX: Improved detection for empty score fields
        This handles cases where quiz is complete but score field is empty or missing
        which happens in many SCORM packages (especially Articulate Storyline and Rise 360)
        """
        try:
            # First check if there are completion indicators but no score indicators
            has_completion_indicators = False
            has_score_indicators = False
            
            # Check for completion indicators
            completion_indicators = [
                'qd"true', '"qd"true', '"qd":true',
                'quiz_done', 'assessment_complete',
                '"completed":true', '"complete":true',
                '"finished":true', '"passed":true',
                '"success":true', '"status":"completed"',
                '"status":"passed"', '"lesson_status":"completed"',
                '"lesson_status":"passed"'
            ]
            
            for indicator in completion_indicators:
                if indicator.lower() in decoded_data.lower():
                    has_completion_indicators = True
                    logger.info(f"Found completion indicator: {indicator}")
                    break
            
            # Check for score indicators with values
            score_indicators = [
                'score":', 'score=', 'scor":', 'scors":',
                'quiz_score":', 'user_score":', 'raw_score":',
                '"cmi.score.raw":', '"cmi.core.score.raw":'
            ]
            
            for indicator in score_indicators:
                pattern = f"{re.escape(indicator)}\\s*[\"']?\\d+[\\.\\d]*[\"']?"
                if re.search(pattern, decoded_data, re.IGNORECASE):
                    has_score_indicators = True
                    logger.info(f"Found score indicator with value: {indicator}")
                    break
            
            # If we have completion indicators but no score indicators with values,
            # check for empty score fields
            if has_completion_indicators and not has_score_indicators:
                # Check for empty score patterns
                empty_patterns = [
                    # Articulate Storyline patterns
                    r'scors"[\s]*[,}]',                # scors" followed by comma or closing brace
                    r'scor"[\s]*[,}]',                 # scor" followed by comma or closing brace
                    r'scor"[\s]*:[\s]*["\s]*[,}]',     # scor": followed by comma or closing brace
                    r'scors"[\s]*:[\s]*["\s]*[,}]',    # scors": followed by comma or closing brace
                    
                    # Generic patterns
                    r'"score"[\s]*:[\s]*""',           # "score": ""
                    r'"score"[\s]*:[\s]*null',         # "score": null
                    r'"score"[\s]*:[\s]*[,}]',         # "score": followed by comma or closing brace
                    r'quiz_score"[\s]*:[\s]*[""]?[,}]',  # "quiz_score": "" or followed by comma/brace
                    r'user_score"[\s]*:[\s]*[""]?[,}]',  # "user_score": "" or followed by comma/brace
                    
                    # SCORM specific patterns
                    r'"cmi\.score\.raw"[\s]*:[\s]*[""]?[,}]',  # "cmi.score.raw": followed by comma/brace
                    r'"cmi\.core\.score\.raw"[\s]*:[\s]*[""]?[,}]',  # "cmi.core.score.raw": followed by comma/brace
                ]
                
                for pattern in empty_patterns:
                    try:
                        if re.search(pattern, decoded_data, re.IGNORECASE):
                            logger.info(f"Dynamic Processor: Found empty score field with pattern: {pattern}")
                            return True
                    except re.error:
                        # Skip invalid regex patterns
                        continue
                
                # If we have completion indicators but couldn't find explicit empty score fields,
                # it's still likely that the score should be 100%
                logger.info("Dynamic Processor: Found completion indicators without score - likely 100%")
                return True
            
            # Additional check for Storyline specific format
            # Look for 'scor"' at the end of the string or followed by }
            if 'scor"' in decoded_data:
                pos = decoded_data.find('scor"')
                # Check what comes after 'scor"'
                next_chars = decoded_data[pos+5:pos+15] if pos+5 < len(decoded_data) else ''
                if not next_chars or next_chars[0] in ['}', ',', ']', ' ']:
                    logger.info(f"Dynamic Processor: Found empty score field (scor\" with no value)")
                    return True
            
            # Check if suspend_data contains quiz completion indicators but no score
            quiz_completion_indicators = [
                'quiz_complete', 'assessment_complete', 'quiz_passed',
                'quiz_finished', 'quiz_done', 'quiz_status":"completed"'
            ]
            
            for indicator in quiz_completion_indicators:
                if indicator.lower() in decoded_data.lower():
                    # If we found a quiz completion indicator but no score indicators,
                    # it's likely that the score should be 100%
                    if not has_score_indicators:
                        logger.info(f"Dynamic Processor: Found quiz completion indicator {indicator} without score - likely 100%")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Dynamic Processor: Error checking for empty score field: {str(e)}")
            return False
    
    def _extract_score_by_format(self, decoded_data, format_name):
        """Extract score using format-specific patterns - with robust validation"""
        patterns = self.SCORE_PATTERNS.get(format_name, [])
        
        # Get actual passing threshold from multiple sources
        config_values = []
        
        # 1. Try to extract passing threshold from suspend_data first
        # This is most accurate as it's what the SCORM package itself uses
        try:
            # Common patterns for passing thresholds in suspend data
            threshold_patterns = [
                r'passing_?score"?:?"?(\d+)',          # passing_score:80
                r'mastery_?score"?:?"?(\d+)',          # mastery_score:80
                r'min_?score"?:?"?(\d+)',              # min_score:80
                r'passing_?threshold"?:?"?(\d+)',      # passing_threshold:80
                r'ps"?:?"?(\d+)',                      # ps:80 (Storyline)
                r'"pass_score"?:?"?(\d+)',             # "pass_score":80
                r'"threshold"?:?"?(\d+)',              # "threshold":80
            ]
            
            for pattern in threshold_patterns:
                match = re.search(pattern, decoded_data, re.IGNORECASE)
                if match:
                    try:
                        threshold = float(match.group(1))
                        if 0 <= threshold <= 100:
                            config_values.append(threshold)
                            logger.info(f"Extracted passing threshold from suspend_data: {threshold}")
                            break
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            logger.warning(f"Error extracting threshold from suspend_data: {e}")
        
        # 2. Get the mastery score from the package if available
        if not config_values and self.package.mastery_score is not None:
            try:
                mastery_score = float(self.package.mastery_score)
                if 0 <= mastery_score <= 100:
                    config_values.append(mastery_score)
                    logger.info(f"Using package mastery score: {mastery_score}")
            except (ValueError, TypeError):
                pass
                
        # 3. Add common passing thresholds as fallback only if we couldn't get specific values
        if not config_values:
            config_values = [70, 75, 80, 85, 90, 100]
            logger.info("Using default passing thresholds as no package value available")
        
        # Track potential scores with evidence strength
        potential_scores = []
        
        for pattern in patterns:
            match = re.search(pattern, decoded_data, re.IGNORECASE)
            if match:
                try:
                    # Special case: Captivate correct/total questions pattern
                    if 'correct_questions' in pattern and match.lastindex >= 2:
                        correct = float(match.group(1))
                        total = float(match.group(2))
                        if total > 0:
                            score = (correct / total) * 100
                            potential_scores.append((score, 'high', 'correct/total ratio'))
                            continue
                            
                    # Standard score extraction
                    score = float(match.group(1))
                    
                    # Skip if we just have a suspicious config value without context
                    if score in config_values and '[^"]' not in pattern:
                        evidence = 'low'  # Simple pattern without context near a config value is suspicious
                    elif 'true' in pattern or 'completed' in pattern or 'passed' in pattern:
                        evidence = 'high'  # Pattern has completion context
                    else:
                        evidence = 'medium'  # Standard pattern
                        
                    # Validate score range
                    if 0 <= score <= 100:
                        potential_scores.append((score, evidence, pattern))
                    elif score <= 10 and format_name in ['articulate_storyline', 'rise360']:
                        # Some packages report scores out of 10
                        adjusted_score = score * 10
                        potential_scores.append((adjusted_score, evidence, f"{pattern} (adjusted *10)"))
                        
                except (ValueError, IndexError):
                    continue
        
        # Find the best score based on evidence
        if potential_scores:
            # Sort by evidence strength (high > medium > low)
            sorted_scores = sorted(potential_scores, 
                                  key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x[1]])
            
            best_score = sorted_scores[0]
            logger.info(f"Selected score {best_score[0]} (evidence: {best_score[1]}) from pattern: {best_score[2]}")
            return best_score[0]
            
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
