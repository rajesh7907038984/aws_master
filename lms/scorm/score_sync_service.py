"""
SCORM Score Sync Service
Centralized service for SCORM score synchronization with proper error handling and validation
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class ScormScoreSyncService:
    """
    Centralized service for SCORM score synchronization with robust error handling
    """
    
    @staticmethod
    def sync_score(attempt, force=False):
        """
        Synchronize SCORM score data with proper validation and error handling
        
        Args:
            attempt: ScormAttempt instance
            force: Force synchronization even if not needed
            
        Returns:
            dict: {'success': bool, 'message': str, 'data': dict}
        """
        try:
            # Validate attempt object
            if not attempt or not hasattr(attempt, 'id'):
                return {
                    'success': False,
                    'message': 'Invalid attempt object',
                    'data': {}
                }
            
            # Skip if no score data to sync and not forced
            if not force and (attempt.score_raw is None or attempt.score_raw == ''):
                logger.debug(f"No score data to sync for attempt {attempt.id}")
                return {
                    'success': True,
                    'message': 'No score data to sync',
                    'data': {'skipped': True}
                }
            
            # Use transaction to ensure atomicity
            with transaction.atomic():
                # Validate and normalize score data
                sync_result = ScormScoreSyncService._validate_and_normalize_scores(attempt)
                if not sync_result['valid']:
                    return {
                        'success': False,
                        'message': f"Score validation failed: {sync_result['error']}",
                        'data': sync_result
                    }
                
                # Calculate scaled score if raw score exists
                if attempt.score_raw is not None:
                    attempt.score_scaled = ScormScoreSyncService._calculate_scaled_score(
                        attempt.score_raw, 
                        attempt.score_min, 
                        attempt.score_max
                    )
                
                # Update completion status based on score
                ScormScoreSyncService._update_completion_status(attempt)
                
                # Save with timestamp
                attempt.last_accessed = timezone.now()
                attempt.save(update_fields=[
                    'score_scaled', 'lesson_status', 'completion_status', 
                    'success_status', 'last_accessed'
                ])
                
                # Log successful sync
                logger.info(f"Score sync completed for attempt {attempt.id}: "
                          f"raw={attempt.score_raw}, scaled={attempt.score_scaled}, "
                          f"status={attempt.lesson_status}")
                
                return {
                    'success': True,
                    'message': 'Score synchronized successfully',
                    'data': {
                        'raw_score': float(attempt.score_raw) if attempt.score_raw else None,
                        'scaled_score': float(attempt.score_scaled) if attempt.score_scaled else None,
                        'lesson_status': attempt.lesson_status,
                        'completion_status': attempt.completion_status,
                        'success_status': attempt.success_status
                    }
                }
            
        except Exception as e:
            logger.error(f"Error in score sync for attempt {attempt.id}: {str(e)}", 
                        exc_info=True)
            return {
                'success': False,
                'message': f'Score sync failed: {str(e)}',
                'data': {'error': str(e)}
            }
    
    @staticmethod
    def _validate_and_normalize_scores(attempt):
        """
        Validate and normalize score data
        
        Returns:
            dict: {'valid': bool, 'error': str, 'data': dict}
        """
        try:
            # Validate score_raw
            if attempt.score_raw is not None:
                try:
                    raw_score = Decimal(str(attempt.score_raw))
                    if raw_score < 0:
                        return {'valid': False, 'error': 'Raw score cannot be negative'}
                    attempt.score_raw = raw_score
                except (ValueError, TypeError) as e:
                    return {'valid': False, 'error': f'Invalid raw score format: {str(e)}'}
            
            # Validate and set defaults for min/max scores
            if attempt.score_min is None:
                attempt.score_min = Decimal('0')
            else:
                attempt.score_min = Decimal(str(attempt.score_min))
                
            if attempt.score_max is None:
                attempt.score_max = Decimal('100')
            else:
                attempt.score_max = Decimal(str(attempt.score_max))
            
            # Validate score range
            if attempt.score_min >= attempt.score_max:
                return {'valid': False, 'error': 'Score minimum must be less than maximum'}
            
            # Validate raw score is within bounds
            if attempt.score_raw is not None:
                if attempt.score_raw < attempt.score_min:
                    logger.warning(f"Raw score {attempt.score_raw} below minimum {attempt.score_min}")
                if attempt.score_raw > attempt.score_max:
                    logger.warning(f"Raw score {attempt.score_raw} above maximum {attempt.score_max}")
            
            return {'valid': True, 'error': None, 'data': {}}
            
        except Exception as e:
            return {'valid': False, 'error': f'Score validation error: {str(e)}'}
    
    @staticmethod
    def _calculate_scaled_score(raw_score, min_score, max_score):
        """
        Calculate scaled score (0-1 range) from raw score
        
        Returns:
            Decimal: Scaled score between 0 and 1
        """
        try:
            if raw_score is None or min_score is None or max_score is None:
                return None
            
            # Avoid division by zero
            if max_score == min_score:
                return Decimal('0.5')  # Default to middle if no range
            
            # Calculate scaled score: (raw - min) / (max - min)
            scaled = (raw_score - min_score) / (max_score - min_score)
            
            # Ensure it's between 0 and 1
            scaled = max(Decimal('0'), min(Decimal('1'), scaled))
            
            # Round to 4 decimal places
            return scaled.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            
        except Exception as e:
            logger.error(f"Error calculating scaled score: {str(e)}")
            return None
    
    @staticmethod
    def _update_completion_status(attempt):
        """
        Update completion and success status based on score and mastery criteria
        """
        try:
            # Check if there's a mastery score requirement
            mastery_score = attempt.scorm_package.mastery_score
            
            if attempt.score_raw is not None and mastery_score is not None:
                # Determine success based on mastery score
                if attempt.score_raw >= mastery_score:
                    attempt.success_status = 'passed'
                    attempt.lesson_status = 'passed'
                else:
                    attempt.success_status = 'failed'
                    attempt.lesson_status = 'failed'
                
                # Set completion status
                attempt.completion_status = 'completed'
            else:
                # No score-based criteria, use lesson status
                if attempt.lesson_status in ['passed', 'completed']:
                    attempt.completion_status = 'completed'
                    attempt.success_status = 'passed'
                elif attempt.lesson_status == 'failed':
                    attempt.completion_status = 'completed'
                    attempt.success_status = 'failed'
                else:
                    attempt.completion_status = 'incomplete'
                    attempt.success_status = 'unknown'
                    
        except Exception as e:
            logger.error(f"Error updating completion status: {str(e)}")
    
    @staticmethod
    def bulk_sync_scores(attempts, force=False):
        """
        Synchronize multiple SCORM attempts in batch
        
        Args:
            attempts: QuerySet or list of ScormAttempt instances
            force: Force synchronization even if not needed
            
        Returns:
            dict: Summary of sync results
        """
        results = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        try:
            for attempt in attempts:
                results['total'] += 1
                sync_result = ScormScoreSyncService.sync_score(attempt, force)
                
                if sync_result['success']:
                    if sync_result['data'].get('skipped', False):
                        results['skipped'] += 1
                    else:
                        results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'attempt_id': attempt.id,
                        'error': sync_result['message']
                    })
            
            logger.info(f"Bulk sync completed: {results['successful']} successful, "
                       f"{results['failed']} failed, {results['skipped']} skipped")
            
        except Exception as e:
            logger.error(f"Error in bulk score sync: {str(e)}", exc_info=True)
            results['errors'].append({'bulk_error': str(e)})
        
        return results
