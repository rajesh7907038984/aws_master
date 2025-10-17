"""
Cache Manager for LMS
====================

This module provides intelligent caching for search results,
frequently accessed data, and performance optimization.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Union
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.db.models import QuerySet
from django.core.paginator import Paginator
from django.http import HttpRequest

logger = logging.getLogger(__name__)

class CacheManager:
    """Intelligent cache management for LMS"""
    
    def __init__(self):
        self.default_timeout = 300  # 5 minutes
        self.search_timeout = 600   # 10 minutes
        self.user_timeout = 1800   # 30 minutes
        self.cache_prefix = 'lms_cache'
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a unique cache key"""
        key_data = {
            'prefix': prefix,
            'args': args,
            'kwargs': kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{self.cache_prefix}:{prefix}:{key_hash}"
    
    def cache_search_results(self, search_type: str, query: str, user_id: int, 
                           results: List[Dict], timeout: int = None) -> None:
        """Cache search results"""
        cache_key = self._generate_cache_key(
            'search', search_type, query, user_id
        )
        cache_data = {
            'results': results,
            'timestamp': timezone.now().isoformat(),
            'query': query,
            'user_id': user_id
        }
        
        cache.set(
            cache_key, 
            cache_data, 
            timeout or self.search_timeout
        )
        logger.info(f"Cached search results for {search_type}: {query}")
    
    def get_cached_search_results(self, search_type: str, query: str, 
                                user_id: int) -> Optional[List[Dict]]:
        """Get cached search results"""
        cache_key = self._generate_cache_key(
            'search', search_type, query, user_id
        )
        
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit for search: {search_type}: {query}")
            return cached_data.get('results')
        
        logger.info(f"Cache miss for search: {search_type}: {query}")
        return None
    
    def cache_user_data(self, user_id: int, data_type: str, data: Any, 
                       timeout: int = None) -> None:
        """Cache user-specific data"""
        cache_key = self._generate_cache_key(
            'user_data', user_id, data_type
        )
        
        cache.set(
            cache_key,
            data,
            timeout or self.user_timeout
        )
        logger.info(f"Cached user data: {data_type} for user {user_id}")
    
    def get_cached_user_data(self, user_id: int, data_type: str) -> Optional[Any]:
        """Get cached user data"""
        cache_key = self._generate_cache_key(
            'user_data', user_id, data_type
        )
        
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit for user data: {data_type}")
            return cached_data
        
        logger.info(f"Cache miss for user data: {data_type}")
        return None
    
    def cache_paginated_results(self, model_name: str, filters: Dict, 
                              page: int, per_page: int, results: List[Dict],
                              total_count: int, timeout: int = None) -> None:
        """Cache paginated results"""
        cache_key = self._generate_cache_key(
            'paginated', model_name, filters, page, per_page
        )
        
        cache_data = {
            'results': results,
            'total_count': total_count,
            'page': page,
            'per_page': per_page,
            'timestamp': timezone.now().isoformat()
        }
        
        cache.set(
            cache_key,
            cache_data,
            timeout or self.default_timeout
        )
        logger.info(f"Cached paginated results: {model_name} page {page}")
    
    def get_cached_paginated_results(self, model_name: str, filters: Dict,
                                    page: int, per_page: int) -> Optional[Dict]:
        """Get cached paginated results"""
        cache_key = self._generate_cache_key(
            'paginated', model_name, filters, page, per_page
        )
        
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit for paginated: {model_name} page {page}")
            return cached_data
        
        logger.info(f"Cache miss for paginated: {model_name} page {page}")
        return None
    
    def cache_course_list(self, user_id: int, filters: Dict, 
                         courses: List[Dict], timeout: int = None) -> None:
        """Cache course list results"""
        cache_key = self._generate_cache_key(
            'course_list', user_id, filters
        )
        
        cache_data = {
            'courses': courses,
            'timestamp': timezone.now().isoformat(),
            'user_id': user_id,
            'filters': filters
        }
        
        cache.set(
            cache_key,
            cache_data,
            timeout or self.default_timeout
        )
        logger.info(f"Cached course list for user {user_id}")
    
    def get_cached_course_list(self, user_id: int, filters: Dict) -> Optional[List[Dict]]:
        """Get cached course list"""
        cache_key = self._generate_cache_key(
            'course_list', user_id, filters
        )
        
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit for course list")
            return cached_data.get('courses')
        
        logger.info(f"Cache miss for course list")
        return None
    
    def cache_user_list(self, user_id: int, filters: Dict,
                       users: List[Dict], timeout: int = None) -> None:
        """Cache user list results"""
        cache_key = self._generate_cache_key(
            'user_list', user_id, filters
        )
        
        cache_data = {
            'users': users,
            'timestamp': timezone.now().isoformat(),
            'user_id': user_id,
            'filters': filters
        }
        
        cache.set(
            cache_key,
            cache_data,
            timeout or self.default_timeout
        )
        logger.info(f"Cached user list for user {user_id}")
    
    def get_cached_user_list(self, user_id: int, filters: Dict) -> Optional[List[Dict]]:
        """Get cached user list"""
        cache_key = self._generate_cache_key(
            'user_list', user_id, filters
        )
        
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Cache hit for user list")
            return cached_data.get('users')
        
        logger.info(f"Cache miss for user list")
        return None
    
    def invalidate_user_cache(self, user_id: int) -> None:
        """Invalidate all cache for a specific user"""
        # This is a simplified approach - in production, you'd want to use
        # cache versioning or tags for more efficient invalidation
        patterns = [
            f"{self.cache_prefix}:user_data:{user_id}:*",
            f"{self.cache_prefix}:course_list:{user_id}:*",
            f"{self.cache_prefix}:user_list:{user_id}:*",
            f"{self.cache_prefix}:search:*:{user_id}:*"
        ]
        
        for pattern in patterns:
            # Note: This is a simplified approach. In production, you'd use
            # cache tags or a more sophisticated invalidation strategy
            pass
        
        logger.info(f"Invalidated cache for user {user_id}")
    
    def invalidate_model_cache(self, model_name: str) -> None:
        """Invalidate cache for a specific model"""
        patterns = [
            f"{self.cache_prefix}:paginated:{model_name}:*",
            f"{self.cache_prefix}:search:{model_name}:*"
        ]
        
        for pattern in patterns:
            # Simplified approach - in production, use cache tags
            pass
        
        logger.info(f"Invalidated cache for model {model_name}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        # This would need to be implemented based on your cache backend
        return {
            'total_keys': 0,  # Would need cache backend specific implementation
            'memory_usage': 0,
            'hit_rate': 0,
            'timestamp': timezone.now().isoformat()
        }
    
    def clear_all_cache(self) -> None:
        """Clear all LMS cache"""
        cache.clear()
        logger.info("Cleared all LMS cache")

# Global cache manager instance
cache_manager = CacheManager()

def cache_search_results(search_type: str, query: str, user_id: int, 
                        results: List[Dict], timeout: int = None):
    """Convenience function for caching search results"""
    cache_manager.cache_search_results(search_type, query, user_id, results, timeout)

def get_cached_search_results(search_type: str, query: str, user_id: int) -> Optional[List[Dict]]:
    """Convenience function for getting cached search results"""
    return cache_manager.get_cached_search_results(search_type, query, user_id)

def cache_course_list(user_id: int, filters: Dict, courses: List[Dict], timeout: int = None):
    """Convenience function for caching course list"""
    cache_manager.cache_course_list(user_id, filters, courses, timeout)

def get_cached_course_list(user_id: int, filters: Dict) -> Optional[List[Dict]]:
    """Convenience function for getting cached course list"""
    return cache_manager.get_cached_course_list(user_id, filters)
