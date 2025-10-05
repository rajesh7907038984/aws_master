
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
import json

@csrf_exempt
@require_http_methods(['GET'])
def health_check(request):
    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        
        return JsonResponse({
            'status': 'healthy',
            'database': 'connected',
            'message': 'All systems operational'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy', 
            'database': 'disconnected',
            'error': str(e)
        }, status=503)

