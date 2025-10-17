"""
Server time API endpoint for client synchronization
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json

@csrf_exempt
def server_time(request):
    """Return current server time for client synchronization"""
    try:
        current_time = timezone.now()
        
        return JsonResponse({
            'server_time': current_time.isoformat(),
            'timestamp': current_time.timestamp(),
            'timezone': str(current_time.tzinfo) if current_time.tzinfo else 'UTC'
        })
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to get server time',
            'message': str(e)
        }, status=500)
