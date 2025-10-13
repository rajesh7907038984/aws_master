"""
Enhanced Slide and Section Tracking for SCORM
Handles hierarchical structures: Scenes > Slides, Sections > Sub-slides
"""
import logging
import json
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class SlideTracker:
    """
    Tracks slide/section progress for SCORM packages
    Handles both flat and hierarchical structures
    """
    
    @staticmethod
    def extract_slide_info(suspend_data: str, lesson_location: str, cmi_data: Dict) -> Dict[str, Any]:
        """
        Extract slide/section information from SCORM data
        
        Returns:
            dict: {
                'current_slide': str,
                'current_section': str,
                'completed_slides': List[str],
                'total_slides': int,
                'visited_slides': List[str],
                'progress_percentage': float,
                'structure_type': 'flat' | 'hierarchical'
            }
        """
        result = {
            'current_slide': '',
            'current_section': '',
            'completed_slides': [],
            'total_slides': 0,
            'visited_slides': [],
            'progress_percentage': 0.0,
            'structure_type': 'flat'
        }
        
        # Extract from lesson_location (Articulate Storyline format)
        if lesson_location:
            result['current_slide'] = lesson_location
            
            # Parse slide identifier (e.g., "slide cs-6B69syur1W9" or "5VrFzl8pcIo_1_2_3")
            slide_match = re.search(r'slide\s+([a-zA-Z0-9_-]+)', lesson_location)
            if slide_match:
                result['current_slide'] = slide_match.group(1)
            
            # Extract section if present (format: scene_X_slide_Y)
            section_match = re.search(r'scene[_-](\d+)', lesson_location)
            if section_match:
                result['current_section'] = f"scene_{section_match.group(1)}"
                result['structure_type'] = 'hierarchical'
            
            # CRITICAL FIX: Detect button interactions from lesson location changes
            # If lesson location has changed, it indicates user interaction with buttons
            if lesson_location and lesson_location != 'index.html':
                # Extract slide ID from lesson location
                slide_id = lesson_location.split('/')[-1] if '/' in lesson_location else lesson_location
                if slide_id and slide_id not in result['visited_slides']:
                    result['visited_slides'].append(slide_id)
                    logger.info(f"Detected slide interaction: {slide_id}")
                    
                    # CRITICAL FIX: Don't automatically assume completion from slide visits
                    # Slide visits alone don't indicate completion - require actual content interaction
                    if len(result['visited_slides']) > 1:
                        # Much more conservative progress calculation
                        result['progress_percentage'] = min(30.0, len(result['visited_slides']) * 5.0)  # Max 5% per slide, cap at 30%
                        result['total_slides'] = max(result['total_slides'], len(result['visited_slides']))
                        logger.info(f"Conservative progress from slide interactions: {result['progress_percentage']}% (max 30%)")
        
        # CRITICAL FIX: Detect Continue button interactions from CMI data
        if cmi_data:
            # Check for lesson status changes that indicate button interactions
            lesson_status = cmi_data.get('cmi.core.lesson_status', '')
            if lesson_status in ['incomplete', 'browsed']:
                # User has interacted but not completed
                if result['current_slide'] and result['current_slide'] not in result['visited_slides']:
                    result['visited_slides'].append(result['current_slide'])
                    logger.info(f"Detected interaction from lesson status: {lesson_status}")
            
            # Check for score changes that indicate button interactions
            score_raw = cmi_data.get('cmi.core.score.raw', '')
            if score_raw and score_raw != '0':
                # User has interacted and got a score
                if result['current_slide'] and result['current_slide'] not in result['completed_slides']:
                    result['completed_slides'].append(result['current_slide'])
                    logger.info(f"Detected completion from score: {score_raw}")
            
            # NEW: Check for Continue button interactions in CMI data
            for key, value in cmi_data.items():
                if 'continue' in key.lower() and 'button' in key.lower():
                    try:
                        click_count = int(value) if value.isdigit() else 0
                        if click_count > 0:
                            logger.info(f" Found Continue button clicks in CMI: {click_count}")
                            # Mark current slide as completed if Continue button was clicked
                            if result['current_slide'] and result['current_slide'] not in result['completed_slides']:
                                result['completed_slides'].append(result['current_slide'])
                    except (ValueError, TypeError):
                        pass
        
        # Parse suspend_data for slide tracking
        if suspend_data:
            try:
                # Try JSON decode first (some packages use JSON)
                try:
                    suspend_json = json.loads(suspend_data)
                    result.update(SlideTracker._parse_json_suspend_data(suspend_json))
                except (json.JSONDecodeError, ValueError):
                    # Not JSON, parse as string
                    result.update(SlideTracker._parse_string_suspend_data(suspend_data))
            except Exception as e:
                logger.warning(f"Could not parse suspend_data: {e}")
        
        # Extract from CMI data
        if cmi_data:
            # Check for slide visit tracking in CMI data
            for key, value in cmi_data.items():
                if 'slide' in key.lower() and 'visited' in key.lower():
                    try:
                        visited = json.loads(value) if isinstance(value, str) else value
                        if isinstance(visited, list):
                            result['visited_slides'].extend(visited)
                    except:
                        pass
        
        # Calculate progress if we have data
        if result['total_slides'] > 0:
            completed_count = len(set(result['completed_slides']))
            result['progress_percentage'] = (completed_count / result['total_slides']) * 100
        elif result['visited_slides']:
            # CRITICAL FIX: Don't automatically mark visited slides as completed
            # Visited slides are NOT the same as completed slides
            result['total_slides'] = len(set(result['visited_slides']))
            # Don't automatically set completed_slides = visited_slides
            # Only set a small progress percentage for visiting slides
            result['progress_percentage'] = min(20.0, len(result['visited_slides']) * 3.0)  # Max 3% per slide, cap at 20%
        
        # CRITICAL FIX: If no slide data but have time data, use time-based progress
        # Also check if we have minimal slide data (just placeholder) but no real progress
        has_real_slide_data = (result['total_slides'] > 0 and 
                              result['completed_slides'] and 
                              result['progress_percentage'] > 0)
        
        if ((result['total_slides'] == 0 and 
             result['completed_slides'] == [] and 
             result['visited_slides'] == [] and
             result['progress_percentage'] == 0.0) or
            (not has_real_slide_data and result['progress_percentage'] == 0.0)):
            
            # Try to extract time from suspend_data or CMI data
            time_seconds = 0
            if suspend_data:
                try:
                    suspend_json = json.loads(suspend_data)
                    time_seconds = suspend_json.get('totalTime', 0)
                except:
                    pass
            
            # If no time from suspend_data, try to extract from CMI data
            if time_seconds == 0 and cmi_data:
                cmi_total_time = cmi_data.get('cmi.core.total_time', '0000:00:00.00')
                if cmi_total_time and cmi_total_time != '0000:00:00.00':
                    try:
                        # Parse time string (HH:MM:SS format)
                        time_parts = str(cmi_total_time).split(':')
                        if len(time_parts) == 3:
                            hours, minutes, seconds = map(float, time_parts)
                            time_seconds = int(hours * 3600 + minutes * 60 + seconds)
                    except:
                        pass
            
            if time_seconds > 0:
                # CRITICAL FIX: Use much more conservative time-based progress calculation
                # Time alone should NOT determine completion - require actual content interaction
                if time_seconds >= 300:  # 5+ minutes = likely spent time on content
                    result['progress_percentage'] = 25.0  # Still not completed, just time spent
                    result['visited_slides'] = ['slide_1']
                    result['total_slides'] = 1
                elif time_seconds >= 180:  # 3+ minutes = some time spent
                    result['progress_percentage'] = 15.0
                    result['visited_slides'] = ['slide_1']
                    result['total_slides'] = 1
                elif time_seconds >= 120:  # 2+ minutes = minimal time
                    result['progress_percentage'] = 10.0
                    result['visited_slides'] = ['slide_1']
                    result['total_slides'] = 1
                elif time_seconds >= 60:  # 1+ minute = just started
                    result['progress_percentage'] = 5.0
                    result['visited_slides'] = ['slide_1']
                    result['total_slides'] = 1
                else:  # Less than 1 minute = just opened
                    result['progress_percentage'] = 1.0
                    result['visited_slides'] = ['slide_1']
                    result['total_slides'] = 1
                
                logger.info(f"Time-based progress calculation: {time_seconds}s = {result['progress_percentage']}%")
        
        return result
    
    @staticmethod
    def _parse_json_suspend_data(data: Dict) -> Dict[str, Any]:
        """Parse JSON-formatted suspend data"""
        result = {
            'completed_slides': [],
            'visited_slides': [],
            'total_slides': 0
        }
        
        # Common JSON keys for slide tracking
        slide_keys = ['slides', 'visitedSlides', 'completedSlides', 'slideVisits']
        
        for key in slide_keys:
            if key in data:
                value = data[key]
                if isinstance(value, list):
                    if 'completed' in key.lower():
                        result['completed_slides'] = value
                    else:
                        result['visited_slides'] = value
                elif isinstance(value, dict):
                    # Count visited/completed from dictionary
                    visited = [k for k, v in value.items() if v]
                    result['visited_slides'].extend(visited)
        
        # NEW: Check for Continue button interactions in JSON data
        continue_keys = ['continueClicks', 'buttonClicks', 'continueCount', 'slideProgress', 'interactions']
        for key in continue_keys:
            if key in data:
                try:
                    click_count = int(data[key]) if isinstance(data[key], (int, str)) else 0
                    if click_count > 0:
                        logger.info(f" Found Continue button interactions in JSON: {click_count}")
                        # If we have Continue button clicks, mark slides as completed
                        if not result['completed_slides'] and result['visited_slides']:
                            result['completed_slides'] = result['visited_slides'].copy()
                except (ValueError, TypeError):
                    pass
        
        # Check for total slides
        if 'totalSlides' in data:
            result['total_slides'] = int(data['totalSlides'])
        elif 'slideCount' in data:
            result['total_slides'] = int(data['slideCount'])
        
        # CRITICAL FIX: Handle empty slide tracking data
        # If SCORM package is not tracking slides properly, use time-based progress percentage
        if (result['total_slides'] == 0 and 
            result['completed_slides'] == [] and 
            result['visited_slides'] == [] and
            'totalTime' in data and data['totalTime'] > 0):
            
            # Calculate progress percentage based on time spent
            total_time = data['totalTime']
            
            # CRITICAL FIX: Use conservative time-based progress calculation
            # Time alone should NOT determine completion - require actual content interaction
            if total_time >= 300:  # 5+ minutes = likely spent time on content
                result['progress_percentage'] = 25.0  # Still not completed, just time spent
                result['visited_slides'] = ['slide_1']
                result['total_slides'] = 1
            elif total_time >= 180:  # 3+ minutes = some time spent
                result['progress_percentage'] = 15.0
                result['visited_slides'] = ['slide_1']
                result['total_slides'] = 1
            elif total_time >= 120:  # 2+ minutes = minimal time
                result['progress_percentage'] = 10.0
                result['visited_slides'] = ['slide_1']
                result['total_slides'] = 1
            elif total_time >= 60:  # 1+ minute = just started
                result['progress_percentage'] = 5.0
                result['visited_slides'] = ['slide_1']
                result['total_slides'] = 1
            else:  # Less than 1 minute = just opened
                result['progress_percentage'] = 1.0
                result['visited_slides'] = ['slide_1']
                result['total_slides'] = 1
            
            logger.info(f"Time-based progress calculation: {total_time}s = {result['progress_percentage']}%")
        
        return result
    
    @staticmethod
    def _parse_string_suspend_data(data: str) -> Dict[str, Any]:
        """Parse string-formatted suspend data"""
        result = {
            'completed_slides': [],
            'visited_slides': [],
            'total_slides': 0
        }
        
        # Pattern 1: Slide list (comma-separated)
        slide_list_match = re.search(r'slides?[=:]\s*([a-zA-Z0-9,_-]+)', data, re.IGNORECASE)
        if slide_list_match:
            slides = slide_list_match.group(1).split(',')
            result['visited_slides'] = [s.strip() for s in slides if s.strip()]
        
        # Pattern 2: Visited count
        visited_match = re.search(r'visited[=:]\s*(\d+)', data, re.IGNORECASE)
        if visited_match:
            visited_count = int(visited_match.group(1))
            # Generate slide IDs if we have count but no list
            if not result['visited_slides']:
                result['visited_slides'] = [f'slide_{i}' for i in range(1, visited_count + 1)]
        
        # Pattern 3: Total slides
        total_match = re.search(r'total[Ss]lides?[=:]\s*(\d+)', data, re.IGNORECASE)
        if total_match:
            result['total_slides'] = int(total_match.group(1))
        
        # Pattern 4: Completed bitmap or list
        completed_match = re.search(r'completed[=:]\s*([01,]+)', data, re.IGNORECASE)
        if completed_match:
            completed_str = completed_match.group(1)
            if ',' in completed_str:
                # List of slide IDs
                result['completed_slides'] = [s.strip() for s in completed_str.split(',') if s.strip()]
            else:
                # Bitmap (0/1 for each slide)
                result['completed_slides'] = [
                    f'slide_{i+1}' for i, bit in enumerate(completed_str) if bit == '1'
                ]
        
        # NEW: Pattern 5: Continue button interactions
        continue_patterns = [
            r'continue[_-]?button[_-]?clicked[=:]\s*(\d+)',
            r'continue[_-]?clicks[=:]\s*(\d+)',
            r'button[_-]?interactions[=:]\s*(\d+)',
            r'slide[_-]?progress[=:]\s*(\d+)',
            r'continue[_-]?count[=:]\s*(\d+)'
        ]
        
        for pattern in continue_patterns:
            match = re.search(pattern, data, re.IGNORECASE)
            if match:
                click_count = int(match.group(1))
                if click_count > 0:
                    logger.info(f" Found Continue button interactions in string: {click_count}")
                    # If we have Continue button clicks, mark slides as completed
                    if not result['completed_slides'] and result['visited_slides']:
                        result['completed_slides'] = result['visited_slides'].copy()
                    break
        
        return result
    
    @staticmethod
    def update_slide_progress(attempt: 'ScormAttempt') -> bool:
        """
        Update slide progress tracking for an attempt
        
        Returns:
            bool: True if progress was updated
        """
        try:
            slide_info = SlideTracker.extract_slide_info(
                attempt.suspend_data,
                attempt.lesson_location,
                attempt.cmi_data
            )
            
            # Update attempt fields
            updated = False
            
            if slide_info['total_slides'] > 0 and attempt.total_slides != slide_info['total_slides']:
                attempt.total_slides = slide_info['total_slides']
                updated = True
            
            if slide_info['completed_slides'] and attempt.completed_slides != slide_info['completed_slides']:
                attempt.completed_slides = slide_info['completed_slides']
                updated = True
            
            if slide_info['progress_percentage'] > 0 and attempt.progress_percentage != slide_info['progress_percentage']:
                attempt.progress_percentage = slide_info['progress_percentage']
                updated = True
            
            if slide_info['current_slide'] and attempt.last_visited_slide != slide_info['current_slide']:
                attempt.last_visited_slide = slide_info['current_slide']
                updated = True
            
            # Store structure type in detailed_tracking
            if not attempt.detailed_tracking:
                attempt.detailed_tracking = {}
            attempt.detailed_tracking['structure_type'] = slide_info['structure_type']
            attempt.detailed_tracking['current_section'] = slide_info['current_section']
            updated = True
            
            if updated:
                logger.info(
                    f" Slide Progress Updated for attempt {attempt.id}:\n"
                    f"   Current: {slide_info['current_slide']}\n"
                    f"   Section: {slide_info['current_section']}\n"
                    f"   Progress: {slide_info['progress_percentage']:.1f}%\n"
                    f"   Completed: {len(slide_info['completed_slides'])}/{slide_info['total_slides']}\n"
                    f"   Type: {slide_info['structure_type']}"
                )
                attempt.save()
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating slide progress for attempt {attempt.id}: {e}")
            return False
    
    @staticmethod
    def get_section_progress(attempt: 'ScormAttempt') -> List[Dict[str, Any]]:
        """
        Get section-by-section progress for hierarchical packages
        
        Returns:
            List of sections with progress info
        """
        sections = []
        
        if not attempt.detailed_tracking or attempt.detailed_tracking.get('structure_type') != 'hierarchical':
            return sections
        
        # Parse completed slides by section
        section_slides = {}
        for slide in attempt.completed_slides:
            section_match = re.search(r'scene[_-](\d+)', str(slide))
            if section_match:
                section = f"scene_{section_match.group(1)}"
                if section not in section_slides:
                    section_slides[section] = []
                section_slides[section].append(slide)
        
        # Build section progress list
        for section, slides in section_slides.items():
            sections.append({
                'section': section,
                'completed_slides': len(slides),
                'slides': slides
            })
        
        return sections

