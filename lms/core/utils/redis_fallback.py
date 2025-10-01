"""
Redis Fallback Utility
Provides in-memory fallback when Redis is unavailable
"""

import time
import threading
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Thread-local storage for in-memory cache when Redis is unavailable
_local_cache = threading.local()

def ensure_local_cache_initialized():
    """Ensure the thread-local cache is initialized"""
    _local_cache.cache = {}
    _local_cache.locks = {}
    _local_cache.expiry = {}


def with_redis_fallback(f):
    """
    Decorator to wrap Redis operations with fallback mechanism.
    If Redis fails, it falls back to in-memory operations.
    """
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Redis operation failed, using fallback: {e}")
            # Map function names to fallback functions
            fallback_map = {
                'get': memory_get,
                'set': memory_set,
                'add': memory_add,
                'delete': memory_delete,
                'get_many': memory_get_many,
                'set_many': memory_set_many,
                'delete_many': memory_delete_many,
                'clear': memory_clear,
                'incr': memory_incr,
                'decr': memory_decr,
            }
            
            fallback_func = fallback_map.get(f.__name__)
            if fallback_func:
                return fallback_func(*args, **kwargs)
            else:
                raise e
    
    return wrapper


def memory_get(key, default=None, **kwargs):
    """In-memory fallback for cache.get"""
    ensure_local_cache_initialized()
    
    # Check if key exists
    if key not in _local_cache.cache:
        return default
    
    # Check if key has expired
    if key in _local_cache.expiry and time.time() > _local_cache.expiry[key]:
        del _local_cache.cache[key]
        del _local_cache.expiry[key]
        return default
    
    return _local_cache.cache.get(key, default)


def memory_set(key, value, timeout=None, **kwargs):
    """In-memory fallback for cache.set"""
    ensure_local_cache_initialized()
    
    _local_cache.cache[key] = value
    
    # Store expiry time if timeout is provided
    if timeout:
        _local_cache.expiry[key] = time.time() + timeout
    elif key in _local_cache.expiry:
        del _local_cache.expiry[key]
    
    return True


def memory_add(key, value, timeout=None, **kwargs):
    """In-memory fallback for cache.add (atomic add)"""
    ensure_local_cache_initialized()
    
    # If key already exists and hasn't expired, return False
    if key in _local_cache.cache:
        if key not in _local_cache.expiry or time.time() <= _local_cache.expiry[key]:
            return False
    
    # Add the key
    _local_cache.cache[key] = value
    
    # Store expiry time if timeout is provided
    if timeout:
        _local_cache.expiry[key] = time.time() + timeout
    
    return True


def memory_delete(key, **kwargs):
    """In-memory fallback for cache.delete"""
    ensure_local_cache_initialized()
    
    # Remove from cache and expiry if exists
    if key in _local_cache.cache:
        del _local_cache.cache[key]
    
    if key in _local_cache.expiry:
        del _local_cache.expiry[key]
    
    return True


def memory_get_many(keys, **kwargs):
    """In-memory fallback for cache.get_many"""
    ensure_local_cache_initialized()
    
    result = {}
    current_time = time.time()
    
    for key in keys:
        if key in _local_cache.cache:
            # Check if key has expired
            if key in _local_cache.expiry and current_time > _local_cache.expiry[key]:
                del _local_cache.cache[key]
                del _local_cache.expiry[key]
            else:
                result[key] = _local_cache.cache[key]
    
    return result


def memory_set_many(data, timeout=None, **kwargs):
    """In-memory fallback for cache.set_many"""
    ensure_local_cache_initialized()
    
    failed_keys = []
    current_time = time.time()
    
    for key, value in data.items():
        try:
            _local_cache.cache[key] = value
            
            if timeout:
                _local_cache.expiry[key] = current_time + timeout
            elif key in _local_cache.expiry:
                del _local_cache.expiry[key]
        except Exception:
            failed_keys.append(key)
    
    return failed_keys


def memory_delete_many(keys, **kwargs):
    """In-memory fallback for cache.delete_many"""
    ensure_local_cache_initialized()
    
    for key in keys:
        if key in _local_cache.cache:
            del _local_cache.cache[key]
        if key in _local_cache.expiry:
            del _local_cache.expiry[key]
    
    return True


