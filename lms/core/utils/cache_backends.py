"""
Custom cache backends with fallback mechanisms for Redis unavailability.
"""

import logging
try:
    from django.core.cache.backends.redis import RedisCache
except ImportError:
    # Fallback for Django 3.2 - use django-redis
    from django_redis.cache import RedisCache
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache import InvalidCacheBackendError

logger = logging.getLogger(__name__)

class FallbackRedisCache(RedisCache):
    """
    Redis cache backend with fallback to local memory cache.
    When Redis is unavailable, it falls back to an in-memory cache.
    """
    
    def __init__(self, server, params):
        super().__init__(server, params)
        # Initialize fallback cache
        self._fallback_cache = LocMemCache('locmem://unique_fallback', {})
        self._redis_available = True
        self._last_check_time = 0
        self._check_interval = 30  # Check Redis availability every 30 seconds
        
    def _is_redis_available(self):
        """Check if Redis is available with periodic checks to avoid constant testing"""
        import time
        current_time = time.time()
        
        # If we recently checked and Redis was down, don't check again immediately
        if not self._redis_available and (current_time - self._last_check_time) < self._check_interval:
            return False
            
        # If Redis was previously available or enough time has passed, test the connection
        if self._redis_available or (current_time - self._last_check_time) >= self._check_interval:
            try:
                # Try a simple operation to test the connection
                # Use the proper Django Redis backend method
                if hasattr(self._cache, 'get_client'):
                    # For django-redis
                    client = self._cache.get_client()
                    client.ping()
                else:
                    # For django-redis-cache or other backends
                    # Try a simple get operation as a connection test
                    self._cache.get('__redis_connection_test__')
                    
                if not self._redis_available:
                    logger.info("Redis connection restored, switching back from fallback cache")
                self._redis_available = True
                self._last_check_time = current_time
                return True
            except Exception as e:
                if self._redis_available:
                    # logger.warning(f"Redis connection lost, switching to fallback cache: {str(e)}")  # COMMENTED OUT to reduce log noise
                    pass
                self._redis_available = False
                self._last_check_time = current_time
                return False
        
        return self._redis_available
    
    def _safe_redis_operation(self, operation, *args, **kwargs):
        """Safely execute Redis operations with fallback"""
        if not self._is_redis_available():
            return self._fallback_operation(operation.__name__, *args, **kwargs)
        
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            # logger.warning(f"Redis operation failed: {str(e)}, using fallback")  # COMMENTED OUT to reduce log noise
            self._redis_available = False
            return self._fallback_operation(operation.__name__, *args, **kwargs)
    
    def _fallback_operation(self, operation_name, *args, **kwargs):
        """Execute operation on fallback cache"""
        try:
            fallback_method = getattr(self._fallback_cache, operation_name)
            return fallback_method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Fallback cache operation failed: {str(e)}")
            # Return sensible defaults for different operations
            if operation_name in ['get', 'get_many']:
                return None if operation_name == 'get' else {}
            elif operation_name in ['set', 'add', 'delete', 'set_many', 'delete_many']:
                return True
            elif operation_name == 'incr':
                return 1
            else:
                return None
    
    def get(self, key, default=None, version=None):
        """Get value from cache with fallback"""
        return self._safe_redis_operation(super().get, key, default, version)
    
    def set(self, key, value, timeout=None, version=None):
        """Set value in cache with fallback"""
        return self._safe_redis_operation(super().set, key, value, timeout, version)
    
    def add(self, key, value, timeout=None, version=None):
        """Add value to cache with fallback"""
        return self._safe_redis_operation(super().add, key, value, timeout, version)
    
    def delete(self, key, version=None):
        """Delete value from cache with fallback"""
        return self._safe_redis_operation(super().delete, key, version)
    
    def get_many(self, keys, version=None):
        """Get multiple values from cache with fallback"""
        return self._safe_redis_operation(super().get_many, keys, version)
    
    def set_many(self, data, timeout=None, version=None):
        """Set multiple values in cache with fallback"""
        return self._safe_redis_operation(super().set_many, data, timeout, version)
    
    def delete_many(self, keys, version=None):
        """Delete multiple values from cache with fallback"""
        return self._safe_redis_operation(super().delete_many, keys, version)
    
    def incr(self, key, delta=1, version=None):
        """Increment value in cache with fallback"""
        return self._safe_redis_operation(super().incr, key, delta, version)
    
    def decr(self, key, delta=1, version=None):
        """Decrement value in cache with fallback"""
        return self._safe_redis_operation(super().decr, key, delta, version)
    
    def clear(self):
        """Clear cache with fallback"""
        return self._safe_redis_operation(super().clear)
    
    def has_key(self, key, version=None):
        """Check if key exists in cache with fallback"""
        return self._safe_redis_operation(super().has_key, key, version)
    
    def ttl(self, key, version=None):
        """Get time to live for key with fallback"""
        return self._safe_redis_operation(super().ttl, key, version)
    
    def expire(self, key, timeout, version=None):
        """Set expiration for key with fallback"""
        return self._safe_redis_operation(super().expire, key, timeout, version) 