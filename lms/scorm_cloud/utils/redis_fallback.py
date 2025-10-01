"""
Robust Redis fallback system for SCORM worker
Handles Redis connection failures gracefully
"""
import os
import logging
import threading
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache

logger = logging.getLogger(__name__)

class RobustRedisFallback:
    """Robust Redis fallback with local memory cache"""
    
    def __init__(self):
        self.local_cache = LocMemCache('scorm_local', {})
        self.redis_available = False
        self._lock = threading.Lock()
        self._test_redis()
    
    def _test_redis(self):
        """Test Redis connection with timeout"""
        try:
            with self._lock:
                cache.set('redis_test', 'ok', 1)
                result = cache.get('redis_test')
                if result == 'ok':
                    self.redis_available = True
                    logger.info("Redis connection working")
                else:
                    logger.warning("Redis cache not working, using local fallback")
                    self.redis_available = False
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using local fallback")
            self.redis_available = False
    
    def get(self, key, default=None):
        """Get value with Redis fallback"""
        if self.redis_available:
            try:
                return cache.get(key, default)
            except Exception as e:
                logger.warning(f"Redis get failed: {e}, using local fallback")
                self.redis_available = False
        
        try:
            return self.local_cache.get(key, default)
        except Exception as e:
            logger.error(f"Local cache get failed: {e}")
            return default
    
    def set(self, key, value, timeout=None):
        """Set value with Redis fallback"""
        if self.redis_available:
            try:
                cache.set(key, value, timeout)
                return True
            except Exception as e:
                logger.warning(f"Redis set failed: {e}, using local fallback")
                self.redis_available = False
        
        try:
            self.local_cache.set(key, value, timeout)
            return True
        except Exception as e:
            logger.error(f"Local cache set failed: {e}")
            return False
    
    def delete(self, key):
        """Delete value with Redis fallback"""
        if self.redis_available:
            try:
                cache.delete(key)
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}, using local fallback")
                self.redis_available = False
        
        try:
            self.local_cache.delete(key)
        except Exception as e:
            logger.error(f"Local cache delete failed: {e}")

# Global fallback instance
_robust_fallback = None

def get_robust_fallback():
    """Get or create robust fallback instance"""
    global _robust_fallback
    if _robust_fallback is None:
        _robust_fallback = RobustRedisFallback()
    return _robust_fallback
