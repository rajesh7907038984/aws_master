"""
Unified Scoring Service for LMS
Provides consistent score calculations across all modules
"""

import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Tuple, Dict, Any
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class ScoreCalculationService:
    """Centralized service for all score calculations in the LMS"""
    
    # Field limits based on database schema
    MAX_SCORE_VALUE = Decimal('999.99')
    MIN_SCORE_VALUE = Decimal('0.00')
    DECIMAL_PLACES = 2
    
    @classmethod
    def normalize_score(cls, score: Any, max_possible: Optional[Decimal] = None) -> Optional[Decimal]:
        """
        Normalize any score value to a valid Decimal within field limits
        
        Args:
            score: The score value (can be int, float, str, Decimal, or None)
            max_possible: Maximum possible score for validation
            
        Returns:
            Normalized Decimal score or None if invalid
        """
        if score is None or score == '':
            return None
            
        try:
            # Convert to Decimal for precision
            if isinstance(score, str):
                score = score.strip()
                if not score:
                    return None
            
            decimal_score = Decimal(str(score)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            
            # Enforce field limits
            if decimal_score > cls.MAX_SCORE_VALUE:
                logger.warning(f"Score {decimal_score} exceeds maximum, capping to {cls.MAX_SCORE_VALUE}")
                decimal_score = cls.MAX_SCORE_VALUE
            elif decimal_score < cls.MIN_SCORE_VALUE:
                logger.warning(f"Score {decimal_score} below minimum, setting to {cls.MIN_SCORE_VALUE}")
                decimal_score = cls.MIN_SCORE_VALUE
            
            # Validate against max possible if provided
            if max_possible is not None and decimal_score > max_possible:
                logger.warning(f"Score {decimal_score} exceeds max possible {max_possible}, capping")
                decimal_score = min(decimal_score, max_possible)
            
            return decimal_score
            
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.error(f"Failed to normalize score '{score}': {e}")
            return None
    
    @classmethod
    def calculate_percentage(cls, earned: Any, total: Any) -> Optional[Decimal]:
        """
        Calculate percentage score with proper error handling
        
        Args:
            earned: Points earned
            total: Total possible points
            
        Returns:
            Percentage as Decimal or None if calculation fails
        """
        try:
            earned_decimal = cls.normalize_score(earned)
            total_decimal = cls.normalize_score(total)
            
            if earned_decimal is None or total_decimal is None:
                return None
            
            if total_decimal == 0:
                logger.warning("Cannot calculate percentage with zero total points")
                return Decimal('0.00')
            
            percentage = (earned_decimal / total_decimal * 100).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            
            return cls.normalize_score(percentage, Decimal('100.00'))
            
        except Exception as e:
            logger.error(f"Failed to calculate percentage for {earned}/{total}: {e}")
            return None
    
    @classmethod
    def convert_percentage_to_points(cls, percentage: Any, total_points: Any) -> Optional[Decimal]:
        """
        Convert percentage score to points
        
        Args:
            percentage: Percentage value (0-100)
            total_points: Total possible points
            
        Returns:
            Points as Decimal or None if conversion fails
        """
        try:
            percentage_decimal = cls.normalize_score(percentage, Decimal('100.00'))
            total_decimal = cls.normalize_score(total_points)
            
            if percentage_decimal is None or total_decimal is None:
                return None
            
            points = (percentage_decimal * total_decimal / 100).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            
            return cls.normalize_score(points, total_decimal)
            
        except Exception as e:
            logger.error(f"Failed to convert {percentage}% to points out of {total_points}: {e}")
            return None
    
    @classmethod
    def handle_scorm_score(cls, scorm_score_data: Dict[str, Any]) -> Optional[Decimal]:
        """
        Handle SCORM score data with proper normalization
        
        Args:
            scorm_score_data: Dictionary containing SCORM score information
            
        Returns:
            Normalized score or None
        """
        if not isinstance(scorm_score_data, dict):
            return cls.normalize_score(scorm_score_data)
        
        score = None
        
        # Try scaled score first (0-1 range)
        if 'scaled' in scorm_score_data:
            try:
                scaled_score = float(scorm_score_data['scaled'])
                # Convert to percentage (0-100)
                score = scaled_score * 100
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to process SCORM scaled score: {e}")
        
        # Try raw score if scaled not available
        elif 'raw' in scorm_score_data:
            try:
                score = float(scorm_score_data['raw'])
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to process SCORM raw score: {e}")
        
        return cls.normalize_score(score)
    
    @classmethod
    def validate_score_update(cls, current_score: Any, new_score: Any, 
                            max_possible: Optional[Decimal] = None) -> Tuple[bool, str, Optional[Decimal]]:
        """
        Validate a score update with detailed feedback
        
        Args:
            current_score: Current score value
            new_score: New score value to validate
            max_possible: Maximum possible score
            
        Returns:
            Tuple of (is_valid, error_message, normalized_score)
        """
        try:
            normalized_score = cls.normalize_score(new_score, max_possible)
            
            if normalized_score is None:
                return False, "Invalid score format", None
            
            # Additional business logic validation can be added here
            if max_possible and normalized_score > max_possible:
                return False, f"Score cannot exceed maximum of {max_possible}", None
            
            return True, "", normalized_score
            
        except Exception as e:
            logger.error(f"Score validation failed: {e}")
            return False, f"Score validation error: {str(e)}", None
    
    @classmethod
    def calculate_quiz_score(cls, earned_points: Any, total_points: Any, 
                           is_percentage_based: bool = False) -> Dict[str, Any]:
        """
        Calculate quiz score with consistent handling
        
        Args:
            earned_points: Points earned by student
            total_points: Total possible points
            is_percentage_based: Whether the quiz uses percentage scoring
            
        Returns:
            Dictionary with score calculation results
        """
        try:
            earned = cls.normalize_score(earned_points)
            total = cls.normalize_score(total_points)
            
            if earned is None or total is None:
                return {
                    'success': False,
                    'error': 'Invalid score values',
                    'final_score': None,
                    'percentage': None,
                    'max_score': None
                }
            
            if is_percentage_based or total == 0:
                # For percentage-based or when no total points defined
                final_score = earned  # Treat earned as percentage
                percentage = final_score
                max_score = Decimal('100.00')
            else:
                # For points-based scoring
                percentage = cls.calculate_percentage(earned, total)
                final_score = earned
                max_score = total
            
            return {
                'success': True,
                'final_score': final_score,
                'percentage': percentage,
                'max_score': max_score,
                'earned_points': earned,
                'total_points': total
            }
            
        except Exception as e:
            logger.error(f"Quiz score calculation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'final_score': None,
                'percentage': None,
                'max_score': None
            }

# Convenience functions for backward compatibility
def normalize_score(score, max_possible=None):
    """Backward compatibility function"""
    return ScoreCalculationService.normalize_score(score, max_possible)

def calculate_percentage(earned, total):
    """Backward compatibility function"""
    return ScoreCalculationService.calculate_percentage(earned, total)

def handle_scorm_score(scorm_data):
    """Backward compatibility function"""
    return ScoreCalculationService.handle_scorm_score(scorm_data)
