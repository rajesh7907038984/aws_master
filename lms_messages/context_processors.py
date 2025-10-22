from django.db.models import Q, Exists, OuterRef
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from .models import Message, MessageReadStatus

def messages_context(request):
    """
    Context processor to provide message-related data to all templates.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'unread_messages_count': 0,
            'total_messages_count': 0,
        }
    
    # Cache key based on user and current minute (refresh every minute for real-time updates)
    cache_key = f"messages_context_{request.user.id}_{timezone.now().minute}"
    
    # Try to get cached data first
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data
    
    # Get unread messages count for the user
    unread_count = Message.objects.filter(
        Q(recipients=request.user) & ~Q(sender=request.user)
    ).exclude(
        read_statuses__user=request.user,
        read_statuses__is_read=True
    ).distinct().count()
    
    # Get total messages count for the user
    total_count = Message.objects.filter(
        Q(sender=request.user) | Q(recipients=request.user)
    ).distinct().count()
    
    result = {
        'unread_messages_count': unread_count,
        'total_messages_count': total_count,
    }
    
    # Cache for 1 minute, or 30 seconds in development
    cache_timeout = 30 if settings.DEBUG else 60  # 30 seconds in debug, 1 minute in production
    cache.set(cache_key, result, cache_timeout)
    
    return result 