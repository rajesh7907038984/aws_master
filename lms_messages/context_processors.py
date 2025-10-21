from django.db.models import Q, Exists, OuterRef
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
    
    return result 