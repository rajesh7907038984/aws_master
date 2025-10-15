"""
xAPI Wrapper for SCORM Packages
Provides xAPI/Tin Can API compatibility for modern SCORM packages
"""
import json
import logging
from datetime import datetime
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt

logger = logging.getLogger(__name__)


class xAPIWrapper:
    """
    xAPI wrapper that provides Tin Can API compatibility
    Maps xAPI statements to SCORM data model
    """
    
    def __init__(self, attempt):
        self.attempt = attempt
        self.actor = {
            "objectType": "Agent",
            "name": attempt.user.get_full_name() or attempt.user.username,
            "mbox": f"mailto:{attempt.user.email}"
        }
        self.verb_map = {
            "experienced": "completed",
            "completed": "completed", 
            "passed": "passed",
            "failed": "failed",
            "attempted": "incomplete"
        }
    
    def process_statement(self, statement):
        """
        Process xAPI statement and update SCORM attempt data
        
        Args:
            statement: xAPI statement object
            
        Returns:
            Boolean indicating success
        """
        try:
            # Extract verb and result
            verb = statement.get('verb', {}).get('id', '')
            result = statement.get('result', {})
            
            # Map xAPI verb to SCORM status
            if 'experienced' in verb or 'completed' in verb:
                self.attempt.lesson_status = 'completed'
                self.attempt.completion_status = 'completed'
            elif 'passed' in verb:
                self.attempt.lesson_status = 'passed'
                self.attempt.success_status = 'passed'
            elif 'failed' in verb:
                self.attempt.lesson_status = 'failed'
                self.attempt.success_status = 'failed'
            elif 'attempted' in verb:
                self.attempt.lesson_status = 'incomplete'
                self.attempt.completion_status = 'incomplete'
            
            # Handle score data
            if 'score' in result:
                score_data = result['score']
                if 'raw' in score_data:
                    try:
                        from decimal import Decimal
                        self.attempt.score_raw = Decimal(str(score_data['raw']))
                    except (ValueError, TypeError):
                        pass
                
                if 'scaled' in score_data:
                    try:
                        from decimal import Decimal
                        self.attempt.score_scaled = Decimal(str(score_data['scaled']))
                    except (ValueError, TypeError):
                        pass
            
            # Handle completion
            if result.get('completion', False):
                self.attempt.lesson_status = 'completed'
                self.attempt.completion_status = 'completed'
            
            # Handle success
            if result.get('success', False):
                self.attempt.success_status = 'passed'
            elif 'success' in result and not result['success']:
                self.attempt.success_status = 'failed'
            
            # Handle duration
            if 'duration' in result:
                duration = result['duration']
                # Convert ISO 8601 duration to SCORM time format
                self.attempt.total_time = self._convert_duration_to_scorm(duration)
            
            # Update last accessed
            self.attempt.last_accessed = timezone.now()
            self.attempt.save()
            
            logger.info(f"xAPI statement processed for attempt {self.attempt.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing xAPI statement: {e}")
            return False
    
    def _convert_duration_to_scorm(self, duration):
        """
        Convert ISO 8601 duration to SCORM time format
        
        Args:
            duration: ISO 8601 duration string (e.g., "PT1H30M45S")
            
        Returns:
            SCORM time format string (e.g., "0001:30:45.00")
        """
        try:
            # Parse ISO 8601 duration
            import re
            
            # Extract hours, minutes, seconds
            hours_match = re.search(r'(\d+)H', duration)
            minutes_match = re.search(r'(\d+)M', duration)
            seconds_match = re.search(r'(\d+(?:\.\d+)?)S', duration)
            
            hours = int(hours_match.group(1)) if hours_match else 0
            minutes = int(minutes_match.group(1)) if minutes_match else 0
            seconds = float(seconds_match.group(1)) if seconds_match else 0.0
            
            # Convert to SCORM format (HHHH:MM:SS.SS)
            return f"{hours:04d}:{minutes:02d}:{seconds:05.2f}"
            
        except Exception as e:
            logger.warning(f"Could not convert duration {duration}: {e}")
            return "0000:00:00.00"
    
    def generate_statement(self, verb, activity_id, result=None):
        """
        Generate xAPI statement from SCORM data
        
        Args:
            verb: xAPI verb
            activity_id: Activity identifier
            result: Optional result object
            
        Returns:
            xAPI statement object
        """
        statement = {
            "id": str(timezone.now().timestamp()),
            "actor": self.actor,
            "verb": {
                "id": verb,
                "display": {"en-US": verb.replace('http://adlnet.gov/expapi/verbs/', '')}
            },
            "object": {
                "id": activity_id,
                "objectType": "Activity",
                "definition": {
                    "name": {"en-US": self.attempt.scorm_package.title or "SCORM Activity"}
                }
            },
            "timestamp": timezone.now().isoformat(),
            "stored": timezone.now().isoformat()
        }
        
        if result:
            statement["result"] = result
        
        return statement


@csrf_exempt
@xframe_options_exempt
def xapi_endpoint(request, attempt_id):
    """
    xAPI endpoint for SCORM packages that use Tin Can API
    
    Args:
        request: HTTP request
        attempt_id: SCORM attempt ID
        
    Returns:
        JSON response
    """
    try:
        from .models import ScormAttempt
        
        # Get attempt
        attempt = ScormAttempt.objects.get(id=attempt_id)
        wrapper = xAPIWrapper(attempt)
        
        if request.method == 'POST':
            # Process xAPI statement
            try:
                statement = json.loads(request.body)
                success = wrapper.process_statement(statement)
                
                if success:
                    return JsonResponse({"success": True})
                else:
                    return JsonResponse({"success": False, "error": "Failed to process statement"}, status=400)
                    
            except json.JSONDecodeError:
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        
        elif request.method == 'GET':
            # Return actor information
            return JsonResponse({
                "actor": wrapper.actor,
                "success": True
            })
        
        else:
            return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
            
    except ScormAttempt.DoesNotExist:
        return JsonResponse({"success": False, "error": "Attempt not found"}, status=404)
    except Exception as e:
        logger.error(f"xAPI endpoint error: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
