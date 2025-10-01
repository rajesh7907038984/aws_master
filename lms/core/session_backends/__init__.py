# Session backends
from .robust import RobustSessionStore

# Django expects SessionStore for session engine
SessionStore = RobustSessionStore

__all__ = ['RobustSessionStore', 'SessionStore']
