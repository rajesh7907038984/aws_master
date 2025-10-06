"""
Working database session backend that ensures sessions are properly saved
"""
from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class SessionStore(DatabaseSessionStore):
    """
    Custom session store that ensures sessions are actually saved to database
    """
    
    def save(self, must_create=False):
        """
        Override save method to ensure session data is actually written
        """
        try:
            # Force session key generation if needed
            if self.session_key is None:
                self.session_key = self._get_new_session_key()
            
            # Get session data
            data = self._get_session(no_load=must_create)
            
            # Force session to be dirty so it saves
            self.modified = True
            
            # Log the save attempt
            logger.info(f"Attempting to save session {self.session_key} with data length: {len(str(data))}")
            
            # Call parent save method
            result = super().save(must_create=must_create)
            
            # Verify the session was actually saved by checking the database
            try:
                session_obj = Session.objects.get(session_key=self.session_key)
                logger.info(f" Session {self.session_key} successfully saved to database")
                return result
            except Session.DoesNotExist:
                logger.error(f" Session {self.session_key} was not saved to database despite save() call")
                
                # Fallback: manually save to database
                session_obj = Session(
                    session_key=self.session_key,
                    session_data=self.encode(data),
                    expire_date=self.get_expiry_date()
                )
                session_obj.save()
                logger.info(f" Session {self.session_key} manually saved to database")
                return result
                
        except Exception as e:
            logger.error(f" Session save error: {str(e)}")
            raise
            
        return result
    
    def load(self):
        """
        Override load method with better error handling
        """
        try:
            result = super().load()
            if self.session_key:
                logger.info(f"Session {self.session_key} loaded with {len(self._session_cache)} items")
            return result
        except Exception as e:
            logger.error(f"Session load error: {str(e)}")
            return {}