def memory_clear(**kwargs):
    """In-memory fallback for cache.clear"""
    ensure_local_cache_initialized()
    
    _local_cache.cache.clear()
    _local_cache.expiry.clear()
    _local_cache.locks.clear()
    
    return True


def memory_incr(key, delta=1, **kwargs):
    """In-memory fallback for cache.incr"""
    ensure_local_cache_initialized()
    
    if key not in _local_cache.cache:
        raise ValueError(f"Key '{key}' not found")
    
    try:
        current_value = int(_local_cache.cache[key])
        new_value = current_value + delta
        _local_cache.cache[key] = new_value
        return new_value
    except (ValueError, TypeError):
        raise ValueError(f"Key '{key}' value is not a number")


def memory_decr(key, delta=1, **kwargs):
    """In-memory fallback for cache.decr"""
    return memory_incr(key, -delta, **kwargs)


# Production-ready cache operations with fallback
def safe_get(key, default=None, **kwargs):
    """Get value from cache with Redis fallback"""
    try:
        return cache._original_get(key, default, **kwargs)
    except Exception as e:
        logger.warning(f"Redis get failed, using memory fallback: {e}")
        return memory_get(key, default, **kwargs)


def safe_set(key, value, timeout=None, **kwargs):
    """Set value in cache with Redis fallback"""
    try:
        return cache._original_set(key, value, timeout, **kwargs)
    except Exception as e:
        logger.warning(f"Redis set failed, using memory fallback: {e}")
        return memory_set(key, value, timeout, **kwargs)


def safe_add(key, value, timeout=None, **kwargs):
    """Add value to cache with Redis fallback"""
    try:
        return cache._original_add(key, value, timeout, **kwargs)
    except Exception as e:
        logger.warning(f"Redis add failed, using memory fallback: {e}")
        return memory_add(key, value, timeout, **kwargs)


def safe_delete(key, **kwargs):
    """Delete value from cache with Redis fallback"""
    try:
        return cache._original_delete(key, **kwargs)
    except Exception as e:
        logger.warning(f"Redis delete failed, using memory fallback: {e}")
        return memory_delete(key, **kwargs)


def safe_get_many(keys, **kwargs):
    """Get multiple values from cache with Redis fallback"""
    try:
        return cache._original_get_many(keys, **kwargs)
    except Exception as e:
        logger.warning(f"Redis get_many failed, using memory fallback: {e}")
        return memory_get_many(keys, **kwargs)


def safe_set_many(data, timeout=None, **kwargs):
    """Set multiple values in cache with Redis fallback"""
    try:
        return cache._original_set_many(data, timeout, **kwargs)
    except Exception as e:
        logger.warning(f"Redis set_many failed, using memory fallback: {e}")
        return memory_set_many(data, timeout, **kwargs)


def safe_delete_many(keys, **kwargs):
    """Delete multiple values from cache with Redis fallback"""
    try:
        return cache.delete_many(keys, **kwargs)
    except Exception as e:
        logger.warning(f"Redis delete_many failed, using memory fallback: {e}")
        return memory_delete_many(keys, **kwargs)


def safe_clear(**kwargs):
    """Clear cache with Redis fallback"""
    try:
        return cache.clear(**kwargs)
    except Exception as e:
        logger.warning(f"Redis clear failed, using memory fallback: {e}")
        return memory_clear(**kwargs)


def safe_incr(key, delta=1, **kwargs):
    """Increment value in cache with Redis fallback"""
    try:
        return cache.incr(key, delta, **kwargs)
    except Exception as e:
        logger.warning(f"Redis incr failed, using memory fallback: {e}")
        return memory_incr(key, delta, **kwargs)


def safe_decr(key, delta=1, **kwargs):
    """Decrement value in cache with Redis fallback"""
    try:
        return cache.decr(key, delta, **kwargs)
    except Exception as e:
        logger.warning(f"Redis decr failed, using memory fallback: {e}")
        return memory_decr(key, delta, **kwargs)


def apply_cache_patches():
    """
    Cache patches disabled for system stability.
    Using database-only session management.
    """
    logger.info("Cache system disabled - using database-only approach")
    return True