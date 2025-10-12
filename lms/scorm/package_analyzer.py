"""
Dynamic SCORM Package Analyzer
Automatically detects package characteristics without hardcoding
Analyzes: scoring methods, completion methods, package types
"""
import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ScormPackageAnalyzer:
    """
    Dynamically analyzes SCORM packages to determine their characteristics
    """
    
    @staticmethod
    def analyze_package(manifest_data: Dict[str, Any], manifest_content: str = None) -> Dict[str, Any]:
        """
        Analyze a SCORM package and return its characteristics
        
        Args:
            manifest_data: Parsed manifest data dictionary
            manifest_content: Raw manifest XML content (optional)
            
        Returns:
            dict: Package metadata including:
                - scoring_method: 'quiz', 'slide_completion', 'time_based', 'mixed', 'unknown'
                - completion_method: 'score_based', 'slide_based', 'viewed', 'passed'
                - package_type: 'articulate_storyline', 'captivate', 'lectora', 'generic'
                - has_quiz: bool
                - has_slides: bool
                - max_score_display: int (always 100 for proper display)
        """
        metadata = {
            'scoring_method': 'unknown',
            'completion_method': 'unknown',
            'package_type': 'generic',
            'has_quiz': False,
            'has_slides': False,
            'max_score_display': 100,  # ALWAYS 100 for SCORM (score_raw is 0-100 percentage)
            'detected_at': None,
            'detection_confidence': 'low'
        }
        
        # Detect package type from manifest content
        metadata['package_type'] = ScormPackageAnalyzer._detect_package_type(
            manifest_data, manifest_content
        )
        
        # Detect if package has quiz/assessment
        metadata['has_quiz'] = ScormPackageAnalyzer._detect_quiz_presence(
            manifest_data, manifest_content
        )
        
        # Detect if package is slide-based
        metadata['has_slides'] = ScormPackageAnalyzer._detect_slide_based(
            manifest_data, manifest_content
        )
        
        # Determine scoring method based on detected characteristics
        metadata['scoring_method'] = ScormPackageAnalyzer._determine_scoring_method(metadata)
        
        # Determine completion method
        metadata['completion_method'] = ScormPackageAnalyzer._determine_completion_method(metadata)
        
        # Set detection confidence
        metadata['detection_confidence'] = ScormPackageAnalyzer._calculate_confidence(metadata)
        
        from django.utils import timezone
        metadata['detected_at'] = timezone.now().isoformat()
        
        logger.info(
            f"📊 Package Analysis Complete:\n"
            f"  Type: {metadata['package_type']}\n"
            f"  Scoring: {metadata['scoring_method']}\n"
            f"  Completion: {metadata['completion_method']}\n"
            f"  Has Quiz: {metadata['has_quiz']}\n"
            f"  Has Slides: {metadata['has_slides']}\n"
            f"  Confidence: {metadata['detection_confidence']}"
        )
        
        return metadata
    
    @staticmethod
    def _detect_package_type(manifest_data: Dict, manifest_content: str = None) -> str:
        """Detect the authoring tool/package type"""
        
        # Check for Articulate Storyline indicators
        if manifest_content:
            storyline_indicators = [
                'articulate', 'storyline', 'story.html', 'story_html5.html',
                'story_content', 'storyline 360', 'articulate 360'
            ]
            content_lower = manifest_content.lower()
            if any(indicator in content_lower for indicator in storyline_indicators):
                logger.info("✅ Detected: Articulate Storyline")
                return 'articulate_storyline'
            
            # Check for Adobe Captivate
            captivate_indicators = ['captivate', 'adobe captivate', 'cp_infobox']
            if any(indicator in content_lower for indicator in captivate_indicators):
                logger.info("✅ Detected: Adobe Captivate")
                return 'adobe_captivate'
            
            # Check for Lectora
            lectora_indicators = ['lectora', 'trivantis']
            if any(indicator in content_lower for indicator in lectora_indicators):
                logger.info("✅ Detected: Lectora")
                return 'lectora'
        
        # Check manifest data
        identifier = manifest_data.get('identifier', '').lower()
        if 'articulate' in identifier or 'story' in identifier:
            return 'articulate_storyline'
        
        return 'generic'
    
    @staticmethod
    def _detect_quiz_presence(manifest_data: Dict, manifest_content: str = None) -> bool:
        """Detect if package contains quiz/assessment"""
        
        if manifest_content:
            quiz_indicators = [
                'quiz', 'assessment', 'test', 'question', 'interaction',
                'cmi.interactions', 'score.raw', 'correct_response',
                'student_response', 'result_slide'
            ]
            content_lower = manifest_content.lower()
            quiz_count = sum(1 for indicator in quiz_indicators if indicator in content_lower)
            
            # If multiple quiz indicators found, likely has quiz
            if quiz_count >= 3:
                logger.info(f"✅ Quiz detected (indicators: {quiz_count})")
                return True
        
        return False
    
    @staticmethod
    def _detect_slide_based(manifest_data: Dict, manifest_content: str = None) -> bool:
        """Detect if package is slide-based (presentation style)"""
        
        if manifest_content:
            slide_indicators = [
                'slide', 'scene', 'navigation', 'menu', 'toc',
                'table of contents', 'sidebar', 'player'
            ]
            content_lower = manifest_content.lower()
            slide_count = sum(1 for indicator in slide_indicators if indicator in content_lower)
            
            # If multiple slide indicators found, likely slide-based
            if slide_count >= 2:
                logger.info(f"✅ Slide-based detected (indicators: {slide_count})")
                return True
        
        return False
    
    @staticmethod
    def _determine_scoring_method(metadata: Dict) -> str:
        """Determine how the package scores learners"""
        
        has_quiz = metadata.get('has_quiz', False)
        has_slides = metadata.get('has_slides', False)
        package_type = metadata.get('package_type', 'generic')
        
        # Articulate Storyline with quiz
        if package_type == 'articulate_storyline' and has_quiz:
            return 'quiz'  # Score comes from quiz results
        
        # Articulate Storyline without quiz (slide-based)
        elif package_type == 'articulate_storyline' and has_slides:
            return 'slide_completion'  # Score = % of slides viewed
        
        # Other quiz-based packages
        elif has_quiz and not has_slides:
            return 'quiz'
        
        # Slide-based without quiz
        elif has_slides and not has_quiz:
            return 'slide_completion'
        
        # Mixed (has both)
        elif has_quiz and has_slides:
            return 'mixed'  # Depends on package configuration
        
        return 'unknown'
    
    @staticmethod
    def _determine_completion_method(metadata: Dict) -> str:
        """Determine how completion is tracked"""
        
        scoring_method = metadata.get('scoring_method', 'unknown')
        
        # Quiz-based: completion = passing score
        if scoring_method == 'quiz':
            return 'score_based'
        
        # Slide-based: completion = viewing all slides
        elif scoring_method == 'slide_completion':
            return 'slide_based'
        
        # Mixed: depends on manifest settings
        elif scoring_method == 'mixed':
            return 'viewed'  # Default to "viewed all content"
        
        return 'viewed'  # Default: just view the content
    
    @staticmethod
    def _calculate_confidence(metadata: Dict) -> str:
        """Calculate confidence level of detection"""
        
        # High confidence: package type detected + clear scoring/completion method
        if (metadata['package_type'] != 'generic' and 
            metadata['scoring_method'] != 'unknown' and
            metadata['completion_method'] != 'unknown'):
            return 'high'
        
        # Medium confidence: some indicators found
        elif (metadata['has_quiz'] or metadata['has_slides']):
            return 'medium'
        
        # Low confidence: minimal information
        return 'low'
    
    @staticmethod
    def get_display_config(package_metadata: Dict) -> Dict[str, Any]:
        """
        Get display configuration for gradebook based on package metadata
        
        Returns:
            dict: Display configuration with max_score, format, etc.
        """
        return {
            'max_score': 100,  # ALWAYS 100 for SCORM (score_raw is 0-100 percentage)
            'score_format': 'percentage',  # Display as X/100
            'completion_label': ScormPackageAnalyzer._get_completion_label(package_metadata),
            'show_progress': package_metadata.get('has_slides', False),
        }
    
    @staticmethod
    def _get_completion_label(metadata: Dict) -> str:
        """Get appropriate completion label based on package type"""
        
        completion_method = metadata.get('completion_method', 'viewed')
        
        if completion_method == 'score_based':
            return 'Passed'
        elif completion_method == 'slide_based':
            return 'Completed'
        else:
            return 'Viewed'

