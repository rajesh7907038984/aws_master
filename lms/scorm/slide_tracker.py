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
            # If no total but have visited slides, estimate
            result['total_slides'] = len(set(result['visited_slides']))
            result['completed_slides'] = result['visited_slides']
            result['progress_percentage'] = 100.0
        
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
        
        # Check for total slides
        if 'totalSlides' in data:
            result['total_slides'] = int(data['totalSlides'])
        elif 'slideCount' in data:
            result['total_slides'] = int(data['slideCount'])
        
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
                    f"📊 Slide Progress Updated for attempt {attempt.id}:\n"
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

