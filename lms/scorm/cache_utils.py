"""
Centralized cache key management for SCORM module
Ensures consistent cache key patterns across all modules
"""
import logging
from django.core.cache import cache
from typing import List, Optional

logger = logging.getLogger(__name__)


class ScormCacheManager:
    """
    Centralized cache management for SCORM-related data
    Provides consistent key patterns and bulk invalidation
    """
    
    # Cache key pattern templates
    GRADEBOOK_COURSE = "gradebook_course_{course_id}"
    COURSE_PROGRESS = "course_progress_{course_id}_{user_id}"
    TOPIC_PROGRESS = "topic_progress_{topic_id}_{user_id}"
    USER_PROGRESS = "user_{user_id}_progress"
    SCORM_ATTEMPT = "scorm_attempt_{attempt_id}"
    
    # Cache timeouts (in seconds)
    TIMEOUT_SHORT = 300      # 5 minutes
    TIMEOUT_MEDIUM = 1800    # 30 minutes
    TIMEOUT_LONG = 3600      # 1 hour
    
    @classmethod
    def get_gradebook_key(cls, course_id: int) -> str:
        """Get cache key for course gradebook"""
        return cls.GRADEBOOK_COURSE.format(course_id=course_id)
    
    @classmethod
    def get_course_progress_key(cls, course_id: int, user_id: int) -> str:
        """Get cache key for user course progress"""
        return cls.COURSE_PROGRESS.format(course_id=course_id, user_id=user_id)
    
    @classmethod
    def get_topic_progress_key(cls, topic_id: int, user_id: int) -> str:
        """Get cache key for user topic progress"""
        return cls.TOPIC_PROGRESS.format(topic_id=topic_id, user_id=user_id)
    
    @classmethod
    def get_user_progress_key(cls, user_id: int) -> str:
        """Get cache key for overall user progress"""
        return cls.USER_PROGRESS.format(user_id=user_id)
    
    @classmethod
    def get_scorm_attempt_key(cls, attempt_id: int) -> str:
        """Get cache key for SCORM attempt data"""
        return cls.SCORM_ATTEMPT.format(attempt_id=attempt_id)
    
    @classmethod
    def invalidate_for_attempt(cls, attempt_id: int, user_id: int, topic_id: Optional[int] = None, 
                               course_ids: Optional[List[int]] = None) -> None:
        """
        Invalidate all cache keys related to a SCORM attempt
        
        Args:
            attempt_id: SCORM attempt ID
            user_id: User ID
            topic_id: Optional topic ID
            course_ids: Optional list of course IDs
        """
        keys_to_delete = [
            cls.get_scorm_attempt_key(attempt_id),
            cls.get_user_progress_key(user_id),
        ]
        
        # Add topic-specific keys if topic_id provided
        if topic_id:
            keys_to_delete.append(cls.get_topic_progress_key(topic_id, user_id))
        
        # Add course-specific keys if course_ids provided
        if course_ids:
            for course_id in course_ids:
                keys_to_delete.extend([
                    cls.get_gradebook_key(course_id),
                    cls.get_course_progress_key(course_id, user_id),
                ])
        
        # Delete all keys
        deleted_count = 0
        for key in keys_to_delete:
            try:
                cache.delete(key)
                deleted_count += 1
                logger.debug(f"Deleted cache key: {key}")
            except Exception as e:
                logger.warning(f"Failed to delete cache key {key}: {e}")
        
        logger.info(f"Invalidated {deleted_count}/{len(keys_to_delete)} cache keys for attempt {attempt_id}")
    
    @classmethod
    def invalidate_for_topic(cls, topic_id: int, course_ids: Optional[List[int]] = None) -> None:
        """
        Invalidate all cache keys related to a topic (for all users)
        
        Args:
            topic_id: Topic ID
            course_ids: Optional list of course IDs containing this topic
        """
        keys_to_delete = []
        
        # Add course-specific keys if course_ids provided
        if course_ids:
            for course_id in course_ids:
                keys_to_delete.append(cls.get_gradebook_key(course_id))
        
        # For topic progress, we can't enumerate all users, so we log a warning
        logger.info(f"Invalidating cache for topic {topic_id}")
        
        # Delete known keys
        deleted_count = 0
        for key in keys_to_delete:
            try:
                cache.delete(key)
                deleted_count += 1
                logger.debug(f"Deleted cache key: {key}")
            except Exception as e:
                logger.warning(f"Failed to delete cache key {key}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Invalidated {deleted_count} cache keys for topic {topic_id}")
    
    @classmethod
    def invalidate_for_course(cls, course_id: int) -> None:
        """
        Invalidate all cache keys related to a course
        
        Args:
            course_id: Course ID
        """
        keys_to_delete = [
            cls.get_gradebook_key(course_id),
        ]
        
        # Delete all keys
        deleted_count = 0
        for key in keys_to_delete:
            try:
                cache.delete(key)
                deleted_count += 1
                logger.debug(f"Deleted cache key: {key}")
            except Exception as e:
                logger.warning(f"Failed to delete cache key {key}: {e}")
        
        logger.info(f"Invalidated {deleted_count} cache keys for course {course_id}")
    
    @classmethod
    def invalidate_for_user(cls, user_id: int, course_ids: Optional[List[int]] = None) -> None:
        """
        Invalidate all cache keys related to a user
        
        Args:
            user_id: User ID
            course_ids: Optional list of course IDs to invalidate
        """
        keys_to_delete = [
            cls.get_user_progress_key(user_id),
        ]
        
        # Add course-specific keys if course_ids provided
        if course_ids:
            for course_id in course_ids:
                keys_to_delete.append(cls.get_course_progress_key(course_id, user_id))
        
        # Delete all keys
        deleted_count = 0
        for key in keys_to_delete:
            try:
                cache.delete(key)
                deleted_count += 1
                logger.debug(f"Deleted cache key: {key}")
            except Exception as e:
                logger.warning(f"Failed to delete cache key {key}: {e}")
        
        logger.info(f"Invalidated {deleted_count} cache keys for user {user_id}")
    
    @classmethod
    def set_with_timeout(cls, key: str, value: any, timeout: int = TIMEOUT_MEDIUM) -> bool:
        """
        Set a cache value with standard timeout
        
        Args:
            key: Cache key
            value: Value to cache
            timeout: Timeout in seconds (default: TIMEOUT_MEDIUM)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache.set(key, value, timeout)
            return True
        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    @classmethod
    def get_or_none(cls, key: str) -> Optional[any]:
        """
        Get a cache value, returning None if not found or on error
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        try:
            return cache.get(key)
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}")
            return None

