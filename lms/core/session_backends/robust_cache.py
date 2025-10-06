"""
Robust Cache Session Backend
Handles cache failures gracefully with database fallback
"""

import logging
from django.contrib.sessions.backends.cache import SessionStore as CacheSessionStore
from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.core.cache import cache
from django.contrib.sessions.models import Session
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class RobustCacheSessionStore(CacheSessionStore):
    """
    Robust session store that falls back to database if cache fails
    """
    
    def __init__(self, session_key=None):
        super().__init__(session_key)
        self._cache_fallback = True
        self._db_fallback = True
    
    def save(self, must_create=False):
        """Save session with cache and database fallback"""
        try:
            # Try cache first for performance
            if self._cache_fallback:
                try:
                    super().save(must_create)
                    logger.debug(f"Session {self.session_key} saved to cache")
                    return
                except Exception as e:
                    logger.warning(f"Cache save failed: {e}, falling back to database")
                    self._cache_fallback = False
            
            # Fallback to database
            if self._db_fallback:
                try:
                    self._save_to_database(must_create)
                    logger.debug(f"Session {self.session_key} saved to database")
                except Exception as e:
                    logger.error(f"Database save failed: {e}")
                    raise
                    
        except Exception as e:
            logger.error(f"Session save failed completely: {e}")
            raise
    
    def load(self):
        """Load session with cache and database fallback"""
        try:
            # Try cache first for performance
            if self._cache_fallback:
                try:
                    # FIXED: super().load() modifies self._session_cache and returns it
                    # We need to call it and then check if session was loaded
                    data = super().load()
                    # Check if we actually got session data (non-empty dict)
                    if data:
                        logger.debug(f"Session {self.session_key} loaded from cache")
                        return data
                except Exception as e:
                    logger.warning(f"Cache load failed: {e}, falling back to database")
                    self._cache_fallback = False
            
            # Fallback to database
            if self._db_fallback:
                try:
                    result = self._load_from_database()
                    if result is not None:
                        logger.debug(f"Session {self.session_key} loaded from database")
                        # Try to cache the result for next time
                        if self._cache_fallback:
                            try:
                                cache.set(f'session:{self.session_key}', result, timeout=86400)
                            except Exception as e:
                                logger.warning(f"Failed to cache session after DB load: {e}")
                        return result
                except Exception as e:
                    logger.error(f"Database load failed: {e}")
                    self._db_fallback = False
            
            # If all else fails, return empty session
            logger.warning(f"All session backends failed for {self.session_key}")
            return {}
            
        except Exception as e:
            logger.error(f"Session load failed: {e}")
            return {}
    
    def delete(self, session_key=None):
        """Delete session from both cache and database"""
        try:
            key = session_key or self.session_key
            
            # Delete from cache
            if self._cache_fallback:
                try:
                    cache.delete(f'session:{key}')
                except Exception as e:
                    logger.warning(f"Cache delete failed: {e}")
            
            # Delete from database
            if self._db_fallback:
                try:
                    Session.objects.filter(session_key=key).delete()
                except Exception as e:
                    logger.warning(f"Database delete failed: {e}")
                    
        except Exception as e:
            logger.error(f"Session delete failed: {e}")
    
    def _save_to_database(self, must_create=False):
        """Save session to database"""
        session_data = self.encode(self._get_session(no_load=True))
        expire_date = self.get_expiry_date()
        
        session_obj, created = Session.objects.get_or_create(
            session_key=self.session_key,
            defaults={
                'session_data': session_data,
                'expire_date': expire_date
            }
        )
        
        if not created:
            session_obj.session_data = session_data
            session_obj.expire_date = expire_date
            session_obj.save()
    
    def _load_from_database(self):
        """Load session from database"""
        try:
            session_obj = Session.objects.get(session_key=self.session_key)
            if session_obj.expire_date > timezone.now():
                self._session_cache = self.decode(session_obj.session_data)
                return self._session_cache
            else:
                # Session expired, delete it
                session_obj.delete()
                return None
        except Session.DoesNotExist:
            return None
    
    def exists(self, session_key):
        """Check if session exists in cache or database"""
        try:
            # Check cache first
            if self._cache_fallback:
                try:
                    return cache.get(f'session:{session_key}') is not None
                except Exception:
                    pass
            
            # Check database
            if self._db_fallback:
                try:
                    return Session.objects.filter(
                        session_key=session_key,
                        expire_date__gt=timezone.now()
                    ).exists()
                except Exception:
                    pass
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking session existence: {e}")
            return False


# Django's session framework expects a class named SessionStore
SessionStore = RobustCacheSessionStore