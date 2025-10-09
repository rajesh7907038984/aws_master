"""
SCORM Real-time Validation Middleware
Automatically validates and fixes SCORM score issues during user interactions
"""
import logging
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from .real_time_validator import ScormScoreValidator

logger = logging.getLogger(__name__)


class ScormRealTimeValidationMiddleware:
    """
    Middleware that performs real-time SCORM validation for gradebook and course views
    Automatically fixes score synchronization issues before users see incorrect data
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Process request normally
        response = self.get_response(request)
        
        # Run SCORM validation for relevant views
        if self._should_validate(request):
            self._perform_real_time_validation(request)
        
        return response
    
    def _should_validate(self, request):
        """Determine if SCORM validation should run for this request"""
        # Only validate for authenticated users
        if not request.user.is_authenticated:
            return False
        
        # Only validate for specific views that show SCORM data
        validation_paths = [
            '/gradebook/',
            '/courses/',
            '/scorm/',
        ]
        
        return any(request.path.startswith(path) for path in validation_paths)
    
    def _perform_real_time_validation(self, request):
        """
        Perform real-time validation of SCORM scores for the current user
        """
        try:
            # Use cache to prevent excessive validation
            cache_key = f'scorm_validation_{request.user.id}'
            last_validation = cache.get(cache_key)
            
            # Only validate once every 5 minutes per user
            if last_validation:
                return
            
            # Set cache for 5 minutes
            cache.set(cache_key, timezone.now().isoformat(), 300)
            
            # Run quick validation for user's recent attempts
            from .models import ScormAttempt
            
            # Check attempts from last 24 hours
            since = timezone.now() - timedelta(hours=24)
            user_attempts = ScormAttempt.objects.filter(
                user=request.user,
                last_accessed__gte=since
            ).order_by('-last_accessed')[:10]  # Limit to 10 most recent
            
            fixes_applied = 0
            
            for attempt in user_attempts:
                # Quick check for obvious issues
                needs_fix = (
                    # Has suspend data but no score
                    (attempt.suspend_data and len(attempt.suspend_data) > 50 and not attempt.score_raw) or
                    # Has score but wrong status
                    (attempt.score_raw and attempt.lesson_status == 'not_attempted')
                )
                
                if needs_fix:
                    logger.info(f"Real-time Validator: Fixing attempt {attempt.id} for user {request.user.username}")
                    
                    # Use the dynamic processor
                    from .dynamic_score_processor import auto_process_scorm_score
                    
                    if auto_process_scorm_score(attempt):
                        fixes_applied += 1
                        logger.info(f"Real-time Validator: Fixed attempt {attempt.id}")
            
            if fixes_applied > 0:
                logger.info(f"Real-time Validator: Applied {fixes_applied} fixes for user {request.user.username}")
                
                # Clear user-specific caches for immediate UI updates
                user_cache_keys = [
                    f'gradebook_scores_{request.user.id}',
                    f'user_progress_{request.user.id}',
                    f'topic_progress_{request.user.id}_*',
                ]
                
                for key in user_cache_keys:
                    cache.delete_pattern(key) if hasattr(cache, 'delete_pattern') else None
                
        except Exception as e:
            logger.error(f"Real-time Validator: Error during validation: {str(e)}")
    
    def _check_topic_progress_sync(self, attempt):
        """Quick check if TopicProgress is out of sync"""
        if not attempt.score_raw:
            return False
        
        try:
            from courses.models import TopicProgress
            
            progress = TopicProgress.objects.filter(
                user=attempt.user,
                topic=attempt.scorm_package.topic
            ).first()
            
            if not progress:
                return True  # Missing
            
            if progress.last_score != float(attempt.score_raw):
                return True  # Out of sync
                
            return False
            
        except Exception:
            return False