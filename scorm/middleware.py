"""
SCORM Time Tracking Middleware
Processes cached time tracking data when database is available
"""

import logging
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

class ScormTimeTrackingMiddleware:
    """
    Middleware to process cached time tracking data when database is available
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Process cached time data before handling request
        self.process_cached_time_data()
        
        response = self.get_response(request)
        return response
    
    def process_cached_time_data(self):
        """Process any cached time tracking data"""
        try:
            # Get all cached time tracking data
            cache_keys = cache.keys("scorm_time_fallback_*")
            
            if cache_keys:
                logger.info(f"Processing {len(cache_keys)} cached time tracking entries")
                
                for key in cache_keys:
                    try:
                        data = cache.get(key)
                        if data:
                            # Process the cached data
                            attempt_id = data.get('attempt_id')
                            if attempt_id:
                                from scorm.models import ScormAttempt
                                
                                attempt = ScormAttempt.objects.get(id=attempt_id)
                                
                                # Update attempt with cached time data
                                session_time = data.get('session_time')
                                total_time = data.get('total_time')
                                
                                if session_time:
                                    attempt.session_time = session_time
                                if total_time:
                                    attempt.total_time = total_time
                                
                                attempt.save()
                                
                                # Success - remove from cache
                                cache.delete(key)
                                logger.info(f"✅ Processed cached time data for attempt {attempt_id}")
                            
                    except Exception as e:
                        logger.error(f"Error processing cached time data for key {key}: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error processing cached time data: {str(e)}")


class ScormTimeTrackingHealthMiddleware:
    """
    Middleware to monitor SCORM time tracking health
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check time tracking health periodically
        if self._should_check_health():
            self._check_time_tracking_health()
        
        response = self.get_response(request)
        return response
    
    def _should_check_health(self):
        """Check if we should run health check (every 5 minutes)"""
        last_check = cache.get('scorm_time_health_last_check')
        if not last_check:
            return True
        
        # Check every 5 minutes
        return (timezone.now() - last_check).total_seconds() > 300
    
    def _check_time_tracking_health(self):
        """Check SCORM time tracking health"""
        try:
            from scorm.models import ScormAttempt
            
            # Check for CMI data integrity
            cmi_attempts = ScormAttempt.objects.filter(
                cmi_data__isnull=False
            ).count()
            
            # Check for cache fallbacks
            cache_keys = cache.keys("scorm_time_fallback_*")
            fallback_count = len(cache_keys)
            
            # Check database connection health
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            health_status = {
                'status': 'healthy',
                'cmi_attempts': cmi_attempts,
                'fallback_count': fallback_count,
                'database_connected': True,
                'timestamp': timezone.now().isoformat()
            }
            
            # Store health status
            cache.set('scorm_time_health_status', health_status, timeout=600)
            cache.set('scorm_time_health_last_check', timezone.now(), timeout=600)
            
            if fallback_count > 0:
                logger.warning(f"SCORM time tracking health: {fallback_count} fallbacks")
            else:
                logger.info("SCORM time tracking health: All systems operational")
                
        except Exception as e:
            logger.error(f"Error checking time tracking health: {str(e)}")
            cache.set('scorm_time_health_status', {
                'status': 'unhealthy',
                'error': str(e),
                'database_connected': False,
                'timestamp': timezone.now().isoformat()
            }, timeout=600)


class ScormSSLExemptMiddleware:
    """
    Middleware to exempt SCORM content from SSL requirements
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if this is a SCORM content request
        if request.path.startswith('/scorm/content/'):
            # Add header to exempt from SSL requirements
            request.META['HTTP_X_FORWARDED_PROTO'] = 'https'
        
        response = self.get_response(request)
        return response