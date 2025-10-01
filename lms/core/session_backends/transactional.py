"""
Transactional Session Backend for Production LMS
Handles database transaction issues properly
"""
from django.contrib.sessions.backends.db import SessionStore as DatabaseSessionStore
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class TransactionalSessionStore(DatabaseSessionStore):
    """
    Production session store with proper transaction handling
    """
    
    def save(self, must_create=False):
        """Save session with explicit transaction handling"""
        try:
            if self.session_key is None:
                self.session_key = self._get_new_session_key()
            
            # Force session to be dirty
            self.modified = True
            
            # Use explicit transaction
            with transaction.atomic():
                # Try to get existing session
                try:
                    session_obj = Session.objects.get(session_key=self.session_key)
                    if must_create:
                        # Session exists but we need to create - conflict
                        raise Session.DoesNotExist
                    # Update existing session
                    session_obj.session_data = self.encode(self._get_session(no_load=True))
                    session_obj.expire_date = self.get_expiry_date()
                    session_obj.save()
                    logger.info(f"✅ Updated existing session {self.session_key}")
                except Session.DoesNotExist:
                    # Create new session
                    session_obj = Session.objects.create(
                        session_key=self.session_key,
                        session_data=self.encode(self._get_session(no_load=True)),
                        expire_date=self.get_expiry_date()
                    )
                    logger.info(f"✅ Created new session {self.session_key}")
                
                # Verify save worked
                if Session.objects.filter(session_key=self.session_key).exists():
                    logger.info(f"✅ Session {self.session_key} verified in database")
                    return True
                else:
                    logger.error(f"❌ Session {self.session_key} not found after save")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Session save failed: {str(e)}")
            return False
    
    def load(self):
        """Load session with proper error handling"""
        try:
            return super().load()
        except Exception as e:
            logger.error(f"❌ Session load failed: {str(e)}")
            return {}
