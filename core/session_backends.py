from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.contrib.sessions.backends.cache import SessionStore as CacheSessionStore
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

class SessionStore(DatabaseSessionStore):
    """
    Robust session store that falls back to database if cache fails
    """
    
    def __init__(self, session_key=None):
        super().__init__(session_key)
        self._cache_fallback = True
    
    def save(self, must_create=False):
        try:
            # Try to save to database first
            super().save(must_create)
            
            # Also try to cache for performance
            if self._cache_fallback:
                try:
                    cache_key = f'session:{self.session_key}'
                    cache.set(cache_key, self._session, timeout=86400)  # 1 day
                except Exception as e:
                    logger.warning(f'Cache save failed: {e}')
                    self._cache_fallback = False
                    
        except Exception as e:
            logger.error(f'Session save failed: {e}')
            raise
    
    def load(self):
        try:
            # Try cache first for performance
            if self._cache_fallback:
                try:
                    cache_key = f'session:{self.session_key}'
                    cached_session = cache.get(cache_key)
                    if cached_session is not None:
                        self._session = cached_session
                        return
                except Exception as e:
                    logger.warning(f'Cache load failed: {e}')
                    self._cache_fallback = False
            
            # Fallback to database
            return super().load()
            
        except Exception as e:
            logger.error(f'Session load failed: {e}')
            return super().load()
    
    def delete(self, session_key=None):
        try:
            super().delete(session_key)
            
            # Also clear from cache
            if self._cache_fallback:
                try:
                    cache_key = f'session:{session_key or self.session_key}'
                    cache.delete(cache_key)
                except Exception as e:
                    logger.warning(f'Cache delete failed: {e}')
                    
        except Exception as e:
            logger.error(f'Session delete failed: {e}')
            raise
