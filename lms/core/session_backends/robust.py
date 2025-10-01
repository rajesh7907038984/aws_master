
"""
Robust Session Backend for Production LMS
Prevents auto-logout issues with comprehensive error handling
"""
from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
import logging
import json

logger = logging.getLogger(__name__)

class RobustSessionStore(DatabaseSessionStore):
    """
    Production-ready session store with fallback mechanisms
    """
    
    def save(self, must_create=False):
        """Enhanced save with multiple fallback strategies"""
        try:
            # Strategy 1: Standard Django save
            if self.session_key is None:
                self.session_key = self._get_new_session_key()
            
            # Force session to be dirty
            self.modified = True
            
            # Attempt standard save
            result = super().save(must_create=must_create)
            
            # Verify save worked
            if self._verify_session_saved():
                logger.info(f"✅ Session {self.session_key} saved successfully")
                return result
            else:
                # Strategy 2: Manual database save
                return self._manual_save()
                
        except Exception as e:
            logger.error(f"❌ Session save failed: {str(e)}")
            # Strategy 3: Cache fallback
            return self._cache_fallback()
    
    def _verify_session_saved(self):
        """Verify session was actually saved to database"""
        try:
            session_obj = Session.objects.get(session_key=self.session_key)
            return session_obj is not None
        except Session.DoesNotExist:
            return False
    
    def _manual_save(self):
        """Manually save session to database"""
        try:
            with transaction.atomic():
                session_obj, created = Session.objects.get_or_create(
                    session_key=self.session_key,
                    defaults={
                        'session_data': self.encode(self._get_session(no_load=True)),
                        'expire_date': self.get_expiry_date()
                    }
                )
                if not created:
                    session_obj.session_data = self.encode(self._get_session(no_load=True))
                    session_obj.expire_date = self.get_expiry_date()
                    session_obj.save()
                
                logger.info(f"✅ Session {self.session_key} manually saved")
                return True
        except Exception as e:
            logger.error(f"❌ Manual save failed: {str(e)}")
            return False
    
    def _cache_fallback(self):
        """Database-only fallback - no cache used"""
        try:
            # Force database save with transaction
            with transaction.atomic():
                session_obj, created = Session.objects.get_or_create(
                    session_key=self.session_key,
                    defaults={
                        'session_data': self.encode(self._get_session(no_load=True)),
                        'expire_date': self.get_expiry_date()
                    }
                )
                if not created:
                    session_obj.session_data = self.encode(self._get_session(no_load=True))
                    session_obj.expire_date = self.get_expiry_date()
                    session_obj.save()
            
            logger.info(f"✅ Session {self.session_key} saved to database fallback")
            return True
        except Exception as e:
            logger.error(f"❌ Database fallback failed: {str(e)}")
            return False
    
    def load(self):
        """Enhanced load with fallback mechanisms"""
        try:
            # Try standard load first
            result = super().load()
            if result:
                return result
            
            # Try cache fallback
            return self._load_from_cache()
            
        except Exception as e:
            logger.error(f"❌ Session load failed: {str(e)}")
            return {}
    
    def _load_from_cache(self):
        """Database-only load - no cache used"""
        try:
            # Try to load from database directly
            session_obj = Session.objects.get(session_key=self.session_key)
            if session_obj and not session_obj.expired():
                self._session_cache = self.decode(session_obj.session_data)
                logger.info(f"✅ Session {self.session_key} loaded from database")
                return self._session_cache
        except Session.DoesNotExist:
            logger.info(f"Session {self.session_key} not found in database")
        except Exception as e:
            logger.error(f"❌ Database load failed: {str(e)}")
        
        return {}
