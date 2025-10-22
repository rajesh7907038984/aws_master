from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def notifications_context(request):
    """
    Context processor to provide notification-related data to all templates.
    Enhanced with comprehensive error handling to prevent crashes.
    """
    # Default empty response
    default_response = {
        'unread_notifications_count': 0,
        'total_notifications_count': 0,
        'urgent_notifications_count': 0,
    }
    
    # Check authentication
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return default_response
    
    # Check user ID validity
    if not hasattr(request.user, 'id') or not request.user.id:
        return default_response
    
    # Skip for AJAX requests and API calls to improve performance
    if (hasattr(request, 'headers') and request.headers.get('X-Requested-With') == 'XMLHttpRequest') or \
       (hasattr(request, 'path') and request.path.startswith('/api/')):
        return default_response
    
    try:
        # Cache key based on user and current minute (refresh every minute for real-time updates)
        cache_key = f"notifications_context_{request.user.id}_{timezone.now().minute}"
        
        # Try to get cached data first
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        # Import here to avoid circular imports and ensure model is ready
        try:
            from .models import Notification
        except ImportError as e:
            logger.error(f"Failed to import Notification model: {e}")
            return default_response
        
        # Query notifications with error handling
        notifications = Notification.objects.filter(recipient_id=request.user.id)
        
        unread_count = notifications.filter(is_read=False).count()
        total_count = notifications.count()
        urgent_count = notifications.filter(is_read=False, priority='urgent').count()
        
        result = {
            'unread_notifications_count': unread_count,
            'total_notifications_count': total_count,
            'urgent_notifications_count': urgent_count,
        }
        
        # Cache for 1 minute, or 30 seconds in development
        try:
            cache_timeout = 30 if settings.DEBUG else 60  # 30 seconds in debug, 1 minute in production
            cache.set(cache_key, result, cache_timeout)
        except Exception as e:
            logger.error(f"Failed to cache notifications context: {e}")
        
        return result
        
    except Exception as e:
        # Log the error but don't crash the application
        logger.error(f"Error in notifications_context for user {getattr(request.user, 'id', 'unknown')}: {str(e)}", exc_info=True)
        return default_response 